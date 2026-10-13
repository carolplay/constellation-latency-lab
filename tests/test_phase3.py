import unittest
import numpy as np
from hftsim.phase3 import ring_geometry, proposal_constellation, access_audit, possible_footprint_angle
from hftsim.config import Simulation, RE_KM
from hftsim.benchmarks import load_data
from hftsim.geometry import geodetic_ecef, ground_up, elevation_deg, unit


class Phase3AuditTests(unittest.TestCase):
    def test_six_ring_is_clear_and_five_ring_is_occulted_at_1180km(self):
        six, five = ring_geometry(1180, 6), ring_geometry(1180, 5)
        self.assertGreater(six['minimum_limb_altitude_km'], 80)
        self.assertLess(five['minimum_limb_altitude_km'], 0)
        self.assertAlmostEqual(six['adjacent_isl_km'], RE_KM+1180)

    def test_continuum_bound_does_not_reject_actual_visible_satellite(self):
        f, _, _ = access_audit(sim=Simulation(duration_s=3600), step_s=5)
        for name in ['LD4', 'NY4', 'TOKYO']:
            self.assertFalse((f[f'{name}_access'] & ~f[f'{name}_continuum_possible']).any())

    def test_proposal_fails_even_infinite_ring_geometry(self):
        _, _, profile = access_audit(sim=Simulation(duration_s=60), step_s=10)
        self.assertTrue(profile.phase_independent_rejection.all())
        self.assertTrue((profile.relative_rotation_period_h < 24).all())
        self.assertTrue((profile.worst_nearest_plane_deg > profile.conservative_footprint_deg+10).all())

    def test_conservative_footprint_contains_all_visible_shell_samples(self):
        stations, _ = load_data()
        rng = np.random.default_rng(7)
        rays = unit(rng.normal(size=(20000, 3)))
        radius = RE_KM+1180
        for name in ['LD4', 'NY4', 'TOKYO']:
            s = stations[name]
            g = geodetic_ecef(s['lat_deg'], s['lon_deg'], s['height_km'])
            up = ground_up(s['lat_deg'], s['lon_deg'])
            visible = elevation_deg(radius*rays, g, up) >= 20
            separation = np.arccos(np.clip(rays@unit(g), -1, 1))
            self.assertTrue((separation[visible] <= possible_footprint_angle(s, radius)).all())


if __name__ == '__main__':
    unittest.main()
