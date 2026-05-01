# Developer Guide

## Project Structure

```
kimi_blender_terminal/
├── __init__.py              # Addon entry point, bl_info, register/unregister
├── preferences.py           # Addon preferences panel
├── ui.py                    # Main panel, operators, message drawing
├── conversation_agent.py    # Orchestrates think→code→execute→observe loop
├── kimi_client.py           # Subprocess wrapper for Kimi CLI
├── executor.py              # Safe Python execution in Blender with helpers
├── mcp_bridge.py            # Socket server + command handlers + client
├── scene_context.py         # Scene summary builder for LLM context
├── session_manager.py       # Persistent JSON session storage
├── integrations.py          # Poly Haven, Sketchfab, Hyper3D, Hunyuan3D
├── blender_tools.py         # Core tool registry
├── tool_registry.py         # Tool registration utilities
└── utils.py                 # run_in_main_thread, logging helpers
```

---

## Development Setup

### Symlink Install

```bash
# Windows PowerShell (Admin)
$addonDir = "$env:APPDATA\Blender Foundation\Blender\4.2\scripts\addons"
$src = "C:\path\to\kimi-blender-terminal\kimi_blender_terminal"
New-Item -ItemType Junction -Path "$addonDir\kimi_blender_terminal" -Target $src

# macOS
ln -s /path/to/kimi-blender-terminal/kimi_blender_terminal \
  ~/Library/Application\ Support/Blender/4.2/scripts/addons/kimi_blender_terminal

# Linux
ln -s /path/to/kimi-blender-terminal/kimi_blender_terminal \
  ~/.config/blender/4.2/scripts/addons/kimi_blender_terminal
```

### Hot Reload

After editing Python files:

1. **Disable** the addon in Preferences
2. **Enable** it again

Or use the **F3** menu → **Reload Scripts**.

### Debug Mode

In Blender's Python console:

```python
import kimi_blender_terminal
import importlib
importlib.reload(kimi_blender_terminal)
```

Enable console logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

## Adding a New MCP Command

### 1. Define the handler in `mcp_bridge.py`

```python
@_handler("my_command")
def _cmd_my_command(params):
    name = params.get("name", "Default")
    count = params.get("count", 1)

    # Do something in Blender
    for i in range(count):
        bpy.ops.mesh.primitive_cube_add(location=(i*2, 0, 0))

    return {
        "created": count,
        "names": [f"Cube.{i:03d}" for i in range(count)]
    }
```

### 2. Document it in `executor.py` HELPER_DOCS

```
MY_COMMANDS:
  my_command(name, count=1) -> {"created", "names"}
    # Creates count cubes spaced along X axis
```

### 3. Test it

```python
from kimi_blender_terminal.mcp_bridge import get_client
client = get_client()
client.connect()
result = client.send_command("my_command", {"name": "Test", "count": 3})
print(result)  # {'created': 3, 'names': ['Cube.000', ...]}
client.disconnect()
```

---

## Adding a New UI Operator

### 1. Define the operator in `ui.py`

```python
class KIMI_TERMINAL_OT_MyAction(Operator):
    bl_idname = "kimi_terminal.my_action"
    bl_label = "My Action"
    bl_description = "Does something cool"
    bl_options = {"REGISTER"}

    def execute(self, context):
        # Your logic here
        self.report({"INFO"}, "Action completed!")
        return {"FINISHED"}
```

### 2. Add to the panel draw method

```python
row = layout.row()
row.operator("kimi_terminal.my_action", text="Do It", icon="PLAY")
```

### 3. Register the class

Add `KIMI_TERMINAL_OT_MyAction` to the `classes` list.

---

## Adding a New Helper Function

### 1. Define in `executor.py`

```python
def _create_torus(name="Torus", location=(0,0,0), major_radius=1, minor_radius=0.25):
    bpy.ops.mesh.primitive_torus_add(
        location=location,
        major_radius=major_radius,
        minor_radius=minor_radius
    )
    obj = bpy.context.active_object
    obj.name = name
    return obj
```

### 2. Add to namespace

In `execute_blender_python()`:

```python
namespace["create_torus"] = _create_torus
```

### 3. Document in HELPER_DOCS

```
PRIMITIVES:
  create_torus(name, location, major_radius, minor_radius) -> obj
```

---

## Modifying the System Prompt

Edit `artist_guide.py` → `ARTIST_PROMPT`:

```python
ARTIST_PROMPT = """\
You are Kimi Blender Terminal...

[Your new instructions here]
"""
```

The prompt is sent with every LLM request. Keep it under ~4000 tokens.

---

## Modifying the Conversation Flow

Edit `conversation_agent.py` → `ConversationAgent.run_turn()`:

Key methods:
- `_build_prompt()` — How the prompt is assembled
- `_execute_via_mcp()` — How code is executed
- `_capture_screenshot()` — How screenshots are captured

To change the number of autonomous turns:

```python
agent.max_autonomous_turns = 10  # Default is 5
```

To disable screenshots:

```python
agent.use_screenshots = False
```

---

## Testing

### Unit Test Pattern

```python
import bpy
from kimi_blender_terminal import executor

# Test helper
result = executor._create_cube("TestCube", (0,0,0), 2.0)
assert result.name == "TestCube"
assert result.location == (0,0,0)

# Test material
mat = executor._create_pbr_material("TestMat", (1,0,0), 0.5, 0.0)
assert mat.name == "TestMat"

# Test execution
result = executor.execute_blender_python("create_cube('Another')")
assert result["status"] == "success"
```

### Integration Test

```python
from kimi_blender_terminal.mcp_bridge import get_client

client = get_client()
client.connect()

# Test scene query
scene = client.send_command("get_scene_info")
assert "object_count" in scene

# Test execution
result = client.send_command("execute_code", {"code": "create_cube('IntTest')"})
assert result["executed"]

client.disconnect()
```

---

## Code Style

- **PEP 8** for Python
- **Type hints** where helpful
- **Docstrings** for public functions
- **f-strings** for string formatting
- **Constants** in UPPER_CASE

---

## Release Checklist

Before I publish a new version, I check:

- [ ] Update `bl_info["version"]` in `__init__.py`
- [ ] Update README.md version references
- [ ] Run syntax check on all files
- [ ] Test basic prompt: "create a red cube"
- [ ] Test multi-turn prompt: "create a mountain scene"
- [ ] Test MCP Bridge: verify screenshots work
- [ ] Test session save/load
- [ ] Verify no API keys in code
- [ ] Build ZIP with correct folder structure
- [ ] Update CHANGELOG.md (if exists)
- [ ] Tag git release

---

## Contributing

1. Fork the repo
2. Create a feature branch
3. Make changes
4. Test in Blender
5. Submit a pull request

### What I'd Love Help With

- Blender 5.x compatibility testing
- macOS/Linux specific fixes
- New terrain noise types
- Additional PBR material presets
- Better error recovery
- Performance optimizations
- Documentation translations
