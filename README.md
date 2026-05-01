# Kimi Blender Terminal

**Kimi Blender Terminal** is an open-source, local-first AI assistant for Blender, designed for production-grade 3D workflows, autonomous scene building, and long-form creative iteration.

It connects Blender to a local CLI-based AI backend, such as Kimi CLI, and allows the model to execute Blender Python, inspect viewport screenshots, iterate across multiple turns, and persist sessions across projects.

---

## Why This Exists

Official Blender MCP-style integrations prove that AI-assisted 3D workflows are powerful, but many existing solutions are tied to specific vendors, token-based pricing models, and desktop-only workflows.

Kimi Blender Terminal is built as an open alternative.

It is designed for artists, developers, technical directors, and automation-heavy Blender users who want:

- Local-first control
- Long autonomous sessions
- Persistent project memory
- Screenshot-based feedback loops
- Terminal, script, and CI access
- Flexible backend support through CLI-compatible models

Instead of requiring every scene query, correction, and iteration to run through a paid API workflow, this project allows Blender to be driven through a local CLI backend while preserving a production-ready multi-turn assistant experience.

---

## Key Features

### Autonomous Multi-Turn Execution

Kimi Blender Terminal can chain multiple operations from a single prompt.

The assistant can:

1. Inspect the current Blender scene
2. Generate Python or structured tool calls
3. Execute the operation inside Blender
4. Capture a viewport screenshot
5. Analyze the result
6. Correct mistakes
7. Continue until the task is complete

This makes it useful for complex workflows such as terrain generation, lighting setup, material refinement, asset placement, and scene cleanup.

---

### Viewport Screenshot Feedback

After each execution round, the assistant can receive a viewport screenshot as visual feedback.

This allows the model to detect and correct issues such as:

- Incorrect colors
- Bad scale
- Clipping problems
- Poor object placement
- Missing materials
- Lighting issues
- Camera framing problems

The assistant does not have to rely only on scene metadata. It can see the result of its actions and continue improving the scene.

---

### Blender MCP Bridge

The project includes a persistent JSON-over-TCP bridge running inside Blender.

Default address:

```txt
localhost:9742
```

This allows external tools to control Blender without interacting with the UI directly.

Supported clients include:

- Terminal commands
- Local scripts
- CI pipelines
- SSH sessions
- Automation agents
- Custom MCP-compatible workflows

### CLI Bridge

The included CLI bridge allows prompts to be sent directly from a terminal while Blender is open.

Example:

```bash
python cli_bridge.py "create a red cube"
```

This makes it possible to batch-process `.blend` files, automate scene generation, integrate with shell scripts, or drive Blender remotely from a render machine.

### Session Persistence

Conversation history and Kimi CLI sessions are saved locally:

```
~/.kimi/blender-terminal/sessions.json
```

This allows work to resume later without losing project context.

### Hybrid Tool Calling

The assistant supports both structured tool calls and raw Python execution.

It can emit reliable XML-style tool calls:

```xml
<tool_call>
  ...
</tool_call>
```

Or generate Python directly for more advanced Blender operations.

This gives the system flexibility while still supporting safer, structured workflows.

## Core Capabilities

### Blender Scene Operations

| Category | Supported Tools |
|----------|-----------------|
| Primitives | Cube, sphere, cylinder, cone, torus, plane, camera, light, text |
| Terrain | Procedural landscapes, ridged multifractal terrain, hybrid terrain, thermal erosion, displacement |
| Materials | PBR materials, metallic, roughness, clearcoat, subsurface, emission, vertex color mixing |
| Object Operations | Select, move, rotate, scale, duplicate, delete, rename, apply transforms, set origin |
| Collections | Create collections, move objects, batch organize scenes |
| Camera & Lighting | Active camera setup, look-at targeting, 3-point lighting, color and energy control |
| Modifiers | Subdivision, mirror, array, bevel, boolean, displace, wireframe, solidify |
| Animation | Insert keyframes, clear animation |
| Rendering | Set engine, resolution, samples, render stills, capture viewport screenshots |
| Export | GLB, OBJ, FBX, Three.js HTML |
| Data Visualization | 3D bar charts, scatter plots, line graphs from CSV data |

### Asset Integrations

Kimi Blender Terminal can optionally integrate with external asset providers.

| Provider | Support |
|----------|---------|
| Poly Haven | HDRIs, textures, and models. No authentication required. |
| BlenderKit | Search and import free assets directly into Blender. |
| Sketchfab | Search, preview, and download models. Requires an API token. |

## Requirements

- Blender 3.0 or newer
- Python 3.10 or newer
- Kimi CLI or another compatible local CLI backend
- `requests` package (for external asset integrations)

Install Kimi CLI:

```bash
pip install kimi-cli
kimi login
```

Install `requests` in Blender's Python (needed for Poly Haven, BlenderKit, and Sketchfab):

```bash
# Find Blender's Python executable, then run:
python -m pip install requests
```

Or from Blender's scripting console:

```python
import subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "install", "requests"])
```

Blender's bundled Python is supported for all core workflows. Asset integrations require `requests`.

## Installation

### Option A: ZIP Install

> **Do not download the repository source ZIP** (the green Code button). That ZIP contains the repo root folder and will not install correctly in Blender. Use the pre-built `kimi_blender_terminal.zip` from the releases page, or build it yourself from source.

1. Download `kimi_blender_terminal.zip` from the [Releases](../../releases) page.
2. Open Blender.
3. Go to **Edit → Preferences → Add-ons → Install from Disk**.
4. Select the ZIP file.
5. Enable **Kimi Blender Terminal**.
6. The MCP Bridge will automatically start on:

```
localhost:9742
```

### Option B: Clone from GitHub

```bash
git clone https://github.com/t957095/kimi-blender-terminal.git
```

Then zip the `kimi_blender_terminal` folder and install it through Blender's add-on installer.

## Configuration

Configuration is available from:

**Edit → Preferences → Add-ons → Kimi Blender Terminal**

### Global Settings

| Setting | Description |
|---------|-------------|
| **Kimi CLI Executable** | Path to `kimi` or `kimi-cli`. Leave blank to auto-detect. |
| **CLI Timeout** | Maximum seconds to wait for a CLI response. Default: 300. |
| **Max Tool Iterations** | Maximum execution loops per prompt. Default: 10. |
| **Auto-send Scene Context** | Injects live scene information into every prompt. |
| **Allow Dangerous Code** | Disables code pattern guardrails. Not recommended. |
| **Sketchfab API Token** | Optional token required for Sketchfab downloads. |

### Per-Scene Settings

Available from:

**3D View → N Panel → Kimi → Settings**

| Setting | Description |
|---------|-------------|
| **MCP Bridge** | Executes operations through the socket server for faster execution and screenshot support. |
| **Screenshots** | Captures the viewport after each execution round. |
| **Max Turns** | Sets autonomous iterations per prompt. Supported range: 1–20. |

## Usage

### Using the Blender UI

1. Open the Blender 3D View.
2. Press **N** to open the sidebar.
3. Open the **Kimi** panel.
4. Click **Test** to verify the CLI connection.
5. Enter a prompt.
6. Click **Send**.

Example prompt:

```
Create a shiny red cube and set up cinematic 3-point lighting.
```

### Terminal Usage

Run prompts from the terminal while Blender is open.

#### Basic Prompt

```bash
python cli_bridge.py "create a red cube"
```

#### Long Autonomous Task

```bash
python cli_bridge.py "make a snowy mountain landscape" --turns 10
```

#### Open a Blend File First

```bash
python cli_bridge.py --blend myscene.blend "add a chair next to the table"
```

#### Save Screenshots and Auto-Backup

```bash
python cli_bridge.py "set up studio lighting" --screenshots ./shots --save-blend
```

#### Read Prompt from File

```bash
python cli_bridge.py --prompt-file prompt.txt
```

#### List Available Tools

```bash
python cli_bridge.py --list-tools
```

#### Windows

```cmd
cli_bridge.bat "create a red cube"
```

### CLI Execution Flow

When a terminal prompt is submitted, the CLI bridge performs the following sequence:

1. Connects to the Blender MCP Bridge at `localhost:9742`
2. Fetches the live tool registry and current scene context
3. Sends the prompt to the local CLI backend
4. Parses Python code blocks and structured tool calls
5. Executes operations inside Blender's main thread
6. Captures a viewport screenshot
7. Sends the result back to the model
8. Repeats until the assistant returns `<done>` or reaches the max turn limit

### Example Prompts

```
Create a shiny red cube and set up 3-point lighting.
```

```
Make a snowy mountain landscape with PBR materials and HDRI lighting.
```

```
Set up a clean white studio with softbox lighting and a 50mm camera.
```

```
Create a cyberpunk street scene with neon signs, wet pavement, and volumetric fog.
```

```
Build a low-poly desert environment with rocks, dunes, warm lighting, and a cinematic camera angle.
```

### Long-Form Scene Generation

For complex scenes, set **Max Turns** to 10–20.

The assistant will continuously:

- Inspect the scene
- Plan the next step
- Generate code or tool calls
- Execute the operation
- Capture a screenshot
- Evaluate the result
- Correct errors
- Continue building

Because the model receives viewport feedback after each round, it can self-correct issues with color, scale, composition, and placement without requiring constant user input.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ External Clients                                             │
│ CLI, Scripts, CI, SSH                                        │
│ └─ CLI Bridge → localhost:9742                               │
├─────────────────────────────────────────────────────────────┤
│ Kimi Terminal UI                                             │
│ Blender N-Panel                                              │
│ ├─ Chat history                                               │
│ ├─ Live working area                                          │
│ ├─ Code and execution output                                  │
│ ├─ Viewport screenshot thumbnails                             │
│ └─ Input bar and quick prompts                                │
├─────────────────────────────────────────────────────────────┤
│ Conversation Engine                                           │
│ ├─ System prompt and tool schemas                             │
│ ├─ Local CLI subprocess                                       │
│ ├─ Python and XML tool-call parser                            │
│ ├─ Multi-turn autonomous loop                                 │
│ ├─ Error categorization                                       │
│ └─ Screenshot feedback loop                                   │
├─────────────────────────────────────────────────────────────┤
│ MCP Bridge                                                    │
│ TCP Socket Server                                             │
│ ├─ Persistent Blender connection                              │
│ ├─ JSON command handlers                                      │
│ ├─ Tool registry introspection                                │
│ ├─ Viewport screenshot capture                                │
│ └─ Main-thread execution via bpy.app.timers                   │
├─────────────────────────────────────────────────────────────┤
│ Executor                                                      │
│ Helper Namespace and Validation                              │
│ ├─ Terrain generation                                         │
│ ├─ PBR material creation                                      │
│ ├─ Primitive creation                                         │
│ ├─ Export utilities                                           │
│ └─ Sandboxed builtins                                         │
└─────────────────────────────────────────────────────────────┘
```

## MCP Bridge Protocol

The MCP Bridge uses JSON over TCP.

Default address:

```
localhost:9742
```

### Execute Blender Code

```json
{
  "type": "execute_code",
  "params": {
    "code": "create_cube('Box')"
  }
}
```

### Capture Viewport Screenshot

```json
{
  "type": "get_viewport_screenshot",
  "params": {
    "max_size": 800
  }
}
```

### Get Scene Information

```json
{
  "type": "get_scene_info",
  "params": {}
}
```

See `mcp_bridge.py` for the full command registry.

## Security

Kimi Blender Terminal includes several safety controls for generated code execution.

### Sandboxed Execution

The executor runs inside a restricted namespace.

The following operations are blocked by default:

- `open`
- `eval`
- `exec`
- `__import__`
- `os.system`
- `subprocess`

### Pattern Guardrails

Additional regex-based checks block dangerous operations before execution, including:

- Unsafe `bpy.ops` calls
- File deletion operations
- Process execution
- Restricted imports
- Quit or destructive commands

### Dangerous Mode

The **Allow Dangerous Code** setting disables pattern checks.

This is intended only for advanced users who need unrestricted Python access.

Use with caution.

### Local-Only Socket

The MCP Bridge binds to:

```
localhost
```

It is not exposed remotely by default.

## Troubleshooting

### `kimi-cli` not found

Install Kimi CLI:

```bash
pip install kimi-cli
```

Then log in:

```bash
kimi login
```

Alternatively, set the executable path manually:

**Preferences → Kimi Blender Terminal → Kimi CLI Executable**

### Cannot Connect to Blender MCP Server

The bridge should start automatically when the add-on is enabled.

Check Blender's system console for:

```
[Kimi MCP Bridge] Server started on localhost:9742
```

If the port is stuck, disable and re-enable the add-on.

### Colors Are Not Showing

Switch the viewport shading mode to:

**Material Preview**

or

**Rendered**

The assistant can also call:

```python
set_viewport_shading("MATERIAL")
```

after creating materials.

## Recommended Use Cases

Kimi Blender Terminal is useful for:

- AI-assisted scene generation
- Procedural environment creation
- Rapid material iteration
- Automated lighting setup
- Batch `.blend` file processing
- Terminal-driven Blender workflows
- 3D data visualization
- Render-node automation
- AI-assisted asset organization
- Long-form autonomous creative sessions

## Roadmap Ideas

Potential future improvements include:

- Multi-model backend support
- Better asset search routing
- Improved visual critique loop
- Render comparison mode
- Prompt templates for common Blender workflows
- Scene diffing between turns
- Project-level memory
- More structured MCP tool schemas
- Automated test scenes
- Plugin marketplace support

## License

MIT License.

See [LICENSE](LICENSE) for details.
