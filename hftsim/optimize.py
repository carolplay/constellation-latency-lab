from dataclasses import replace, asdict
from itertools import product
import pandas as pd
from .config import Constellation, Physics
from .engine import simulate, summarize


def grid_search(sim, heights=(1000, 1200, 1400), inclinations=(65, 75, 85),
                spans=(60, 120, 180), starts=(0,), phases=(0,), layouts=((3, 6),),
                physics=Physics(), minimum_availability=.999, jitter_limit_ms=.2, rtt_limit_ms=100):
    """Feasibility first; never rewards outage by minimizing conditional jitter alone.

    RAAN start and orbital phase are explicitly exposed to avoid phase-biased claims.
    Results remain candidate evaluations, not a global optimality certificate.
    """
    rows = []
    for h, inc, span, start, phase, (planes, satellites) in product(heights, inclinations, spans, starts, phases, layouts):
        if planes*satellites > 18 or planes*satellites < 12:
            continue
        c = Constellation.bespoke(planes=planes, sats_per_plane=satellites, altitude_km=h,
                                 inclination_deg=inc, raan_span_deg=span,
                                 raan_start_deg=start, phase_deg=phase)
        frame, events, _ = simulate(sim, c, physics)
        s = summarize(frame, events)
        feasible = (s['availability'] >= minimum_availability and s['p99_p1_jitter_ms'] is not None
                    and s['p99_p1_jitter_ms'] < jitter_limit_ms and s['p99_rtt_ms'] < rtt_limit_ms)
        rows.append(dict(**asdict(c), **s, feasible=feasible))
    if not rows:
        raise ValueError("No 12-18 satellite configurations in search domain")
    return pd.DataFrame(rows).sort_values(['feasible', 'availability', 'p99_p1_jitter_ms'],
                                        ascending=[False, False, True], na_position='last').reset_index(drop=True)


def cable_disruption(frame, start_s=43200, end_s=64800, backup_rtt_ms=225):
    """User-assumed detour latency; independent backbone, no synthetic capacity claim."""
    out = frame.copy()
    mask = (out.time_s >= start_s) & (out.time_s < end_s)
    out['scenario_fiber_rtt_ms'] = out.reference_rtt_ms.where(~mask, backup_rtt_ms)
    out['scenario_delta_rtt_ms'] = out.scenario_fiber_rtt_ms-out.rtt_ms
    out['best_available_rtt_ms'] = out[['scenario_fiber_rtt_ms', 'rtt_ms']].min(axis=1)
    return out
