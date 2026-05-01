# Comparison: Kimi Blender Terminal vs BlenderMCP (Claude)

## At A Glance

| | **BlenderMCP** | **Kimi Blender Terminal** |
|---|---|---|
| **LLM** | Claude (Anthropic) | Kimi (Moonshot AI) |
| **Protocol** | Model Context Protocol (MCP) | Code-block execution + MCP Bridge |
| **Execution** | Socket server | Socket server |
| **License** | MIT | MIT |

---

## Feature Comparison

### Core Capabilities

| Feature | BlenderMCP | Kimi Terminal |
|---------|:----------:|:-------------:|
| Socket server in Blender | ✅ | ✅ |
| JSON command protocol | ✅ | ✅ |
| Viewport screenshots | ✅ | ✅ |
| Code execution | ✅ | ✅ |
| Scene info query | ✅ | ✅ |
| Object info query | ✅ | ✅ |
| Multi-turn execution | ✅ | ✅ |
| Session persistence | ❌ | ✅ |
| Chat history UI | ❌ | ✅ |
| Quick prompt buttons | ❌ | ✅ |
| Reasoning display | ❌ | ✅ |
| Live execution log | ❌ | ✅ |
| Progress indicator | ❌ | ✅ |
| Message cards | ❌ | ✅ |
| Copy/Run code buttons | ❌ | ✅ |

### 3D Tools

| Feature | BlenderMCP | Kimi Terminal |
|---------|:----------:|:-------------:|
| Create primitives | ✅ | ✅ |
| Object manipulation | ✅ | ✅ |
| Camera control | ✅ | ✅ |
| Lighting setup | ✅ | ✅ |
| Material creation | ✅ Basic | ✅ Advanced |
| Terrain generation | ❌ | ✅ |
| Thermal erosion | ❌ | ✅ |
| Vertex color painting | ❌ | ✅ |
| PBR coat / subsurface | ❌ | ✅ |
| Emission materials | ❌ | ✅ |
| Modifier management | ✅ | ✅ |
| Animation keyframing | ❌ | ✅ |
| Render pipeline | ❌ | ✅ |
| Collection management | ❌ | ✅ |

### Export

| Format | BlenderMCP | Kimi Terminal |
|--------|:----------:|:-------------:|
| GLB | ❌ | ✅ |
| OBJ | ❌ | ✅ |
| FBX | ❌ | ✅ |

### Asset Integrations

| Service | BlenderMCP | Kimi Terminal |
|---------|:----------:|:-------------:|
| Poly Haven | ✅ | ✅ |
| Sketchfab | ✅ | ✅ |
| Hyper3D Rodin | ✅ | ✅ |
| Hunyuan3D | ✅ | ✅ |

---

## Architecture Differences

### BlenderMCP

```
Claude Desktop App
    ↓ (MCP protocol over stdio)
MCP Server (Python process)
    ↓ (TCP socket)
Blender Addon (socket server)
    ↓ (bpy.app.timers)
Blender Main Thread
```

**Pros:**
- Native MCP support in Claude
- Structured tool schemas
- Official standard

**Cons:**
- Requires Claude Desktop or MCP-compatible client
- No chat history UI in Blender
- No session persistence
- Terrain/material workflows require manual scripting

### Kimi Blender Terminal

```
Blender Panel (built-in UI)
    ↓ (operators + scene properties)
Conversation Engine (Python thread)
    ↓ (subprocess)
Kimi CLI
    ↓ (HTTP API)
Moonshot AI
    ↓ (text response with code blocks)
Conversation Engine
    ↓ (TCP socket or direct exec)
MCP Bridge
    ↓ (bpy.app.timers)
Blender Main Thread
```

**Pros:**
- Self-contained in Blender (no external client needed)
- Chat-first UI with message cards
- Session persistence
- Autonomous multi-turn execution
- Built-in terrain/material helpers
- Viewport screenshots with inline thumbnails
- Quick prompt buttons
- Works with any Kimi CLI installation

**Cons:**
- Requires Kimi CLI (not a native API client)
- Code-block parsing vs structured MCP tools
- No direct integration with Cursor/VSCode

---

## Use Case Recommendations

### Use BlenderMCP if...

- You already use Claude Desktop as your primary AI assistant
- You want MCP integration with other tools (not just Blender)
- You prefer structured tool calling over code generation
- You don't need terrain generation or advanced materials

### Use Kimi Blender Terminal if...

- You use Kimi/Moonshot AI
- You want a chat UI directly inside Blender
- You do procedural terrain or complex PBR workflows
- You want the assistant to chain multiple operations automatically
- You want session persistence across Blender restarts
- You want viewport screenshots as visual feedback

---

## Performance

Both addons use the same socket server architecture for execution, so performance is comparable for:
- Code execution speed
- Viewport screenshot capture
- Scene query response time

Differences:
- **LLM latency**: Depends on Claude vs Kimi API speeds
- **Round trips**: BlenderMCP does 1 LLM call per tool use. Kimi Terminal does 1-2 calls per turn, but can chain multiple executions.
- **Context size**: Both send scene context. Kimi Terminal also sends helper docs and artist guide.

---

## Security

| Aspect | BlenderMCP | Kimi Terminal |
|--------|-----------|---------------|
| Code sandboxing | execute_code runs arbitrary Python | Dangerous patterns blocked |
| Network access | Same as Blender | Same as Blender |
| API key storage | In MCP client config | In Blender preferences |
| Telemetry | Optional (anonymous) | None |

---

## Extensibility

Both addons are open-source (MIT) and easy to extend.

| Extension Point | BlenderMCP | Kimi Terminal |
|-----------------|-----------|---------------|
| Add commands | `addon.py` handlers + `server.py` tools | `mcp_bridge.py` handlers |
| Add UI | N/A (external client) | `ui.py` panel |
| Add helpers | N/A | `executor.py` namespace |
| Change system prompt | N/A | `artist_guide.py` |
