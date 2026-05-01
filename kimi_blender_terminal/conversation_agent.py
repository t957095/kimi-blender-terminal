"""
ConversationAgent — multi-turn autonomous execution with hybrid tool calling.

The assistant can use TWO methods:
  1. Structured TOOL CALLS (preferred): <tool_call><name>...</name><arguments>{...}</arguments></tool_call>
     These are parsed, validated, and executed via the ToolRegistry. Reliable, fast, no syntax errors.
  2. Python CODE BLOCKS (fallback): ```python ... ```
     These are executed via exec() in Blender's namespace. More flexible but error-prone.

After each execution, we capture viewport state and feed it back. The model continues
until the task is complete or max turns are reached.
"""

import ast
import hashlib
import re
import traceback

from . import artist_guide
from . import executor
from . import kimi_client
from . import mcp_bridge
from . import scene_context
from . import tool_registry
from . import utils

SYSTEM_PERSONA = artist_guide.ARTIST_PROMPT


def _parse_code_blocks(text: str) -> list:
    pattern = r"```python\n(.*?)\n```"
    return re.findall(pattern, text, re.DOTALL)


def _strip_code_blocks(text: str) -> str:
    pattern = r"```python\n.*?\n```"
    return re.sub(pattern, "", text, flags=re.DOTALL).strip()


def _strip_tool_calls(text: str) -> str:
    pattern = r"<tool_call>\s*<name>.*?</name>\s*<arguments>.*?</arguments>\s*</tool_call>"
    return re.sub(pattern, "", text, flags=re.DOTALL | re.IGNORECASE).strip()


def _has_done_marker(text: str) -> bool:
    markers = ["<done>", "task complete", "all done", "finished", "completed successfully"]
    lower = text.lower()
    return any(m in lower for m in markers)


def _hash_code(code: str) -> str:
    return hashlib.md5(code.strip().encode("utf-8")).hexdigest()[:12]


def _categorize_error(message: str, traceback_str: str) -> dict:
    """Categorize an execution error and suggest a fix."""
    msg = message.lower()
    tb = traceback_str.lower()

    if "nameerror" in msg or "nameerror" in tb:
        # Extract the undefined name
        match = re.search(r"name ['\"](\w+)['\"] is not defined", message + traceback_str)
        name = match.group(1) if match else "unknown"
        return {
            "category": "NameError",
            "message": f"'{name}' is not defined.",
            "suggestion": f"Check spelling. Use get_objects() to see what's in the scene. "
                          f"Available helpers: create_cube, create_sphere, create_landscape, "
                          f"move, rotate, scale, delete, create_pbr_material, assign_mat, etc.",
        }
    if "attributeerror" in msg or "attributeerror" in tb:
        match = re.search(r"'(\w+)' object has no attribute '(\w+)'", message + traceback_str)
        if match:
            return {
                "category": "AttributeError",
                "message": f"{match.group(1)} has no attribute '{match.group(2)}'.",
                "suggestion": "Check the object type. Use get_object_info(name) to inspect.",
            }
        return {"category": "AttributeError", "message": message, "suggestion": "Check object type and available attributes."}
    if "keyerror" in msg or "keyerror" in tb:
        return {"category": "KeyError", "message": message, "suggestion": "Check dictionary keys before accessing."}
    if "indexerror" in msg or "indexerror" in tb:
        return {"category": "IndexError", "message": message, "suggestion": "Check list/collection length before indexing."}
    if "typeerror" in msg or "typeerror" in tb:
        return {"category": "TypeError", "message": message, "suggestion": "Check argument types and counts."}
    if "syntaxerror" in msg or "syntaxerror" in tb:
        return {"category": "SyntaxError", "message": message, "suggestion": "Fix Python syntax. Check parentheses, colons, quotes."}
    if "runtimeerror" in msg or "runtimeerror" in tb:
        return {"category": "RuntimeError", "message": message, "suggestion": "This is a Blender runtime error. Check object state and mode."}
    if "operator" in msg and "error" in msg:
        return {"category": "BlenderOperatorError", "message": message, "suggestion": "Check the operator context. Some ops need the right object type or edit mode."}
    return {"category": "Unknown", "message": message, "suggestion": "Review the error and try a different approach."}


class ConversationAgent:
    def __init__(self, client: kimi_client.KimiClient = None):
        self.client = client or kimi_client.KimiClient()
        self.status = "IDLE"
        self.last_error = None
        self._abort = False
        self.max_autonomous_turns = 5
        self.use_mcp_bridge = True
        self.use_screenshots = True
        self.mcp_client = None
        self._executed_hashes = set()  # Dedup: don't run identical code twice

    def reset(self):
        self.client.reset_session()
        self.status = "IDLE"
        self.last_error = None
        self._executed_hashes.clear()
        if self.mcp_client:
            self.mcp_client.disconnect()
            self.mcp_client = None

    def abort(self):
        self._abort = True
        self.client.abort()
        self.status = "ABORTED"

    def _ensure_mcp(self):
        if self.use_mcp_bridge and self.mcp_client is None:
            self.mcp_client = mcp_bridge.get_client()
            try:
                self.mcp_client.connect()
            except ConnectionError:
                self.use_mcp_bridge = False
                self.mcp_client = None

    def _execute_via_mcp(self, code: str) -> dict:
        self._ensure_mcp()
        if self.mcp_client:
            try:
                result = self.mcp_client.send_command("execute_code", {"code": code})
                return {
                    "status": "success" if result.get("executed") else "error",
                    "stdout": result.get("stdout", ""),
                    "stderr": result.get("stderr", ""),
                    "message": result.get("message", ""),
                }
            except Exception:
                return executor.execute_blender_python(code)
        return executor.execute_blender_python(code)

    def _capture_screenshot(self) -> dict:
        if not self.use_screenshots:
            return None
        self._ensure_mcp()
        if self.mcp_client:
            try:
                result = self.mcp_client.send_command("get_viewport_screenshot", {"max_size": 600})
                if "image_data" in result:
                    return result
            except Exception:
                pass
        return None

    def _execute_tools(self, tool_calls: list) -> list:
        """Execute structured tool calls and return results."""
        results = []
        for call in tool_calls:
            name = call.get("name")
            args = call.get("arguments", {})
            try:
                result = utils.run_in_main_thread(
                    tool_registry.execute_tool, name, args, timeout=60.0
                )
                results.append({"tool": name, "result": result})
            except Exception as e:
                results.append({"tool": name, "error": str(e)})
        return results

    def _execute_python(self, code: str) -> dict:
        """Execute Python code with validation and deduplication."""
        code_hash = _hash_code(code)
        if code_hash in self._executed_hashes:
            return {
                "status": "error",
                "message": "This exact code was already executed in a previous turn. Do not repeat the same code.",
            }
        self._executed_hashes.add(code_hash)

        # Pre-validate syntax
        ok, reason = executor.validate_code(code, allow_dangerous=False)
        if not ok:
            return {"status": "error", "message": reason}

        if self.use_mcp_bridge:
            result = self._execute_via_mcp(code)
        else:
            result = utils.run_in_main_thread(
                executor.execute_blender_python,
                code, allow_dangerous=False, timeout=30.0,
            )
        return result

    def _build_prompt(self, user_message: str, execution_result: str = None,
                      turn_number: int = 0, screenshot_desc: str = "") -> str:
        parts = [SYSTEM_PERSONA]

        # Add tool schemas
        parts.append("\n" + tool_registry.get_tools_prompt())

        # Add executor helper docs (condensed)
        parts.append("\n" + executor.HELPER_DOCS)

        # Add scene context
        try:
            ctx = scene_context.SceneContext.get_text_summary(force_refresh=False)
            parts.append(f"\nCURRENT SCENE:\n{ctx}\n")
        except Exception as e:
            parts.append(f"\nCURRENT SCENE:\n(unavailable: {e})\n")

        system = "\n".join(parts)

        if execution_result:
            extra = ""
            if screenshot_desc:
                extra = f"\nViewport screenshot after execution: {screenshot_desc}\n"
            if turn_number > 0:
                extra += f"\nThis is autonomous turn {turn_number}. Continue working until the task is fully complete. If done, say '<done>' and summarize.\n"
            return (
                f"{system}\n\n"
                f"The user asked: {user_message}\n\n"
                f"Your previous code produced this result:\n{execution_result}\n"
                f"{extra}\n"
                f"Please provide a brief summary. If there were errors, provide corrected code or tool calls.\n\n"
                f"If the task is not yet complete, continue with more code or tools. When fully done, say '<done>' and summarize.\n\n"
                f"ASSISTANT:"
            )
        return f"{system}\n\nUSER: {user_message}\n\nASSISTANT:"

    def run_turn(self, user_message: str, on_status=None, on_log=None,
                 on_thinking=None, on_code=None, on_turn=None, on_done=None):
        self._abort = False
        code_blocks_log = []
        final_text = ""
        final_think = ""
        error = None
        turn = 0

        def log(line: str):
            if on_log:
                on_log(line)

        def set_status(s: str):
            self.status = s
            if on_status:
                on_status(s)

        def emit_thinking(think_text: str):
            if on_thinking:
                on_thinking(think_text)

        def emit_code(code_text: str):
            if on_code:
                on_code(code_text)

        def emit_turn(current: int, total: int):
            if on_turn:
                on_turn(current, total)

        try:
            # === Turn 1: Initial generation ===
            set_status("THINKING")
            log("[Agent] Sending prompt to Kimi...")

            prompt = self._build_prompt(user_message)
            text, think, sid, err = self.client.send_message(prompt)

            if err:
                raise RuntimeError(f"Kimi CLI error: {err}")

            final_think = think
            emit_thinking(think)
            log(f"[Agent] Received response ({len(text)} chars)")

            # Main autonomous loop
            while turn < self.max_autonomous_turns and not self._abort:
                turn += 1
                emit_turn(turn, self.max_autonomous_turns)
                log(f"[Agent] === Autonomous turn {turn}/{self.max_autonomous_turns} ===")

                # Parse BOTH tool calls and code blocks
                tool_calls = tool_registry.parse_tool_calls(text)
                code_blocks = _parse_code_blocks(text)
                text_without_tools = _strip_tool_calls(_strip_code_blocks(text))

                execution_summaries = []

                # === Execute tool calls first (preferred) ===
                if tool_calls:
                    set_status("EXECUTING")
                    log(f"[Agent] Executing {len(tool_calls)} tool call(s)...")
                    tool_results = self._execute_tools(tool_calls)
                    for i, tr in enumerate(tool_results):
                        if "error" in tr:
                            summary = f"Tool {tr['tool']}: ERROR - {tr['error']}"
                        else:
                            result = tr.get("result", {})
                            status = result.get("status", "unknown")
                            msg = result.get("message", "")
                            summary = f"Tool {tr['tool']}: {status}"
                            if msg:
                                summary += f" - {msg[:200]}"
                            if "result" in result and isinstance(result["result"], dict):
                                r = result["result"]
                                if "imported_objects" in r:
                                    summary += f" | Imported: {', '.join(r['imported_objects'])[:100]}"
                                elif "name" in r:
                                    summary += f" | Name: {r['name']}"
                        execution_summaries.append(summary)
                        log(f"[Tool] {summary[:300]}")
                        code_blocks_log.append({"tool": tr["tool"], "result": tr.get("result", {}), "error": tr.get("error")})

                # === Execute code blocks ===
                if code_blocks:
                    set_status("EXECUTING")
                    log(f"[Agent] Executing {len(code_blocks)} code block(s)...")

                    for i, code in enumerate(code_blocks):
                        log(f"[Code] Block {i + 1} ({len(code)} chars)")
                        emit_code(code)

                        result = self._execute_python(code)

                        code_blocks_log.append({"code": code, "result": result})

                        summary_lines = [f"Block {i + 1}:", f"Status: {result.get('status', 'unknown')}"]
                        if result.get("stdout"):
                            summary_lines.append(f"stdout:\n{result['stdout'][:500]}")
                        if result.get("stderr"):
                            summary_lines.append(f"stderr:\n{result['stderr'][:200]}")
                        if result.get("scene_changes"):
                            summary_lines.append(f"Scene changes: {', '.join(result['scene_changes'])}")
                        if result.get("status") == "error":
                            err_info = _categorize_error(
                                result.get("message", ""),
                                result.get("traceback", "")
                            )
                            summary_lines.append(f"ERROR [{err_info['category']}]: {err_info['message']}")
                            summary_lines.append(f"SUGGESTION: {err_info['suggestion']}")

                        summary = "\n".join(summary_lines)
                        execution_summaries.append(summary)
                        log(f"[Result] {summary[:300]}")

                # If nothing to execute, we're done
                if not tool_calls and not code_blocks:
                    final_text = text or text_without_tools or "(No response)"
                    set_status("DONE")
                    break

                combined_results = "\n\n".join(execution_summaries)

                # === Capture screenshot ===
                screenshot_desc = ""
                if self.use_screenshots and turn < self.max_autonomous_turns:
                    log("[Agent] Capturing viewport screenshot...")
                    try:
                        ss = self._capture_screenshot()
                        if ss and ss.get("success"):
                            screenshot_desc = (
                                f"Viewport screenshot captured ({ss['width']}x{ss['height']}). "
                                f"The scene is visible in the 3D viewport."
                            )
                            log("[Agent] Screenshot captured")
                    except Exception as e:
                        log(f"[Agent] Screenshot failed: {e}")

                # Check done marker
                if _has_done_marker(text_without_tools) or _has_done_marker(text):
                    final_text = text_without_tools or text
                    set_status("DONE")
                    log("[Agent] Model signaled completion.")
                    break

                # Max turns reached
                if turn >= self.max_autonomous_turns:
                    final_text = f"{text_without_tools}\n\n(Reached max autonomous turns: {self.max_autonomous_turns})"
                    set_status("DONE")
                    log("[Agent] Max autonomous turns reached.")
                    break

                # === Next turn ===
                set_status("THINKING")
                log("[Agent] Asking model to continue...")

                followup_prompt = self._build_prompt(
                    user_message, combined_results,
                    turn_number=turn, screenshot_desc=screenshot_desc
                )
                text, think_next, sid_next, err_next = self.client.send_message(followup_prompt)

                if err_next:
                    final_text = f"Executed. Results:\n\n{combined_results}"
                    set_status("DONE")
                    log("[Agent] Follow-up failed, stopping.")
                    break

                if think_next:
                    final_think += "\n" + think_next
                    emit_thinking(final_think)

                # Check if new response has anything to execute
                new_tool_calls = tool_registry.parse_tool_calls(text)
                new_code_blocks = _parse_code_blocks(text)
                if not new_tool_calls and not new_code_blocks:
                    final_text = text or text_without_tools or f"Executed. Results:\n\n{combined_results}"
                    set_status("DONE")
                    log("[Agent] Model provided no more actions. Stopping.")
                    break

                log(f"[Agent] Model provided {len(new_tool_calls)} tool call(s) and {len(new_code_blocks)} code block(s). Continuing...")

        except Exception as e:
            traceback.print_exc()
            error = str(e)
            set_status("ERROR")
            log(f"[Agent] Exception: {e}")

        if on_done:
            on_done({
                "text": final_text,
                "thinking": final_think,
                "error": error,
                "code_blocks": code_blocks_log,
                "status": self.status,
                "turns_executed": turn,
            })
