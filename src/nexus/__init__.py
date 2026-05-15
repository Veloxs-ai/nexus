"""Single entry point for the Nexus enterprise AI platform."""

from nexus.config import load_config
from nexus.platform import NexusPlatform

__all__ = ["NexusPlatform", "load_config"]

__version__ = "0.1.0"

