# Kimi Blender Terminal — Wiki

> An AI-powered terminal-style assistant panel inside Blender, powered by the local Kimi CLI.

---

## Quick Links

| Document | What You'll Learn |
|----------|-------------------|
| [Installation](INSTALL.md) | How to install the addon in Blender |
| [User Guide](USER-GUIDE.md) | How to use every feature |
| [Architecture](ARCHITECTURE.md) | How I built the system |
| [MCP Bridge API](MCP-BRIDGE.md) | All 30+ JSON commands available |
| [Troubleshooting](TROUBLESHOOTING.md) | Fix common problems |
| [Developer Guide](DEVELOPER.md) | How to extend the addon |

---

## What Is This?

I built Kimi Blender Terminal because I was tired of context-switching between Blender and a chat window. It's an **AI-powered Blender addon** that lets you control Blender using natural language. You type what you want — *"create a snowy mountain"* — and the assistant writes Python code that executes directly in Blender.

### Key Capabilities

- **Chat-first UI** — Talk to Blender without leaving the viewport
- **Autonomous execution** — The assistant chains 5-20 operations automatically
- **Viewport screenshots** — Visual feedback after each step
- **Professional workflows** — Terrain, PBR materials, lighting, rendering, export
- **Asset integrations** — Poly Haven, Sketchfab, Hyper3D, Hunyuan3D
- **Session persistence** — Save and resume conversations

---

## 30-Second Demo

1. Open Blender
2. Press **N** → Click **Kimi** tab
3. Type: `Create a shiny red cube with studio lighting`
4. Press **Send**
5. Watch the assistant write code, execute it, and show you the result

---

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| Blender | 3.6 | 4.2 or 5.x |
| Python | 3.10 | 3.11 |
| Kimi CLI | Latest | Latest |
| OS | Windows / macOS / Linux | Windows 11 / macOS 14 |
| Internet | Optional* | Required for asset downloads |

\* Internet only needed for Poly Haven, Sketchfab, and 3D generation. Basic primitives work offline.

---

## Architecture At A Glance

```
You (natural language)
    ↓
Kimi Terminal Panel (Blender UI)
    ↓
Conversation Engine (orchestrates the loop)
    ↓
Kimi CLI (subprocess) ←→ Moonshot AI API
    ↓
```python code blocks```
    ↓
MCP Bridge (TCP socket server inside Blender)
    ↓
Blender Main Thread (executes code, captures screenshots)
    ↓
3D Scene updates
```

---

## Feature Checklist

- [x] Chat UI with message cards
- [x] Real-time reasoning display
- [x] Code block display with Run/Copy
- [x] Viewport screenshot thumbnails
- [x] Quick prompt buttons
- [x] Multi-turn autonomous execution
- [x] MCP Bridge socket server
- [x] Terrain generation (noise + erosion)
- [x] Vertex color painting
- [x] PBR material creation
- [x] Object manipulation (30+ commands)
- [x] Camera controls
- [x] Lighting setup
- [x] Animation keyframing
- [x] Render pipeline
- [x] GLB/OBJ/FBX export
- [x] Collection management
- [x] Poly Haven integration
- [x] Sketchfab integration
- [x] Hyper3D Rodin integration
- [x] Hunyuan3D integration
- [x] Session save/load
- [x] CLI session resume

---

## License

MIT License — see [LICENSE](../LICENSE)
