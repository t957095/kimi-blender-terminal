# Troubleshooting Guide

## Connection Issues

### "kimi-cli not found"

**Symptoms:** Status bar shows **● Error**, console says `kimi-cli not found`

**Causes & Fixes:**

1. **Kimi CLI not installed**
   ```bash
   pip install kimi-cli
   # or
   uv tool install kimi-cli
   ```

2. **Not in PATH**
   - Set the full path in **Preferences → Kimi Blender Terminal → Kimi CLI Executable**
   - Example: `C:\Users\You\.local\bin\kimi.exe`

3. **Wrong executable name**
   - Try `kimi` instead of `kimi-cli` (or vice versa)
   - Verify: `kimi --version` in terminal

### "Could not connect to Blender MCP server"

**Symptoms:** Code execution fails, MCP status shows red

**Causes & Fixes:**

1. **Port conflict**
   - Default port is 9742. If another app uses it:
   - Edit `mcp_bridge.py` → change `DEFAULT_PORT`
   - Restart Blender

2. **Firewall blocking**
   - Allow Blender to accept connections on localhost
   - The server only binds to `127.0.0.1` (local only)

3. **Addon not enabled**
   - Check **Edit → Preferences → Add-ons** that Kimi Terminal is checked

4. **Socket stuck from crash**
   - Restart Blender completely
   - The server auto-starts on addon enable

---

## Execution Issues

### "Code execution error"

**Symptoms:** Result shows ✗, error message in output

**Common Causes:**

1. **Object not found**
   - The assistant referenced an object that doesn't exist
   - The assistant should call `get_scene_info()` first

2. **Material not found**
   - Similar to above — material was deleted or never created

3. **Invalid parameter**
   - The assistant passed a wrong value (e.g., negative radius)
   - The assistant will usually retry with corrected code

4. **Modifier type doesn't exist**
   - Some modifier types vary by Blender version
   - Check `bpy.types.Modifier.bl_rna.properties['type'].enum_items`

### "Execution wrapper failed"

**Symptoms:** The exec() call itself crashed

**Causes:**
- Code tried to access a property on a None object
- Code used a bpy operator outside the correct context
- Code hit a Blender bug

**Fix:** The assistant receives the error and usually generates corrected code in the next turn.

---

## Visual Issues

### "Object is grey / no color"

**Symptoms:** Mesh is white/grey in viewport

**Causes & Fixes:**

1. **Viewport shading is SOLID**
   - Switch to **Material Preview** or **Rendered**
   - The assistant should call `set_viewport_shading("MATERIAL")`

2. **No material assigned**
   - The assistant created a material but didn't assign it
   - Check the code for `assign_material()` or `assign_mat()`

3. **Material has no nodes**
   - Rare Blender quirk — toggle `use_nodes = True`

### "Pink material (magenta)"

**Symptoms:** Object is bright pink

**Cause:** Missing texture file (Blender's "missing texture" color)

**Fix:**
- If using Poly Haven textures, re-download
- If using procedural materials, the assistant should regenerate

### "Terrain is flat"

**Symptoms:** Landscape plane has no height

**Causes & Fixes:**

1. **max_height is 0 or very low**
   - Check the `create_landscape()` call

2. **noise_scale too small**
   - Auto-calculated, but can be overridden

3. **Displace modifier not applied**
   - The assistant may need to apply modifiers

4. **Viewport clip start/end**
   - Check **View → Viewport → Clip Start/End**

---

## LLM Issues

### "Assistant keeps generating wrong code"

**Symptoms:** Same error repeats across turns

**Fixes:**

1. **Be more specific in your prompt**
   - ❌ "Make it better"
   - ✅ "Move the camera 5 units back on the Z axis"

2. **Stop and restart**
   - Click **Clear Chat** to reset context
   - Start fresh with a clearer prompt

3. **Check the thinking**
   - Expand the **Thinking** section
   - If the assistant is confused, rephrase

4. **Reduce Max Turns**
   - Sometimes the assistant overcomplicates with too many turns
   - Set **Max Turns** to 3-5 for simple tasks

### "Assistant ignores my instructions"

**Symptoms:** Assistant does something different from what you asked

**Fixes:**

1. **Use imperative language**
   - ❌ "Can you maybe create a cube?"
   - ✅ "Create a cube. Size 2. Location (0,0,0)."

2. **Specify order of operations**
   - "First clear the scene, then create the cube"

3. **Reference specific objects by name**
   - "Apply a red material to the object named 'Cube'"

---

## Performance Issues

### "Blender freezes during execution"

**Symptoms:** Blender UI locks up, becomes unresponsive

**Causes & Fixes:**

1. **Code is doing too much at once**
   - High subdivision counts (200+ on large landscapes)
   - Heavy modifiers without limits
   - **Fix:** Reduce subdivisions or decimate after creation

2. **Screenshot capture is slow**
   - Large viewports with complex scenes
   - **Fix:** Reduce `max_size` or disable screenshots

3. **Infinite loop in code**
   - Assistant generated a `while True:` or recursion
   - **Fix:** Click **Stop** button, clear chat, retry

### "Very slow responses"

**Symptoms:** Long wait between prompt and response

**Causes:**

1. **Kimi CLI latency**
   - Network-dependent, not fixable by us
   - **Workaround:** Use shorter prompts for faster responses

2. **Large scene context**
   - Scene with 1000+ objects creates huge prompts
   - **Fix:** Simplify scene or disable auto-context in preferences

3. **Multi-turn execution**
   - Each turn requires a full LLM round-trip
   - **Fix:** Reduce Max Turns

---

## Session Issues

### "Session not saving"

**Symptoms:** Save button does nothing

**Fixes:**

1. **Sessions directory doesn't exist**
   - Addon auto-creates `~/.kimi/blender-terminal/`
   - Check permissions

2. **No history to save**
   - Send at least one message first

### "Session won't load"

**Symptoms:** Load button fails

**Causes:**
- Session file corrupted
- CLI session ID expired

**Fix:** Start a new session. Old history is preserved in the JSON file.

---

## Platform-Specific Issues

### Windows

**PowerShell Execution Policy**
- If Kimi CLI subprocess fails: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

**Antivirus blocking**
- Some AV software blocks subprocess spawning
- Add Blender and Kimi CLI to exclusions

### macOS

**Gatekeeper blocking Kimi CLI**
- Right-click `kimi` → Open → Allow
- Or: `xattr -dr com.apple.quarantine /path/to/kimi`

**Blender permissions**
- Grant Blender "Accessibility" permissions for screenshots

### Linux

**Port binding permission**
- Port 9742 is >1024 so no root needed
- If using a custom port <1024, run Blender with sudo (not recommended)

---

## Getting Help

If none of the above fixes work, here's what I usually do:

1. **Check the Blender Console**
   - **Window → Toggle System Console** (Windows)
   - Start Blender from terminal (macOS/Linux)

2. **Enable debug logging**
   - Set `log_to_terminal = True` in addon preferences

3. **Check the MCP Bridge logs**
   - Look for `[Kimi MCP Bridge]` messages in console

4. **File an issue**
   - Include: Blender version, OS, error message, steps to reproduce
