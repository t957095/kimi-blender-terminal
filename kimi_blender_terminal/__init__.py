"""
Kimi Blender Terminal — Blender Add-on.

A terminal-style assistant panel inside Blender, powered by the local Kimi CLI.
Supports autonomous multi-turn execution, viewport screenshots, and MCP-bridge
socket communication for fast, reliable tool execution.
"""

bl_info = {
    "name": "Kimi Blender Terminal",
    "author": "Thomas",
    "version": (2, 5, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Kimi",
    "description": "Assistant panel with autonomous execution, viewport screenshots, and MCP bridge",
    "category": "Interface",
    "support": "COMMUNITY",
}

modules = []


def register():
    import bpy
    from . import preferences
    from . import ui
    from . import blender_tools
    from . import integrations
    from . import blenderkit_integration
    from . import web_exporter
    from . import data_viz
    from . import session_manager
    from . import knowledge_base
    from . import mcp_bridge

    global modules
    modules = [preferences, ui]
    for mod in modules:
        mod.register()

    # Start the MCP bridge socket server
    try:
        mcp_bridge.start_server()
        print("[Kimi Blender Terminal] MCP bridge server started")
    except Exception as e:
        print(f"[Kimi Blender Terminal] MCP bridge failed to start: {e}")

    print("[Kimi Blender Terminal] Registered v2.5.0")


def unregister():
    from . import mcp_bridge

    # Stop the MCP bridge socket server
    try:
        mcp_bridge.stop_server()
        print("[Kimi Blender Terminal] MCP bridge server stopped")
    except Exception as e:
        print(f"[Kimi Blender Terminal] MCP bridge stop error: {e}")

    for mod in reversed(modules):
        mod.unregister()
    print("[Kimi Blender Terminal] Unregistered")


if __name__ == "__main__":
    register()
