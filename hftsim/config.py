from dataclasses import dataclass
from datetime import datetime, timezone
import math

C_KM_S = 299792.458
RE_KM = 6378.137  # conservative equatorial sphere for ISL occultation
MU = 398600.4418
J2 = 1.08262668e-3
OMEGA_E = 7.2921150e-5


@dataclass(frozen=True)
class Constellation:
    planes: int = 24
    sats_per_plane: int = 22
    altitude_km: float = 550.0
    inclination_deg: float = 53.0
    raan_span_deg: float = 360.0
    raan_start_deg: float = 0.0
    phase_deg: float = 0.0
    walker_f: int = 1
    eccentricity: float = 0.0
    arg_perigee_deg: float = 0.0
    j2: bool = True
    topology: str = "grid"
    label: str = "Generic 528-sat grid (synthetic)"

    def __post_init__(self):
        if self.planes < 1 or self.sats_per_plane < 1:
            raise ValueError("Positive plane and satellite counts required")
        if self.altitude_km <= 0 or not 0 <= self.eccentricity < 1:
            raise ValueError("Invalid elliptic orbit")
        if (RE_KM + self.altitude_km) * (1-self.eccentricity) <= RE_KM:
            raise ValueError("Perigee must be above the Earth")
        if not 0 <= self.inclination_deg <= 180 or not 0 < self.raan_span_deg <= 360:
            raise ValueError("Invalid inclination or RAAN span")
        if self.topology not in {"grid", "complete"}:
            raise ValueError("topology must be grid or complete")
        if self.topology == "complete" and self.count > 150:
            raise ValueError("Complete graphs limited to 150 satellites; use grid for large shells")

    @property
    def count(self):
        return self.planes * self.sats_per_plane

    @classmethod
    def bespoke(cls, **kwargs):
        defaults = dict(planes=3, sats_per_plane=6, altitude_km=1200,
                        inclination_deg=75, raan_span_deg=120,
                        label="Bespoke 18-sat candidate (unvalidated)")
        defaults.update(kwargs)
        return cls(**defaults)


@dataclass(frozen=True)
class Physics:
    atmosphere_km: float = 80.0
    min_elevation_deg: float = 20.0
    optical_constraints: bool = True
    fov_half_angle_deg: float = 80.0
    slew_limit_deg_s: float = 2.0
    wavelength_nm: float = 1550.0
    max_doppler_hz: float = 10e9  # assumed acquisition range, not vendor specification
    max_isl_range_km: float = 6000.0
    satellite_processing_us: float = 5.0
    ground_modem_ms: float = 0.5  # per ground-space leg per direction
    acquire_s: float = 20.0
    isl_acquire_s: float = 5.0
    antennas: int = 2
    routing_reconvergence_ms: float = 0.0  # configured disruption; not computational wall time
    ground_track_limit_deg_s: float = 2.0

    def __post_init__(self):
        values = (self.atmosphere_km, self.satellite_processing_us, self.ground_modem_ms,
                  self.acquire_s, self.isl_acquire_s, self.routing_reconvergence_ms)
        if any(not math.isfinite(x) or x < 0 for x in values):
            raise ValueError("Timing and clearance parameters must be finite and nonnegative")
        if not 0 <= self.min_elevation_deg < 90 or not 0 < self.fov_half_angle_deg <= 180:
            raise ValueError("Invalid elevation or FOV")
        if self.antennas not in {1, 2}:
            raise ValueError("Only one- or two-antenna access supported")
        if min(self.slew_limit_deg_s, self.wavelength_nm, self.max_doppler_hz,
               self.max_isl_range_km, self.ground_track_limit_deg_s) <= 0:
            raise ValueError("Optical limits must be positive")

    @classmethod
    def phase1(cls):
        return cls(atmosphere_km=0, optical_constraints=False, acquire_s=0, isl_acquire_s=0)


@dataclass(frozen=True)
class Simulation:
    route: str = "LD4-TOKYO"
    duration_s: float = 86400
    step_s: float = 10
    epoch: str = "2026-10-12T00:00:00+00:00"
    baseline_rtt_ms: float | None = None

    def __post_init__(self):
        if not math.isfinite(self.duration_s) or not math.isfinite(self.step_s):
            raise ValueError("Time parameters must be finite")
        if self.duration_s <= 0 or self.step_s <= 0 or self.step_s > self.duration_s:
            raise ValueError("Require 0 < step <= duration")
        dt = datetime.fromisoformat(self.epoch)
        if dt.tzinfo is None:
            raise ValueError("Epoch must include UTC offset")
        if self.baseline_rtt_ms is not None and self.baseline_rtt_ms <= 0:
            raise ValueError("Baseline RTT must be positive")

    @property
    def epoch_datetime(self):
        return datetime.fromisoformat(self.epoch).astimezone(timezone.utc)
