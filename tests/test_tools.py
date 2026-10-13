import unittest
from copy import deepcopy
import numpy as np
from hftsim.tools import parse_config,geometry_latency,engineering_latency,topology_edges
from hftsim.orbits import CompositeEphemeris

PAYLOAD={'schema_version':1,'name':'Functional test','simulation':{'route':'NY4-LD4','duration_s':120,'step_s':60},
         'shells':[dict(pattern='delta',planes=8,sats_per_plane=6,altitude_km=1414,inclination_deg=52,walker_f=1)],
         'topology':'complete','physics':{'min_elevation_deg':20}}

class ToolTests(unittest.TestCase):
    def test_geometry_and_engineering_have_distinct_acquisition_semantics(self):
        p=deepcopy(PAYLOAD);p['physics']['acquire_s']=600
        geometry,_,gm=geometry_latency(p);engineering,events,em=engineering_latency(p)
        self.assertTrue(geometry.rtt_ms.notna().all())
        self.assertTrue(engineering.rtt_ms.isna().all())
        self.assertEqual(gm['mode'],'geometry');self.assertEqual(em['mode'],'engineering')
        self.assertGreater(len(events),0)

    def test_walker_star_exclusive_seam_and_multishell_grid(self):
        p=deepcopy(PAYLOAD);p['topology']='grid';p['shells'][0].update(pattern='star',planes=6,sats_per_plane=13)
        p['shells'].append(dict(pattern='delta',planes=2,sats_per_plane=6,altitude_km=1180,inclination_deg=50,walker_f=1))
        sim,shells,_=parse_config(p);ep=CompositeEphemeris(shells,sim.epoch_datetime)
        np.testing.assert_allclose(np.rad2deg(ep.ephemerides[0].raan0[::13]),np.arange(6)*30)
        edges=topology_edges(shells)
        self.assertFalse(any(a<78<=b for a,b in edges))
        self.assertFalse(any(a<13 and b>=65 and b<78 for a,b in edges))
        self.assertLessEqual(np.bincount(edges.ravel()).max(),4)

    def test_config_version_and_phase_are_rejected(self):
        p=deepcopy(PAYLOAD);p['schema_version']=2
        with self.assertRaises(ValueError):parse_config(p)
        p=deepcopy(PAYLOAD);p['shells'][0]['walker_f']=8
        with self.assertRaises(ValueError):parse_config(p)
