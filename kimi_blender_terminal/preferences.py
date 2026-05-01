"""
Addon Preferences for Kimi Blender Terminal.
"""

import bpy
import os
from bpy.props import StringProperty, IntProperty, BoolProperty, EnumProperty


class KIMI_TERMINALAddonPreferences(bpy.types.AddonPreferences):
    bl_idname = "kimi_blender_terminal"

    kimi_executable: StringProperty(
        name="Kimi CLI Executable",
        description="Path to kimi-cli or kimi executable. Leave blank to auto-detect.",
        default="",
        subtype="FILE_PATH",
    )

    timeout: IntProperty(
        name="CLI Timeout (seconds)",
        description="Max seconds to wait for a CLI response",
        default=300,
        min=30,
        max=3600,
    )

    max_tool_iterations: IntProperty(
        name="Max Tool Iterations",
        description="Maximum number of tool-call loops per user message",
        default=10,
        min=1,
        max=50,
    )

    send_scene_context: BoolProperty(
        name="Auto-send Scene Context",
        description="Include current scene summary in every prompt",
        default=True,
    )

    allow_dangerous_code: BoolProperty(
        name="Allow Dangerous Code",
        description="Remove guardrails from run_blender_python (use with caution)",
        default=False,
    )

    log_to_terminal: BoolProperty(
        name="Log to System Console",
        description="Also print logs to Blender's system console",
        default=False,
    )

    ui_theme: EnumProperty(
        name="Theme",
        items=[
            ("DARK", "Dark Terminal", "Dark terminal aesthetic"),
            ("AUTO", "Auto", "Follow Blender theme"),
        ],
        default="DARK",
    )

    sketchfab_token: StringProperty(
        name="Sketchfab API Token",
        description="Optional Sketchfab API token for downloading models",
        default="",
        subtype="PASSWORD",
    )

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text="Kimi CLI Path", icon="FILEBROWSER")
        box.prop(self, "kimi_executable")
        if not self.kimi_executable:
            box.label(text="Auto-detect will search PATH and common install locations.", icon="INFO")

        box = layout.box()
        box.label(text="Behavior", icon="PREFERENCES")
        box.prop(self, "timeout")
        box.prop(self, "max_tool_iterations")
        box.prop(self, "send_scene_context")
        box.prop(self, "allow_dangerous_code")
        box.prop(self, "log_to_terminal")

        box = layout.box()
        box.label(text="Appearance", icon="COLOR")
        box.prop(self, "ui_theme")

        box = layout.box()
        box.label(text="External Services", icon="URL")
        box.prop(self, "sketchfab_token")
        box.label(text="Sketchfab token is optional. Poly Haven works without auth.", icon="INFO")

        row = layout.row()
        row.operator("kimi_terminal.test_connection", icon="PLUGIN")


def get_prefs(context=None) -> KIMI_TERMINALAddonPreferences:
    if context is None:
        context = bpy.context
    return context.preferences.addons[__package__].preferences


classes = [KIMI_TERMINALAddonPreferences]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
