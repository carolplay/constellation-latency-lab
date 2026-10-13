"""Portable Cesium core CZML export and WGS84 access auditing."""
from datetime import timedelta
from dataclasses import asdict
import numpy as np
from .config import RE_KM, Constellation, Simulation
from .orbits import KeplerEphemeris
from .geometry import unit, geodetic_ecef, ground_up, elevation_deg
from .benchmarks import load_data

WGS84_B_KM = 6356.752314245
COLORS = [[36, 145, 218, 255], [230, 126, 45, 255], [153, 108, 219, 255]]


def walker_delta(f=1):
    if f not in (0, 1, 2):
        raise ValueError('For three Walker planes, F must be 0, 1 or 2')
    return Constellation(planes=3, sats_per_plane=6, altitude_km=1180,
                         inclination_deg=71.5, raan_span_deg=360, walker_f=f,
                         label=f'Walker-Delta 71.5:18/3/{f}')


def sensor_geometry(height_km=1180, min_elevation_deg=20):
    if height_km <= 0 or not 0 <= min_elevation_deg < 90:
        raise ValueError('Require positive altitude and 0 <= elevation < 90')
    r = RE_KM+height_km
    eps = np.deg2rad(min_elevation_deg)
    beta = np.arccos(RE_KM/r*np.cos(eps))-eps
    alpha = np.pi/2-eps-beta
    axial = r-RE_KM*np.cos(beta)
    base = RE_KM*np.sin(beta)
    return dict(footprint_half_angle_deg=float(np.rad2deg(beta)),
                cone_half_angle_deg=float(np.rad2deg(alpha)),
                cone_full_angle_deg=float(np.rad2deg(2*alpha)),
                cone_axial_length_km=float(axial), cone_base_radius_km=float(base),
                boundary_slant_range_km=float(np.hypot(axial, base)))


def quaternion_z_to_direction(direction):
    """Quaternion x,y,z,w rotating cylinder +Z towards outward radial direction."""
    direction = unit(np.asarray(direction))
    q = np.zeros(direction.shape[:-1]+(4,))
    regular = direction[..., 2] > -1+1e-12
    denominator = np.sqrt(np.maximum(2*(1+direction[..., 2]), 1e-30))
    q[..., 0] = -direction[..., 1]/denominator
    q[..., 1] = direction[..., 0]/denominator
    q[..., 3] = denominator/2
    q[~regular] = [1, 0, 0, 0]
    return q/np.linalg.norm(q, axis=-1, keepdims=True)


def route_samples(count=97, source='LD4', destination='TOKYO'):
    """Spherical great-circle interpolation of lat/lon, mapped onto WGS84.

    Route is a geographical proxy; not a survey-grade ellipsoidal geodesic.
    """
    if count < 2:
        raise ValueError('At least two route points are required')
    stations, _ = load_data()
    a, b = [ground_up(stations[name]['lat_deg'], stations[name]['lon_deg']) for name in (source, destination)]
    theta = np.arccos(np.clip(a@b, -1, 1))
    fractions = np.linspace(0, 1, count)
    rays = (np.sin((1-fractions)*theta)[:, None]*a+np.sin(fractions*theta)[:, None]*b)/np.sin(theta)
    lat = np.rad2deg(np.arcsin(rays[:, 2]))
    lon = np.rad2deg(np.arctan2(rays[:, 1], rays[:, 0]))
    ground = np.array([geodetic_ecef(la, lo) for la, lo in zip(lat, lon)])
    up = np.array([ground_up(la, lo) for la, lo in zip(lat, lon)])
    return fractions, lat, lon, ground, up


def visible_counts(satellites_ecef_km, ground_ecef_km, up, elevation_deg_min=20):
    """Vectorized exact ellipsoid-normal elevation, output time x ground_point."""
    sat = np.asarray(satellites_ecef_km)
    if sat.ndim == 2:
        sat = sat[None, ...]
    ground = np.asarray(ground_ecef_km)
    up = np.asarray(up)
    range2 = np.sum(sat*sat, axis=-1)[..., None] + np.sum(ground*ground, axis=-1) - 2*np.einsum('tnj,pj->tnp', sat, ground)
    numerator = np.einsum('tnj,pj->tnp', sat, up)-np.sum(ground*up, axis=-1)
    sin_elevation = numerator/np.sqrt(np.maximum(range2, 1e-20))
    return (sin_elevation >= np.sin(np.deg2rad(elevation_deg_min))).sum(axis=1).astype(np.uint16)


def footprint_wgs84(satellite_ecef_km, elevation_deg_min=20, vertices=64):
    """Geocentric angular sweep, root-solved against WGS84 normal elevation.

    Points lie on the ellipsoid. The 20-degree boundary is not assumed circular.
    """
    sat = np.asarray(satellite_ecef_km, dtype=float)
    radial = unit(sat)
    if np.linalg.norm(sat) <= RE_KM:
        raise ValueError('Satellite must be outside Earth')
    reference = np.array([0., 0., 1.]) if abs(radial[2]) < .95 else np.array([1., 0., 0.])
    x = unit(np.cross(reference, radial)); y = np.cross(radial, x)
    azimuth = np.linspace(0, 2*np.pi, vertices, endpoint=False)
    tangent = np.cos(azimuth)[:, None]*x+np.sin(azimuth)[:, None]*y
    low, high = np.zeros(vertices), np.full(vertices, np.pi/2)
    radii = np.array([RE_KM, RE_KM, WGS84_B_KM])
    for _ in range(45):
        angle = (low+high)/2
        ray = np.cos(angle)[:, None]*radial+np.sin(angle)[:, None]*tangent
        surface = ray/np.sqrt(np.sum((ray/radii)**2, axis=-1))[:, None]
        normal = unit(surface/(radii*radii))
        actual = np.rad2deg(np.arcsin(np.clip(np.sum(unit(sat-surface)*normal, axis=-1), -1, 1)))
        inside = actual >= elevation_deg_min
        low = np.where(inside, angle, low); high = np.where(inside, high, angle)
    return surface


def export_czml(config=None, sim=None, min_elevation_deg=20, include_cones=True):
    config, sim = config or walker_delta(), sim or Simulation()
    if config.eccentricity != 0:
        raise ValueError('Fixed-size approximate cones require circular orbits')
    ep = KeplerEphemeris(config, sim.epoch_datetime)
    # Include the final endpoint so the viewer has no undefined terminal sample.
    times = np.unique(np.append(np.arange(0, sim.duration_s, sim.step_s), sim.duration_s))
    _, _, positions, _ = ep.state(times[:, None])
    epoch = sim.epoch_datetime.isoformat().replace('+00:00', 'Z')
    stop = (sim.epoch_datetime+timedelta(seconds=sim.duration_s)).isoformat().replace('+00:00', 'Z')
    interval = f'{epoch}/{stop}'
    shape = sensor_geometry(config.altitude_km, min_elevation_deg)
    packets = [dict(id='document', name=config.label, version='1.0', clock=dict(
        interval=interval, currentTime=epoch, multiplier=120, range='LOOP_STOP', step='SYSTEM_CLOCK_MULTIPLIER'))]
    packets.append(dict(id='configuration', properties={
        'minElevationDeg': {'number': min_elevation_deg}, 'altitudeKm': {'number': config.altitude_km},
        'walkerF': {'number': config.walker_f}, 'inclinationDeg': {'number': config.inclination_deg},
        'raanSpreadDeg': {'number': config.raan_span_deg}, 'planeCount': {'number': config.planes},
        'satellitesPerPlane': {'number': config.sats_per_plane}}))
    for index in range(config.count):
        plane, slot = divmod(index, config.sats_per_plane)
        identifier = f'P{plane+1}-S{slot+1}'
        color = COLORS[plane % len(COLORS)]
        sampled = np.column_stack([times, np.round(positions[:, index]*1000, 3)]).ravel().tolist()
        packets.append(dict(id=identifier, name=identifier, availability=interval,
            properties={'satellite': {'boolean': True}, 'plane': {'number': plane+1}},
            position=dict(epoch=epoch, referenceFrame='FIXED', cartesian=sampled,
                          interpolationAlgorithm='LINEAR', interpolationDegree=1),
            point=dict(pixelSize=7, color={'rgba': color}, outlineColor={'rgba': [255,255,255,255]}, outlineWidth=1),
            path=dict(show=True, leadTime=0, trailTime=1800, resolution=60,
                      width=1, material={'solidColor': {'color': {'rgba': color}}})))
        if include_cones:
            radial = unit(positions[:, index])
            axial = shape['cone_axial_length_km']
            center = positions[:, index]-radial*axial/2
            quaternion = quaternion_z_to_direction(radial)
            packets.append(dict(id=f'cone-{identifier}', name=f'{identifier} spherical cone (approx.)',
                availability=interval,
                description='Sphere approximation of a nadir 20-degree-elevation access envelope. Not a WGS84 footprint or physical antenna beam.',
                properties={'cone': {'boolean': True}, 'sourceSatellite': {'string': identifier}},
                position=dict(epoch=epoch, referenceFrame='FIXED',
                              cartesian=np.column_stack([times,np.round(center*1000,3)]).ravel().tolist(),
                              interpolationAlgorithm='LINEAR', interpolationDegree=1),
                orientation=dict(epoch=epoch, unitQuaternion=np.column_stack([times,quaternion]).ravel().tolist(),
                                 interpolationAlgorithm='LINEAR', interpolationDegree=1),
                cylinder=dict(length=axial*1000, topRadius=0, bottomRadius=shape['cone_base_radius_km']*1000,
                              slices=64, material={'solidColor': {'color': {'rgba': color[:3]+[28]}}})))
    stations, _ = load_data()
    for name in ['LD4', 'NY4', 'TOKYO']:
        g = stations[name]
        packets.append(dict(id=f'station-{name}', name=g['label'], properties={'station': {'boolean': True}},
                            position={'cartographicDegrees': [g['lon_deg'],g['lat_deg'],g['height_km']*1000]},
                            point={'pixelSize':10,'color':{'rgba':[240,209,69,255]}},
                            label={'text':name,'font':'14px sans-serif','pixelOffset':{'cartesian2':[10,-12]},
                                   'fillColor':{'rgba':[255,255,255,255]},'showBackground':True,
                                   'disableDepthTestDistance':1e12}))
    fractions, lat, lon, _, _ = route_samples()
    packets.append(dict(id='route-london-tokyo', name='LD4-Tokyo approximate great circle',
        polyline={'positions': {'cartographicDegrees': np.column_stack([lon,lat,np.full(len(lat),1000.)]).ravel().tolist()},
                  'width':2,'material':{'solidColor':{'color':{'rgba':[240,209,69,255]}}},'arcType':'NONE'}))
    for index, (fraction, la, lo) in enumerate(zip(fractions, lat, lon)):
        packets.append(dict(id=f'route-point-{index:03d}', name=f'Route sample {index+1}/97',
                            properties={'routeSample':{'boolean':True},'fraction':{'number':float(fraction)}},
                            position={'cartographicDegrees':[float(lo),float(la),1000.]},
                            point={'pixelSize':5,'color':{'rgba':[210,80,70,255]},'outlineColor':{'rgba':[255,255,255,180]},'outlineWidth':.5}))
    metadata = dict(constellation=asdict(config), simulation=asdict(sim), coordinate_units='meters',
                    reference_frame='FIXED/ECEF; no second Earth rotation in Cesium',
                    position_sample_count=len(times), interpolation='LINEAR, not an orbit propagator',
                    approximate_cone=shape, minimum_elevation_deg=min_elevation_deg,
                    footprints='WGS84 20deg contour computed separately in viewer',
                    exclusions='terrain, actual RF/optical beam pattern, weather, ISL topology, acquisition, capacity',
                    route='97 spherical-great-circle samples mapped to WGS84; not continuous corridor proof')
    return packets, metadata


def export_shells_czml(shells, sim=None, min_elevation_deg=20, label='Multi-shell constellation'):
    """Share stations and clock; retain each shell's native ECEF positions."""
    sim = sim or Simulation()
    packets, metadata, plane_offset = [], [], 0
    for k, config in enumerate(shells):
        shell_packets, meta = export_czml(config, sim, min_elevation_deg, include_cones=False)
        if not packets:
            packets = [p for p in shell_packets if not p.get('properties', {}).get('satellite')]
            packets[0]['name'] = label
        for packet in shell_packets:
            if not packet.get('properties', {}).get('satellite'):
                continue
            packet['id'] = f'shell{k+1}-' + packet['id']
            packet['name'] = f'{config.label} · ' + packet['name']
            packet['properties']['shell'] = {'number': k+1}
            packet['properties']['plane']['number'] += plane_offset
            packet['properties']['altitudeKm'] = {'number': config.altitude_km}
            packet['position']['interpolationAlgorithm'] = 'LAGRANGE'
            packet['position']['interpolationDegree'] = 5
            color = COLORS[k % len(COLORS)] if len(shells)>1 else COLORS[(packet['properties']['plane']['number']-1)%3]
            packet['point']['color'] = {'rgba': color}
            packet['path']['material']['solidColor']['color'] = {'rgba': color}
            packets.append(packet)
        metadata.append(meta)
        plane_offset += config.planes
    cfg = next(p for p in packets if p['id']=='configuration')
    cfg['properties']['planeCount'] = {'number': plane_offset}
    cfg['properties']['displayDescription'] = {'string': label}
    cfg['properties']['multiShell'] = {'boolean': len(shells)>1}
    return packets, {'shells': metadata, 'label': label}
