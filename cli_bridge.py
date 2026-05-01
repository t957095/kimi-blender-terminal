"""
Kimi Blender Terminal — CLI Bridge Wrapper

Run this script from the repo root to control Blender from the terminal.

Usage:
    python cli_bridge.py "create a red cube"
    python cli_bridge.py "make a snowy mountain" --turns 10
    python cli_bridge.py --prompt-file prompt.txt --blend myscene.blend
    python cli_bridge.py --list-tools

Requirements:
    1. Blender must be running with the Kimi Blender Terminal addon enabled.
    2. Kimi CLI must be installed and authenticated (kimi login).
"""

import sys
import os

# Ensure the package is importable
repo_root = os.path.dirname(os.path.abspath(__file__))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from kimi_blender_terminal.cli_bridge import main

if __name__ == "__main__":
    main()
