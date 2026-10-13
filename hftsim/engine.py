from dataclasses import asdict
import json
import numpy as np
import pandas as pd
import networkx as nx
from .benchmarks import load_data
from .config import C_KM_S, Simulation, Constellation, Physics
from .geometry import geodetic_ecef, ground_up, elevation_deg
from .orbits import KeplerEphemeris
from .optics import candidate_edges, OpticalLinks
from .handover import GroundAccess


def build_graph(count, edges, usable, distances, ready, ground_distances, physics):
    """Half node processing on each incident edge charges each relay exactly once."""
    graph = nx.Graph()
    graph.add_nodes_from(range(count+2))
    proc = physics.satellite_processing_us*1e-6
    for (a, b), d in zip(edges[usable], distances[usable]):
        graph.add_edge(int(a), int(b), weight=float(d/C_KM_S+proc), distance_km=float(d), kind='isl')
    for side in range(2):
        for satellite in ready[side]:
            d = ground_distances[side][satellite]
            graph.add_edge(count+side, satellite,
                           weight=float(d/C_KM_S+proc/2+physics.ground_modem_ms/1000),
                           distance_km=float(d), kind='gsl')
    return graph


def simulate(sim=Simulation(), constellation=Constellation(), physics=Physics(), ephemeris=None, progress=None, edges=None):
    stations, baselines = load_data()
    if sim.route not in baselines['routes']:
        raise ValueError(f"Unknown route: {sim.route}")
    baseline = baselines['routes'][sim.route]
    ground_specs = [stations[n] for n in baseline['stations']]
    ground = [geodetic_ecef(g['lat_deg'], g['lon_deg'], g['height_km']) for g in ground_specs]
    up = [ground_up(g['lat_deg'], g['lon_deg']) for g in ground_specs]
    ephemeris = ephemeris or KeplerEphemeris(constellation, sim.epoch_datetime)
    if ephemeris.count != constellation.count:
        raise ValueError("Ephemeris and configured topology node counts must match")
    edges = candidate_edges(constellation) if edges is None else np.asarray(edges, dtype=int).reshape(-1, 2)
    if len(edges) and (edges.min() < 0 or edges.max() >= ephemeris.count):
        raise ValueError('Topology contains an invalid satellite index')
    optical = OpticalLinks(ephemeris, edges, physics)
    access = [GroundAccess(physics.antennas, physics.acquire_s) for _ in ground]
    times = np.arange(0, sim.duration_s, sim.step_s)
    rows, previous_path, changes = [], None, 0
    reference = sim.baseline_rtt_ms if sim.baseline_rtt_ms is not None else baseline['rtt_ms']
    for k, t in enumerate(times):
        state = ephemeris.state(float(t))
        _, _, re, ve = state
        if not all(np.isfinite(x).all() for x in state):
            raise ValueError(f"Non-finite ephemeris state at {t}s")
        usable, distances, diag = optical.evaluate(float(t), state)
        ready, ground_distances, visibility = [], [], []
        for g, normal, machine in zip(ground, up, access):
            elev = elevation_deg(re, g, normal)
            delta = re-g
            d = np.linalg.norm(delta, axis=-1)
            track = np.rad2deg(np.linalg.norm(np.cross(delta, ve), axis=-1)/np.maximum(d*d, 1e-20))
            visible = (elev >= physics.min_elevation_deg) & (track <= physics.ground_track_limit_deg_s)
            scores = {int(s): float(elev[s]) for s in np.flatnonzero(visible)}
            ready.append(machine.update(float(t), scores))
            ground_distances.append(d)
            visibility.append(int(visible.sum()))
        graph = build_graph(constellation.count, edges, usable, distances, ready, ground_distances, physics)
        rtt, owtt, path_length, hops, path_changed = np.nan, np.nan, np.nan, np.nan, False
        path = None
        try:
            owtt, path_list = nx.single_source_dijkstra(graph, constellation.count, constellation.count+1, weight='weight')
            path = tuple(path_list)
            path_changed = previous_path is not None and path != previous_path
            changes += int(path_changed)
            rtt = 2*owtt*1000+(physics.routing_reconvergence_ms if path_changed else 0)
            path_length = sum(graph[a][b]['distance_km'] for a, b in zip(path[:-1], path[1:]))
            hops = len(path)-2  # satellite relay count; ISL edges = hops-1
            access[0].choose(float(t), path[1]); access[1].choose(float(t), path[-2])
            reason = 'connected'
        except nx.NetworkXNoPath:
            reason = 'no_visible_ground_satellite' if min(visibility) == 0 else (
                'ground_acquisition' if min(map(len, ready)) == 0 else 'no_isl_route')
            # Antennas keep tracking during backbone outage; no fictitious access loss.
        previous_path = path
        rows.append(dict(time_s=float(t), sample_duration_s=float(min(sim.step_s, sim.duration_s-t)),
                         rtt_ms=rtt, owtt_ms=owtt*1000, delta_rtt_ms=reference-rtt,
                         reference_rtt_ms=reference, satellite_relays=hops, path_length_km=path_length,
                         path='>'.join(map(str, path)) if path else '', path_changed=path_changed,
                         outage_reason=reason, source_visible=visibility[0], destination_visible=visibility[1],
                         source_ready=len(ready[0]), destination_ready=len(ready[1]), **diag))
        if progress and k % max(1, len(times)//20) == 0:
            progress(k/len(times))
    frame = pd.DataFrame(rows)
    event_rows = [dict(station=baseline['stations'][i], **e) for i, m in enumerate(access) for e in m.events]
    events = pd.DataFrame(event_rows, columns=['station', 'time_s', 'kind', 'satellite', 'previous', 'make_before_break'])
    metadata = dict(simulation=asdict(sim), constellation=asdict(constellation), physics=asdict(physics),
                    ephemeris=type(ephemeris).__name__, benchmark=baseline,
                    conventions=dict(rtt='2 * same-epoch symmetric OWTT + configured first-packet convergence delay',
                                     samples='left endpoints of [0,duration), sample-held availability',
                                     jitter='conditional online RTT P99 - P1; not packet delay variation',
                                     pat='epoch-calibrated nominal terminal boresights fixed in LVLH',
                                     acquisition='sampled continuous visibility; initial cold start',
                                     excluded='traffic queues, serialization, weather, link budget, capacity, failures, asymmetric and causal flight-time routing'))
    if hasattr(ephemeris, 'elements'):
        metadata['custom_elements'] = ephemeris.elements
        metadata['custom_elements_j2'] = ephemeris.j2_enabled
    if hasattr(ephemeris, 'pairs'):
        metadata['tle_pairs'] = ephemeris.pairs
    return frame, events, metadata


def summarize(frame, events=None):
    online = frame.rtt_ms.notna()
    values = frame.loc[online, 'rtt_ms'].to_numpy()
    weights = frame.sample_duration_s.to_numpy()
    covered = float(weights[online].sum()/weights.sum())
    longest, streak = 0.0, 0.0
    for good, w in zip(online, weights):
        streak = 0.0 if good else streak+w
        longest = max(longest, streak)
    result = dict(samples=len(frame), online_samples=int(online.sum()), availability=covered,
                  outage_s=float(weights[~online].sum()), longest_outage_s=longest,
                  path_changes=int(frame.path_changed.sum()),
                  path_changes_per_24h=float(frame.path_changed.sum()*86400/weights.sum()),
                  advantage_fraction_all_time=float(weights[(frame.delta_rtt_ms > 0) & online].sum()/weights.sum()),
                  unconditional_p99_rtt_ms=float('inf') if covered < .99 else None)
    if len(values):
        p1, p50, p99 = np.percentile(values, [1, 50, 99])
        jumps = frame.rtt_ms.diff().abs().dropna()
        result.update(mean_rtt_ms=float(np.average(values, weights=weights[online])),
                      std_rtt_ms=float(np.std(values)), p1_rtt_ms=float(p1), p50_rtt_ms=float(p50),
                      p99_rtt_ms=float(p99), p99_p1_jitter_ms=float(p99-p1),
                      mean_delta_rtt_ms=float(np.average(frame.loc[online, 'delta_rtt_ms'], weights=weights[online])),
                      max_consecutive_rtt_jump_ms=float(jumps.max()) if len(jumps) else None)
        if covered >= .99:
            # Offline samples treated as +inf; locate unconditional quantile in finite mass.
            result['unconditional_p99_rtt_ms'] = float(np.quantile(values, min(.99/covered, 1)))
    else:
        result.update({key: None for key in ['mean_rtt_ms', 'std_rtt_ms', 'p1_rtt_ms', 'p50_rtt_ms',
                                            'p99_rtt_ms', 'p99_p1_jitter_ms', 'mean_delta_rtt_ms',
                                            'max_consecutive_rtt_jump_ms']})
    result['handover_count'] = int((events.kind == 'handover').sum()) if events is not None and len(events) else 0
    return result


def save_result(directory, frame, events, metadata):
    from pathlib import Path
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    frame.to_csv(directory/'timeseries.csv', index=False)
    events.to_csv(directory/'access_events.csv', index=False)
    (directory/'metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
    summary = summarize(frame, events)
    # JSON has no Infinity. Explicit string preserves outages rather than dropping them.
    summary = {k: ('infinity_due_to_outage' if isinstance(v, float) and np.isinf(v) else v) for k, v in summary.items()}
    (directory/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))
