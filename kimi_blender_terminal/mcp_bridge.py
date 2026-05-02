"""
MCP Bridge — Embedded socket server for Blender command execution.

Runs a JSON-over-TCP server inside Blender so the conversation agent
can execute commands, capture screenshots, and query scene state
without spawning subprocesses per operation.

Architecture:
    ConversationAgent → TCP socket → mcp_bridge → Blender main thread

This gives us:
  - Persistent connection (faster than exec-per-call)
  - Viewport screenshots (visual feedback)
  - Structured scene queries
  - Reliable execution in Blender's main thread
"""

import bpy
import json
import socket
import threading
import time
import traceback
import base64
import tempfile
import os
import mathutils
import math
import io
from contextlib import redirect_stdout

from . import executor

DEFAULT_PORT = 9742

# ═════════════════════════════════════════════════════════════════════════════
# COMMAND HANDLERS — map JSON commands to Blender operations
# ═════════════════════════════════════════════════════════════════════════════

class CommandRegistry:
    def __init__(self):
        self._handlers = {}

    def register(self, name, fn):
        self._handlers[name] = fn

    def get(self, name):
        return self._handlers.get(name)

    def list_commands(self):
        return sorted(self._handlers.keys())


_registry = CommandRegistry()


def _handler(name):
    """Decorator to register a command handler."""
    def decorator(fn):
        _registry.register(name, fn)
        return fn
    return decorator


# ── Scene ──

@_handler("get_scene_info")
def _get_scene_info(params):
    scene = bpy.context.scene
    objects = []
    for i, obj in enumerate(scene.objects):
        if i >= 20:
            break
        objects.append({
            "name": obj.name,
            "type": obj.type,
            "location": [round(obj.location.x, 2), round(obj.location.y, 2), round(obj.location.z, 2)],
        })
    return {
        "name": scene.name,
        "object_count": len(scene.objects),
        "objects": objects,
        "materials_count": len(bpy.data.materials),
        "camera": scene.camera.name if scene.camera else None,
        "engine": scene.render.engine,
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
    }


@_handler("get_object_info")
def _get_object_info(params):
    name = params.get("name")
    obj = bpy.data.objects.get(name)
    if not obj:
        return {"error": f"Object not found: {name}"}

    info = {
        "name": obj.name,
        "type": obj.type,
        "location": [obj.location.x, obj.location.y, obj.location.z],
        "rotation": [obj.rotation_euler.x, obj.rotation_euler.y, obj.rotation_euler.z],
        "scale": [obj.scale.x, obj.scale.y, obj.scale.z],
        "visible": obj.visible_get(),
        "materials": [s.material.name for s in obj.material_slots if s.material],
    }
    if obj.type == "MESH" and obj.data:
        mesh = obj.data
        info["mesh"] = {
            "vertices": len(mesh.vertices),
            "edges": len(mesh.edges),
            "polygons": len(mesh.polygons),
        }
        # Bounding box
        local_corners = [mathutils.Vector(c) for c in obj.bound_box]
        world_corners = [obj.matrix_world @ c for c in local_corners]
        mins = [min(c[i] for c in world_corners) for i in range(3)]
        maxs = [max(c[i] for c in world_corners) for i in range(3)]
        info["world_bounding_box"] = [mins, maxs]
    # CRITICAL: EMPTY objects often contain mesh children (GLTF imports)
    if obj.type == "EMPTY" and obj.children:
        info["children"] = [{"name": c.name, "type": c.type} for c in obj.children]
    return info


# ── Execution ──

@_handler("execute_code")
def _execute_code(params):
    code = params.get("code", "")
    if not code.strip():
        return {"error": "No code provided"}
    result = executor.execute_blender_python(code, allow_dangerous=False)
    return {
        "executed": result.get("status") == "success",
        "status": result.get("status"),
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
        "message": result.get("message", ""),
        "traceback": result.get("traceback", ""),
    }


# ── Viewport Screenshot ──

@_handler("get_viewport_screenshot")
def _get_viewport_screenshot(params):
    """Capture 3D viewport and return base64 PNG."""
    max_size = params.get("max_size", 800)
    fmt = params.get("format", "png")

    area = None
    for a in bpy.context.screen.areas:
        if a.type == "VIEW_3D":
            area = a
            break
    if not area:
        return {"error": "No 3D viewport found"}

    # Temp file
    with tempfile.NamedTemporaryFile(suffix=f".{fmt}", prefix="blender_screenshot_", delete=False) as tmp:
        temp_path = tmp.name

    try:
        with bpy.context.temp_override(area=area):
            bpy.ops.screen.screenshot_area(filepath=temp_path)

        # Load, resize if needed
        img = bpy.data.images.load(temp_path)
        width, height = img.size
        if max(width, height) > max_size:
            scale = max_size / max(width, height)
            new_w = int(width * scale)
            new_h = int(height * scale)
            img.scale(new_w, new_h)
            width, height = new_w, new_h

        # Save resized
        img.file_format = fmt.upper()
        img.save()
        bpy.data.images.remove(img)

        # Read back as base64
        with open(temp_path, "rb") as f:
            data = f.read()
        os.unlink(temp_path)

        return {
            "success": True,
            "width": width,
            "height": height,
            "format": fmt,
            "image_data": base64.b64encode(data).decode("ascii"),
        }
    except Exception as e:
        traceback.print_exc()
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        return {"error": str(e)}


# ── Helpers exposed as commands ──

@_handler("clear_scene")
def _cmd_clear_scene(params):
    executor._clear_scene()
    return {"cleared": True}


@_handler("create_cube")
def _cmd_create_cube(params):
    obj = executor._create_cube(
        name=params.get("name", "Cube"),
        location=tuple(params.get("location", [0, 0, 0])),
        size=params.get("size", 2.0),
    )
    return {"name": obj.name, "location": list(obj.location)}


@_handler("create_sphere")
def _cmd_create_sphere(params):
    obj = executor._create_sphere(
        name=params.get("name", "Sphere"),
        location=tuple(params.get("location", [0, 0, 0])),
        radius=params.get("radius", 1.0),
    )
    return {"name": obj.name, "location": list(obj.location)}


@_handler("create_material")
def _cmd_create_material(params):
    mat = executor._create_material(
        name=params.get("name", "Material"),
        color=tuple(params.get("color", [0.8, 0.8, 0.8])),
        roughness=params.get("roughness", 0.5),
        metallic=params.get("metallic", 0.0),
    )
    return {"name": mat.name}


@_handler("assign_material")
def _cmd_assign_material(params):
    obj = executor._assign_material(params.get("object_name"), params.get("material_name"))
    return {"assigned": obj is not None}


@_handler("set_material_color")
def _cmd_set_material_color(params):
    obj_name = params.get("object")
    color = tuple(params.get("color", [1, 0, 0]))
    mat = executor._set_material_color(obj_name, color)
    return {"name": mat.name if mat else None}


@_handler("set_viewport_shading")
def _cmd_set_viewport_shading(params):
    mode = params.get("mode", "MATERIAL")
    ok = executor._set_viewport_shading(mode)
    return {"set": ok}


@_handler("create_pbr_material")
def _cmd_create_pbr_material(params):
    mat = executor._create_pbr_material(
        name=params.get("name", "PBR"),
        base_color=tuple(params.get("base_color", [0.8, 0.8, 0.8])),
        roughness=params.get("roughness", 0.8),
        metallic=params.get("metallic", 0.0),
        use_vertex_color=params.get("use_vertex_color", False),
        coat=params.get("coat", 0.0),
        subsurface=params.get("subsurface", 0.0),
        emission=tuple(params.get("emission", [0, 0, 0])),
        emission_strength=params.get("emission_strength", 0.0),
    )
    return {"name": mat.name}


@_handler("create_landscape")
def _cmd_create_landscape(params):
    obj = executor._create_landscape(
        name=params.get("name", "Landscape"),
        size_x=params.get("size_x", 100),
        size_y=params.get("size_y", 100),
        max_height=params.get("max_height", 10),
        noise_type=params.get("noise_type", "ridged_multi_fractal"),
        H=params.get("H", 1.0),
        lacunarity=params.get("lacunarity", 2.0),
        octaves=params.get("octaves", 8),
        subdivisions=params.get("subdivisions", 200),
    )
    return {"name": obj.name}


@_handler("thermal_erosion")
def _cmd_thermal_erosion(params):
    executor._thermal_erosion(
        params.get("object"),
        iterations=params.get("iterations", 12),
        talus_angle=params.get("talus_angle", 0.6),
    )
    return {"applied": True}


@_handler("paint_vertex_colors")
def _cmd_paint_vertex_colors(params):
    executor._paint_vertex_colors_by_height(
        params.get("object"),
        low_color=tuple(params.get("low_color", [0.5, 0.5, 0.5])),
        high_color=tuple(params.get("high_color", [1.0, 1.0, 1.0])),
        threshold=params.get("threshold", 0.55),
        blend=params.get("blend", 0.25),
    )
    return {"painted": True}


@_handler("shade_smooth")
def _cmd_shade_smooth(params):
    executor._shade_smooth(params.get("object"))
    return {"smoothed": True}


@_handler("compute_normals")
def _cmd_compute_normals(params):
    executor._compute_vertex_normals(params.get("object"))
    return {"computed": True}


@_handler("export_glb")
def _cmd_export_glb(params):
    path = params.get("filepath", "")
    executor._export_glb(path)
    return {"exported": path}


@_handler("list_commands")
def _cmd_list_commands(params):
    return {"commands": _registry.list_commands()}


@_handler("list_tools")
def _cmd_list_tools(params):
    """Return all registered ToolRegistry tools for external CLI use."""
    from . import tool_registry
    tools = []
    for name, t in tool_registry.REGISTRY.items():
        tools.append({
            "name": name,
            "description": t.get("description", ""),
            "parameters": t.get("parameters", {}),
        })
    return {"tools": tools}


@_handler("execute_tool")
def _cmd_execute_tool(params):
    """Execute a ToolRegistry tool by name with given arguments."""
    from . import tool_registry
    import json, traceback
    name = params.get("name")
    arguments = params.get("arguments", {})
    try:
        result = tool_registry.execute_tool(name, arguments)
        return {
            "executed": True,
            "status": "success",
            "stdout": json.dumps(result),
            "stderr": "",
            "message": "",
            "traceback": "",
        }
    except Exception as e:
        tb = traceback.format_exc()
        return {
            "executed": False,
            "status": "error",
            "stdout": "",
            "stderr": tb,
            "message": str(e),
            "traceback": tb,
        }


# ── Object Manipulation ──

@_handler("select_object")
def _cmd_select_object(params):
    name = params.get("name")
    obj = bpy.data.objects.get(name)
    if obj:
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        return {"selected": True}
    return {"error": f"Object not found: {name}"}


@_handler("deselect_all")
def _cmd_deselect_all(params):
    bpy.ops.object.select_all(action="DESELECT")
    return {"deselected": True}


@_handler("delete_object")
def _cmd_delete_object(params):
    name = params.get("name")
    obj = bpy.data.objects.get(name)
    if obj:
        bpy.data.objects.remove(obj, do_unlink=True)
        return {"deleted": True}
    return {"error": f"Object not found: {name}"}


@_handler("duplicate_object")
def _cmd_duplicate_object(params):
    name = params.get("name")
    obj = bpy.data.objects.get(name)
    if not obj:
        return {"error": f"Object not found: {name}"}
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.ops.object.duplicate()
    new_obj = bpy.context.active_object
    if new_obj:
        new_obj.name = params.get("new_name", f"{name}.001")
        return {"name": new_obj.name, "location": list(new_obj.location)}
    return {"error": "Duplicate failed"}


@_handler("rename_object")
def _cmd_rename_object(params):
    old = params.get("old_name")
    new = params.get("new_name")
    obj = bpy.data.objects.get(old)
    if obj:
        obj.name = new
        return {"renamed": True, "name": new}
    return {"error": f"Object not found: {old}"}


@_handler("move_object")
def _cmd_move_object(params):
    name = params.get("name")
    loc = params.get("location", [0, 0, 0])
    obj = bpy.data.objects.get(name)
    if obj:
        obj.location = tuple(loc)
        return {"location": list(obj.location)}
    return {"error": f"Object not found: {name}"}


@_handler("rotate_object")
def _cmd_rotate_object(params):
    name = params.get("name")
    rot = params.get("rotation", [0, 0, 0])
    obj = bpy.data.objects.get(name)
    if obj:
        obj.rotation_euler = tuple(rot)
        return {"rotation": list(obj.rotation_euler)}
    return {"error": f"Object not found: {name}"}


@_handler("scale_object")
def _cmd_scale_object(params):
    name = params.get("name")
    scl = params.get("scale", [1, 1, 1])
    obj = bpy.data.objects.get(name)
    if obj:
        obj.scale = tuple(scl)
        return {"scale": list(obj.scale)}
    return {"error": f"Object not found: {name}"}


@_handler("apply_transforms")
def _cmd_apply_transforms(params):
    name = params.get("name")
    obj = bpy.data.objects.get(name)
    if not obj:
        return {"error": f"Object not found: {name}"}
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return {"applied": True}


# ── Camera ──

@_handler("create_camera")
def _cmd_create_camera(params):
    obj = executor._create_camera(
        name=params.get("name", "Camera"),
        location=tuple(params.get("location", [7, -7, 5])),
        rotation=tuple(params.get("rotation", [1.1, 0, 0.8])),
        lens=params.get("lens", 50),
    )
    return {"name": obj.name, "location": list(obj.location)}


@_handler("set_active_camera")
def _cmd_set_active_camera(params):
    name = params.get("name")
    obj = bpy.data.objects.get(name)
    if obj and obj.type == "CAMERA":
        bpy.context.scene.camera = obj
        return {"active": True}
    return {"error": f"Camera not found: {name}"}


@_handler("camera_look_at")
def _cmd_camera_look_at(params):
    cam_name = params.get("camera")
    target = params.get("target")
    cam = bpy.data.objects.get(cam_name)
    tgt = bpy.data.objects.get(target)
    if not cam:
        return {"error": f"Camera not found: {cam_name}"}
    if not tgt:
        return {"error": f"Target not found: {target}"}
    direction = tgt.location - cam.location
    rot_quat = direction.to_track_quat("-Z", "Y")
    cam.rotation_euler = rot_quat.to_euler()
    return {"rotation": list(cam.rotation_euler)}


# ── Lights ──

@_handler("create_light")
def _cmd_create_light(params):
    obj = executor._create_light(
        name=params.get("name", "Light"),
        type=params.get("type", "POINT"),
        location=tuple(params.get("location", [0, 0, 5])),
        energy=params.get("energy", 1000),
        color=tuple(params.get("color", [1, 1, 1])),
    )
    return {"name": obj.name, "type": obj.data.type, "location": list(obj.location)}


@_handler("set_light_energy")
def _cmd_set_light_energy(params):
    name = params.get("name")
    energy = params.get("energy", 1000)
    obj = bpy.data.objects.get(name)
    if obj and obj.type == "LIGHT":
        obj.data.energy = energy
        return {"energy": energy}
    return {"error": f"Light not found: {name}"}


@_handler("set_light_color")
def _cmd_set_light_color(params):
    name = params.get("name")
    color = tuple(params.get("color", [1, 1, 1]))
    obj = bpy.data.objects.get(name)
    if obj and obj.type == "LIGHT":
        obj.data.color = color
        return {"color": list(color)}
    return {"error": f"Light not found: {name}"}


# ── Material Editing ──

@_handler("edit_material")
def _cmd_edit_material(params):
    name = params.get("name")
    mat = bpy.data.materials.get(name)
    if not mat or not mat.use_nodes:
        return {"error": f"Material not found or no nodes: {name}"}
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if not bsdf:
        return {"error": "No Principled BSDF found"}
    if "base_color" in params:
        bsdf.inputs["Base Color"].default_value = (*tuple(params["base_color"]), 1.0)
    if "roughness" in params:
        bsdf.inputs["Roughness"].default_value = params["roughness"]
    if "metallic" in params:
        bsdf.inputs["Metallic"].default_value = params["metallic"]
    if "emission_strength" in params:
        bsdf.inputs["Emission Strength"].default_value = params["emission_strength"]
    return {"edited": True}


@_handler("get_material_info")
def _cmd_get_material_info(params):
    name = params.get("name")
    mat = bpy.data.materials.get(name)
    if not mat or not mat.use_nodes:
        return {"error": f"Material not found: {name}"}
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    info = {"name": mat.name, "has_nodes": mat.use_nodes}
    if bsdf:
        info["base_color"] = list(bsdf.inputs["Base Color"].default_value)[:3]
        info["roughness"] = bsdf.inputs["Roughness"].default_value
        info["metallic"] = bsdf.inputs["Metallic"].default_value
    return info


# ── Render ──

@_handler("set_resolution")
def _cmd_set_resolution(params):
    x = params.get("x", 1920)
    y = params.get("y", 1080)
    bpy.context.scene.render.resolution_x = x
    bpy.context.scene.render.resolution_y = y
    return {"resolution": [x, y]}


@_handler("set_render_engine")
def _cmd_set_render_engine(params):
    engine = params.get("engine", "CYCLES")
    bpy.context.scene.render.engine = engine
    return {"engine": engine}


@_handler("set_render_samples")
def _cmd_set_render_samples(params):
    samples = params.get("samples", 128)
    scene = bpy.context.scene
    if scene.render.engine == "CYCLES":
        scene.cycles.samples = samples
    return {"samples": samples}


@_handler("render_still")
def _cmd_render_still(params):
    filepath = params.get("filepath", "")
    if filepath:
        bpy.context.scene.render.filepath = filepath
    bpy.ops.render.render(write_still=bool(filepath))
    return {"rendered": True, "filepath": filepath or bpy.context.scene.render.filepath}


# ── Modifiers ──

@_handler("add_modifier")
def _cmd_add_modifier(params):
    name = params.get("object")
    mod_type = params.get("type")
    mod_name = params.get("name")
    obj = bpy.data.objects.get(name)
    if not obj or obj.type != "MESH":
        return {"error": f"Mesh object not found: {name}"}
    mod = obj.modifiers.new(name=mod_name or mod_type, type=mod_type)
    return {"modifier": mod.name, "type": mod.type}


@_handler("remove_modifier")
def _cmd_remove_modifier(params):
    name = params.get("object")
    mod_name = params.get("modifier")
    obj = bpy.data.objects.get(name)
    if not obj:
        return {"error": f"Object not found: {name}"}
    mod = obj.modifiers.get(mod_name)
    if mod:
        obj.modifiers.remove(mod)
        return {"removed": True}
    return {"error": f"Modifier not found: {mod_name}"}


@_handler("apply_modifier")
def _cmd_apply_modifier(params):
    name = params.get("object")
    mod_name = params.get("modifier")
    obj = bpy.data.objects.get(name)
    if not obj:
        return {"error": f"Object not found: {name}"}
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.modifier_apply(modifier=mod_name)
        return {"applied": True}
    except Exception as e:
        return {"error": str(e)}


# ── Animation ──

@_handler("set_keyframe")
def _cmd_set_keyframe(params):
    name = params.get("object")
    frame = params.get("frame")
    location = params.get("location")
    rotation = params.get("rotation")
    scale = params.get("scale")
    obj = bpy.data.objects.get(name)
    if not obj:
        return {"error": f"Object not found: {name}"}
    if frame is not None:
        bpy.context.scene.frame_set(frame)
    if location:
        obj.location = tuple(location)
        obj.keyframe_insert(data_path="location")
    if rotation:
        obj.rotation_euler = tuple(rotation)
        obj.keyframe_insert(data_path="rotation_euler")
    if scale:
        obj.scale = tuple(scale)
        obj.keyframe_insert(data_path="scale")
    return {"keyframed": True, "frame": bpy.context.scene.frame_current}


@_handler("clear_animation")
def _cmd_clear_animation(params):
    name = params.get("object")
    obj = bpy.data.objects.get(name)
    if not obj:
        return {"error": f"Object not found: {name}"}
    obj.animation_data_clear()
    return {"cleared": True}


# ── Export ──

@_handler("export_obj")
def _cmd_export_obj(params):
    filepath = params.get("filepath", "")
    bpy.ops.wm.obj_export(filepath=filepath)
    return {"exported": filepath}


@_handler("export_fbx")
def _cmd_export_fbx(params):
    filepath = params.get("filepath", "")
    bpy.ops.export_scene.fbx(filepath=filepath)
    return {"exported": filepath}


# ── Collections ──

@_handler("create_collection")
def _cmd_create_collection(params):
    name = params.get("name", "Collection")
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return {"name": col.name}


@_handler("move_to_collection")
def _cmd_move_to_collection(params):
    obj_name = params.get("object")
    col_name = params.get("collection")
    obj = bpy.data.objects.get(obj_name)
    col = bpy.data.collections.get(col_name)
    if not obj:
        return {"error": f"Object not found: {obj_name}"}
    if not col:
        return {"error": f"Collection not found: {col_name}"}
    # Unlink from all collections
    for c in bpy.data.collections:
        if obj.name in c.objects:
            c.objects.unlink(obj)
    col.objects.link(obj)
    return {"moved": True}


# ═════════════════════════════════════════════════════════════════════════════
# SOCKET SERVER — runs inside Blender
# ═════════════════════════════════════════════════════════════════════════════

class BridgeServer:
    def __init__(self, host="localhost", port=DEFAULT_PORT):
        self.host = host
        self.port = port
        self.running = False
        self.socket = None
        self.server_thread = None

    def start(self):
        if self.running:
            print("[Kimi MCP Bridge] Server already running")
            return
        self.running = True
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.listen(1)
            self.server_thread = threading.Thread(target=self._server_loop, daemon=True)
            self.server_thread.start()
            print(f"[Kimi MCP Bridge] Server started on {self.host}:{self.port}")
        except Exception as e:
            print(f"[Kimi MCP Bridge] Failed to start: {e}")
            self.stop()

    def stop(self):
        self.running = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        if self.server_thread:
            try:
                if self.server_thread.is_alive():
                    self.server_thread.join(timeout=1.0)
            except:
                pass
            self.server_thread = None
        print("[Kimi MCP Bridge] Server stopped")

    def _server_loop(self):
        self.socket.settimeout(1.0)
        while self.running:
            try:
                client, address = self.socket.accept()
                print(f"[Kimi MCP Bridge] Client connected: {address}")
                client_thread = threading.Thread(
                    target=self._handle_client, args=(client,), daemon=True
                )
                client_thread.start()
            except socket.timeout:
                continue
            except Exception as e:
                print(f"[Kimi MCP Bridge] Accept error: {e}")
                time.sleep(0.5)

    def _handle_client(self, client):
        client.settimeout(None)
        buffer = b""
        try:
            while self.running:
                data = client.recv(65536)
                if not data:
                    break
                buffer += data
                try:
                    command = json.loads(buffer.decode("utf-8"))
                    buffer = b""

                    def execute_wrapper():
                        try:
                            response = self._execute_command(command)
                            response_json = json.dumps(response)
                            try:
                                client.sendall(response_json.encode("utf-8"))
                            except:
                                pass
                        except Exception as e:
                            traceback.print_exc()
                            try:
                                err = json.dumps({"status": "error", "message": str(e)})
                                client.sendall(err.encode("utf-8"))
                            except:
                                pass

                    bpy.app.timers.register(execute_wrapper, first_interval=0.0)
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            print(f"[Kimi MCP Bridge] Client handler error: {e}")
        finally:
            try:
                client.close()
            except:
                pass

    def _execute_command(self, command):
        cmd_type = command.get("type")
        params = command.get("params", {})
        handler = _registry.get(cmd_type)
        if handler:
            result = handler(params)
            return {"status": "success", "result": result}
        return {"status": "error", "message": f"Unknown command: {cmd_type}"}


# ═════════════════════════════════════════════════════════════════════════════
# CLIENT — for the conversation agent to talk to the server
# ═════════════════════════════════════════════════════════════════════════════

class BridgeClient:
    """Client that connects to the Blender MCP server."""

    def __init__(self, host="localhost", port=DEFAULT_PORT):
        self.host = host
        self.port = port
        self.sock = None

    def connect(self):
        if self.sock:
            return True
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            self.sock.settimeout(60.0)
            return True
        except Exception as e:
            self.sock = None
            raise ConnectionError(f"Cannot connect to Blender MCP server at {self.host}:{self.port}. Is the addon enabled? {e}")

    def disconnect(self):
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None

    def send_command(self, command_type: str, params: dict = None) -> dict:
        if not self.sock and not self.connect():
            raise ConnectionError("Not connected to Blender")

        command = {"type": command_type, "params": params or {}}
        try:
            self.sock.sendall(json.dumps(command).encode("utf-8"))
            response_data = self._receive_full_response()
            response = json.loads(response_data.decode("utf-8"))
            if response.get("status") == "error":
                raise RuntimeError(response.get("message", "Unknown Blender error"))
            return response.get("result", {})
        except (ConnectionError, BrokenPipeError):
            self.sock = None
            raise

    def _receive_full_response(self, buffer_size=65536):
        chunks = []
        self.sock.settimeout(60.0)
        while True:
            try:
                chunk = self.sock.recv(buffer_size)
                if not chunk:
                    break
                chunks.append(chunk)
                try:
                    data = b"".join(chunks)
                    json.loads(data.decode("utf-8"))
                    return data
                except json.JSONDecodeError:
                    continue
            except socket.timeout:
                break
        if chunks:
            data = b"".join(chunks)
            try:
                json.loads(data.decode("utf-8"))
                return data
            except json.JSONDecodeError:
                raise Exception("Incomplete JSON response")
        raise Exception("No data received")


# ═════════════════════════════════════════════════════════════════════════════
# SINGLETON — managed by the addon
# ═════════════════════════════════════════════════════════════════════════════

_server_instance = None

def start_server(port=DEFAULT_PORT):
    global _server_instance
    if _server_instance is None:
        _server_instance = BridgeServer(port=port)
        _server_instance.start()
    return _server_instance


def stop_server():
    global _server_instance
    if _server_instance:
        _server_instance.stop()
        _server_instance = None


def get_client() -> BridgeClient:
    return BridgeClient(port=DEFAULT_PORT)


def is_running() -> bool:
    return _server_instance is not None and _server_instance.running
