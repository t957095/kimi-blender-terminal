"""
Kimi Blender Terminal — Sleek Chat-First UI v2.1.

Design goals:
  - Chat is the hero. Everything else collapses away.
  - See thinking, code generation, and execution in real time.
  - Viewport screenshots visible inline.
  - Quick prompts for one-click common tasks.
  - Execution timeline for multi-turn autonomous tasks.
  - Minimal chrome, maximal information density.
"""

import bpy
import threading
import time
import os
from bpy.props import StringProperty, BoolProperty, IntProperty, CollectionProperty
from bpy.types import Panel, Operator, PropertyGroup

from . import preferences
from . import kimi_client
from . import conversation_agent
from . import scene_context
from . import session_manager as sm
from . import mcp_bridge

_session_mgr = sm.SessionManager()

# ── Property Groups ──

class KIMI_TERMINAL_HistoryItem(PropertyGroup):
    role: StringProperty()          # user | assistant | system
    content: StringProperty()
    thinking: StringProperty()
    code: StringProperty()          # generated code for this turn
    output: StringProperty()        # execution output
    status: StringProperty()        # ok | error | pending
    screenshot_path: StringProperty()  # path to viewport screenshot
    timestamp: StringProperty()
    turn_number: IntProperty(default=0)


class KIMI_TERMINAL_SessionItem(PropertyGroup):
    uuid: StringProperty()
    name: StringProperty()
    updated: StringProperty()


class KIMI_TERMINAL_ToolLogItem(PropertyGroup):
    name: StringProperty()
    status: StringProperty()
    detail: StringProperty()
    elapsed_ms: IntProperty()


# ── Global Agent Singleton ──
_agent = None
_agent_lock = threading.Lock()

def get_agent() -> conversation_agent.ConversationAgent:
    global _agent
    with _agent_lock:
        if _agent is None:
            prefs = preferences.get_prefs()
            exe = prefs.kimi_executable if prefs.kimi_executable else None
            _agent = conversation_agent.ConversationAgent(
                client=kimi_client.KimiClient(executable=exe, timeout=prefs.timeout)
            )
        return _agent


def reset_agent():
    global _agent
    with _agent_lock:
        if _agent:
            _agent.abort()
            _agent = None


# ── Operators ──

class KIMI_TERMINAL_OT_TestConnection(Operator):
    bl_idname = "kimi_terminal.test_connection"
    bl_label = "Test"
    bl_description = "Test connection to Kimi CLI"
    bl_options = {"REGISTER"}

    def execute(self, context):
        scene = context.scene
        scene.kimi_terminal_status = "TESTING"
        exe = preferences.get_prefs().kimi_executable or kimi_client.find_kimi_executable()
        if not exe:
            self.report({"ERROR"}, "kimi-cli not found. Set path in Preferences > Add-ons > Kimi Blender Terminal")
            scene.kimi_terminal_status = "ERROR"
            return {"CANCELLED"}

        def worker():
            client = kimi_client.KimiClient(executable=exe)
            result = client.test_connection()
            def apply():
                if result.get("ok"):
                    scene.kimi_terminal_status = "CONNECTED"
                    scene.kimi_terminal_last_message = f"Connected. Session: {result.get('session_id', 'new')[:16]}..."
                else:
                    scene.kimi_terminal_status = "ERROR"
                    scene.kimi_terminal_last_message = result.get("error", "Unknown error")
            bpy.app.timers.register(apply, first_interval=0.0)

        threading.Thread(target=worker, daemon=True).start()
        return {"FINISHED"}


class KIMI_TERMINAL_OT_Send(Operator):
    bl_idname = "kimi_terminal.send"
    bl_label = "Send"
    bl_options = {"REGISTER"}

    def execute(self, context):
        scene = context.scene
        text = scene.kimi_terminal_input.strip()
        if not text:
            return {"CANCELLED"}
        if scene.kimi_terminal_status in {"THINKING", "EXECUTING"}:
            self.report({"WARNING"}, "Already running. Wait or press Stop.")
            return {"CANCELLED"}

        # Prepend attached file reference if present
        attached = scene.kimi_terminal_attached_file.strip()
        if attached and os.path.isfile(attached):
            text = f"[Attached file: {attached}]\n{text}"
            scene.kimi_terminal_attached_file = ""

        # Add user message
        item = scene.kimi_terminal_history.add()
        item.role = "user"
        item.content = text
        item.timestamp = time.strftime("%H:%M:%S")
        scene.kimi_terminal_input = ""

        # Reset live state
        scene.kimi_terminal_status = "THINKING"
        scene.kimi_terminal_live_thinking = ""
        scene.kimi_terminal_live_code = ""
        scene.kimi_terminal_live_output = ""
        scene.kimi_terminal_live_status = "THINKING"
        scene.kimi_terminal_tool_log.clear()
        scene.kimi_terminal_current_turn = 0
        scene.kimi_terminal_total_turns = scene.kimi_terminal_max_autonomous_turns

        agent = get_agent()
        agent.max_tool_iterations = preferences.get_prefs().max_tool_iterations
        agent.max_autonomous_turns = scene.kimi_terminal_max_autonomous_turns
        agent.use_mcp_bridge = scene.kimi_terminal_use_mcp_bridge
        agent.use_screenshots = scene.kimi_terminal_use_screenshots

        def on_status(status):
            def apply():
                scene.kimi_terminal_status = status
                scene.kimi_terminal_live_status = status
            bpy.app.timers.register(apply, first_interval=0.0)

        def on_log(line):
            def apply():
                scene.kimi_terminal_last_message = line
                current = scene.kimi_terminal_live_output
                scene.kimi_terminal_live_output = (current + "\n" + line).strip()[-2000:]
            bpy.app.timers.register(apply, first_interval=0.0)

        def on_thinking(think_text):
            def apply():
                scene.kimi_terminal_live_thinking = think_text
            bpy.app.timers.register(apply, first_interval=0.0)

        def on_code(code_text):
            def apply():
                scene.kimi_terminal_live_code = code_text
            bpy.app.timers.register(apply, first_interval=0.0)

        def on_turn(current, total):
            def apply():
                scene.kimi_terminal_current_turn = current
                scene.kimi_terminal_total_turns = total
                scene.kimi_terminal_progress_dummy = int((current / max(total, 1)) * 100)
            bpy.app.timers.register(apply, first_interval=0.0)

        def on_done(result):
            def apply():
                scene.kimi_terminal_status = result.get("status", "DONE")
                scene.kimi_terminal_live_status = result.get("status", "DONE")
                turns = result.get("turns_executed", 1)

                # Build assistant history item
                a_item = scene.kimi_terminal_history.add()
                a_item.role = "assistant"
                a_item.content = result.get("text", "")
                a_item.thinking = result.get("thinking", "")
                a_item.turn_number = turns
                a_item.timestamp = time.strftime("%H:%M:%S")

                # Attach code/output from the turn
                code_blocks = result.get("code_blocks", [])
                if code_blocks:
                    a_item.code = code_blocks[-1].get("code", "")
                    res = code_blocks[-1].get("result", {})
                    out = res.get("stdout", "")
                    err = res.get("stderr", "")
                    msg = res.get("message", "")
                    a_item.output = "\n".join(filter(None, [out, err, msg]))[:800]
                    a_item.status = res.get("status", "ok")

                    # Populate tool log
                    for cb in code_blocks:
                        tli = scene.kimi_terminal_tool_log.add()
                        res2 = cb.get("result", {})
                        tli.name = f"Code ({len(cb.get('code', ''))} chars)"
                        tli.status = "success" if res2.get("status") == "success" else "error"
                        detail = res2.get("stdout", "") or res2.get("message", "")
                        tli.detail = detail[:240]
                        tli.elapsed_ms = 0

                # Try to load screenshot if available
                _try_load_screenshot(a_item)

                if result.get("error"):
                    err_item = scene.kimi_terminal_history.add()
                    err_item.role = "system"
                    err_item.content = f"Error: {result['error']}"
                    err_item.timestamp = time.strftime("%H:%M:%S")
                    scene.kimi_terminal_last_message = f"Error: {result['error']}"
                else:
                    scene.kimi_terminal_last_message = f"Done ({turns} turn{'s' if turns > 1 else ''})"

                # Prune
                while len(scene.kimi_terminal_history) > 200:
                    scene.kimi_terminal_history.remove(0)

                # Clear live state
                scene.kimi_terminal_live_thinking = ""
                scene.kimi_terminal_live_code = ""
                scene.kimi_terminal_live_output = ""
                scene.kimi_terminal_current_turn = 0
            bpy.app.timers.register(apply, first_interval=0.0)

        def worker():
            try:
                agent.run_turn(text, on_status=on_status, on_log=on_log,
                              on_thinking=on_thinking, on_code=on_code, on_turn=on_turn, on_done=on_done)
            except Exception as e:
                def apply():
                    scene.kimi_terminal_status = "ERROR"
                    scene.kimi_terminal_live_status = "ERROR"
                    err_item = scene.kimi_terminal_history.add()
                    err_item.role = "system"
                    err_item.content = f"Exception: {e}"
                    err_item.timestamp = time.strftime("%H:%M:%S")
                bpy.app.timers.register(apply, first_interval=0.0)

        threading.Thread(target=worker, daemon=True).start()
        return {"FINISHED"}


class KIMI_TERMINAL_OT_SelectFile(Operator):
    bl_idname = "kimi_terminal.select_file"
    bl_label = "Attach File"
    bl_description = "Select an image or file to include with the prompt"
    bl_options = {"REGISTER"}

    filepath: StringProperty(subtype="FILE_PATH")

    def execute(self, context):
        context.scene.kimi_terminal_attached_file = self.filepath
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class KIMI_TERMINAL_OT_ClearFile(Operator):
    bl_idname = "kimi_terminal.clear_file"
    bl_label = "Clear"
    bl_description = "Remove attached file"
    bl_options = {"REGISTER"}

    def execute(self, context):
        context.scene.kimi_terminal_attached_file = ""
        return {"FINISHED"}


class KIMI_TERMINAL_OT_ClearKB(Operator):
    bl_idname = "kimi_terminal.clear_kb"
    bl_label = "Clear Knowledge Base"
    bl_description = "Delete all learned patterns and preferences"
    bl_options = {"REGISTER"}

    def execute(self, context):
        from . import knowledge_base as kb
        kb.clear_knowledge_base()
        self.report({"INFO"}, "Knowledge base cleared.")
        return {"FINISHED"}


class KIMI_TERMINAL_OT_SavePreference(Operator):
    bl_idname = "kimi_terminal.save_preference"
    bl_label = "Save Preference"
    bl_description = "Store a user preference for future sessions"
    bl_options = {"REGISTER"}

    key: StringProperty(name="Key", default="style")
    value: StringProperty(name="Value", default="")

    def execute(self, context):
        from . import knowledge_base as kb
        if self.value:
            kb.update_user_profile(self.key, self.value)
            self.report({"INFO"}, f"Saved: {self.key} = {self.value}")
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=300)


class KIMI_TERMINAL_OT_Stop(Operator):
    bl_idname = "kimi_terminal.stop"
    bl_label = "Stop"
    bl_description = "Abort the current operation"
    bl_options = {"REGISTER"}

    def execute(self, context):
        agent = get_agent()
        agent.abort()
        context.scene.kimi_terminal_status = "ABORTED"
        context.scene.kimi_terminal_live_status = "ABORTED"
        self.report({"INFO"}, "Stopped.")
        return {"FINISHED"}


class KIMI_TERMINAL_OT_Clear(Operator):
    bl_idname = "kimi_terminal.clear"
    bl_label = "Clear"
    bl_description = "Clear chat history"
    bl_options = {"REGISTER"}

    def execute(self, context):
        scene = context.scene
        scene.kimi_terminal_history.clear()
        scene.kimi_terminal_tool_log.clear()
        scene.kimi_terminal_last_message = ""
        scene.kimi_terminal_live_thinking = ""
        scene.kimi_terminal_live_code = ""
        scene.kimi_terminal_live_output = ""
        scene.kimi_terminal_status = "IDLE"
        scene.kimi_terminal_live_status = "IDLE"
        scene.kimi_terminal_current_turn = 0
        reset_agent()
        _cleanup_screenshots()
        return {"FINISHED"}


class KIMI_TERMINAL_OT_RefreshScene(Operator):
    bl_idname = "kimi_terminal.refresh_scene"
    bl_label = "Refresh"
    bl_description = "Refresh scene context"
    bl_options = {"REGISTER"}

    def execute(self, context):
        scene_context.SceneContext.invalidate()
        summary = scene_context.SceneContext.get_text_summary(force_refresh=True)
        context.scene.kimi_terminal_scene_summary = summary
        self.report({"INFO"}, "Scene refreshed")
        return {"FINISHED"}


class KIMI_TERMINAL_OT_CopyCode(Operator):
    bl_idname = "kimi_terminal.copy_code"
    bl_label = "Copy"
    bl_description = "Copy code to clipboard"
    bl_options = {"REGISTER"}

    code: StringProperty()

    def execute(self, context):
        context.window_manager.clipboard = self.code
        self.report({"INFO"}, "Code copied to clipboard")
        return {"FINISHED"}


class KIMI_TERMINAL_OT_CopyMessage(Operator):
    bl_idname = "kimi_terminal.copy_message"
    bl_label = "Copy Message"
    bl_description = "Copy this message text to clipboard"
    bl_options = {"REGISTER"}

    text: StringProperty()

    def execute(self, context):
        context.window_manager.clipboard = self.text
        self.report({"INFO"}, "Message copied to clipboard")
        return {"FINISHED"}


class KIMI_TERMINAL_OT_CopyAll(Operator):
    bl_idname = "kimi_terminal.copy_all"
    bl_label = "Copy All"
    bl_description = "Copy entire chat history to clipboard"
    bl_options = {"REGISTER"}

    def execute(self, context):
        lines = []
        for msg in context.scene.kimi_terminal_history:
            if msg.role == "user":
                lines.append(f"[USER] {msg.content}")
            elif msg.role == "assistant":
                lines.append(f"[KIMI] {msg.content}")
                if msg.thinking:
                    lines.append(f"[THINKING] {msg.thinking}")
                if msg.code:
                    lines.append(f"[CODE]\n{msg.code}")
                if msg.output:
                    lines.append(f"[OUTPUT] {msg.output}")
            elif msg.role == "system":
                lines.append(f"[SYSTEM] {msg.content}")
        text = "\n\n".join(lines)
        context.window_manager.clipboard = text
        self.report({"INFO"}, f"Copied {len(lines)} messages to clipboard")
        return {"FINISHED"}


class KIMI_TERMINAL_OT_RunCode(Operator):
    bl_idname = "kimi_terminal.run_code"
    bl_label = "Run"
    bl_description = "Run this code block"
    bl_options = {"REGISTER", "UNDO"}

    code: StringProperty()

    def execute(self, context):
        from . import executor, utils
        try:
            result = utils.run_in_main_thread(
                executor.execute_blender_python, self.code,
                allow_dangerous=False, timeout=30.0
            )
            msg = result.get("stdout", "") or result.get("message", "Done")
            if result.get("status") == "error":
                self.report({"ERROR"}, f"Error: {msg}")
            else:
                self.report({"INFO"}, f"OK: {msg[:200]}")
        except Exception as e:
            self.report({"ERROR"}, str(e))
        return {"FINISHED"}


class KIMI_TERMINAL_OT_ToggleThinking(Operator):
    bl_idname = "kimi_terminal.toggle_thinking"
    bl_label = "Thinking"
    bl_description = "Toggle thinking visibility"
    bl_options = {"REGISTER"}

    index: IntProperty()

    def execute(self, context):
        # Toggle thinking visibility by storing in a set-like string
        scene = context.scene
        key = f"{self.index}"
        current = set(scene.kimi_terminal_expanded_thinking.split(",")) if scene.kimi_terminal_expanded_thinking else set()
        if key in current:
            current.discard(key)
        else:
            current.add(key)
        scene.kimi_terminal_expanded_thinking = ",".join(current)
        return {"FINISHED"}


# ── Session Operators ──

def _refresh_session_list(scene):
    scene.kimi_terminal_sessions.clear()
    active = _session_mgr.active_id()
    for s in _session_mgr.list_sessions():
        item = scene.kimi_terminal_sessions.add()
        item.uuid = s["uuid"]
        item.name = s["name"]
        item.updated = time.strftime("%Y-%m-%d %H:%M", time.localtime(s.get("updated_at", 0)))
    scene.kimi_terminal_active_session = active or ""


class KIMI_TERMINAL_OT_NewSession(Operator):
    bl_idname = "kimi_terminal.new_session"
    bl_label = "New"
    bl_description = "Start a new session"
    bl_options = {"REGISTER"}

    def execute(self, context):
        scene = context.scene
        reset_agent()
        scene.kimi_terminal_history.clear()
        scene.kimi_terminal_tool_log.clear()
        sid = _session_mgr.create(name=f"Session {len(_session_mgr.list_sessions()) + 1}")
        _refresh_session_list(scene)
        scene.kimi_terminal_last_message = f"New session: {sid[:8]}..."
        scene.kimi_terminal_status = "IDLE"
        return {"FINISHED"}


class KIMI_TERMINAL_OT_SaveSession(Operator):
    bl_idname = "kimi_terminal.save_session"
    bl_label = "Save"
    bl_description = "Save current session"
    bl_options = {"REGISTER"}

    def execute(self, context):
        scene = context.scene
        agent = get_agent()
        sid = _session_mgr.active_id()
        if not sid:
            sid = _session_mgr.create(name=scene.kimi_terminal_session_name or "Untitled")
        history = [{"role": h.role, "content": h.content} for h in scene.kimi_terminal_history]
        _session_mgr.save(
            sid, history=history,
            kimi_session_id=agent.client.session_id or "",
            blender_file=bpy.data.filepath,
        )
        _refresh_session_list(scene)
        self.report({"INFO"}, "Session saved")
        return {"FINISHED"}


class KIMI_TERMINAL_OT_LoadSession(Operator):
    bl_idname = "kimi_terminal.load_session"
    bl_label = "Load"
    bl_description = "Load a saved session"
    bl_options = {"REGISTER"}

    session_uuid: StringProperty()

    def execute(self, context):
        scene = context.scene
        s = _session_mgr.load(self.session_uuid)
        if not s:
            self.report({"ERROR"}, "Session not found")
            return {"CANCELLED"}
        reset_agent()
        agent = get_agent()
        agent.client.session_id = s.get("kimi_session_id", "")
        scene.kimi_terminal_history.clear()
        scene.kimi_terminal_tool_log.clear()
        for entry in s.get("history", []):
            item = scene.kimi_terminal_history.add()
            item.role = entry.get("role", "")
            item.content = entry.get("content", "")
            item.timestamp = time.strftime("%H:%M:%S")
        scene.kimi_terminal_session_name = s.get("name", "")
        scene.kimi_terminal_status = "IDLE"
        _refresh_session_list(scene)
        self.report({"INFO"}, f"Loaded: {s.get('name')}")
        return {"FINISHED"}


class KIMI_TERMINAL_OT_DeleteSession(Operator):
    bl_idname = "kimi_terminal.delete_session"
    bl_label = ""
    bl_description = "Delete session"
    bl_options = {"REGISTER"}

    session_uuid: StringProperty()

    def execute(self, context):
        _session_mgr.delete(self.session_uuid)
        _refresh_session_list(context.scene)
        return {"FINISHED"}


# ── Screenshot Helpers ──

SCREENSHOT_IMG_NAME = "_kimi_terminal_screenshot"

def _cleanup_screenshots():
    """Remove old screenshot images from bpy.data.images."""
    for img in list(bpy.data.images):
        if img.name.startswith(SCREENSHOT_IMG_NAME):
            bpy.data.images.remove(img)


def _try_load_screenshot(history_item):
    """Attempt to load the latest viewport screenshot into the history item."""
    import tempfile
    # The MCP bridge saves screenshots to temp files. We look for the most recent PNG.
    temp_dir = tempfile.gettempdir()
    pngs = [f for f in os.listdir(temp_dir) if f.endswith(".png") and "blender_screenshot" in f]
    if not pngs:
        return
    # Get most recent
    pngs.sort(key=lambda f: os.path.getmtime(os.path.join(temp_dir, f)), reverse=True)
    latest = os.path.join(temp_dir, pngs[0])
    history_item.screenshot_path = latest


def _get_screenshot_icon_id(path):
    """Load image and return its icon_id for display in UI."""
    if not path or not os.path.exists(path):
        return 0
    img_name = SCREENSHOT_IMG_NAME + "_" + str(hash(path))[:8]
    if img_name in bpy.data.images:
        img = bpy.data.images[img_name]
    else:
        try:
            img = bpy.data.images.load(path)
            img.name = img_name
        except:
            return 0
    # Ensure preview exists
    if not img.preview:
        img.preview_ensure()
    return img.preview.icon_id if img.preview else 0


# ── Panel ──

class KIMI_TERMINAL_PT_Panel(Panel):
    bl_label = "Kimi"
    bl_idname = "KIMI_TERMINAL_PT_Panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Kimi"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        prefs = preferences.get_prefs(context)
        status = scene.kimi_terminal_status

        # ═══════════════════════════════════════════════════════════════
        # 1. STATUS BAR — minimal, neutral
        # ═══════════════════════════════════════════════════════════════
        status_cfg = {
            "IDLE":        ("Ready",       "CHECKMARK"),
            "CONNECTED":   ("Connected",   "CHECKMARK"),
            "TESTING":     ("Testing...",  "QUESTION"),
            "THINKING":    ("Thinking...", "TEMP"),
            "EXECUTING":   ("Working...",  "PLAY"),
            "DONE":        ("Done",        "CHECKMARK"),
            "ERROR":       ("Error",       "ERROR"),
            "ABORTED":     ("Stopped",     "CANCEL"),
        }
        label, icon = status_cfg.get(status, (status, "INFO"))

        row = layout.row(align=True)
        row.scale_y = 0.85
        if status == "ERROR":
            row.alert = True
        row.label(text=label, icon=icon)
        row.separator()
        if status in {"THINKING", "EXECUTING"}:
            row.operator("kimi_terminal.stop", text="", icon="PAUSE", emboss=False)
        row.operator("kimi_terminal.test_connection", text="", icon="PLUGIN", emboss=False)

        # ═══════════════════════════════════════════════════════════════
        # 2. CHAT HISTORY — message cards
        # ═══════════════════════════════════════════════════════════════
        history = scene.kimi_terminal_history
        start = max(0, len(history) - scene.kimi_terminal_max_visible_messages)
        expanded = set(scene.kimi_terminal_expanded_thinking.split(",")) if scene.kimi_terminal_expanded_thinking else set()

        for i in range(start, len(history)):
            msg = history[i]
            idx = str(i)

            if msg.role == "user":
                box = layout.box()
                row = box.row()
                row.alignment = "RIGHT"
                row.label(text=f">>> {msg.content[:100]}", icon="USER")
                if msg.timestamp:
                    row2 = box.row()
                    row2.alignment = "RIGHT"
                    row2.active = False
                    row2.label(text=msg.timestamp)

            elif msg.role == "assistant":
                box = layout.box()

                # Header
                row = box.row(align=True)
                row.label(text="Kimi", icon="INFO")
                if msg.turn_number > 1:
                    row.label(text=f"  {msg.turn_number} turns", icon="LOOP_BACK")
                if msg.timestamp:
                    row.alignment = "RIGHT"
                    row.label(text=msg.timestamp)
                # Copy message button
                copy_op = row.operator("kimi_terminal.copy_message", text="", icon="COPYDOWN", emboss=False)
                copy_op.text = msg.content or ""

                # Text content
                if msg.content:
                    col = box.column(align=True)
                    col.scale_y = 0.85
                    for para in msg.content.split("\n"):
                        if para.strip():
                            col.label(text=para[:120])

                # Screenshot thumbnail
                if msg.screenshot_path and scene.kimi_terminal_show_code:
                    icon_id = _get_screenshot_icon_id(msg.screenshot_path)
                    if icon_id:
                        sub = box.box()
                        sub.scale_y = 0.9
                        sub.label(text="Viewport", icon="RESTRICT_VIEW_OFF")
                        row = sub.row()
                        row.template_icon(icon_id, scale=6.0)

                # Thinking (collapsible)
                if msg.thinking and scene.kimi_terminal_show_thinking:
                    sub = box.box()
                    sub.scale_y = 0.85
                    row = sub.row(align=True)
                    is_expanded = idx in expanded
                    row.operator("kimi_terminal.toggle_thinking", text="",
                                icon="DOWNARROW_HLT" if is_expanded else "RIGHTARROW",
                                emboss=False).index = i
                    row.label(text="Thinking", icon="INFO")
                    if is_expanded:
                        col = sub.column(align=True)
                        col.active = False
                        for line in msg.thinking.split("\n")[:10]:
                            if line.strip():
                                col.label(text=f"  {line[:56]}")

                # Generated code block
                if msg.code and scene.kimi_terminal_show_code:
                    sub = box.box()
                    sub.scale_y = 0.9
                    row = sub.row(align=True)
                    row.label(text="Code", icon="SCRIPT")
                    row2 = sub.row(align=True)
                    run_op = row2.operator("kimi_terminal.run_code", text="Run", icon="PLAY")
                    run_op.code = msg.code
                    copy_op = row2.operator("kimi_terminal.copy_code", text="Copy", icon="COPYDOWN")
                    copy_op.code = msg.code

                    col = sub.column(align=True)
                    for line in msg.code.split("\n")[:10]:
                        row = col.row()
                        row.scale_y = 0.75
                        row.label(text=f"  {line[:54]}")
                    if len(msg.code.split("\n")) > 10:
                        col.label(text=f"  ... ({len(msg.code.split(chr(10)))} lines)", icon="DOT")

                # Execution output
                if msg.output:
                    sub = box.box()
                    sub.scale_y = 0.8
                    icon = "CHECKMARK" if msg.status == "success" else "ERROR"
                    row = sub.row()
                    row.label(text=f"  {'OK' if msg.status == 'success' else 'FAIL'}  Result", icon=icon)
                    col = sub.column(align=True)
                    for line in msg.output.split("\n")[:6]:
                        if line.strip():
                            row = col.row()
                            row.scale_y = 0.75
                            row.label(text=f"    {line[:52]}")

            elif msg.role == "system":
                # Error / system message — red alert only here
                box = layout.box()
                box.alert = True
                row = box.row()
                row.label(text=msg.content[:120], icon="ERROR")

        # Empty state
        if len(history) == 0 and status == "IDLE":
            box = layout.box()
            col = box.column(align=True)
            col.scale_y = 0.9
            col.label(text="Ask me anything...", icon="INFO")

        # ═══════════════════════════════════════════════════════════════
        # 3. INPUT BAR
        # ═══════════════════════════════════════════════════════════════
        layout.separator(factor=0.3)
        box = layout.box()
        row = box.row(align=True)
        row.scale_y = 1.3
        row.prop(scene, "kimi_terminal_input", text="")
        if status in {"THINKING", "EXECUTING"}:
            row.operator("kimi_terminal.stop", text="", icon="PAUSE")
        else:
            row.operator("kimi_terminal.send", text="", icon="PLAY")

        # ═══════════════════════════════════════════════════════════════
        # 4. FILE ATTACHMENT
        # ═══════════════════════════════════════════════════════════════
        if status == "IDLE":
            row = layout.row(align=True)
            row.scale_y = 0.8
            if scene.kimi_terminal_attached_file:
                row.label(text=f"Attached: {os.path.basename(scene.kimi_terminal_attached_file)}", icon="FILE_IMAGE")
                row.operator("kimi_terminal.clear_file", text="", icon="X")
            else:
                row.operator("kimi_terminal.select_file", text="Attach Image/File", icon="FILE_IMAGE")

        # ═══════════════════════════════════════════════════════════════
        # 5. FOOTER — view toggles + MCP status
        # ═══════════════════════════════════════════════════════════════
        row = layout.row(align=True)
        row.scale_y = 0.75
        row.alignment = "CENTER"
        row.operator("kimi_terminal.clear", text="Clear", icon="TRASH", emboss=False)
        row.operator("kimi_terminal.copy_all", text="Copy All", icon="COPYDOWN", emboss=False)
        row.prop(scene, "kimi_terminal_show_thinking",
                 text="Think", icon="INFO", emboss=False, toggle=True)
        row.prop(scene, "kimi_terminal_show_code",
                 text="Code", icon="SCRIPT", emboss=False, toggle=True)
        if mcp_bridge.is_running():
            row.label(text="MCP", icon="CHECKMARK")
        else:
            row.label(text="MCP", icon="ERROR")

        # ═══════════════════════════════════════════════════════════════
        # 6. SETTINGS — independent collapsible panel at bottom
        # ═══════════════════════════════════════════════════════════════
        layout.separator(factor=0.5)
        box = layout.box()
        box.scale_y = 0.9
        row = box.row()
        row.prop(scene, "kimi_terminal_show_settings",
                 text="Settings", icon="PREFERENCES", emboss=False, toggle=True)

        if scene.kimi_terminal_show_settings:
            # Sessions
            sub = box.column(align=True)
            sub.separator(factor=0.3)
            row = sub.row(align=True)
            row.operator("kimi_terminal.new_session", text="New", icon="FILE_NEW")
            row.operator("kimi_terminal.save_session", text="Save", icon="FILE_TICK")

            if scene.kimi_terminal_sessions:
                for s in scene.kimi_terminal_sessions:
                    row = sub.row(align=True)
                    row.label(text=f"  {s.name}", icon="DOT")
                    op = row.operator("kimi_terminal.load_session", text="Load", icon="IMPORT")
                    op.session_uuid = s.uuid
                    op = row.operator("kimi_terminal.delete_session", text="", icon="X")
                    op.session_uuid = s.uuid
            else:
                sub.label(text="  No saved sessions", icon="INFO")

            # Scene Context
            sub.separator(factor=0.3)
            row = sub.row(align=True)
            row.prop(scene, "kimi_terminal_show_scene",
                     text="Scene Context", icon="SCENE_DATA", emboss=False, toggle=True)
            if scene.kimi_terminal_show_scene:
                col = sub.column(align=True)
                for line in scene.kimi_terminal_scene_summary.split("\n"):
                    if line.strip():
                        col.label(text=f"  {line[:55]}")
                row2 = sub.row(align=True)
                row2.operator("kimi_terminal.refresh_scene", text="Refresh", icon="FILE_REFRESH")

            # Execution Engine
            sub.separator(factor=0.3)
            sub.label(text="Execution Engine", icon="MODIFIER")
            row = sub.row(align=True)
            row.prop(scene, "kimi_terminal_use_mcp_bridge", text="MCP Bridge", toggle=True)
            row.prop(scene, "kimi_terminal_use_screenshots", text="Screenshots", toggle=True)
            sub.prop(scene, "kimi_terminal_max_autonomous_turns", text="Max Turns")
            sub.label(text="Higher turns = longer tasks, more tokens.", icon="INFO")

            # Knowledge Base
            sub.separator(factor=0.3)
            sub.label(text="Knowledge Base", icon="BOOKMARKS")
            from . import knowledge_base as kb
            stats = kb.get_stats()
            sub.label(text=f"  Learned: {stats['count']} entries, {stats['patterns']} patterns", icon="DOT")
            if stats['corrections']:
                sub.label(text=f"  Corrections applied: {stats['corrections']}", icon="CHECKMARK")
            row = sub.row(align=True)
            row.operator("kimi_terminal.clear_kb", text="Clear Memory", icon="TRASH")
            row.operator("kimi_terminal.save_preference", text="Save Preference", icon="PREFERENCES")

        # ═══════════════════════════════════════════════════════════════
        # 7. LIVE WORKING AREA — real-time execution display
        # ═══════════════════════════════════════════════════════════════
        if status in {"THINKING", "EXECUTING"}:
            box = layout.box()
            row = box.row()
            row.label(text=f"Working...  turn {scene.kimi_terminal_current_turn + 1}/{scene.kimi_terminal_total_turns}", icon="TEMP")

            progress = 0.0
            if scene.kimi_terminal_total_turns > 0:
                progress = (scene.kimi_terminal_current_turn + 1) / scene.kimi_terminal_total_turns
            row = box.row()
            row.prop(scene, "kimi_terminal_progress_dummy", text="", slider=True)

            if scene.kimi_terminal_live_thinking:
                sub = box.column(align=True)
                sub.active = False
                for line in scene.kimi_terminal_live_thinking.split("\n")[:4]:
                    if line.strip():
                        sub.label(text=f"  {line[:60]}")

            if scene.kimi_terminal_live_code:
                sub = box.column(align=True)
                sub.separator(factor=0.3)
                sub.label(text="Generated code:", icon="SCRIPT")
                code_lines = scene.kimi_terminal_live_code.split("\n")[:6]
                for line in code_lines:
                    row = sub.row()
                    row.scale_y = 0.75
                    row.label(text=f"  {line[:58]}")
                if len(scene.kimi_terminal_live_code.split("\n")) > 6:
                    sub.label(text="  ...", icon="DOT")

            if scene.kimi_terminal_live_output:
                sub = box.column(align=True)
                sub.separator(factor=0.3)
                sub.label(text="Output:", icon="CONSOLE")
                for line in scene.kimi_terminal_live_output.split("\n")[-4:]:
                    if line.strip():
                        row = sub.row()
                        row.scale_y = 0.75
                        row.label(text=f"  {line[:58]}")


# ── Register ──

classes = [
    KIMI_TERMINAL_HistoryItem,
    KIMI_TERMINAL_ToolLogItem,
    KIMI_TERMINAL_SessionItem,
    KIMI_TERMINAL_OT_TestConnection,
    KIMI_TERMINAL_OT_Send,
    KIMI_TERMINAL_OT_SelectFile,
    KIMI_TERMINAL_OT_ClearFile,
    KIMI_TERMINAL_OT_Stop,
    KIMI_TERMINAL_OT_Clear,
    KIMI_TERMINAL_OT_RefreshScene,
    KIMI_TERMINAL_OT_CopyCode,
    KIMI_TERMINAL_OT_CopyMessage,
    KIMI_TERMINAL_OT_CopyAll,
    KIMI_TERMINAL_OT_RunCode,
    KIMI_TERMINAL_OT_ToggleThinking,
    KIMI_TERMINAL_OT_NewSession,
    KIMI_TERMINAL_OT_SaveSession,
    KIMI_TERMINAL_OT_LoadSession,
    KIMI_TERMINAL_OT_DeleteSession,
    KIMI_TERMINAL_OT_ClearKB,
    KIMI_TERMINAL_OT_SavePreference,
    KIMI_TERMINAL_PT_Panel,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.kimi_terminal_input = StringProperty(name="Input", default="", description="Message to send")
    bpy.types.Scene.kimi_terminal_status = StringProperty(name="Status", default="IDLE")
    bpy.types.Scene.kimi_terminal_last_message = StringProperty(name="Last Message", default="")
    bpy.types.Scene.kimi_terminal_scene_summary = StringProperty(name="Scene Summary", default="Press Refresh to load scene context")

    bpy.types.Scene.kimi_terminal_show_settings = BoolProperty(name="Show Settings", default=False)
    bpy.types.Scene.kimi_terminal_show_scene = BoolProperty(name="Show Scene", default=False)
    bpy.types.Scene.kimi_terminal_show_thinking = BoolProperty(name="Show Thinking", default=True)
    bpy.types.Scene.kimi_terminal_show_code = BoolProperty(name="Show Code", default=True)

    bpy.types.Scene.kimi_terminal_history = CollectionProperty(type=KIMI_TERMINAL_HistoryItem)
    bpy.types.Scene.kimi_terminal_tool_log = CollectionProperty(type=KIMI_TERMINAL_ToolLogItem)
    bpy.types.Scene.kimi_terminal_sessions = CollectionProperty(type=KIMI_TERMINAL_SessionItem)
    bpy.types.Scene.kimi_terminal_session_name = StringProperty(default="")
    bpy.types.Scene.kimi_terminal_active_session = StringProperty(default="")

    # Live working state
    bpy.types.Scene.kimi_terminal_live_thinking = StringProperty(default="")
    bpy.types.Scene.kimi_terminal_live_code = StringProperty(default="")
    bpy.types.Scene.kimi_terminal_live_output = StringProperty(default="")
    bpy.types.Scene.kimi_terminal_live_status = StringProperty(default="IDLE")
    bpy.types.Scene.kimi_terminal_current_turn = IntProperty(default=0)
    bpy.types.Scene.kimi_terminal_total_turns = IntProperty(default=5)
    bpy.types.Scene.kimi_terminal_max_visible_messages = IntProperty(default=20, min=5, max=100)
    bpy.types.Scene.kimi_terminal_max_autonomous_turns = IntProperty(
        name="Max Autonomous Turns", default=10, min=1, max=50,
        description="How many code→execute loops per prompt (enables long tasks)"
    )
    bpy.types.Scene.kimi_terminal_attached_file = StringProperty(
        name="Attached File", default="", subtype="FILE_PATH",
        description="Image or file to include with the next prompt"
    )
    bpy.types.Scene.kimi_terminal_use_mcp_bridge = BoolProperty(
        name="Use MCP Bridge", default=True,
        description="Execute via socket server (faster, supports screenshots)"
    )
    bpy.types.Scene.kimi_terminal_use_screenshots = BoolProperty(
        name="Viewport Screenshots", default=True,
        description="Capture viewport after each execution for visual feedback"
    )
    bpy.types.Scene.kimi_terminal_expanded_thinking = StringProperty(default="")
    # Dummy progress property for visual slider
    bpy.types.Scene.kimi_terminal_progress_dummy = IntProperty(
        name="Progress", default=0, min=0, max=100, subtype="PERCENTAGE"
    )


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.kimi_terminal_input
    del bpy.types.Scene.kimi_terminal_status
    del bpy.types.Scene.kimi_terminal_last_message
    del bpy.types.Scene.kimi_terminal_scene_summary
    del bpy.types.Scene.kimi_terminal_show_settings
    del bpy.types.Scene.kimi_terminal_show_scene
    del bpy.types.Scene.kimi_terminal_show_thinking
    del bpy.types.Scene.kimi_terminal_show_code
    del bpy.types.Scene.kimi_terminal_history
    del bpy.types.Scene.kimi_terminal_tool_log
    del bpy.types.Scene.kimi_terminal_sessions
    del bpy.types.Scene.kimi_terminal_session_name
    del bpy.types.Scene.kimi_terminal_active_session
    del bpy.types.Scene.kimi_terminal_live_thinking
    del bpy.types.Scene.kimi_terminal_live_code
    del bpy.types.Scene.kimi_terminal_live_output
    del bpy.types.Scene.kimi_terminal_live_status
    del bpy.types.Scene.kimi_terminal_current_turn
    del bpy.types.Scene.kimi_terminal_total_turns
    del bpy.types.Scene.kimi_terminal_max_visible_messages
    del bpy.types.Scene.kimi_terminal_max_autonomous_turns
    del bpy.types.Scene.kimi_terminal_attached_file
    del bpy.types.Scene.kimi_terminal_use_mcp_bridge
    del bpy.types.Scene.kimi_terminal_use_screenshots
    del bpy.types.Scene.kimi_terminal_expanded_thinking
    del bpy.types.Scene.kimi_terminal_progress_dummy
