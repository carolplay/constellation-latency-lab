import unittest
import numpy as np
from hftsim.czml import sensor_geometry,export_czml,walker_delta,footprint_wgs84,visible_counts
from hftsim.config import Simulation,RE_KM
from hftsim.geometry import unit
from hftsim.orbits import KeplerEphemeris


class CesiumExportTests(unittest.TestCase):
    def test_cone_formula_and_disk_geometry_agree(self):
        shape=sensor_geometry()
        self.assertAlmostEqual(shape['cone_half_angle_deg'],52.46533359016291)
        angle=np.rad2deg(np.arctan2(shape['cone_base_radius_km'],shape['cone_axial_length_km']))
        self.assertAlmostEqual(angle,shape['cone_half_angle_deg'])

    def test_positions_are_ecef_meters_and_include_stop(self):
        sim=Simulation(duration_s=25,step_s=10)
        packets,meta=export_czml(sim=sim)
        sats=[p for p in packets if p.get('properties',{}).get('satellite')]
        self.assertEqual(len(sats),18)
        position=sats[0]['position']
        self.assertEqual(position['referenceFrame'],'FIXED')
        values=np.array(position['cartesian']).reshape(-1,4)
        np.testing.assert_array_equal(values[:,0],[0,10,20,25])
        ep=KeplerEphemeris(walker_delta(),sim.epoch_datetime)
        np.testing.assert_allclose(values[0,1:],ep.state(0)[2][0]*1000,atol=.0006)

    def test_cylinder_apex_matches_satellite_and_quaternion_is_unit(self):
        packets,_=export_czml(sim=Simulation(duration_s=60))
        sat=next(p for p in packets if p['id']=='P1-S1')
        cone=next(p for p in packets if p['id']=='cone-P1-S1')
        r=np.array(sat['position']['cartesian']).reshape(-1,4)[:,1:]
        center=np.array(cone['position']['cartesian']).reshape(-1,4)[:,1:]
        q=np.array(cone['orientation']['unitQuaternion']).reshape(-1,5)[:,1:]
        np.testing.assert_allclose(np.linalg.norm(q,axis=1),1,atol=1e-12)
        x,y,z,w=q.T
        direction=np.column_stack([2*(x*z+w*y),2*(y*z-w*x),1-2*(x*x+y*y)])
        np.testing.assert_allclose(center+direction*cone['cylinder']['length']/2,r,atol=.002)

    def test_footprint_is_on_wgs84_and_at_twenty_degree_elevation(self):
        sat=np.array([6000.,3000.,3500.]);sat=unit(sat)*(RE_KM+1180)
        ring=footprint_wgs84(sat)
        radii=np.array([RE_KM,RE_KM,6356.752314245])
        np.testing.assert_allclose(np.sum((ring/radii)**2,axis=1),1,atol=1e-12)
        normals=unit(ring/(radii*radii))
        eps=np.rad2deg(np.arcsin(np.sum(unit(sat-ring)*normals,axis=1)))
        np.testing.assert_allclose(eps,20,atol=1e-8)
        inside=ring*.99
        self.assertEqual(visible_counts(np.array([sat]),np.array([unit(sat)*RE_KM]),np.array([unit(sat)]))[0,0],1)


if __name__=='__main__':
    unittest.main()
