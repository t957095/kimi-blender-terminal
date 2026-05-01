"""
KimiClient — wraps the local kimi CLI for non-blocking, JSON-stream conversation.

Working invocation:
    kimi-cli --output-format stream-json --print --prompt "..."
    kimi-cli -r <session> --output-format stream-json --print --prompt "..."

The CLI writes a JSON line to stdout like:
    {"role":"assistant","content":[{"type":"think","think":"..."},{"type":"text","text":"..."}]}
"""

import json
import os
import re
import shutil
import subprocess
import threading
import time
import traceback

DEFAULT_TIMEOUT = 300  # seconds


def _test_executable(exe: str) -> bool:
    """Quickly verify an executable can run --version."""
    try:
        proc = subprocess.run(
            [exe, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        return proc.returncode == 0 and "kimi" in (proc.stdout + proc.stderr).lower()
    except Exception:
        return False


def find_kimi_executable():
    """Locate a working kimi-cli executable."""
    # Try PATH first
    for name in ("kimi-cli", "kimi"):
        exe = shutil.which(name)
        if exe and _test_executable(exe):
            return exe
    # Fallback to common install locations
    candidates = [
        os.path.expanduser(r"~\.local\bin\kimi-cli.exe"),
        os.path.expanduser(r"~\.local\bin\kimi.exe"),
        os.path.expanduser(r"~\AppData\Roaming\uv\tools\kimi-cli\Scripts\kimi.exe"),
        os.path.expanduser(r"~\AppData\Roaming\uv\tools\kimi-cli\Scripts\kimi-cli.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c) and _test_executable(c):
            return c
    return None


def parse_stream_json_output(stdout: str):
    """
    Parse the stdout from --output-format stream-json.
    Returns (text_content, thinking_content, session_id, error).
    """
    text_parts = []
    think_parts = []
    session_id = None
    error = None

    # Session resumption line
    session_match = re.search(r"To resume this session:\s*kimi\s+-r\s+([A-Fa-f0-9\-]+)", stdout)
    if session_match:
        session_id = session_match.group(1)

    # Look for JSON blocks
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("{") and line.endswith("}"):
            try:
                data = json.loads(line)
                if isinstance(data, dict) and data.get("role") == "assistant":
                    content = data.get("content", [])
                    for part in content:
                        if isinstance(part, dict):
                            if part.get("type") == "text":
                                text_parts.append(part.get("text", ""))
                            elif part.get("type") == "think":
                                think_parts.append(part.get("think", ""))
                continue
            except json.JSONDecodeError:
                pass
        # stderr / error lines
        if line.startswith("Error") or "Traceback" in line:
            error = (error or "") + line + "\n"

    # If no structured JSON found, fallback to naive extraction
    if not text_parts:
        # Try to extract TextPart legacy format
        for m in re.finditer(r"TextPart\([^)]*text='((?:[^'\\]|\\.)*)'", stdout):
            text_parts.append(m.group(1).replace("\\'", "'"))
        for m in re.finditer(r'TextPart\([^)]*text="((?:[^"\\]|\\.)*)"', stdout):
            text_parts.append(m.group(1).replace('\\"', '"'))

    return (
        "\n".join(text_parts).strip(),
        "\n".join(think_parts).strip(),
        session_id,
        error.strip() if error else None,
    )


class KimiClient:
    def __init__(self, executable: str = None, timeout: int = DEFAULT_TIMEOUT):
        self.executable = executable or find_kimi_executable()
        self.timeout = timeout
        self.session_id = None
        self._proc = None
        self._lock = threading.Lock()

    def test_connection(self) -> dict:
        """Send a ping-like prompt and verify we get a response."""
        if not self.executable or not os.path.isfile(self.executable):
            return {"ok": False, "error": "kimi-cli executable not found. Install via: uv tool install kimi-cli"}
        text, think, sid, err = self.send_message("Respond with exactly the word 'pong'.", stream=False)
        if err:
            return {"ok": False, "error": err}
        if "pong" in text.lower():
            return {"ok": True, "session_id": sid or self.session_id}
        return {"ok": False, "error": f"Unexpected response: {text[:200]}", "session_id": sid}

    def send_message(
        self,
        prompt: str,
        system: str = None,
        messages: list = None,
        stream: bool = False,
    ) -> tuple:
        """
        Send a prompt and return (text, thinking, session_id, error).
        Runs in a background thread; this method blocks until done or timeout.
        For non-blocking use, call from a thread and poll.
        """
        if not self.executable or not os.path.isfile(self.executable):
            return "", "", None, "kimi-cli executable not found"

        args = [self.executable, "--output-format", "stream-json", "--print", "--prompt", prompt]
        if self.session_id:
            args += ["-r", self.session_id]
        if system:
            # kimi-cli doesn't have a native --system flag; prepend to prompt
            pass

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        stdout_data = ""
        stderr_data = ""
        exception = None

        try:
            proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            self._proc = proc
            try:
                stdout_data, stderr_data = proc.communicate(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout_data, stderr_data = proc.communicate()
                exception = f"Timed out after {self.timeout}s"
            finally:
                self._proc = None
        except Exception as e:
            exception = str(e)
            traceback.print_exc()

        if exception:
            return "", "", None, exception

        text, think, sid, err = parse_stream_json_output(stdout_data + "\n" + stderr_data)
        if sid:
            self.session_id = sid
        return text, think, sid, err

    def abort(self):
        """Kill the running subprocess if any."""
        with self._lock:
            if self._proc and self._proc.poll() is None:
                try:
                    self._proc.kill()
                except Exception:
                    pass

    def reset_session(self):
        self.session_id = None
