import os
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR', str(Path(__file__).resolve().parents[1]/'.mplconfig'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def comparison_plot(results, path):
    fig, axes = plt.subplots(3, 1, figsize=(13, 9), sharex=True, height_ratios=[3, 1, 1])
    colors = ['#007ea8', '#d76826', '#5b45a0', '#389167']
    for (label, frame), color in zip(results.items(), colors):
        axes[0].plot(frame.time_s/3600, frame.rtt_ms, label=label, linewidth=.65, color=color)
        axes[1].plot(frame.time_s/3600, frame.satellite_relays, linewidth=.5, color=color)
        axes[2].plot(frame.time_s/3600, frame.rtt_ms.notna().astype(int), linewidth=.7, label=label, color=color)
    first = next(iter(results.values()))
    axes[0].axhline(first.reference_rtt_ms.iloc[0], color='#555', ls='--', label='User fiber reference')
    axes[0].set_ylabel('Snapshot RTT (ms)'); axes[1].set_ylabel('Sat. relays')
    axes[2].set_ylabel('Online'); axes[2].set_xlabel('Hours from UTC epoch')
    axes[0].legend(loc='upper right', fontsize=8)
    axes[0].set_title('Space / fiber latency — outages are gaps, not zero latency')
    for ax in axes:
        ax.grid(alpha=.15)
    fig.tight_layout(); fig.savefig(path, dpi=160); plt.close(fig)


def jitter_boxplot(results, path):
    labels, values = [], []
    for label, frame in results.items():
        data = frame.rtt_ms.dropna().to_numpy()
        if len(data):
            labels.append(f"{label}\nOnline {frame.rtt_ms.notna().mean():.1%}")
            values.append(data)
    fig, ax = plt.subplots(figsize=(11, 5))
    if values:
        ax.boxplot(values, tick_labels=labels, whis=(1, 99), showfliers=False)
    ax.set_ylabel('Conditional online RTT (ms)'); ax.grid(axis='y', alpha=.2)
    ax.set_title('Whiskers: P1–P99; box: P25–P75; line: median')
    fig.tight_layout(); fig.savefig(path, dpi=160); plt.close(fig)


def matrix_plot(frame, path):
    matrix = frame.pivot(index='latitude_deg', columns='distance_km', values='ideal_delta_ms')
    fig, ax = plt.subplots(figsize=(10, 5))
    im = ax.imshow(matrix, cmap='RdBu', aspect='auto')
    ax.set_xticks(range(len(matrix.columns)), matrix.columns)
    ax.set_yticks(range(len(matrix.index)), matrix.index)
    for y, row in enumerate(matrix.to_numpy()):
        for x, value in enumerate(row):
            ax.text(x, y, f'{value:.1f}', ha='center', va='center', fontsize=9)
    ax.set_xlabel('Surface distance (km)'); ax.set_ylabel('Endpoint latitude (degrees)')
    ax.set_title('Ideal continuum screening: fiber minus space RTT (ms)\nLatitude affects access feasibility; does not prove continuous coverage')
    fig.colorbar(im, ax=ax, label='Ideal delta RTT (ms)')
    fig.tight_layout(); fig.savefig(path, dpi=160); plt.close(fig)
