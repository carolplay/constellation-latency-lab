import numpy as np
from .config import RE_KM, C_KM_S
from .geometry import unit, segment_min_radius
from .orbits import body_basis


def candidate_edges(c):
    """Four fixed terminals: in-plane ring and adjacent-plane same-index links.

    A full 360-degree shell closes the plane seam; partial spans stay open.
    This is a generic degree<=4 abstraction, not a claim about Starlink hardware.
    """
    if c.topology == 'complete':
        return np.array([(i, j) for i in range(c.count) for j in range(i+1, c.count)], dtype=int).reshape(-1, 2)
    edges = set()
    for p in range(c.planes):
        for s in range(c.sats_per_plane):
            a = p*c.sats_per_plane+s
            if c.sats_per_plane > 1:
                edges.add(tuple(sorted((a, p*c.sats_per_plane+(s+1) % c.sats_per_plane))))
            if p+1 < c.planes:
                edges.add((a, (p+1)*c.sats_per_plane+s))
            elif c.raan_span_deg == 360 and c.planes > 2:
                edges.add(tuple(sorted((a, s))))
    return np.array(sorted(edges), dtype=int).reshape(-1, 2)


def body_los(r, v, edges):
    b = body_basis(r, v)
    a, z = edges.T
    u = unit(r[z]-r[a])
    return (np.einsum('nij,ni->nj', b[a], u),
            np.einsum('nij,ni->nj', b[z], -u))


class OpticalLinks:
    def __init__(self, ephemeris, edges, physics):
        self.ephemeris, self.edges, self.physics = ephemeris, edges, physics
        r, v, _, _ = ephemeris.state(0)
        # Assumed per-terminal nominal pointing, calibrated at epoch, held in LVLH.
        self.boresights = body_los(r, v, edges)
        self.valid_since = np.full(len(edges), np.nan)

    def evaluate(self, t, state):
        p, e = self.physics, self.edges
        r, v, re, _ = state
        a, z = e.T
        delta = r[z]-r[a]
        ranges = np.linalg.norm(delta, axis=-1)
        clearance = segment_min_radius(re[a], re[z])-RE_KM
        limb = clearance >= p.atmosphere_km
        in_range = ranges <= p.max_isl_range_km
        range_rate = np.sum(unit(delta)*(v[z]-v[a]), axis=-1)
        doppler = -range_rate/C_KM_S*(C_KM_S*1000/(p.wavelength_nm*1e-9))
        fov_ok, slew_ok, doppler_ok = [np.ones(len(e), dtype=bool) for _ in range(3)]
        max_slew = np.zeros(len(e))
        if p.optical_constraints and len(e):
            pointing = body_los(r, v, e)
            r0, v0, _, _ = self.ephemeris.state(t-0.1)
            r1, v1, _, _ = self.ephemeris.state(t+0.1)
            before, after = body_los(r0, v0, e), body_los(r1, v1, e)
            for los, bore, lo, hi in zip(pointing, self.boresights, before, after):
                angle = np.rad2deg(np.arccos(np.clip(np.sum(los*bore, axis=-1), -1, 1)))
                slew = np.rad2deg(np.linalg.norm((hi-lo)/0.2, axis=-1))
                fov_ok &= angle <= p.fov_half_angle_deg
                slew_ok &= slew <= p.slew_limit_deg_s
                max_slew = np.maximum(max_slew, slew)
            doppler_ok = np.abs(doppler) <= p.max_doppler_hz
        geometric = limb & in_range & fov_ok & slew_ok & doppler_ok
        self.valid_since[~geometric] = np.nan
        fresh = geometric & np.isnan(self.valid_since)
        self.valid_since[fresh] = t
        usable = geometric & ((t-self.valid_since) >= p.isl_acquire_s)
        diagnostics = dict(candidate_isl=len(e), accepted_isl=int(usable.sum()),
                           rejected_limb=int((~limb).sum()), rejected_range=int((~in_range).sum()),
                           rejected_fov=int((~fov_ok).sum()), rejected_slew=int((~slew_ok).sum()),
                           rejected_doppler=int((~doppler_ok).sum()),
                           acquiring_isl=int((geometric & ~usable).sum()),
                           max_candidate_doppler_ghz=float(np.max(np.abs(doppler), initial=0)/1e9),
                           max_candidate_slew_deg_s=float(np.max(max_slew, initial=0)))
        return usable, ranges, diagnostics
