# Architecture Deep Dive

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              BLENDER PROCESS                                 │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                         USER INTERFACE                                 │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │  │
│  │  │ Status Bar  │  │  Settings   │  │   Chat      │  │   Input     │  │  │
│  │  │  (colors)   │  │ (sessions)  │  │  (cards)    │  │   (bar)     │  │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘  │  │
│  │                                                                       │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │  │
│  │  │              KIMI_TERMINAL_PT_Panel (ui.py)                      │  │  │
│  │  │  - Draws all UI elements                                         │  │  │
│  │  │  - Manages scene properties (bpy.types.Scene.*)                  │  │  │
│  │  │  - Handles user input (operators)                                │  │  │
│  │  └─────────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                    ↓                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                     CONVERSATION ENGINE                                │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │  │
│  │  │           ConversationAgent (conversation_agent.py)                │  │  │
│  │  │                                                                    │  │  │
│  │  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │  │  │
│  │  │  │   Turn 1    │───→│  Execute    │───→│  Screenshot │         │  │  │
│  │  │  │  THINKING   │    │  EXECUTING  │    │   capture   │         │  │  │
│  │  │  └─────────────┘    └─────────────┘    └─────────────┘         │  │  │
│  │  │         ↑                                    │                  │  │  │
│  │  │         └────────────────────────────────────┘                  │  │  │
│  │  │              (loop up to max_autonomous_turns)                  │  │  │
│  │  │                                                                    │  │  │
│  │  │  Flow:                                                             │  │  │
│  │  │  1. Build prompt (system + scene + user)                         │  │  │
│  │  │  2. Send to Kimi CLI via subprocess                              │  │  │
│  │  │  3. Parse ```python blocks from response                         │  │  │
│  │  │  4. Execute code                                                 │  │  │
│  │  │  5. Capture screenshot (optional)                                │  │  │
│  │  │  6. Feed results back                                            │  │  │
│  │  │  7. Repeat if assistant generates more code                      │  │  │
│  │  └─────────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                    ↓                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                         KIMI CLIENT                                    │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │  │
│  │  │              KimiClient (kimi_client.py)                         │  │  │
│  │  │                                                                    │  │  │
│  │  │  - Finds kimi executable (PATH, ~/.local/bin, etc.)              │  │  │
│  │  │  - Spawns subprocess: kimi --output-format stream-json --print   │  │  │
│  │  │  - Parses JSON stream: {"role":"assistant","content":...}        │  │  │
│  │  │  - Extracts reasoning blocks <think>...</think>                  │  │  │
│  │  │  - Manages session IDs (-r for resume)                           │  │  │
│  │  │  - Handles timeout and abort                                     │  │  │
│  │  └─────────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                    ↓                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                         MCP BRIDGE                                     │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │  │
│  │  │              BridgeServer (mcp_bridge.py)                        │  │  │
│  │  │                                                                    │  │  │
│  │  │  TCP Socket Server (localhost:9742)                               │  │  │
│  │  │  ├─ Accepts JSON commands from Conversation Engine                │  │  │
│  │  │  ├─ Dispatches to command handlers (30+ registered)               │  │  │
│  │  │  ├─ Executes in Blender's main thread via bpy.app.timers          │  │  │
│  │  │  ├─ Captures viewport screenshots                                 │  │  │
│  │  │  └─ Returns JSON responses                                        │  │  │
│  │  │                                                                    │  │  │
│  │  │  Alternative: direct exec() if MCP bridge is disabled             │  │  │
│  │  └─────────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                    ↓                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                         EXECUTOR                                       │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │  │
│  │  │           execute_blender_python (executor.py)                   │  │  │
│  │  │                                                                    │  │  │
│  │  │  Namespace includes:                                             │  │  │
│  │  │  - bpy, context, scene, data, ops, mathutils, bmesh, math       │  │  │
│  │  │  - 30+ helper functions (create_cube, create_landscape, etc.)   │  │  │
│  │  │  - 15 color constants (RED, GREEN, BLUE, etc.)                  │  │  │
│  │  │  - Dangerous pattern blocking (quit, delete, system calls)      │  │  │
│  │  │  - Tee stdout to both StringIO and Blender console              │  │  │
│  │  └─────────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
                         ┌─────────────────────┐
                         │   MOONSHOT AI API   │
                         │   (api.moonshot.cn) │
                         └─────────────────────┘
```

---

## Data Flow

### Single Turn (Simple Prompt)

```
User types: "make the cube red"
    ↓
UI stores message in scene.kimi_terminal_history
    ↓
ConversationAgent.run_turn() called in background thread
    ↓
Build prompt = SYSTEM_PERSONA + HELPER_DOCS + CURRENT_SCENE + USER_MESSAGE
    ↓
KimiClient.send_message(prompt) spawns subprocess
    ↓
Kimi CLI → Moonshot API → Response text
    ↓
Parse ```python blocks
    ↓
Execute via MCP Bridge (or direct exec)
    ↓
Capture stdout/stderr
    ↓
Store results in history item
    ↓
UI redraws with assistant message card
```

### Multi-Turn (Complex Prompt)

```
User types: "create a mountain scene"
    ↓
Turn 1: Assistant generates terrain code
    ↓
Execute → Screenshot → Results fed back
    ↓
Turn 2: Assistant generates erosion code
    ↓
Execute → Screenshot → Results fed back
    ↓
Turn 3: Assistant generates material code
    ↓
Execute → Screenshot → Results fed back
    ↓
Turn 4: Assistant generates lighting code
    ↓
Execute → Screenshot → Results fed back
    ↓
Turn 5: Assistant says "<done>" and summarizes
    ↓
Final assistant message shown
```

---

## Key Design Decisions

### Why Code Blocks Instead of XML Tool Calls?

I tried XML tool calling (`<tool_call>` tags) in early versions. The Kimi CLI text model struggled to format them reliably — it would forget closing tags, misplace attributes, or generate invalid XML half the time. Code blocks (`python`) work way better because:
- They're more natural for LLMs trained on code
- Self-documenting (the code IS the tool call)
- Easier to debug (you can read and modify the output)
- The official Blender MCP server uses the same approach

### Why a Socket Server (MCP Bridge)?

Blender's Python API is not thread-safe. All operations must run in the main thread. I considered two options:

1. **Direct exec()** — Works, but each execution is isolated and slow
2. **Socket server** — Persistent connection, structured commands, viewport screenshots

I went with the socket server because it gives me:
- Faster execution (no subprocess spawning per call)
- Viewport screenshot capability
- Structured JSON protocol
- Easy to extend with new commands

### Why Subprocess Instead of Direct API?

I tried calling the Moonshot API (`api.moonshot.cn/v1/chat/completions`) directly. It returns 403 from my environment — probably missing some auth headers or signatures that the CLI handles internally. The Kimi CLI takes care of:
- OAuth token management
- Request signing
- Rate limiting
- Session persistence

So subprocess is the only reliable path I found.

### Why Multi-Turn Autonomous Execution?

Complex 3D scenes need many steps. A single LLM response can't fit 500 lines of code without getting truncated or confused. The autonomous loop lets the assistant:
- Plan and execute incrementally
- Get visual feedback (screenshots) between steps
- Recover from errors (see the error, generate a fix)
- Work like I do — iterate, evaluate, adjust

---

## Thread Safety

Blender's API is **single-threaded**. All bpy calls must happen in the main thread.

```
Background Thread (Worker)          Main Thread (Blender)
─────────────────────               ─────────────────────
Agent.run_turn()                        |
    ↓                                   |
KimiClient.send_message()               |
    ↓                                   |
Parse response                          |
    ↓                                   |
Need to execute code ─────────────────→ bpy.app.timers.register(execute_wrapper)
                                        ↓
                                    execute_wrapper()
                                        ↓
                                    exec(code, namespace)
                                        ↓
                                    bpy.ops.* calls
                                        ↓
                                    UI updates automatically
```

The `utils.run_in_main_thread()` function uses `bpy.app.timers` to schedule execution on the main thread.

### CLI Bridge Tool Execution

The CLI bridge (`cli_bridge.py`) parses tool calls from the model's response and sends them to Blender via the MCP bridge. Originally it sent Python code strings like:

```python
code = (
    "from kimi_blender_terminal.tool_registry import execute_tool\n"
    "import json\n"
    f"result = execute_tool({name}, {args})\n"
    "print(json.dumps(result))\n"
)
result = bridge.send("execute_code", {"code": code})
```

This failed in the sandbox because `import` statements require `__import__`, which was blocked. The fix was adding a dedicated `execute_tool` MCP handler in `mcp_bridge.py` that calls `tool_registry.execute_tool()` directly, bypassing the sandbox entirely:

```python
@_handler("execute_tool")
def _cmd_execute_tool(params):
    from . import tool_registry
    name = params.get("name")
    arguments = params.get("arguments", {})
    result = tool_registry.execute_tool(name, arguments)
    return {"executed": True, "status": "success", "stdout": json.dumps(result), ...}
```

The CLI bridge now sends: `bridge.send("execute_tool", {"name": name, "arguments": args})`.

---

## State Management

### Scene Properties

All UI state is stored in `bpy.types.Scene` properties:

```python
scene.kimi_terminal_status          # "IDLE", "THINKING", "EXECUTING"
scene.kimi_terminal_input           # Current text in input box
scene.kimi_terminal_history         # CollectionProperty of messages
scene.kimi_terminal_live_thinking   # Current turn's reasoning
scene.kimi_terminal_live_code       # Current turn's code
scene.kimi_terminal_live_output     # Current turn's output
```

### Session Persistence

Sessions are stored in `~/.kimi/blender-terminal/sessions.json`:

```json
{
  "uuid": "abc123",
  "name": "Mountain Scene",
  "kimi_session_id": "sess_xyz789",
  "history": [
    {"role": "user", "content": "create a mountain"},
    {"role": "assistant", "content": "Done!"}
  ],
  "blender_file": "/path/to/scene.blend",
  "updated_at": 1714500000
}
```

The `kimi_session_id` allows resuming the same CLI session with `-r <id>`.

---

## Security Model

### Sandboxing

Code execution uses `exec(code, namespace)` with a controlled namespace. The namespace includes:
- Safe helpers (create_cube, create_landscape, etc.)
- Read-only bpy access
- Color constants
- Restricted builtins via `SAFE_BUILTINS` dict

### Safe Import Wrapper

The sandbox provides a custom `__import__` function (`_safe_import`) that:
- Returns already-injected modules (`bpy`, `mathutils`, `bmesh`, `math`, `json`, `random`) without re-importing
- Allows a whitelist of safe stdlib modules (`itertools`, `collections`, `functools`, `datetime`, `typing`, `statistics`, `fractions`, `decimal`, `string`, `copy`, `numbers`)
- Blocks everything else (`os`, `sys`, `subprocess`, `shutil`, `socket`, etc.)

**Lesson learned:** `inspect` was initially whitelisted but removed because `inspect.currentframe()` enables stack-frame walking to access the executor's unrestricted globals — a sandbox escape vector.

### Dangerous Patterns Blocked

```python
DEFAULT_BLOCKED_PATTERNS = [
    r"bpy\.ops\.wm\.quit_blender",
    r"os\.system\s*\(",
    r"subprocess\.call\s*\(",
    r"eval\s*\(",
    r"exec\s*\(",
    r"importlib\.import_module",
    r"shutil\.rmtree",
    r"shutil\.move",
    ...
]
```

### No API Keys in Code

All external service tokens are stored in Blender's addon preferences (user-configurable, never committed to repo).

---

## Root Shim for GitHub ZIP Installs

GitHub's "Download ZIP" wraps the repository in a folder like `kimi-blender-terminal-master/`. Blender looks for `__init__.py` at the root of the extracted folder. Since the real addon lives in `kimi_blender_terminal/`, a root shim bridges the gap:

```python
# repo/__init__.py
import sys, os
_SHIM_DIR = os.path.dirname(os.path.abspath(__file__))
if _SHIM_DIR not in sys.path:
    sys.path.insert(0, _SHIM_DIR)

import kimi_blender_terminal as _real
bl_info = _real.bl_info

def register():
    _real.register()

def unregister():
    _real.unregister()
```

This makes the green Code button work out of the box while preserving the existing package structure and relative imports.

## Extension Points

### Adding New MCP Commands

In `mcp_bridge.py`:

```python
@_handler("my_new_command")
def _cmd_my_new_command(params):
    # Do something in Blender
    return {"success": True, "data": ...}
```

The command becomes available to the assistant immediately.

### Adding New UI Elements

In `ui.py`, extend `KIMI_TERMINAL_PT_Panel.draw()`:

```python
row = layout.row()
row.operator("my_new.operator", text="My Button")
```

### Adding New Helpers

In `executor.py`, define a function and add it to the namespace:

```python
def _my_helper():
    ...

namespace["my_helper"] = _my_helper
```

Update `HELPER_DOCS` so the assistant knows about it.
