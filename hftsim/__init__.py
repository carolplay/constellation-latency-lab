"""Space/fiber latency sandbox. All geometry uses km, seconds and radians internally."""
from .config import Constellation, Physics, Simulation
from .engine import simulate, summarize

__all__ = ["Constellation", "Physics", "Simulation", "simulate", "summarize"]
