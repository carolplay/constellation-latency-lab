import unittest
import numpy as np
from hftsim.config import Simulation, RE_KM
from hftsim.orbits import CompositeEphemeris, KeplerEphemeris
from hftsim.public_models import lightspeed298, globalstar48
from hftsim.czml import export_shells_czml, visible_counts


class PublicModelsTests(unittest.TestCase):
    def test_shells_keep_distinct_radii_nodes_and_velocities(self):
        sim=Simulation(); shells=lightspeed298(); ep=CompositeEphemeris(shells,sim.epoch_datetime)
        state=ep.state(3210)
        self.assertEqual(ep.count,298)
        np.testing.assert_allclose(np.linalg.norm(state[2][:78],axis=-1),RE_KM+1015,atol=1e-8)
        np.testing.assert_allclose(np.linalg.norm(state[2][78:],axis=-1),RE_KM+1325,atol=1e-8)
        numerical=(ep.state(3210.01)[2]-ep.state(3209.99)[2])/.02
        np.testing.assert_allclose(state[3],numerical,atol=2e-7)
        polar=KeplerEphemeris(shells[0],sim.epoch_datetime)
        np.testing.assert_allclose(np.rad2deg(polar.raan0[::13]),np.arange(6)*30)
        self.assertGreater(polar.raan_rate,0)

    def test_multishell_export_unique_ids_and_correct_second_shell(self):
        sim=Simulation(duration_s=60,step_s=30);shells=lightspeed298()
        packets,_=export_shells_czml(shells,sim)
        self.assertEqual(len({p['id'] for p in packets}),len(packets))
        self.assertEqual(sum(p['id'].startswith('station-') for p in packets),3)
        sats=[p for p in packets if p.get('properties',{}).get('satellite')]
        self.assertEqual(len(sats),298)
        second=sats[78]
        expected=CompositeEphemeris(shells,sim.epoch_datetime).state(0)[2][78]*1000
        np.testing.assert_allclose(second['position']['cartesian'][1:4],expected,atol=.0006)
        self.assertEqual(second['properties']['plane']['number'],7)

    def test_counts_do_not_wrap_above_255(self):
        satellites=np.repeat([[RE_KM+1414,0,0]],298,axis=0)
        self.assertEqual(visible_counts(satellites,[[RE_KM,0,0]],[[1,0,0]])[0,0],298)
        self.assertEqual(sum(c.count for c in globalstar48()),48)
