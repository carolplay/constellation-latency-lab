import unittest
from dataclasses import replace
from datetime import datetime, timezone
import numpy as np
from hftsim.config import Constellation, Physics, Simulation, RE_KM, C_KM_S, MU
from hftsim.geometry import segment_min_radius, geodetic_ecef, ground_up, elevation_deg, spherical_obstacle_bound
from hftsim.orbits import KeplerEphemeris, body_basis, TLEEphemeris, ElementsEphemeris
from hftsim.optics import candidate_edges, OpticalLinks
from hftsim.handover import GroundAccess
from hftsim.engine import build_graph, simulate, summarize
import networkx as nx

EPOCH = datetime(2026, 10, 12, tzinfo=timezone.utc)


class GeometryTests(unittest.TestCase):
    def test_finite_segment_clamps_outside_projection(self):
        self.assertAlmostEqual(segment_min_radius(np.array([7000., 0, 0]), np.array([8000., 0, 0])), 7000)

    def test_limb_tangency_and_occultation(self):
        boundary = RE_KM+80
        a, b = np.array([-1000, boundary, 0]), np.array([1000, boundary, 0])
        self.assertAlmostEqual(segment_min_radius(a, b), boundary)
        self.assertLess(segment_min_radius(a-np.array([0, 1, 0]), b-np.array([0, 1, 0])), boundary)
        self.assertEqual(segment_min_radius(np.array([-7000., 0, 0]), np.array([7000., 0, 0])), 0)

    def test_ellipsoid_up_and_overhead(self):
        g = geodetic_ecef(51.5, -.6)
        u = ground_up(51.5, -.6)
        self.assertAlmostEqual(elevation_deg(np.array([g+550*u]), g, u)[0], 90, delta=2e-6)
        self.assertAlmostEqual(np.linalg.norm(geodetic_ecef(0, 0)), RE_KM)

    def test_obstacle_bound_is_longer_than_chord(self):
        a, b = geodetic_ecef(0, 0), geodetic_ecef(0, 90)
        d = spherical_obstacle_bound(a, b)
        self.assertGreater(d, np.linalg.norm(b-a))
        self.assertLess(d, np.pi/2*RE_KM)


class OrbitTests(unittest.TestCase):
    def test_custom_six_elements_have_independent_radii(self):
        elements = [dict(a_km=a, e=0, i_deg=65, raan_deg=20, arg_perigee_deg=0,
                         mean_anomaly_deg=phase) for a, phase in [(7500, 0), (7800, 180)]]
        ep = ElementsEphemeris(elements, EPOCH, j2=False)
        np.testing.assert_allclose(np.linalg.norm(ep.state(100)[0], axis=-1), [7500, 7800], atol=1e-8)

    def test_kepler_energy_and_angular_momentum(self):
        c = Constellation(planes=2, sats_per_plane=3, eccentricity=.02, altitude_km=1400, j2=False)
        ep = KeplerEphemeris(c, EPOCH)
        r, v, re, ve = ep.state(3210)
        energy = np.sum(v*v, axis=-1)/2-MU/np.linalg.norm(r, axis=-1)
        np.testing.assert_allclose(energy, -MU/(2*ep.a), rtol=1e-8)
        h = np.linalg.norm(np.cross(r, v), axis=-1)
        np.testing.assert_allclose(h, np.sqrt(MU*ep.a*(1-ep.e**2)), rtol=1e-8)
        np.testing.assert_allclose(np.linalg.norm(r, axis=-1), np.linalg.norm(re, axis=-1), atol=1e-9)

    def test_ecef_velocity_matches_time_derivative(self):
        ep = KeplerEphemeris(Constellation(planes=1, sats_per_plane=3), EPOCH)
        _, _, re, ve = ep.state(1000)
        numerical = (ep.state(1000.01)[2]-ep.state(999.99)[2])/.02
        np.testing.assert_allclose(ve, numerical, atol=1e-7)

    def test_j2_regresses_prograde_nodes_and_lvlh_is_orthonormal(self):
        ep = KeplerEphemeris(Constellation(planes=1, sats_per_plane=3), EPOCH)
        self.assertLess(ep.raan_rate, 0)
        r, v, _, _ = ep.state(0)
        basis = body_basis(r, v)
        np.testing.assert_allclose(basis[0].T @ basis[0], np.eye(3), atol=1e-12)
        self.assertAlmostEqual(np.linalg.det(basis[0]), 1)

    def test_sgp4_reference_tle_and_ecef_velocity(self):
        # Vallado SGP4 verification case, epoch is local to the fixture (not a live TLE).
        pairs = [('1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  4753',
                  '2 00005  34.2682 348.7242 1859667 331.7664  19.3264 10.82419157413667')]
        epoch = datetime(2000, 6, 27, 18, 50, 19, tzinfo=timezone.utc)
        ep = TLEEphemeris(pairs, epoch)
        state = ep.state(0)
        self.assertTrue(all(np.isfinite(s).all() for s in state))
        numerical = (ep.state(.1)[2]-ep.state(-.1)[2])/.2
        # SGP4 supplied velocity is not an exact derivative of its position model;
        # 2 m/s accommodates short-period terms while detecting frame/rotation errors.
        np.testing.assert_allclose(state[3], numerical, atol=.002)


class RoutingTests(unittest.TestCase):
    def test_no_more_than_four_grid_neighbors(self):
        c = Constellation(planes=4, sats_per_plane=8)
        edges = candidate_edges(c)
        degrees = np.bincount(edges.ravel(), minlength=c.count)
        self.assertTrue(np.all(degrees == 4))
        partial = candidate_edges(replace(c, raan_span_deg=120))
        self.assertEqual(len(edges)-len(partial), c.sats_per_plane)

    def test_exact_processing_accounting(self):
        p = Physics(satellite_processing_us=5, ground_modem_ms=.5)
        graph = build_graph(2, np.array([[0, 1]]), np.array([True]), np.array([1000.]),
                            [[0], [1]], [np.array([500., 999.]), np.array([999., 500.])], p)
        owtt = nx.shortest_path_length(graph, 2, 3, weight='weight')
        self.assertAlmostEqual(owtt, 2000/C_KM_S+2*5e-6+2*.0005)

    def test_limb_filter_rejects_earth_crossing_even_phase1(self):
        c = Constellation(planes=1, sats_per_plane=2, j2=False)
        ep = KeplerEphemeris(c, EPOCH)
        links = OpticalLinks(ep, candidate_edges(c), Physics.phase1())
        good, _, diagnostic = links.evaluate(0, ep.state(0))
        self.assertFalse(good.any()); self.assertEqual(diagnostic['rejected_limb'], 1)

    def test_fov_doppler_and_slew_gates(self):
        c = Constellation(planes=3, sats_per_plane=6, altitude_km=1400, inclination_deg=75)
        ep = KeplerEphemeris(c, EPOCH)
        p = Physics(fov_half_angle_deg=.1, slew_limit_deg_s=1e-9, max_doppler_hz=1, isl_acquire_s=0)
        links = OpticalLinks(ep, candidate_edges(c), p)
        _, _, diagnostic = links.evaluate(1000, ep.state(1000))
        self.assertGreater(diagnostic['rejected_fov'], 0)
        self.assertGreater(diagnostic['rejected_slew'], 0)
        self.assertGreater(diagnostic['rejected_doppler'], 0)

    def test_dual_antenna_overlap_and_single_antenna_gap(self):
        dual, single = GroundAccess(2, 20), GroundAccess(1, 20)
        for access in (dual, single):
            access.update(0, {0: 50})
            self.assertEqual(access.update(10, {0: 50}), [])
            self.assertIn(0, access.update(20, {0: 50}))
            access.choose(20, 0)
            access.update(30, {0: 40, 1: 30})
        self.assertIn(1, dual.update(50, {0: 30, 1: 40}))
        dual.choose(50, 1)
        self.assertTrue(dual.events[-1]['make_before_break'])
        self.assertEqual(single.update(60, {1: 45}), [])
        self.assertIn(1, single.update(80, {1: 45}))

    def test_no_connection_returns_missing_latency_and_outage(self):
        c = Constellation(planes=1, sats_per_plane=1)
        frame, events, _ = simulate(Simulation(duration_s=60), c)
        s = summarize(frame, events)
        self.assertEqual(s['availability'], 0)
        self.assertIsNone(s['mean_rtt_ms'])
        self.assertTrue(np.isinf(s['unconditional_p99_rtt_ms']))
        self.assertTrue(frame.rtt_ms.isna().all())


if __name__ == '__main__':
    unittest.main()
