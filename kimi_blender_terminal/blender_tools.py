"""
BlenderTools — implementations for every tool registered in the ToolRegistry.
"""

import bpy
import mathutils
import os
import tempfile

from . import tool_registry
from . import scene_context
from . import executor


def _resolve_object(name: str):
    obj = bpy.data.objects.get(name)
    if not obj:
        raise ValueError(f"Object not found: {name}")
    return obj


def _ensure_collection(name: str):
    col = bpy.data.collections.get(name)
    if not col:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


@tool_registry.tool(
    name="get_scene_summary",
    description="Return a compact summary of the current Blender scene.",
    params={"type": "object", "properties": {}}
)
def get_scene_summary():
    return scene_context.SceneContext.get_summary(force_refresh=True)


@tool_registry.tool(
    name="get_selected_objects",
    description="Return a list of currently selected objects.",
    params={"type": "object", "properties": {}}
)
def get_selected_objects():
    selected = [obj for obj in bpy.context.scene.objects if obj.select_get()]
    return [
        {"name": o.name, "type": o.type, "location": [o.location.x, o.location.y, o.location.z]}
        for o in selected
    ]


@tool_registry.tool(
    name="get_object_details",
    description="Get detailed information about a specific object.",
    params={
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Object name"}},
        "required": ["name"],
    }
)
def get_object_details(name: str):
    obj = _resolve_object(name)
    info = {
        "name": obj.name,
        "type": obj.type,
        "location": [round(obj.location.x, 3), round(obj.location.y, 3), round(obj.location.z, 3)],
        "rotation_euler": [round(obj.rotation_euler.x, 3), round(obj.rotation_euler.y, 3), round(obj.rotation_euler.z, 3)],
        "scale": [round(obj.scale.x, 3), round(obj.scale.y, 3), round(obj.scale.z, 3)],
        "visible": obj.visible_get(),
        "materials": [slot.material.name for slot in obj.material_slots if slot.material],
        "collections": [col.name for col in obj.users_collection],
    }
    if obj.type == "MESH" and obj.data:
        mesh = obj.data
        info["mesh"] = {
            "vertices": len(mesh.vertices),
            "edges": len(mesh.edges),
            "polygons": len(mesh.polygons),
        }
    if obj.type == "CAMERA" and obj.data:
        info["camera_data"] = {"lens": obj.data.lens, "type": obj.data.type}
    if obj.type == "LIGHT" and obj.data:
        info["light_data"] = {"type": obj.data.type, "energy": obj.data.energy, "color": list(obj.data.color)}
    return info


@tool_registry.tool(
    name="create_mesh_object",
    description="Create a primitive mesh object (cube, sphere, cylinder, cone, torus, plane).",
    params={
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": ["cube", "sphere", "cylinder", "cone", "torus", "plane"], "description": "Primitive type"},
            "name": {"type": "string", "description": "Desired object name"},
            "location": {"type": "array", "items": {"type": "number"}, "description": "[x, y, z]"},
            "size": {"type": "number", "description": "Size or radius"},
        },
        "required": ["type", "name"],
    }
)
def create_mesh_object(type: str, name: str, location: list = None, size: float = None):
    loc = tuple(location) if location else (0, 0, 0)
    if type == "cube":
        bpy.ops.mesh.primitive_cube_add(location=loc, size=size or 2.0)
    elif type == "sphere":
        bpy.ops.mesh.primitive_uv_sphere_add(location=loc, radius=size or 1.0)
    elif type == "cylinder":
        bpy.ops.mesh.primitive_cylinder_add(location=loc, radius=size or 1.0, depth=2.0)
    elif type == "cone":
        bpy.ops.mesh.primitive_cone_add(location=loc, radius1=size or 1.0, depth=2.0)
    elif type == "torus":
        bpy.ops.mesh.primitive_torus_add(location=loc, major_radius=size or 1.0, minor_radius=(size or 1.0) * 0.25)
    elif type == "plane":
        bpy.ops.mesh.primitive_plane_add(location=loc, size=size or 2.0)
    else:
        raise ValueError(f"Unknown mesh type: {type}")
    obj = bpy.context.active_object
    obj.name = name
    return {"name": obj.name, "type": obj.type, "location": list(obj.location)}


@tool_registry.tool(
    name="create_text_object",
    description="Create a text object in the scene.",
    params={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "name": {"type": "string"},
            "location": {"type": "array", "items": {"type": "number"}},
            "size": {"type": "number"},
        },
        "required": ["text"],
    }
)
def create_text_object(text: str, name: str = None, location: list = None, size: float = None):
    loc = tuple(location) if location else (0, 0, 0)
    bpy.ops.object.text_add(location=loc)
    obj = bpy.context.active_object
    obj.data.body = text
    if name:
        obj.name = name
    if size:
        obj.data.size = size
    return {"name": obj.name, "text": obj.data.body, "location": list(obj.location)}


@tool_registry.tool(
    name="create_camera",
    description="Create a camera object.",
    params={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "location": {"type": "array", "items": {"type": "number"}},
            "rotation": {"type": "array", "items": {"type": "number"}, "description": "Euler angles [x, y, z] in radians"},
            "focal_length": {"type": "number"},
        },
        "required": ["name"],
    }
)
def create_camera(name: str, location: list = None, rotation: list = None, focal_length: float = None):
    loc = tuple(location) if location else (7, -7, 5)
    rot = tuple(rotation) if rotation else (1.1, 0, 0.8)
    bpy.ops.object.camera_add(location=loc, rotation=rot)
    obj = bpy.context.active_object
    obj.name = name
    if focal_length and obj.data:
        obj.data.lens = focal_length
    return {"name": obj.name, "location": list(obj.location), "rotation": list(obj.rotation_euler), "lens": obj.data.lens}


@tool_registry.tool(
    name="create_light",
    description="Create a light (SUN, POINT, SPOT, AREA).",
    params={
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": ["SUN", "POINT", "SPOT", "AREA"]},
            "name": {"type": "string"},
            "location": {"type": "array", "items": {"type": "number"}},
            "energy": {"type": "number"},
            "color": {"type": "array", "items": {"type": "number"}, "description": "[R, G, B] 0-1"},
        },
        "required": ["type", "name"],
    }
)
def create_light(type: str, name: str, location: list = None, energy: float = None, color: list = None):
    loc = tuple(location) if location else (0, 0, 5)
    bpy.ops.object.light_add(type=type, location=loc)
    obj = bpy.context.active_object
    obj.name = name
    if energy and obj.data:
        obj.data.energy = energy
    if color and obj.data:
        obj.data.color = tuple(color)
    return {"name": obj.name, "light_type": obj.data.type, "energy": obj.data.energy, "color": list(obj.data.color)}


@tool_registry.tool(
    name="create_material",
    description="Create a Principled BSDF material with basic properties.",
    params={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "color": {"type": "array", "items": {"type": "number"}, "description": "Base color [R, G, B] 0-1"},
            "roughness": {"type": "number"},
            "metallic": {"type": "number"},
            "emission": {"type": "array", "items": {"type": "number"}, "description": "Emission color [R, G, B]"},
            "emission_strength": {"type": "number"},
        },
        "required": ["name"],
    }
)
def create_material(name: str, color: list = None, roughness: float = None, metallic: float = None, emission: list = None, emission_strength: float = None):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    principled = nodes.get("Principled BSDF")
    if not principled:
        principled = nodes.new(type="ShaderNodeBsdfPrincipled")
        output = nodes.get("Material Output") or nodes.new(type="ShaderNodeOutputMaterial")
        mat.node_tree.links.new(principled.outputs["BSDF"], output.inputs["Surface"])
    if color:
        principled.inputs["Base Color"].default_value = (*tuple(color), 1.0)
    if roughness is not None:
        principled.inputs["Roughness"].default_value = roughness
    if metallic is not None:
        principled.inputs["Metallic"].default_value = metallic
    if emission:
        if "Emission Color" in principled.inputs:
            principled.inputs["Emission Color"].default_value = (*tuple(emission), 1.0)
        elif "Emission" in principled.inputs:
            principled.inputs["Emission"].default_value = (*tuple(emission), 1.0)
    if emission_strength is not None:
        principled.inputs["Emission Strength"].default_value = emission_strength
    return {"name": mat.name, "color": list(principled.inputs["Base Color"].default_value)[:3]}


@tool_registry.tool(
    name="assign_material",
    description="Assign a material to an object.",
    params={
        "type": "object",
        "properties": {
            "object_name": {"type": "string"},
            "material_name": {"type": "string"},
        },
        "required": ["object_name", "material_name"],
    }
)
def assign_material(object_name: str, material_name: str):
    obj = _resolve_object(object_name)
    mat = bpy.data.materials.get(material_name)
    if not mat:
        raise ValueError(f"Material not found: {material_name}")
    if obj.type != "MESH":
        raise ValueError("Can only assign materials to mesh objects")
    if len(obj.material_slots) == 0:
        obj.data.materials.append(mat)
    else:
        obj.material_slots[0].material = mat
    return {"object": obj.name, "material": mat.name}


@tool_registry.tool(
    name="move_object",
    description="Move an object to a new location.",
    params={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "location": {"type": "array", "items": {"type": "number"}},
        },
        "required": ["name", "location"],
    }
)
def move_object(name: str, location: list):
    obj = _resolve_object(name)
    obj.location = tuple(location)
    return {"name": obj.name, "location": list(obj.location)}


@tool_registry.tool(
    name="rotate_object",
    description="Set an object's rotation in Euler angles (radians).",
    params={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "rotation": {"type": "array", "items": {"type": "number"}, "description": "[x, y, z] in radians"},
        },
        "required": ["name", "rotation"],
    }
)
def rotate_object(name: str, rotation: list):
    obj = _resolve_object(name)
    obj.rotation_euler = tuple(rotation)
    return {"name": obj.name, "rotation": list(obj.rotation_euler)}


@tool_registry.tool(
    name="scale_object",
    description="Set an object's scale.",
    params={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "scale": {"type": "array", "items": {"type": "number"}, "description": "[x, y, z]"},
        },
        "required": ["name", "scale"],
    }
)
def scale_object(name: str, scale: list):
    obj = _resolve_object(name)
    obj.scale = tuple(scale)
    return {"name": obj.name, "scale": list(obj.scale)}


@tool_registry.tool(
    name="delete_object",
    description="Delete an object from the scene.",
    params={
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }
)
def delete_object(name: str):
    obj = _resolve_object(name)
    bpy.data.objects.remove(obj, do_unlink=True)
    return {"deleted": name}


@tool_registry.tool(
    name="duplicate_object",
    description="Duplicate an object.",
    params={
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }
)
def duplicate_object(name: str):
    obj = _resolve_object(name)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.ops.object.duplicate()
    new_obj = bpy.context.active_object
    return {"original": name, "duplicate": new_obj.name, "location": list(new_obj.location)}


@tool_registry.tool(
    name="add_modifier",
    description="Add a modifier to a mesh object.",
    params={
        "type": "object",
        "properties": {
            "object_name": {"type": "string"},
            "modifier_type": {"type": "string", "enum": ["SUBSURF", "MIRROR", "ARRAY", "SOLIDIFY", "BEVEL", "BOOLEAN", "DISPLACE", "WIREFRAME"]},
            "name": {"type": "string"},
        },
        "required": ["object_name", "modifier_type"],
    }
)
def add_modifier(object_name: str, modifier_type: str, name: str = None):
    obj = _resolve_object(object_name)
    if obj.type != "MESH":
        raise ValueError("Modifiers can only be added to mesh objects")
    mod = obj.modifiers.new(name=name or modifier_type, type=modifier_type)
    return {"object": obj.name, "modifier": mod.name, "type": mod.type}


@tool_registry.tool(
    name="apply_modifier",
    description="Apply a modifier by name.",
    params={
        "type": "object",
        "properties": {
            "object_name": {"type": "string"},
            "modifier_name": {"type": "string"},
        },
        "required": ["object_name", "modifier_name"],
    }
)
def apply_modifier(object_name: str, modifier_name: str):
    obj = _resolve_object(object_name)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=modifier_name)
    return {"object": obj.name, "applied": modifier_name}


@tool_registry.tool(
    name="set_origin",
    description="Set the origin of an object (geometry_to_origin, origin_to_geometry, origin_to_cursor).",
    params={
        "type": "object",
        "properties": {
            "object_name": {"type": "string"},
            "mode": {"type": "string", "enum": ["GEOMETRY_ORIGIN", "ORIGIN_GEOMETRY", "ORIGIN_CURSOR"]},
        },
        "required": ["object_name", "mode"],
    }
)
def set_origin(object_name: str, mode: str):
    obj = _resolve_object(object_name)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.origin_set(type=mode)
    return {"object": obj.name, "origin_mode": mode}


@tool_registry.tool(
    name="organize_into_collection",
    description="Move an object into a named collection (create if missing).",
    params={
        "type": "object",
        "properties": {
            "object_name": {"type": "string"},
            "collection_name": {"type": "string"},
        },
        "required": ["object_name", "collection_name"],
    }
)
def organize_into_collection(object_name: str, collection_name: str):
    obj = _resolve_object(object_name)
    col = _ensure_collection(collection_name)
    # Unlink from all current collections
    for c in obj.users_collection:
        c.objects.unlink(obj)
    col.objects.link(obj)
    return {"object": obj.name, "collection": col.name}


@tool_registry.tool(
    name="set_render_engine",
    description="Set the render engine (CYCLES, BLENDER_EEVEE_NEXT, WORKBENCH).",
    params={
        "type": "object",
        "properties": {"engine": {"type": "string", "enum": ["CYCLES", "BLENDER_EEVEE_NEXT", "BLENDER_WORKBENCH"]}},
        "required": ["engine"],
    }
)
def set_render_engine(engine: str):
    bpy.context.scene.render.engine = engine
    return {"engine": bpy.context.scene.render.engine}


@tool_registry.tool(
    name="set_resolution",
    description="Set render resolution.",
    params={
        "type": "object",
        "properties": {
            "width": {"type": "integer"},
            "height": {"type": "integer"},
        },
        "required": ["width", "height"],
    }
)
def set_resolution(width: int, height: int):
    bpy.context.scene.render.resolution_x = width
    bpy.context.scene.render.resolution_y = height
    return {"resolution": [bpy.context.scene.render.resolution_x, bpy.context.scene.render.resolution_y]}


@tool_registry.tool(
    name="set_camera",
    description="Set the active scene camera by object name.",
    params={
        "type": "object",
        "properties": {"camera_name": {"type": "string"}},
        "required": ["camera_name"],
    }
)
def set_camera(camera_name: str):
    obj = _resolve_object(camera_name)
    if obj.type != "CAMERA":
        raise ValueError(f"{camera_name} is not a camera")
    bpy.context.scene.camera = obj
    return {"camera": obj.name}


@tool_registry.tool(
    name="render_still",
    description="Render a still image to a file path. Returns the output path.",
    params={
        "type": "object",
        "properties": {"output_path": {"type": "string"}},
        "required": ["output_path"],
    }
)
def render_still(output_path: str):
    bpy.context.scene.render.filepath = output_path
    bpy.context.scene.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)
    return {"rendered": output_path}


@tool_registry.tool(
    name="render_viewport_preview",
    description="Take a viewport screenshot and save to a path.",
    params={
        "type": "object",
        "properties": {"output_path": {"type": "string"}},
        "required": ["output_path"],
    }
)
def render_viewport_preview(output_path: str):
    area = None
    for a in bpy.context.screen.areas:
        if a.type == "VIEW_3D":
            area = a
            break
    if not area:
        raise ValueError("No 3D viewport found")
    with bpy.context.temp_override(area=area):
        bpy.ops.screen.screenshot_area(filepath=output_path)
    return {"screenshot": output_path}


@tool_registry.tool(
    name="save_blend_file",
    description="Save the current .blend file. Provide an absolute path.",
    params={
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }
)
def save_blend_file(path: str):
    bpy.ops.wm.save_as_mainfile(filepath=path)
    return {"saved": path}


@tool_registry.tool(
    name="open_blend_file",
    description="Open a .blend file by absolute path.",
    params={
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }
)
def open_blend_file(path: str):
    bpy.ops.wm.open_mainfile(filepath=path)
    return {"opened": path}


@tool_registry.tool(
    name="run_blender_python",
    description="Execute arbitrary Python code inside Blender with bpy available. Guarded by default.",
    params={
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python code to execute"},
        },
        "required": ["code"],
    }
)
def run_blender_python(code: str):
    return executor.execute_blender_python(code, allow_dangerous=False)


@tool_registry.tool(
    name="validate_blender_python",
    description="Check if Python code passes safety validation without executing it.",
    params={
        "type": "object",
        "properties": {"code": {"type": "string"}},
        "required": ["code"],
    }
)
def validate_blender_python(code: str):
    ok, reason = executor.validate_code(code, allow_dangerous=False)
    return {"valid": ok, "reason": reason}
