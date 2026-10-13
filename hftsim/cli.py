import argparse
from dataclasses import replace
from pathlib import Path
import json
from .config import Simulation, Constellation, Physics
from .engine import simulate, summarize, save_result
from .plots import comparison_plot, jitter_boxplot
from .optimize import grid_search


def main():
    parser = argparse.ArgumentParser(description='Snapshot TVG latency sandbox')
    parser.add_argument('--route', default='LD4-TOKYO', choices=['LD4-TOKYO', 'NY4-LD4', 'AURORA-NY4'])
    parser.add_argument('--preset', choices=['generic', 'bespoke'], default='generic')
    parser.add_argument('--phase', choices=[1, 2], type=int, default=2)
    parser.add_argument('--duration', type=float, default=86400)
    parser.add_argument('--step', type=float, default=10)
    parser.add_argument('--out', default='outputs/run')
    parser.add_argument('--search', action='store_true')
    args = parser.parse_args()
    sim = Simulation(route=args.route, duration_s=args.duration, step_s=args.step)
    physics = Physics() if args.phase == 2 else Physics.phase1()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    if args.search:
        table = grid_search(sim, physics=physics)
        table.to_csv(out/'search.csv', index=False)
        print(table[['altitude_km', 'inclination_deg', 'raan_span_deg', 'availability', 'feasible']].head().to_string(index=False))
    else:
        c = Constellation() if args.preset == 'generic' else Constellation.bespoke()
        frame, events, meta = simulate(sim, c, physics)
        save_result(out, frame, events, meta)
        comparison_plot({c.label: frame}, out/'latency.png')
        jitter_boxplot({c.label: frame}, out/'jitter.png')
        print((out/'summary.json').read_text())


if __name__ == '__main__':
    main()
