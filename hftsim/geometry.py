import numpy as np
from .config import C_KM_S, RE_KM


def unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-15)


def geodetic_ecef(lat_deg, lon_deg, height_km=0):
    """WGS84 geodetic latitude, longitude and ellipsoidal height."""
    lat, lon = np.deg2rad([lat_deg, lon_deg])
    e2 = 6.69437999014e-3
    n = RE_KM / np.sqrt(1-e2*np.sin(lat)**2)
    return np.array([(n+height_km)*np.cos(lat)*np.cos(lon),
                     (n+height_km)*np.cos(lat)*np.sin(lon),
                     (n*(1-e2)+height_km)*np.sin(lat)])


def ground_up(lat_deg, lon_deg):
    lat, lon = np.deg2rad([lat_deg, lon_deg])
    return np.array([np.cos(lat)*np.cos(lon), np.cos(lat)*np.sin(lon), np.sin(lat)])


def segment_min_radius(a, b):
    """Closest point on the finite segment, not on the infinite supporting line."""
    d = b-a
    t = np.clip(-np.sum(a*d, axis=-1) / np.maximum(np.sum(d*d, axis=-1), 1e-30), 0, 1)
    return np.linalg.norm(a+t[..., None]*d, axis=-1)


def elevation_deg(sat, ground, up):
    return np.rad2deg(np.arcsin(np.clip(unit(sat-ground) @ up, -1, 1)))


def great_circle_km(a, b):
    """Mean-radius spherical approximation, not an ellipsoidal absolute bound."""
    u, v = ground_up(a['lat_deg'], a['lon_deg']), ground_up(b['lat_deg'], b['lon_deg'])
    return 6371.0088*np.arctan2(np.linalg.norm(np.cross(u, v)), np.dot(u, v))


def spherical_obstacle_bound(a, b, radius_km=6356.752314245):
    """Shortest external path around an inscribed sphere; conservative WGS84 bound.

    If direct chord is occulted, two tangent lengths plus an obstacle-surface arc.
    The polar-radius sphere is contained in WGS84, so its bound is conservative.
    """
    ra, rb = np.linalg.norm(a), np.linalg.norm(b)
    if min(ra, rb) < radius_km:
        raise ValueError("Endpoints must be outside obstacle sphere")
    angle = np.arccos(np.clip(np.dot(a, b)/(ra*rb), -1, 1))
    alpha, beta = np.arccos(radius_km/ra), np.arccos(radius_km/rb)
    if angle <= alpha+beta:
        return float(np.linalg.norm(b-a))
    return float(np.sqrt(ra*ra-radius_km**2) + np.sqrt(rb*rb-radius_km**2)
                 + radius_km*(angle-alpha-beta))


def ideal_shell_length(distance_km, height_km, elevation_deg=20):
    """Optimistic continuum shell model: ground slants plus shell arc.

    No discrete satellites, processing, PAT or coverage guarantee. If footprints
    overlap, use a midpoint relay rather than a negative shell arc.
    """
    r = RE_KM + height_km
    eps = np.deg2rad(elevation_deg)
    alpha = distance_km/RE_KM
    beta = np.arccos(RE_KM/r*np.cos(eps))-eps
    access_angle = np.minimum(beta, alpha/2)
    slant = np.sqrt(RE_KM**2+r*r-2*RE_KM*r*np.cos(access_angle))
    return 2*slant+r*np.maximum(0, alpha-2*access_angle)
