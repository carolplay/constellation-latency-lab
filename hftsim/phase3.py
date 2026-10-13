"""Phase 3 design audit: geometry-first bounds, not an operational network model."""
import numpy as np
import pandas as pd
import networkx as nx
from .config import RE_KM, C_KM_S, MU, OMEGA_E, Constellation, Simulation
from .geometry import unit, geodetic_ecef, ground_up, elevation_deg, segment_min_radius
from .orbits import KeplerEphemeris, rotate_z
from .benchmarks import load_data

STATIONS = ('LD4', 'NY4', 'TOKYO')
ROUTES = {'LD4-TOKYO': ('LD4', 'TOKYO', 155.),
          'NY4-LD4': ('NY4', 'LD4', 58.9),
          'NY4-TOKYO': ('NY4', 'TOKYO', 132.)}  # user proposal assumptions


def proposal_constellation(**overrides):
    values = dict(planes=3, sats_per_plane=6, altitude_km=1180, inclination_deg=71.5,
                  raan_span_deg=120, raan_start_deg=0, phase_deg=0, walker_f=1,
                  label='User Phase 3 proposal: 18-sat Arctic ring')
    values.update(overrides)
    return Constellation(**values)


def ring_geometry(height_km, satellites_per_plane, atmosphere_km=80, elevation=20):
    radius = RE_KM+height_km
    separation = 2*np.pi/satellites_per_plane
    distance = 2*radius*np.sin(separation/2)
    beta = np.arccos(RE_KM/radius*np.cos(np.deg2rad(elevation)))-np.deg2rad(elevation)
    return dict(altitude_km=height_km, satellites_per_plane=satellites_per_plane,
                adjacent_isl_km=float(distance), adjacent_owtt_ms=float(distance/C_KM_S*1000),
                minimum_limb_altitude_km=float(radius*np.cos(separation/2)-RE_KM),
                required_altitude_km=float((RE_KM+atmosphere_km)/np.cos(separation/2)-RE_KM),
                footprint_half_angle_deg=float(np.rad2deg(beta)),
                footprint_diameter_km=float(2*RE_KM*beta),
                orbit_period_min=float(2*np.pi*np.sqrt(radius**3/MU)/60))


def possible_footprint_angle(station, orbit_radius_km, elevation=20):
    """Conservative necessary geocentric angle with WGS84 normal correction.

    True geodetic elevation differs from radial elevation by at most the angle
    between those two local verticals. Enlarging the radial footprint by that
    bound ensures that a rejected orbital-plane point cannot actually be visible.
    """
    ground = geodetic_ecef(station['lat_deg'], station['lon_deg'], station['height_km'])
    radial = unit(ground)
    normal = ground_up(station['lat_deg'], station['lon_deg'])
    offset = np.arccos(np.clip(radial@normal, -1, 1))
    eps = np.deg2rad(elevation)-offset
    return float(np.arccos(np.linalg.norm(ground)/orbit_radius_km*np.cos(eps))-eps)


def plane_normals(config, ephemeris, times):
    if config.eccentricity != 0:
        raise ValueError('This circular-plane feasibility bound requires e=0')
    omega = ephemeris.raan0[::config.sats_per_plane]+ephemeris.raan_rate*np.asarray(times)[:, None]
    inc = np.deg2rad(config.inclination_deg)
    return np.stack([np.sin(inc)*np.sin(omega), -np.sin(inc)*np.cos(omega),
                     np.full_like(omega, np.cos(inc))], axis=-1)


def access_audit(config=None, sim=None, step_s=1):
    config = config or proposal_constellation()
    sim = sim or Simulation()
    ep = KeplerEphemeris(config, sim.epoch_datetime)
    times = np.arange(0, sim.duration_s, step_s)
    _, _, fixed, _ = ep.state(times[:, None])
    normals = plane_normals(config, ep, times)
    stations, _ = load_data()
    columns = {'time_s': times, 'sample_duration_s': np.minimum(step_s, sim.duration_s-times)}
    actual_masks, continuum_masks = [], []
    profile = []
    # Longitude profile spans a full relative Earth/orbit-plane rotation. The
    # common J2 nodal rate means RAAN-start changes merely shift this profile.
    longitudes = np.linspace(0, 2*np.pi, 36000, endpoint=False)
    static_normals = plane_normals(config, ep, [0])[0]
    for name in STATIONS:
        station = stations[name]
        ground = geodetic_ecef(station['lat_deg'], station['lon_deg'], station['height_km'])
        up = ground_up(station['lat_deg'], station['lon_deg'])
        elevations = elevation_deg(fixed, ground, up)
        counts = (elevations >= 20).sum(axis=-1)
        actual = counts > 0
        radial_eci = rotate_z(np.broadcast_to(unit(ground), (len(times), 3)), ep.theta0+OMEGA_E*times)
        cross_track = np.arcsin(np.clip(np.abs(np.einsum('tpj,tj->tp', normals, radial_eci)), 0, 1))
        closest = cross_track.min(axis=1)
        beta = possible_footprint_angle(station, RE_KM+config.altitude_km)
        continuum = closest <= beta
        columns[f'{name}_visible_count'] = counts
        columns[f'{name}_access'] = actual
        columns[f'{name}_continuum_possible'] = continuum
        columns[f'{name}_nearest_plane_deg'] = np.rad2deg(closest)
        actual_masks.append(actual); continuum_masks.append(continuum)
        latitude = np.arcsin(unit(ground)[2])
        directions = np.stack([np.cos(latitude)*np.cos(longitudes), np.cos(latitude)*np.sin(longitudes),
                               np.full_like(longitudes, np.sin(latitude))], axis=-1)
        profile_angles = np.arcsin(np.clip(np.abs(directions@static_normals.T), 0, 1)).min(axis=1)
        profile.append(dict(station=name, conservative_footprint_deg=np.rad2deg(beta),
                            worst_nearest_plane_deg=np.rad2deg(profile_angles.max()),
                            witness_relative_longitude_deg=float(np.rad2deg(longitudes[np.argmax(profile_angles)])),
                            continuous_ring_possible_fraction=float((profile_angles <= beta).mean()),
                            relative_rotation_period_h=float(2*np.pi/(OMEGA_E-ep.raan_rate)/3600),
                            phase_independent_rejection=bool(profile_angles.max() > beta)))
    columns['three_station_access'] = np.logical_and.reduce(actual_masks)
    columns['three_station_continuum_possible'] = np.logical_and.reduce(continuum_masks)
    frame = pd.DataFrame(columns)
    rows = []
    for name in STATIONS:
        masks = [('actual', frame[f'{name}_access']), ('infinite_ring_upper_bound', frame[f'{name}_continuum_possible'])]
        for kind, mask in masks:
            rows.append(dict(station=name, model=kind, **availability_metrics(mask, frame.sample_duration_s)))
    rows.append(dict(station='ALL_THREE', model='actual',
                     **availability_metrics(frame.three_station_access, frame.sample_duration_s)))
    rows.append(dict(station='ALL_THREE', model='infinite_ring_upper_bound',
                     **availability_metrics(frame.three_station_continuum_possible, frame.sample_duration_s)))
    return frame, pd.DataFrame(rows), pd.DataFrame(profile)


def availability_metrics(mask, durations):
    mask, durations = np.asarray(mask, dtype=bool), np.asarray(durations, dtype=float)
    longest = streak = 0.
    for yes, dt in zip(mask, durations):
        streak = 0 if yes else streak+dt
        longest = max(longest, streak)
    return dict(availability=float(durations[mask].sum()/durations.sum()),
                outage_s=float(durations[~mask].sum()), longest_outage_s=float(longest))


def optimistic_paths(config=None, sim=None, arctic_only=False):
    """Visibility-limited same-epoch routing with all ground access choices.

    Complete mode has unlimited terminals, unlimited ISL range, no PAT or setup
    delay: an optimistic snapshot benchmark, not realizable degree-4 hardware.
    Arctic mode adds rings and greedy shortest cross-plane degree<=2 edges only
    while both satellites are >=65N; still no PAT, setup or weather.
    Neither model allows the third ground station as an uncharged relay.
    """
    config, sim = config or proposal_constellation(), sim or Simulation()
    ep = KeplerEphemeris(config, sim.epoch_datetime)
    stations, _ = load_data()
    ground = {name: geodetic_ecef(stations[name]['lat_deg'], stations[name]['lon_deg'], stations[name]['height_km']) for name in STATIONS}
    up = {name: ground_up(stations[name]['lat_deg'], stations[name]['lon_deg']) for name in STATIONS}
    edges = np.array([(a, b) for a in range(config.count) for b in range(a+1, config.count)])
    a, b = edges.T
    planes = np.arange(config.count)//config.sats_per_plane
    slots = np.arange(config.count) % config.sats_per_plane
    same = planes[a] == planes[b]
    ring = same & ((np.abs(slots[a]-slots[b]) == 1) | (np.abs(slots[a]-slots[b]) == config.sats_per_plane-1))
    rows = []
    for t in np.arange(0, sim.duration_s, sim.step_s):
        _, _, r, _ = ep.state(float(t))
        distances = np.linalg.norm(r[b]-r[a], axis=-1)
        clear = segment_min_radius(r[a], r[b]) >= RE_KM+80
        selected = clear.copy()
        if arctic_only:
            selected &= ring
            latitude = np.rad2deg(np.arcsin(unit(r)[:, 2]))
            cross = np.flatnonzero(clear & ~same & (latitude[a] >= 65) & (latitude[b] >= 65))
            degrees = np.zeros(config.count, dtype=int)
            for edge in cross[np.argsort(distances[cross], kind='stable')]:
                x, y = edges[edge]
                if degrees[x] < 2 and degrees[y] < 2:
                    selected[edge] = True
                    degrees[x] += 1; degrees[y] += 1
        graph = nx.Graph(); graph.add_nodes_from(range(config.count))
        for (x, y), distance in zip(edges[selected], distances[selected]):
            graph.add_edge(int(x), int(y), weight=float(distance/C_KM_S+5e-6))
        ready = {name: np.flatnonzero(elevation_deg(r, ground[name], up[name]) >= 20) for name in STATIONS}
        gsl = {name: np.linalg.norm(r-ground[name], axis=-1) for name in STATIONS}
        for route, (source, destination, baseline) in ROUTES.items():
            network = graph.copy(); network.add_nodes_from([config.count, config.count+1])
            for side, name in enumerate([source, destination]):
                for sat in ready[name]:
                    network.add_edge(config.count+side, int(sat), weight=float(gsl[name][sat]/C_KM_S+2.5e-6+.0005))
            rtt, path = np.nan, []
            try:
                delay, path = nx.single_source_dijkstra(network, config.count, config.count+1)
                rtt = delay*2000
            except nx.NetworkXNoPath:
                pass
            rows.append(dict(time_s=t, sample_duration_s=min(sim.step_s, sim.duration_s-t), route=route,
                             rtt_ms=rtt, baseline_assumption_ms=baseline, path='>'.join(map(str, path)),
                             source_visible=len(ready[source]), destination_visible=len(ready[destination]),
                             selected_isl=int(selected.sum())))
    return pd.DataFrame(rows)
