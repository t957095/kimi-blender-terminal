"""
CLI Bridge — Standalone command-line interface for Kimi Blender Terminal.

Run this from a terminal while Blender is open with the addon enabled.
It connects to Blender's MCP Bridge (port 9742) and sends prompts to Kimi CLI.

Usage:
    cd kimi-blender-terminal
    python -m kimi_blender_terminal.cli_bridge "create a red cube"
    python -m kimi_blender_terminal.cli_bridge "make a snowy mountain" --turns 10
    python -m kimi_blender_terminal.cli_bridge --prompt-file prompt.txt --blend myscene.blend

This is the "text-to-Blender" bridge. You don't need to touch the Blender UI.
Just make sure Blender is running with the Kimi Terminal addon enabled.
"""

import argparse
import base64
import json
import os
import re
import socket
import sys
import tempfile
import time

from . import kimi_client
from . import tool_registry
from . import artist_guide


SYSTEM_PROMPT = artist_guide.ARTIST_PROMPT


def _build_prompt(user_message: str, scene_context: str = "", tool_prompt: str = "",
                   execution_result: str = "", turn_number: int = 0) -> str:
    parts = [SYSTEM_PROMPT]
    if tool_prompt:
        parts.append(tool_prompt)
    if scene_context:
        parts.append("\nCURRENT SCENE:\n" + scene_context + "\n")

    base = "\n".join(parts)

    if execution_result:
        extra = ""
        if turn_number > 0:
            extra = (
                "\nThis is autonomous turn " + str(turn_number) +
                ". Continue working until the task is fully complete. "
                "If done, say '<done>' and summarize.\n"
            )
        return (
            base + "\n\n"
            "The user asked: " + user_message + "\n\n"
            "Your previous code produced this result:\n" + execution_result + "\n"
            + extra + "\n"
            "Please provide a brief summary. If there were errors, provide corrected code or tool calls.\n\n"
            "If the task is not yet complete, continue with more code or tools. "
            "When fully done, say '<done>' and summarize.\n\n"
            "ASSISTANT:"
        )
    return base + "\n\nUSER: " + user_message + "\n\nASSISTANT:"


class BlenderBridgeClient:
    """Connects to Blender's MCP Bridge and sends commands."""

    def __init__(self, host="localhost", port=9742):
        self.host = host
        self.port = port
        self.sock = None

    def connect(self):
        if self.sock:
            return True
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            self.sock.settimeout(120.0)
            return True
        except Exception:
            print(f"[CLI Bridge] Cannot connect to Blender at {self.host}:{self.port}")
            print("[CLI Bridge] Make sure Blender is running with the Kimi Terminal addon enabled.")
            return False

    def disconnect(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def send(self, cmd_type: str, params: dict = None) -> dict:
        if not self.sock and not self.connect():
            return {"status": "error", "message": "Not connected to Blender"}

        payload = json.dumps({"type": cmd_type, "params": params or {}})
        try:
            self.sock.sendall(payload.encode("utf-8"))
            return self._recv_json()
        except (ConnectionError, BrokenPipeError, OSError):
            self.sock = None
            return {"status": "error", "message": "Connection to Blender lost"}

    def _recv_json(self) -> dict:
        chunks = []
        self.sock.settimeout(120.0)
        while True:
            try:
                chunk = self.sock.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
                data = b"".join(chunks)
                try:
                    return json.loads(data.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
            except socket.timeout:
                break
            except OSError:
                break
        if chunks:
            try:
                return json.loads(b"".join(chunks).decode("utf-8"))
            except Exception:
                pass
        return {"status": "error", "message": "No response from Blender"}


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


def _save_screenshot(image_data_b64: str, output_dir: str = None) -> str:
    """Save base64 screenshot to a PNG file."""
    if not image_data_b64:
        return None
    try:
        data = base64.b64decode(image_data_b64)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            path = os.path.join(output_dir, f"screenshot_{int(time.time())}.png")
        else:
            path = os.path.join(tempfile.gettempdir(), f"kimi_screenshot_{int(time.time())}.png")
        with open(path, "wb") as f:
            f.write(data)
        return path
    except Exception as e:
        print(f"[CLI Bridge] Screenshot save error: {e}")
        return None


def _print_section(title: str, content: str, max_lines: int = 20):
    """Print a section with a header, truncating if too long."""
    if not content:
        return
    lines = content.strip().split("\n")
    sep = "=" * 60
    print(f"\n{sep}\n  {title}\n{sep}")
    for line in lines[:max_lines]:
        print(f"  {line}")
    if len(lines) > max_lines:
        print(f"  ... ({len(lines) - max_lines} more lines)")


def _fetch_tool_prompt(bridge: BlenderBridgeClient) -> str:
    """Fetch registered tools from Blender and format them for the prompt."""
    resp = bridge.send("list_tools")
    if resp.get("status") != "success":
        return ""
    tools = resp.get("result", {}).get("tools", [])
    if not tools:
        return ""
    lines = [
        "You have access to structured TOOLS. Use them for reliability.",
        'Format: <tool_call><name>tool_name</name><arguments>{"key":"value"}</arguments></tool_call>',
        "You may use multiple <tool_call> blocks in one response. They execute in order.",
        "For operations NOT covered by tools, use ```python code blocks.",
        "",
        "Available tools:",
    ]
    for t in tools:
        lines.append(f"  {t['name']}: {t['description']}")
        params = t.get("parameters", {})
        req = params.get("required", [])
        if req:
            lines.append(f"    Required: {', '.join(req)}")
    return "\n".join(lines)


def run_cli(prompt: str, host: str = "localhost", port: int = 9742,
            max_turns: int = 5, timeout: int = 300, screenshot_dir: str = None,
            save_blend: bool = False, verbose: bool = False, blend_path: str = None,
            list_tools_only: bool = False):
    """
    Main CLI loop. Connects to Blender, sends prompt to Kimi CLI,
    executes code/tool calls, captures screenshots, repeats until done.
    """
    print("[CLI Bridge] Kimi Blender Terminal — Text-to-3D Bridge")
    print(f"[CLI Bridge] Prompt: {prompt}")
    print(f"[CLI Bridge] Blender: {host}:{port}")
    print(f"[CLI Bridge] Max turns: {max_turns}\n")

    # Connect to Blender
    bridge = BlenderBridgeClient(host, port)
    if not bridge.connect():
        print("[CLI Bridge] FAILED: Is Blender running with the Kimi Terminal addon enabled?")
        sys.exit(1)

    # Open blend file if requested
    if blend_path:
        abs_path = os.path.abspath(blend_path)
        if not os.path.isfile(abs_path):
            print(f"[CLI Bridge] Blend file not found: {abs_path}")
            sys.exit(1)
        print(f"[CLI Bridge] Opening blend file: {abs_path}")
        # Use forward slashes for Blender
        blender_path = abs_path.replace("\\", "/")
        result = bridge.send("execute_code", {
            "code": f"bpy.ops.wm.open_mainfile(filepath={json.dumps(blender_path)})"
        })
        if result.get("result", {}).get("status") == "error":
            print("[CLI Bridge] Warning: failed to open blend file")
        else:
            print("[CLI Bridge] Blend file opened")

    # Debug: list tools
    if list_tools_only:
        tool_prompt = _fetch_tool_prompt(bridge)
        print("\n[CLI Bridge] Tools available in Blender:\n")
        print(tool_prompt)
        bridge.disconnect()
        return

    # Fetch tools prompt from Blender (so we always have the live tool list)
    print("[CLI Bridge] Fetching tool registry from Blender...")
    tool_prompt = _fetch_tool_prompt(bridge)
    if tool_prompt:
        print(f"[CLI Bridge] {tool_prompt.count(chr(10))} lines of tool docs loaded")

    # Get scene context
    print("[CLI Bridge] Fetching scene context...")
    scene_info = bridge.send("get_scene_info")
    scene_text = ""
    if scene_info.get("status") == "success":
        result = scene_info.get("result", {})
        scene_text = json.dumps(result, indent=2)
        if verbose:
            _print_section("SCENE CONTEXT", scene_text, max_lines=10)

    # Initialize Kimi CLI
    print("[CLI Bridge] Initializing Kimi CLI...")
    client = kimi_client.KimiClient(timeout=timeout)
    if not client.executable or not os.path.isfile(client.executable):
        print("[CLI Bridge] FAILED: Kimi CLI not found. Run 'kimi login' first.")
        sys.exit(1)

    # Send initial prompt
    full_prompt = _build_prompt(prompt, scene_context=scene_text, tool_prompt=tool_prompt)
    print("[CLI Bridge] Sending prompt to Kimi...\n")
    text, think, sid, err = client.send_message(full_prompt)

    if err:
        print(f"[CLI Bridge] Kimi CLI error: {err}")
        sys.exit(1)

    if think and verbose:
        _print_section("THINKING", think)

    # Main execution loop
    for turn in range(1, max_turns + 1):
        sep = "─" * 60
        print(f"\n{sep}\n  TURN {turn}/{max_turns}\n{sep}")

        # Parse actions
        tool_calls = tool_registry.parse_tool_calls(text)
        code_blocks = _parse_code_blocks(text)
        text_without_actions = _strip_tool_calls(_strip_code_blocks(text))

        executed_anything = False
        execution_summaries = []

        # Execute tool calls
        for call in tool_calls:
            name = call.get("name")
            args = call.get("arguments", {})
            print(f"[Tool] {name}({json.dumps(args)[:100]}...)")
            try:
                # Tool execution happens inside Blender via the bridge
                code = (
                    "from kimi_blender_terminal.tool_registry import execute_tool\n"
                    "import json\n"
                    f"result = execute_tool({json.dumps(name)}, {json.dumps(args)})\n"
                    "print(json.dumps(result))\n"
                )
                result = bridge.send("execute_code", {"code": code})
                out = result.get("result", {}).get("stdout", "")
                err_out = result.get("result", {}).get("stderr", "")
                status = result.get("result", {}).get("status", "unknown")
                print(f"  -> Status: {status}")
                if out:
                    print(f"  -> Output: {out[:200]}")
                if err_out:
                    print(f"  -> stderr: {err_out[:200]}")
                executed_anything = True
                execution_summaries.append(f"Tool {name}: {status} - {out[:200]}")
            except Exception as e:
                print(f"  -> ERROR: {e}")
                execution_summaries.append(f"Tool {name}: ERROR - {e}")

        # Execute code blocks
        for i, code in enumerate(code_blocks):
            print(f"[Code] Executing block {i + 1} ({len(code)} chars)...")
            if verbose:
                _print_section("CODE", code, max_lines=8)

            result = bridge.send("execute_code", {"code": code})
            res = result.get("result", {})
            status = res.get("status", "unknown")
            stdout = res.get("stdout", "")
            stderr = res.get("stderr", "")
            message = res.get("message", "")

            print(f"  -> Status: {status}")
            if stdout:
                print(f"  -> stdout: {stdout[:200]}")
            if stderr:
                print(f"  -> stderr: {stderr[:200]}")
            if message and status == "error":
                print(f"  -> Error: {message}")

            executed_anything = True
            execution_summaries.append(
                f"Block {i+1}: {status}\nstdout: {stdout[:200]}\nstderr: {stderr[:200]}"
            )

        # Nothing to execute
        if not executed_anything:
            print("\n[CLI Bridge] No code or tools found. Model response:")
            print(text_without_actions or text)
            break

        # Capture screenshot
        print("[CLI Bridge] Capturing viewport screenshot...")
        ss = bridge.send("get_viewport_screenshot", {"max_size": 800})
        ss_result = ss.get("result", {})
        if ss_result.get("success"):
            img_path = _save_screenshot(ss_result.get("image_data"), screenshot_dir)
            if img_path:
                print(f"  -> Screenshot saved: {img_path}")

        # Check done marker
        if _has_done_marker(text_without_actions) or _has_done_marker(text):
            print(f"\n{'=' * 60}\n  TASK COMPLETE\n{'=' * 60}")
            print(text_without_actions or text)
            break

        # Save blend file periodically
        if save_blend and turn % 2 == 0:
            blend_save = os.path.join(tempfile.gettempdir(), f"kimi_backup_{int(time.time())}.blend")
            blender_save_path = blend_save.replace("\\", "/")
            bridge.send("execute_code", {
                "code": f"bpy.ops.wm.save_as_mainfile(filepath={json.dumps(blender_save_path)})"
            })
            print(f"[CLI Bridge] Auto-saved: {blend_save}")

        # Ask for continuation
        if turn >= max_turns:
            print(f"\n[CLI Bridge] Max turns ({max_turns}) reached. Stopping.")
            break

        combined = "\n\n".join(execution_summaries)
        followup = _build_prompt(
            prompt, scene_context=scene_text, tool_prompt=tool_prompt,
            execution_result=combined, turn_number=turn
        )
        print("[CLI Bridge] Asking Kimi to continue...")
        text, think_next, _, err_next = client.send_message(followup)

        if err_next:
            print(f"[CLI Bridge] Follow-up failed: {err_next}")
            break

        if think_next and verbose:
            _print_section("THINKING", think_next)

        # Check if there's more work
        new_tools = tool_registry.parse_tool_calls(text)
        new_code = _parse_code_blocks(text)
        if not new_tools and not new_code:
            print(f"\n{'=' * 60}\n  DONE\n{'=' * 60}")
            print(text_without_actions or text)
            break

    bridge.disconnect()
    print("\n[CLI Bridge] Disconnected from Blender.")


def main():
    parser = argparse.ArgumentParser(
        description="Kimi Blender Terminal — Text-to-3D CLI Bridge. Send prompts to Blender from the terminal.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m kimi_blender_terminal.cli_bridge "create a red cube"
  python -m kimi_blender_terminal.cli_bridge "make a snowy mountain" --turns 10
  python -m kimi_blender_terminal.cli_bridge --prompt-file my_prompt.txt --screenshots ./shots
  python -m kimi_blender_terminal.cli_bridge "set up studio lighting" --save-blend
  python -m kimi_blender_terminal.cli_bridge --blend myscene.blend "add a chair"
  python -m kimi_blender_terminal.cli_bridge --list-tools

Requirements:
  1. Blender must be running with the Kimi Blender Terminal addon enabled.
  2. Kimi CLI must be installed and authenticated (kimi login).
        """
    )
    parser.add_argument("prompt", nargs="?", help="The prompt to send to Kimi")
    parser.add_argument("--prompt-file", "-f", help="Read prompt from a text file")
    parser.add_argument("--host", default="localhost", help="Blender MCP Bridge host (default: localhost)")
    parser.add_argument("--port", type=int, default=9742, help="Blender MCP Bridge port (default: 9742)")
    parser.add_argument("--turns", type=int, default=5, help="Max autonomous turns (default: 5)")
    parser.add_argument("--timeout", type=int, default=300, help="Kimi CLI timeout in seconds (default: 300)")
    parser.add_argument("--screenshots", "-s", help="Directory to save viewport screenshots")
    parser.add_argument("--save-blend", action="store_true", help="Auto-save .blend file every 2 turns")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show thinking and full code")
    parser.add_argument("--blend", help="Open a .blend file in Blender before executing (absolute or relative path)")
    parser.add_argument("--list-tools", action="store_true", help="List available tools and exit")

    args = parser.parse_args()

    if args.list_tools:
        run_cli("", host=args.host, port=args.port, list_tools_only=True)
        return

    # Get prompt
    prompt = None
    if args.prompt_file:
        if not os.path.isfile(args.prompt_file):
            print(f"[CLI Bridge] Prompt file not found: {args.prompt_file}")
            sys.exit(1)
        with open(args.prompt_file, "r", encoding="utf-8") as f:
            prompt = f.read().strip()
    elif args.prompt:
        prompt = args.prompt
    else:
        parser.print_help()
        sys.exit(1)

    run_cli(
        prompt=prompt,
        host=args.host,
        port=args.port,
        max_turns=args.turns,
        timeout=args.timeout,
        screenshot_dir=args.screenshots,
        save_blend=args.save_blend,
        verbose=args.verbose,
        blend_path=args.blend,
    )


if __name__ == "__main__":
    main()
