import json
from pathlib import Path
import numpy as np
import pandas as pd
from .config import C_KM_S
from .geometry import geodetic_ecef, great_circle_km, spherical_obstacle_bound, ideal_shell_length

ROOT = Path(__file__).resolve().parents[1]


def load_data():
    directory = ROOT/'data' if (ROOT/'data/stations.json').exists() else Path(__file__).parent/'data'
    return (json.loads((directory/'stations.json').read_text()),
            json.loads((directory/'baselines.json').read_text()))


def benchmark_table(group_index=1.468):
    stations, data = load_data()
    rows = []
    for route, b in data['routes'].items():
        a, z = [stations[n] for n in b['stations']]
        ra, rz = [geodetic_ecef(s['lat_deg'], s['lon_deg'], s['height_km']) for s in (a, z)]
        distance = great_circle_km(a, z)
        rows.append(dict(route=route, great_circle_km=distance,
                         chord_vacuum_rtt_ms=2*np.linalg.norm(rz-ra)/C_KM_S*1000,
                         external_earth_bound_rtt_ms=2*spherical_obstacle_bound(ra, rz)/C_KM_S*1000,
                         spherical_surface_vacuum_rtt_ms=2*distance/C_KM_S*1000,
                         ideal_geodesic_fiber_rtt_ms=2*distance*group_index/C_KM_S*1000,
                         reference_rtt_ms=b['rtt_ms'], reference_status=b['status'],
                         reference_label=b['label']))
    return pd.DataFrame(rows)


def distance_latitude_matrix(height_km=1200, group_index=1.468, route_stretch=1.0,
                             overhead_rtt_ms=2.0, inclination_deg=75):
    """Screening model, not a TVG result or latitude-dependent coverage proof."""
    rows = []
    for lat in [0, 30, 45, 60, 75, 85]:
        for distance in [1000, 3000, 6000, 9000, 12000, 16000]:
            space = 2*ideal_shell_length(distance, height_km)/C_KM_S*1000+overhead_rtt_ms
            fiber = 2*distance*group_index*route_stretch/C_KM_S*1000
            # Necessary access condition only; no simultaneous coverage assertion.
            eps = np.deg2rad(20)
            beta = np.rad2deg(np.arccos(6378.137/(6378.137+height_km)*np.cos(eps))-eps)
            reachable = abs(lat) <= min(inclination_deg, 180-inclination_deg)+beta
            rows.append(dict(latitude_deg=lat, distance_km=distance,
                             ideal_shell_rtt_ms=space, ideal_fiber_rtt_ms=fiber,
                             ideal_delta_ms=fiber-space, latitude_necessary_condition=reachable,
                             verdict="TVG validation required" if reachable and space < fiber
                             else "no advantage in screening model"))
    return pd.DataFrame(rows)
