"""Dated public orbit designs; phase/epoch reconstruction is explicitly synthetic."""
from .config import Constellation


def globalstar48():
    return (Constellation(planes=8, sats_per_plane=6, altitude_km=1414,
                          inclination_deg=52, walker_f=1,
                          label='Globalstar historical 48/8/1'),)


def lightspeed298(polar_f=1, inclined_f=1, polar_phase_deg=0):
    # Six Walker-Star planes at RAAN 0/30/.../150 degrees. Existing partial-span
    # convention includes endpoints, hence 150 is the occupied extent, not 180.
    return (Constellation(planes=6, sats_per_plane=13, altitude_km=1015,
                          inclination_deg=98.98, raan_span_deg=150, walker_f=polar_f,
                          phase_deg=polar_phase_deg, label='Lightspeed 2020 polar (assumed phasing)'),
            Constellation(planes=20, sats_per_plane=11, altitude_km=1325,
                          inclination_deg=50.88, walker_f=inclined_f,
                          label='Lightspeed 2020 inclined (assumed phasing)'))
