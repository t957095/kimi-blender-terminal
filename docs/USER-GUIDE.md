# User Guide

## The Panel

Open the 3D View sidebar (**N** key) → **Kimi** tab.

```
┌─────────────────────────────┐
│ ● Ready                [Test]│
├─────────────────────────────┤
│ ▶ Settings                  │
├─────────────────────────────┤
│ >>> Create a red cube       │  ← Your message
│                             │
│ ┌─────────────────────────┐ │
│ │ Kimi                    │ │
│ │ I'll create a red cube. │ │
│ │                         │ │
│ │ ⚙ Code                  │ │
│ │   mat = create_pbr...   │ │
│ │   [Run] [Copy]          │ │
│ │                         │ │
│ │ ✓ Result                │ │
│ │   OK: viewport updated  │ │
│ └─────────────────────────┘ │
│                             │
│ [Type prompt...       ] [➤]│
│                             │
│ Clear  Think  Code  MCP     │
└─────────────────────────────┘
```

---

## Status Bar

| Icon | Meaning |
|------|---------|
| ● Ready | Idle, waiting for input |
| ◐ Thinking... | Assistant is generating a response |
| ◑ Working... | Code is executing |
| ● Done | Task complete |
| ● Error | Something went wrong |

Colors:
- **Green/Blue** = Good/Ready/Done
- **Orange/Yellow** = Thinking/Working
- **Red** = Error only

---

## Quick Prompts

When the chat is empty, one-click buttons appear:

| Button | What It Does |
|--------|-------------|
| **Red Cube** | Creates a shiny red cube + 3-point lighting |
| **Mountain** | Snowy mountain landscape + PBR + HDRI |
| **Studio** | Clean white studio + soft box + camera |
| **Island** | Tropical island + ocean + sunset |

Click any button to send the prompt instantly.

---

## Writing Prompts

### Basic Prompts

```
Create a blue sphere
```

```
Make the cube metallic and gold
```

```
Add a sun light from the top left
```

### Complex Prompts

```
Create a complete snowy mountain scene with:
- Ridged multi-fractal terrain
- Thermal erosion
- Snow vertex painting
- PBR rock/snow material
- HDRI sky lighting
- Positioned camera
```

### Long Tasks

For complex scenes, increase **Max Turns** in Settings to 10-20.

```
Create a cyberpunk street scene with:
- Wet pavement with reflections
- Neon sign (emissive material)
- Fog/volumetric lighting
- Street lamps
- Camera at street level
```

The assistant will:
1. Clear the scene
2. Create the ground
3. Add materials
4. Set up lights
5. Position camera
6. Add atmosphere
7. Render a preview

All automatically, across multiple execution turns.

---

## Settings

Click **▶ Settings** to expand.

### Sessions
- **New** — Start a fresh conversation
- **Save** — Save current chat + CLI session ID
- **Load** — Resume a previous session

### Scene Context
- Shows current scene summary (objects, camera, engine)
- Click **Refresh** to update

### Execution Engine
| Setting | Description |
|---------|-------------|
| **MCP Bridge** | Execute via socket server (faster, screenshots) |
| **Screenshots** | Capture viewport after each execution |
| **Max Turns** | How many code→execute loops (1-20) |

**Recommendation**: Keep MCP Bridge ON, Screenshots ON, Max Turns at 5-10 for most tasks. Increase to 15-20 for very complex scenes.

---

## Message Cards

### User Messages
- Right-aligned
- Your prompt text
- Timestamp

### Assistant Messages
- **Header**: "Kimi" + turn count + timestamp
- **Text**: Explanation of what was done
- **Screenshot**: Viewport thumbnail (if enabled)
- **Thinking**: Collapsible reasoning (click arrow)
- **Code**: Dark box with Run/Copy buttons
- **Result**: Execution output (✓ or ✗)

### System Messages
- Red alert box
- Errors or warnings

---

## Working with Code

### Run Code Again
Each code block has a **Run** button. Click to re-execute that specific block.

### Copy Code
Click **Copy** to copy code to your clipboard. Paste into Blender's Text Editor to inspect or modify.

### View Full Code
Code blocks show the first 10 lines. The full code is always executed — the truncation is just for UI space.

---

## Viewport Screenshots

When **Screenshots** is enabled:

1. Assistant executes code
2. Viewport is captured automatically
3. Thumbnail appears in the assistant's message card
4. Assistant receives a description in its next prompt

This lets the assistant **see** mistakes and fix them:
- "The cube is floating, move it down"
- "The material is too dark, increase emission"
- "The camera is inside the mesh, pull it back"

---

## Tips for Best Results

### Be Specific

❌ *"Make it nice"*
✅ *"Make the cube shiny red with roughness 0.2 and metallic 0.8"*

### Break Complex Tasks Into Steps

The assistant handles this automatically with multi-turn execution, but you can also guide it:

```
Step 1: Create a subdivided plane
Step 2: Displace it with noise for hills
Step 3: Paint vertex colors green to yellow
Step 4: Add a sun light
```

### Use Color Constants

The assistant knows these exact colors:
- `RED`, `GREEN`, `BLUE`, `YELLOW`, `ORANGE`
- `WHITE`, `BLACK`, `GREY`, `SILVER`, `GOLD`
- `CYAN`, `MAGENTA`, `PURPLE`, `PINK`, `BROWN`

### Check the Thinking

Expand the **Thinking** section to see the assistant's reasoning. If it's going wrong, stop and rephrase your prompt.

### Save Sessions

Before closing Blender, click **Save** in Settings. This preserves:
- Chat history
- Kimi CLI session ID (for context continuity)
- Blender file path

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| **N** | Toggle sidebar (show/hide Kimi panel) |
| **Enter** | Send prompt (when input box is focused) |

---

## Common Workflows

### Product Photography
```
Create a studio setup for product photography:
- Infinite white cyclorama
- Soft box lighting from left
- Rim light from behind
- Camera at 3/4 angle
- Depth of field f/2.8
```

### Terrain for Games
```
Create a game-ready terrain:
- 100x100 meter landscape
- Rolling hills (multi-fractal)
- Grass vertex colors
- Low poly (subdivisions: 50)
- Export as GLB
```

### Abstract Art
```
Create abstract floating shapes:
- Glassmorphism cubes (transmission 1.0)
- Soft gradient backdrop
- Area lights for soft shadows
- Isometric camera angle
```
