"""Layout helpers for Excalidraw diagrams.

- ``place`` — single declarative placement tool (unifies role-based size
  defaults with anchor-driven positioning).
- ``tighten`` — post-generation layout tightening (grid-snap, spine alignment,
  optional gap-shrink).
"""

from .place import ROLE_DEFAULTS, place

__all__ = ["place", "ROLE_DEFAULTS"]
