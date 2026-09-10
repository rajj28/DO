"""Perception. Nothing in this package performs a side effect; anything that reaches
outside the process takes a Gate and appears in the ledger."""
from .introspect import Sensors, probe_network            # noqa: F401
from .referents import discover as discover_referents     # noqa: F401
