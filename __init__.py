"""
Kimi Blender Terminal — Blender Add-on (Root Shim).

GitHub's "Download ZIP" wraps the repository in a folder like
kimi-blender-terminal-master/. Blender looks for __init__.py at the root
of that folder. This shim adds the subfolder to sys.path and re-exports
the real addon package so the green Code button works out of the box.
"""

import sys
import os

# Make the subfolder importable as "kimi_blender_terminal"
_SHIM_DIR = os.path.dirname(os.path.abspath(__file__))
if _SHIM_DIR not in sys.path:
    sys.path.insert(0, _SHIM_DIR)

# Import and re-export the real addon
import kimi_blender_terminal as _real

bl_info = _real.bl_info


def register():
    _real.register()


def unregister():
    _real.unregister()
