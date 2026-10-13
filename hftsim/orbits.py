from datetime import timedelta
import numpy as np
from .config import RE_KM, MU, J2, OMEGA_E
from .geometry import unit


def gmst(epoch):
    jd = epoch.timestamp()/86400 + 2440587.5
    t = (jd-2451545.0)/36525
    return np.deg2rad((280.46061837+360.98564736629*(jd-2451545.0)
                      +0.000387933*t*t-t*t*t/38710000) % 360)


def rotate_z(v, angle):
    c, s = np.cos(angle), np.sin(angle)
    return np.stack([c*v[..., 0]-s*v[..., 1], s*v[..., 0]+c*v[..., 1], v[..., 2]], axis=-1)


class KeplerEphemeris:
    """Mean-elements Kepler + first-order secular J2, approximate equator-of-date ECI.

    Not an osculating high-fidelity propagator. Earth rotation uses UTC~UT1 GMST;
    polar motion, nutation, drag, maneuvers and short-period J2 terms are omitted.
    """
    def __init__(self, config, epoch):
        self.config, self.epoch = config, epoch
        p = np.repeat(np.arange(config.planes), config.sats_per_plane)
        s = np.tile(np.arange(config.sats_per_plane), config.planes)
        spacing = config.raan_span_deg / (config.planes if config.raan_span_deg == 360 else max(config.planes-1, 1))
        self.raan0 = np.deg2rad(config.raan_start_deg+p*spacing)
        self.m0 = np.deg2rad(config.phase_deg+360*s/config.sats_per_plane
                            +360*config.walker_f*p/config.count)
        self.count = config.count
        self.a, self.e = RE_KM+config.altitude_km, config.eccentricity
        self.inc, self.arg0 = np.deg2rad([config.inclination_deg, config.arg_perigee_deg])
        n = np.sqrt(MU/self.a**3)
        k = J2*n*(RE_KM/(self.a*(1-self.e**2)))**2 if config.j2 else 0
        self.raan_rate = -1.5*k*np.cos(self.inc)
        self.arg_rate = 0.75*k*(5*np.cos(self.inc)**2-1)
        self.m_rate = n+0.75*k*np.sqrt(1-self.e**2)*(3*np.cos(self.inc)**2-1)
        self.theta0 = gmst(epoch)

    def eci_position(self, t):
        m = (self.m0+self.m_rate*t) % (2*np.pi)
        eccentric = m.copy()
        for _ in range(30):
            correction = (eccentric-self.e*np.sin(eccentric)-m)/(1-self.e*np.cos(eccentric))
            eccentric -= correction
            if np.max(np.abs(correction)) < 1e-13:
                break
        else:
            raise ValueError("Kepler equation failed to converge")
        x = self.a*(np.cos(eccentric)-self.e)
        y = self.a*np.sqrt(1-self.e**2)*np.sin(eccentric)
        arg = self.arg0+self.arg_rate*t
        xp, yp = np.cos(arg)*x-np.sin(arg)*y, np.sin(arg)*x+np.cos(arg)*y
        orbital = np.stack([xp, yp*np.cos(self.inc), yp*np.sin(self.inc)], axis=-1)
        return rotate_z(orbital, self.raan0+self.raan_rate*t)

    def state(self, t):
        r = self.eci_position(t)
        v = (self.eci_position(t+0.05)-self.eci_position(t-0.05))/0.1
        theta = self.theta0+OMEGA_E*t
        re = rotate_z(r, -theta)
        ve = rotate_z(v-np.cross(np.array([0, 0, OMEGA_E]), r), -theta)
        return r, v, re, ve


class CompositeEphemeris:
    """Concatenate independent shells without conflating altitude or J2 rates."""
    def __init__(self, shells, epoch):
        self.shells = tuple(shells)
        if not self.shells:
            raise ValueError('At least one shell required')
        self.epoch = epoch
        self.ephemerides = [KeplerEphemeris(c, epoch) for c in self.shells]
        self.count = sum(ep.count for ep in self.ephemerides)

    def state(self, t):
        states = [ep.state(t) for ep in self.ephemerides]
        return tuple(np.concatenate([s[k] for s in states], axis=-2) for k in range(4))


class TLEEphemeris:
    """Offline TLE input via Skyfield/SGP4; explicit frame conversion to ITRS."""
    def __init__(self, pairs, epoch):
        from skyfield.api import EarthSatellite, load
        self.pairs = list(pairs)
        self.ts = load.timescale(builtin=True)
        self.satellites = [EarthSatellite(l1, l2, str(i), self.ts) for i, (l1, l2) in enumerate(self.pairs)]
        self.epoch, self.count = epoch, len(pairs)
        if not self.count:
            raise ValueError("At least one TLE pair is required")
        ages = [abs((epoch-s.epoch.utc_datetime()).total_seconds())/86400 for s in self.satellites]
        if max(ages) > 14:
            raise ValueError("TLE epoch more than 14 days from run epoch; supply fresh elements")

    def state(self, t):
        from skyfield.framelib import itrs
        instant = self.ts.from_datetime(self.epoch+timedelta(seconds=float(t)))
        r, v, re, ve = [], [], [], []
        for sat in self.satellites:
            state = sat.at(instant)
            if state.message:
                raise ValueError(f"SGP4 propagation failed: {state.message}")
            fixed_r, fixed_v = state.frame_xyz_and_velocity(itrs)
            r.append(state.xyz.km); v.append(state.velocity.km_per_s)
            re.append(fixed_r.km); ve.append(fixed_v.km_per_s)
        return tuple(np.asarray(x) for x in (r, v, re, ve))


class ElementsEphemeris(KeplerEphemeris):
    """Per-satellite six mean elements; angles in degrees, semimajor axis in km."""
    def __init__(self, elements, epoch, j2=True):
        if not elements:
            raise ValueError("At least one element set required")
        self.elements, self.j2_enabled = elements, j2
        self.epoch, self.count = epoch, len(elements)
        self.a, self.e, self.inc, self.raan0, self.arg0, self.m0 = (
            np.array([row[key] for row in elements], dtype=float)
            for key in ['a_km', 'e', 'i_deg', 'raan_deg', 'arg_perigee_deg', 'mean_anomaly_deg'])
        if not all(np.isfinite(v).all() for v in (self.a, self.e, self.inc, self.raan0, self.arg0, self.m0)):
            raise ValueError("Elements must be finite")
        if np.any((self.e < 0) | (self.e >= 1) | (self.a*(1-self.e) <= RE_KM)):
            raise ValueError("Require elliptic orbit above Earth")
        if np.any((self.inc < 0) | (self.inc > 180)):
            raise ValueError("Invalid inclination")
        self.inc, self.raan0, self.arg0, self.m0 = [np.deg2rad(v) for v in (self.inc, self.raan0, self.arg0, self.m0)]
        n = np.sqrt(MU/self.a**3)
        k = J2*n*(RE_KM/(self.a*(1-self.e**2)))**2 if j2 else np.zeros(self.count)
        self.raan_rate = -1.5*k*np.cos(self.inc)
        self.arg_rate = .75*k*(5*np.cos(self.inc)**2-1)
        self.m_rate = n+.75*k*np.sqrt(1-self.e**2)*(3*np.cos(self.inc)**2-1)
        self.theta0 = gmst(epoch)


def body_basis(r, v):
    """LVLH: x along transverse flight, z nadir, y completes right-handed frame."""
    radial = unit(r)
    x = unit(v-np.sum(v*radial, axis=-1, keepdims=True)*radial)
    z = -radial
    y = unit(np.cross(z, x))
    return np.stack([x, y, z], axis=-1)
