# Kimi Blender Terminal — Full Command Reference

Complete reference for every operation, tool, and command available in v2.5.0.

---

## MCP Bridge Commands

Send JSON to `localhost:9742`. Format: `{"type": "<cmd>", "params": {...}}`

| Command | Description | Parameters |
|---|---|---|
| `execute_code` | Run Python code in Blender's main thread | `code` (string) |
| `get_scene_info` | Get scene summary | none |
| `get_object_info` | Get detailed object data | `name` (string) |
| `get_viewport_screenshot` | Capture 3D viewport as base64 PNG | `max_size` (int, default 800), `format` (string, default "png") |
| `list_commands` | List all available MCP commands | none |
| `list_tools` | List all registered ToolRegistry tools | none |

### Scene Management
| Command | Description | Parameters |
|---|---|---|
| `clear_scene` | Remove all objects | none |
| `create_collection` | Create a new collection | `name` (string) |
| `move_to_collection` | Move object to collection | `object` (string), `collection` (string) |

### Primitives
| Command | Description | Parameters |
|---|---|---|
| `create_cube` | Add a cube | `name`, `location` [x,y,z], `size` |
| `create_sphere` | Add a UV sphere | `name`, `location` [x,y,z], `radius` |
| `create_landscape` | Generate terrain mesh | `name`, `size_x`, `size_y`, `max_height`, `noise_type`, `H`, `lacunarity`, `octaves`, `subdivisions` |
| `create_camera` | Add a camera | `name`, `location` [x,y,z], `rotation` [x,y,z], `lens` |
| `create_light` | Add a light | `name`, `type` (SUN/POINT/SPOT/AREA), `location` [x,y,z], `energy`, `color` [r,g,b] |

### Object Manipulation
| Command | Description | Parameters |
|---|---|---|
| `select_object` | Select by name | `name` (string) |
| `deselect_all` | Deselect everything | none |
| `delete_object` | Delete an object | `name` (string) |
| `duplicate_object` | Duplicate an object | `name` (string), `new_name` (string, optional) |
| `rename_object` | Rename an object | `old_name` (string), `new_name` (string) |
| `move_object` | Set location | `name` (string), `location` [x,y,z] |
| `rotate_object` | Set rotation (radians) | `name` (string), `rotation` [x,y,z] |
| `scale_object` | Set scale | `name` (string), `scale` [x,y,z] |
| `apply_transforms` | Apply location/rotation/scale | `name` (string) |

### Materials
| Command | Description | Parameters |
|---|---|---|
| `create_material` | Create basic material | `name`, `color` [r,g,b], `roughness`, `metallic` |
| `create_pbr_material` | Create advanced PBR material | `name`, `base_color` [r,g,b], `roughness`, `metallic`, `use_vertex_color`, `coat`, `subsurface`, `emission` [r,g,b], `emission_strength` |
| `assign_material` | Assign material to object | `object_name`, `material_name` |
| `set_material_color` | Change object color | `object` (string), `color` [r,g,b] |
| `edit_material` | Edit existing material | `name` (string), plus any of: `base_color`, `roughness`, `metallic`, `emission_strength` |
| `get_material_info` | Get material properties | `name` (string) |
| `set_viewport_shading` | Set viewport mode | `mode` (MATERIAL/RENDERED/SOLID/WIREFRAME) |

### Terrain Pipeline
| Command | Description | Parameters |
|---|---|---|
| `thermal_erosion` | Erode terrain mesh | `object` (string), `iterations` (int), `talus_angle` (float) |
| `paint_vertex_colors` | Paint by height | `object` (string), `low_color` [r,g,b], `high_color` [r,g,b], `threshold`, `blend` |
| `shade_smooth` | Enable smooth shading | `object` (string) |
| `compute_normals` | Recalculate normals | `object` (string) |

### Modifiers
| Command | Description | Parameters |
|---|---|---|
| `add_modifier` | Add modifier to mesh | `object` (string), `type` (string), `name` (string, optional) |
| `remove_modifier` | Remove modifier | `object` (string), `modifier` (string) |
| `apply_modifier` | Apply modifier | `object` (string), `modifier` (string) |

### Camera
| Command | Description | Parameters |
|---|---|---|
| `set_active_camera` | Set scene camera | `name` (string) |
| `camera_look_at` | Point camera at target | `camera` (string), `target` (string) |

### Lights
| Command | Description | Parameters |
|---|---|---|
| `set_light_energy` | Change light power | `name` (string), `energy` (float) |
| `set_light_color` | Change light color | `name` (string), `color` [r,g,b] |

### Animation
| Command | Description | Parameters |
|---|---|---|
| `set_keyframe` | Insert keyframe | `object` (string), `frame` (int), `location` [x,y,z], `rotation` [x,y,z], `scale` [x,y,z] |
| `clear_animation` | Remove all keyframes | `object` (string) |

### Render
| Command | Description | Parameters |
|---|---|---|
| `set_resolution` | Set render resolution | `x` (int), `y` (int) |
| `set_render_engine` | Set engine | `engine` (CYCLES/BLENDER_EEVEE_NEXT/BLENDER_WORKBENCH) |
| `set_render_samples` | Set sample count | `samples` (int) |
| `render_still` | Render to file | `filepath` (string) |

### Export
| Command | Description | Parameters |
|---|---|---|
| `export_glb` | Export GLB | `filepath` (string) |
| `export_obj` | Export OBJ | `filepath` (string) |
| `export_fbx` | Export FBX | `filepath` (string) |

---

## Tool Registry (XML `<tool_call>`)

Format: `<tool_call><name>tool_name</name><arguments>{"key":"value"}</arguments></tool_call>`

| Tool | Description | Required Params |
|---|---|---|
| `get_scene_summary` | Compact scene summary | none |
| `get_selected_objects` | List selected objects | none |
| `get_object_details` | Detailed object info | `name` |
| `create_mesh_object` | Add primitive mesh | `type`, `name` |
| `create_text_object` | Add text object | `text` |
| `create_camera` | Add camera | `name` |
| `create_light` | Add light | `type`, `name` |
| `create_material` | Create PBR material | `name` |
| `assign_material` | Assign material | `object_name`, `material_name` |
| `move_object` | Move object | `name`, `location` |
| `rotate_object` | Rotate object | `name`, `rotation` |
| `scale_object` | Scale object | `name`, `scale` |
| `delete_object` | Delete object | `name` |
| `duplicate_object` | Duplicate object | `name` |
| `add_modifier` | Add modifier | `object_name`, `modifier_type` |
| `apply_modifier` | Apply modifier | `object_name`, `modifier_name` |
| `set_origin` | Set object origin | `object_name`, `mode` |
| `organize_into_collection` | Move to collection | `object_name`, `collection_name` |
| `set_render_engine` | Set render engine | `engine` |
| `set_resolution` | Set resolution | `width`, `height` |
| `set_camera` | Set active camera | `camera_name` |
| `render_still` | Render image | `output_path` |
| `render_viewport_preview` | Viewport screenshot | `output_path` |
| `save_blend_file` | Save .blend | `path` |
| `open_blend_file` | Open .blend | `path` |
| `run_blender_python` | Execute Python | `code` |
| `validate_blender_python` | Validate code | `code` |

---

## Executor Helpers (Python Code Blocks)

Available inside `execute_code` and ```python blocks.

| Function | Description |
|---|---|
| `create_cube(name, location, size)` | Add cube |
| `create_sphere(name, location, radius)` | Add UV sphere |
| `create_landscape(name, size_x, size_y, max_height, ...)` | Generate terrain |
| `create_pbr_material(name, base_color, roughness, metallic, ...)` | Create PBR material |
| `set_material_color(obj, color)` | Set object color |
| `assign_mat(obj, mat)` | Assign material |
| `thermal_erosion(obj, iterations, talus_angle)` | Erode terrain |
| `paint_vertex_colors_by_height(obj, low_color, high_color, ...)` | Paint by height |
| `shade_smooth(obj)` | Smooth shading |
| `compute_vertex_normals(obj)` | Recalculate normals |
| `add_displace_modifier(obj, strength, scale, seed)` | Add displacement |
| `export_glb(filepath)` | Export GLB |
| `export_web_scene(output_dir, title, auto_rotate, ...)` | Export Three.js web page |
| `create_3d_text(text, name, location, font_size, ...)` | Create 3D text |
| `create_bar_chart_3d(labels, values, ...)` | 3D bar chart |
| `create_scatter_plot_3d(data, x_col, y_col, z_col, ...)` | 3D scatter plot |
| `create_line_graph_3d(data, x_col, y_col, ...)` | 3D line graph |
| `import_csv_data(filepath, max_rows)` | Read CSV |
| `search_blenderkit(keywords, asset_type, ...)` | Search BlenderKit |
| `download_blenderkit_asset(asset_id, location, scale)` | Download asset |
| `_fuzzy_find(name)` | Fuzzy object lookup |
| `_sync_scene()` | Update view layer |
| `_ensure_object_mode()` | Switch to object mode |
| `set_viewport_shading(mode)` | Set viewport mode |

### Color Constants
`RED`, `GREEN`, `BLUE`, `YELLOW`, `ORANGE`, `WHITE`, `BLACK`, `GREY`, `SILVER`, `GOLD`, `CYAN`, `MAGENTA`, `PURPLE`, `PINK`, `BROWN`

---

## CLI Bridge Arguments

```bash
python cli_bridge.py "prompt" [options]
```

| Argument | Default | Description |
|---|---|---|
| `prompt` | — | Text prompt to send to Kimi |
| `--prompt-file, -f` | — | Read prompt from file |
| `--host` | `localhost` | Blender MCP host |
| `--port` | `9742` | Blender MCP port |
| `--turns` | `5` | Max autonomous turns |
| `--timeout` | `300` | CLI timeout (seconds) |
| `--screenshots, -s` | — | Screenshot save directory |
| `--save-blend` | `False` | Auto-save every 2 turns |
| `--verbose, -v` | `False` | Show thinking + code |
| `--blend` | — | Open .blend before running |
| `--list-tools` | — | List tools and exit |
