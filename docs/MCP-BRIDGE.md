# MCP Bridge API Reference

The MCP Bridge is a TCP socket server running inside Blender on `localhost:9742`. It accepts JSON commands and returns JSON responses.

## Protocol

### Request Format

```json
{
  "type": "command_name",
  "params": {
    "key": "value"
  }
}
```

### Response Format

```json
{
  "status": "success",
  "result": { ... }
}
```

Or on error:

```json
{
  "status": "error",
  "message": "Error description"
}
```

---

## Scene Queries

### `get_scene_info`

Get summary of the current scene.

**Params:** None

**Returns:**
```json
{
  "name": "Scene",
  "object_count": 5,
  "objects": [
    {"name": "Cube", "type": "MESH", "location": [0, 0, 0]}
  ],
  "materials_count": 2,
  "camera": "Camera",
  "engine": "CYCLES",
  "resolution": [1920, 1080]
}
```

### `get_object_info`

Get detailed info about a specific object.

**Params:**
```json
{"name": "Cube"}
```

**Returns:**
```json
{
  "name": "Cube",
  "type": "MESH",
  "location": [0, 0, 0],
  "rotation": [0, 0, 0],
  "scale": [1, 1, 1],
  "visible": true,
  "materials": ["Material"],
  "mesh": {"vertices": 8, "edges": 12, "polygons": 6},
  "world_bounding_box": [[-1,-1,-1], [1,1,1]]
}
```

---

## Execution

### `execute_code`

Execute arbitrary Python code in Blender.

**Params:**
```json
{"code": "bpy.ops.mesh.primitive_cube_add()"}
```

**Returns:**
```json
{
  "executed": true,
  "status": "success",
  "stdout": "",
  "stderr": "",
  "message": ""
}
```

---

## Viewport

### `get_viewport_screenshot`

Capture the 3D viewport as a PNG.

**Params:**
```json
{"max_size": 800, "format": "png"}
```

**Returns:**
```json
{
  "success": true,
  "width": 800,
  "height": 600,
  "format": "png",
  "image_data": "base64_encoded_png_data..."
}
```

### `set_viewport_shading`

Change the 3D viewport shading mode.

**Params:**
```json
{"mode": "MATERIAL"}
```

Modes: `WIREFRAME`, `SOLID`, `MATERIAL`, `RENDERED`

---

## Primitives

### `create_cube`

**Params:**
```json
{"name": "Cube", "location": [0, 0, 0], "size": 2.0}
```

**Returns:** `{"name": "Cube", "location": [0, 0, 0]}`

### `create_sphere`

**Params:**
```json
{"name": "Sphere", "location": [0, 0, 0], "radius": 1.0}
```

### `create_camera`

**Params:**
```json
{"name": "Camera", "location": [7, -7, 5], "rotation": [1.1, 0, 0.8], "lens": 50}
```

### `create_light`

**Params:**
```json
{"name": "Light", "type": "POINT", "location": [0, 0, 5], "energy": 1000, "color": [1, 1, 1]}
```

Types: `POINT`, `SUN`, `SPOT`, `AREA`

---

## Object Manipulation

### `select_object`

**Params:** `{"name": "Cube"}`

**Returns:** `{"selected": true}`

### `deselect_all`

**Params:** None

### `delete_object`

**Params:** `{"name": "Cube"}`

### `duplicate_object`

**Params:** `{"name": "Cube", "new_name": "Cube_Copy"}`

**Returns:** `{"name": "Cube_Copy", "location": [0, 0, 0]}`

### `rename_object`

**Params:** `{"old_name": "Cube", "new_name": "Box"}`

### `move_object`

**Params:** `{"name": "Cube", "location": [1, 2, 3]}`

### `rotate_object`

**Params:** `{"name": "Cube", "rotation": [0, 0, 1.57]}`

### `scale_object`

**Params:** `{"name": "Cube", "scale": [2, 2, 2]}`

### `apply_transforms`

**Params:** `{"name": "Cube"}`

---

## Camera

### `set_active_camera`

**Params:** `{"name": "Camera"}`

### `camera_look_at`

Point camera at a target object.

**Params:** `{"camera": "Camera", "target": "Cube"}`

---

## Lights

### `set_light_energy`

**Params:** `{"name": "Light", "energy": 2000}`

### `set_light_color`

**Params:** `{"name": "Light", "color": [1, 0.8, 0.6]}`

---

## Materials

### `create_material`

**Params:**
```json
{"name": "RedMat", "color": [1, 0, 0], "roughness": 0.5, "metallic": 0.0}
```

### `create_pbr_material`

**Params:**
```json
{
  "name": "PBR_Mat",
  "base_color": [0.8, 0.8, 0.8],
  "roughness": 0.8,
  "metallic": 0.0,
  "use_vertex_color": false,
  "coat": 0.0,
  "subsurface": 0.0,
  "emission": [0, 0, 0],
  "emission_strength": 0.0
}
```

### `assign_material`

**Params:** `{"object_name": "Cube", "material_name": "RedMat"}`

### `set_material_color`

Quickly set an object's material color.

**Params:** `{"object": "Cube", "color": [1, 0, 0]}`

### `edit_material`

Edit an existing material's properties.

**Params:**
```json
{
  "name": "RedMat",
  "base_color": [0, 1, 0],
  "roughness": 0.2,
  "metallic": 0.8,
  "emission_strength": 2.0
}
```

### `get_material_info`

**Params:** `{"name": "RedMat"}`

**Returns:**
```json
{"name": "RedMat", "has_nodes": true, "base_color": [1,0,0], "roughness": 0.5, "metallic": 0.0}
```

---

## Terrain

### `create_landscape`

**Params:**
```json
{
  "name": "Mountain",
  "size_x": 120,
  "size_y": 120,
  "max_height": 20,
  "noise_type": "ridged_multi_fractal",
  "H": 1.2,
  "lacunarity": 2.1,
  "octaves": 8,
  "subdivisions": 200
}
```

Noise types: `ridged_multi_fractal`, `multi_fractal`, `fractal`, `hybrid_multi_fractal`

### `thermal_erosion`

**Params:** `{"object": "Mountain", "iterations": 12, "talus_angle": 0.6}`

### `paint_vertex_colors`

**Params:**
```json
{
  "object": "Mountain",
  "low_color": [0.35, 0.33, 0.31],
  "high_color": [0.94, 0.95, 0.96],
  "threshold": 0.55,
  "blend": 0.25
}
```

### `shade_smooth`

**Params:** `{"object": "Mountain"}`

### `compute_normals`

**Params:** `{"object": "Mountain"}`

---

## Modifiers

### `add_modifier`

**Params:** `{"object": "Cube", "type": "SUBSURF", "name": "Subdivision"}`

Common types: `SUBSURF`, `DISPLACE`, `SOLIDIFY`, `BEVEL`, `DECIMATE`, `ARRAY`, `MIRROR`

### `remove_modifier`

**Params:** `{"object": "Cube", "modifier": "Subdivision"}`

### `apply_modifier`

**Params:** `{"object": "Cube", "modifier": "Subdivision"}`

---

## Animation

### `set_keyframe`

**Params:**
```json
{
  "object": "Cube",
  "frame": 1,
  "location": [0, 0, 0],
  "rotation": [0, 0, 0],
  "scale": [1, 1, 1]
}
```

### `clear_animation`

**Params:** `{"object": "Cube"}`

---

## Render

### `set_resolution`

**Params:** `{"x": 1920, "y": 1080}`

### `set_render_engine`

**Params:** `{"engine": "CYCLES"}`

Engines: `CYCLES`, `BLENDER_EEVEE_NEXT`

### `set_render_samples`

**Params:** `{"samples": 128}`

### `render_still`

**Params:** `{"filepath": "/path/to/render.png"}`

If filepath is omitted, renders without saving.

---

## Export

### `export_glb`

**Params:** `{"filepath": "/path/to/export.glb"}`

### `export_obj`

**Params:** `{"filepath": "/path/to/export.obj"}`

### `export_fbx`

**Params:** `{"filepath": "/path/to/export.fbx"}`

---

## Collections

### `create_collection`

**Params:** `{"name": "Assets"}`

### `move_to_collection`

**Params:** `{"object": "Cube", "collection": "Assets"}`

---

## Utilities

### `clear_scene`

Remove all objects and materials.

**Params:** None

### `list_commands`

Get all available command names.

**Params:** None

**Returns:** `{"commands": ["get_scene_info", "execute_code", ...]}`

---

## Using the Client

```python
from kimi_blender_terminal.mcp_bridge import get_client

client = get_client()
client.connect()

# Execute code
result = client.send_command("execute_code", {"code": "create_cube('Box')"})

# Get screenshot
ss = client.send_command("get_viewport_screenshot", {"max_size": 800})

# Query scene
scene = client.send_command("get_scene_info")

client.disconnect()
```
