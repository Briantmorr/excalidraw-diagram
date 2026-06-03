#!/usr/bin/env python3
"""Shared canvas utilities for excalidraw helpers.

Thin re-export layer over helpers/core/excalidraw_core.py for backward
compatibility with helpers that imported from this module.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.excalidraw_core import (
    detect_frames,
    get_canvas_bounds,
    get_element_bounds,
    get_frame_ids,
)

__all__ = [
    "detect_frames",
    "get_canvas_bounds",
    "get_element_bounds",
    "get_frame_ids",
]
