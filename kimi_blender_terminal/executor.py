"""
Executor — safe Blender Python code execution with a rich helper namespace.

Primary interface: exec(code, namespace)
where namespace contains bpy, helper functions, and context.

Includes professional terrain generation, vertex painting, PBR materials,
and GLB export helpers ported from real production workflows.
"""

import bpy
import io
import mathutils
import math
import os
import re
import traceback
import bmesh
from contextlib import redirect_stdout, redirect_stderr

# Dangerous patterns blocked by default
DEFAULT_BLOCKED_PATTERNS = [
    r"bpy\.ops\.wm\.quit_blender",
    r"bpy\.ops\.file\.delete",
    r"os\.system\s*\(",
    r"subprocess\.call\s*\(",
    r"subprocess\.run\s*\(",
    r"subprocess\.Popen\s*\(",
    r"eval\s*\(",
    r"exec\s*\(",
    r"__import__\s*\(",
    r"importlib\.import_module",
    r"shutil\.rmtree",
    r"shutil\.move",
]

SAFE_BUILTINS = {
    "print": print,
    "len": len,
    "range": range,
    "enumerate": enumerate,
    "zip": zip,
    "map": map,
    "filter": filter,
    "abs": abs,
    "min": min,
    "max": max,
    "sum": sum,
    "round": round,
    "int": int,
    "float": float,
    "str": str,
    "list": list,
    "tuple": tuple,
    "dict": dict,
    "set": set,
    "bool": bool,
    "type": type,
    "isinstance": isinstance,
    "hasattr": hasattr,
    "getattr": getattr,
    "setattr": setattr,
    "sorted": sorted,
    "reversed": reversed,
    "any": any,
    "all": all,
    "chr": chr,
    "ord": ord,
    "pow": pow,
    "divmod": divmod,
    "slice": slice,
    "iter": iter,
    "next": next,
    "format": format,
    "hex": hex,
    "bin": bin,
    "oct": oct,
    "Exception": Exception,
    "ValueError": ValueError,
    "TypeError": TypeError,
    "KeyError": KeyError,
    "IndexError": IndexError,
    "AttributeError": AttributeError,
    "RuntimeError": RuntimeError,
    "ZeroDivisionError": ZeroDivisionError,
    "NameError": NameError,
    "AssertionError": AssertionError,
    "ArithmeticError": ArithmeticError,
    "StopIteration": StopIteration,
}


def validate_code(code: str, allow_dangerous: bool = False) -> tuple:
    if not code or not code.strip():
        return False, "Code is empty"
    if allow_dangerous:
        return True, ""
    try:
        import ast as _ast
        _ast.parse(code)
    except SyntaxError as e:
        return False, f"Syntax error at line {e.lineno}: {e.msg}"
    for pattern in DEFAULT_BLOCKED_PATTERNS:
        if re.search(pattern, code, re.IGNORECASE):
            return False, f"Blocked dangerous pattern: {pattern}"
    return True, ""


# ═════════════════════════════════════════════════════════════════════════════
# BASIC HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def _get_active():
    return bpy.context.active_object


def _get_scene():
    return bpy.context.scene


def _fuzzy_find(name: str):
    """Find an object by exact name, then by case-insensitive, then by prefix."""
    obj = bpy.data.objects.get(name)
    if obj:
        return obj
    # Case-insensitive exact match
    for o in bpy.data.objects:
        if o.name.lower() == name.lower():
            return o
    # Prefix match
    for o in bpy.data.objects:
        if o.name.lower().startswith(name.lower()):
            return o
    # Contains match
    for o in bpy.data.objects:
        if name.lower() in o.name.lower():
            return o
    return None


def _ensure_object_mode():
    """Switch from edit/sculpt/etc mode to object mode safely."""
    if bpy.context.active_object and bpy.context.mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except RuntimeError:
            pass


def _sync_scene():
    """Update view layer and depsgraph after modifications."""
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()


def _get_scene_state():
    """Return a compact snapshot of scene state for diffing."""
    return {
        "objects": {o.name: {"loc": tuple(o.location), "type": o.type} for o in bpy.context.scene.objects},
        "materials": [m.name for m in bpy.data.materials],
        "camera": bpy.context.scene.camera.name if bpy.context.scene.camera else None,
    }


def _diff_state(before, after):
    """Return a human-readable diff between two scene states."""
    changes = []
    before_objs = before.get("objects", {})
    after_objs = after.get("objects", {})
    added = [n for n in after_objs if n not in before_objs]
    removed = [n for n in before_objs if n not in after_objs]
    if added:
        changes.append(f"Objects added: {', '.join(added)}")
    if removed:
        changes.append(f"Objects removed: {', '.join(removed)}")
    for name in after_objs:
        if name in before_objs:
            b_loc = before_objs[name]["loc"]
            a_loc = after_objs[name]["loc"]
            if any(abs(b - a) > 0.001 for b, a in zip(b_loc, a_loc)):
                changes.append(f"{name} moved to {a_loc}")
    if not changes:
        changes.append("No visible scene changes detected")
    return changes


def _select(name: str):
    obj = _fuzzy_find(name)
    if obj:
        _ensure_object_mode()
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
    return obj


def _clear_scene():
    """Remove all objects and purge orphaned data."""
    bpy.ops.object.select_all(action="DESELECT")
    for obj in bpy.data.objects:
        if obj.type in {"MESH", "LIGHT", "CAMERA", "EMPTY", "CURVE", "SURFACE", "META", "FONT", "GPENCIL", "VOLUME"}:
            obj.select_set(True)
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.textures):
        for item in list(block):
            if item.users == 0:
                block.remove(item)


def _create_cube(name="Cube", location=(0, 0, 0), size=2.0):
    _ensure_object_mode()
    bpy.ops.mesh.primitive_cube_add(location=location, size=size)
    obj = bpy.context.active_object
    obj.name = name
    _sync_scene()
    return obj


def _create_sphere(name="Sphere", location=(0, 0, 0), radius=1.0):
    _ensure_object_mode()
    bpy.ops.mesh.primitive_uv_sphere_add(location=location, radius=radius)
    obj = bpy.context.active_object
    obj.name = name
    _sync_scene()
    return obj


def _create_cylinder(name="Cylinder", location=(0, 0, 0), radius=1.0, depth=2.0):
    _ensure_object_mode()
    bpy.ops.mesh.primitive_cylinder_add(location=location, radius=radius, depth=depth)
    obj = bpy.context.active_object
    obj.name = name
    _sync_scene()
    return obj


def _create_camera(name="Camera", location=(7, -7, 5), rotation=(1.1, 0, 0.8), lens=50):
    _ensure_object_mode()
    bpy.ops.object.camera_add(location=location, rotation=rotation)
    obj = bpy.context.active_object
    obj.name = name
    obj.data.lens = lens
    _sync_scene()
    return obj


def _create_light(name="Light", type="POINT", location=(0, 0, 5), energy=1000, color=(1, 1, 1)):
    _ensure_object_mode()
    bpy.ops.object.light_add(type=type, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.data.energy = energy
    obj.data.color = color
    _sync_scene()
    return obj


def _create_material(name="Material", color=(0.8, 0.8, 0.8), roughness=0.5, metallic=0.0):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
    return mat


def _assign_material(obj_name: str, mat_name: str):
    obj = _fuzzy_find(obj_name)
    mat = bpy.data.materials.get(mat_name)
    if not obj or not mat:
        return None
    if obj.type == "MESH":
        if len(obj.material_slots) == 0:
            obj.data.materials.append(mat)
        else:
            obj.material_slots[0].material = mat
    _sync_scene()
    return obj


def _move(name: str, location):
    obj = _fuzzy_find(name)
    if obj:
        obj.location = location
        _sync_scene()
        return obj
    return None


def _rotate(name: str, rotation):
    obj = _fuzzy_find(name)
    if obj:
        obj.rotation_euler = rotation
        _sync_scene()
        return obj
    return None


def _scale(name: str, scale):
    obj = _fuzzy_find(name)
    if obj:
        obj.scale = scale
        _sync_scene()
        return obj
    return None


def _delete(name: str):
    obj = _fuzzy_find(name)
    if obj:
        bpy.data.objects.remove(obj, do_unlink=True)
        _sync_scene()
        return True
    return False


def _get_objects():
    return [o.name for o in bpy.context.scene.objects]


def _get_object_info(name: str):
    obj = _fuzzy_find(name)
    if not obj:
        return None
    info = {
        "name": obj.name,
        "type": obj.type,
        "location": [obj.location.x, obj.location.y, obj.location.z],
        "rotation": [obj.rotation_euler.x, obj.rotation_euler.y, obj.rotation_euler.z],
        "scale": [obj.scale.x, obj.scale.y, obj.scale.z],
        "visible": obj.visible_get(),
        "materials": [s.material.name for s in obj.material_slots if s.material],
        "modifiers": [m.name for m in obj.modifiers],
    }
    if obj.type == "MESH" and obj.data:
        mesh = obj.data
        info["mesh"] = {
            "vertices": len(mesh.vertices),
            "edges": len(mesh.edges),
            "polygons": len(mesh.polygons),
        }
    return info


def _get_scene_info():
    scene = bpy.context.scene
    objs = []
    for obj in scene.objects:
        objs.append({
            "name": obj.name,
            "type": obj.type,
            "location": [round(obj.location.x, 2), round(obj.location.y, 2), round(obj.location.z, 2)],
        })
    return {
        "name": scene.name,
        "engine": scene.render.engine,
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
        "object_count": len(scene.objects),
        "objects": objs,
        "camera": scene.camera.name if scene.camera else None,
    }


def _add_modifier(obj_name: str, mod_type: str, name: str = None):
    obj = _fuzzy_find(obj_name)
    if obj and obj.type == "MESH":
        mod = obj.modifiers.new(name=name or mod_type, type=mod_type)
        _sync_scene()
        return mod.name
    return None


def _apply_modifier(obj_name: str, mod_name: str):
    obj = _fuzzy_find(obj_name)
    if obj:
        _ensure_object_mode()
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=mod_name)
        _sync_scene()
        return True
    return False


def _set_resolution(x: int, y: int):
    bpy.context.scene.render.resolution_x = x
    bpy.context.scene.render.resolution_y = y


def _set_engine(engine: str):
    bpy.context.scene.render.engine = engine


def _render(filepath: str):
    bpy.context.scene.render.filepath = filepath
    bpy.ops.render.render(write_still=True)
    return filepath


def _save(filepath: str = None):
    if filepath:
        bpy.ops.wm.save_as_mainfile(filepath=filepath)
    else:
        bpy.ops.wm.save_mainfile()
    return bpy.data.filepath


def _set_viewport_shading(mode="MATERIAL"):
    """Set the 3D viewport shading mode so materials are visible.

    Modes: "WIREFRAME", "SOLID", "MATERIAL", "RENDERED"
    """
    ok = False
    for area in bpy.context.screen.areas:
        if area.type == "VIEW_3D":
            for space in area.spaces:
                if space.type == "VIEW_3D":
                    space.shading.type = mode
                    ok = True
    _sync_scene()
    return ok


def _set_material_color(obj, color):
    """Set or create the object's Principled BSDF base color."""
    if isinstance(obj, str):
        obj = _fuzzy_find(obj)
    if not obj or obj.type != "MESH":
        return None
    mat = None
    if obj.data.materials and obj.data.materials[0]:
        mat = obj.data.materials[0]
    else:
        mat = bpy.data.materials.new(name=f"MAT_{obj.name}")
        mat.use_nodes = True
        obj.data.materials.append(mat)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    _sync_scene()
    return mat


# ═════════════════════════════════════════════════════════════════════════════
# ADVANCED HELPERS — Terrain, Vertex Paint, PBR, GLB Export
# ═════════════════════════════════════════════════════════════════════════════

def _shade_smooth(obj):
    """Enable smooth shading and auto-smooth (Blender 4.x compatible)."""
    if isinstance(obj, str):
        obj = _fuzzy_find(obj)
    if not obj or obj.type != "MESH":
        return
    _ensure_object_mode()
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.shade_smooth()
    obj.data.use_auto_smooth = True
    obj.data.auto_smooth_angle = math.radians(30)
    _sync_scene()


def _add_displace_modifier(obj, strength=0.3, scale=15.0, seed=0):
    """Add a Displace modifier driven by a Clouds texture for micro-detail."""
    if isinstance(obj, str):
        obj = _fuzzy_find(obj)
    if not obj or obj.type != "MESH":
        return None
    tex = bpy.data.textures.new(name=f"Disp_{obj.name}", type="CLOUDS")
    tex.noise_scale = scale
    tex.noise_depth = 2
    tex.noise_basis = "BLENDER_ORIGINAL"
    mod = obj.modifiers.new(name="MicroDetail", type="DISPLACE")
    mod.texture = tex
    mod.strength = strength
    mod.direction = "Z"
    mod.mid_level = 0.5
    mod.texture_coords = "LOCAL"
    _sync_scene()
    return mod.name


def _compute_vertex_normals(obj):
    """Recalculate normals after displacement."""
    if isinstance(obj, str):
        obj = _fuzzy_find(obj)
    if not obj or obj.type != "MESH":
        return
    _ensure_object_mode()
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    _sync_scene()


def _thermal_erosion(obj, iterations=12, talus_angle=0.6):
    """Simple thermal erosion: moves material from steep slopes to neighbors."""
    if isinstance(obj, str):
        obj = _fuzzy_find(obj)
    if not obj or obj.type != "MESH":
        return
    mesh = obj.data
    mesh.update()
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    for _ in range(iterations):
        deltas = [0.0] * len(bm.verts)
        for edge in bm.edges:
            v0, v1 = edge.verts
            h_diff = v0.co.z - v1.co.z
            if h_diff == 0:
                continue
            length_2d = math.sqrt((v0.co.x - v1.co.x) ** 2 + (v0.co.y - v1.co.y) ** 2)
            if length_2d < 0.0001:
                continue
            slope = math.atan2(abs(h_diff), length_2d)
            if slope > talus_angle:
                transfer = (slope - talus_angle) * 0.15 * length_2d
                transfer = min(transfer, abs(h_diff) * 0.5)
                if h_diff > 0:
                    deltas[v0.index] -= transfer
                    deltas[v1.index] += transfer
                else:
                    deltas[v0.index] += transfer
                    deltas[v1.index] -= transfer
        for vert in bm.verts:
            vert.co.z += deltas[vert.index]
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    _sync_scene()


def _paint_vertex_colors_by_height(obj, low_color, high_color, threshold=0.55, blend=0.25):
    """Paint face-corner colors based on normalized height + slope."""
    if isinstance(obj, str):
        obj = _fuzzy_find(obj)
    if not obj or obj.type != "MESH":
        return
    mesh = obj.data
    mesh.update()
    attr_name = "Color"
    if attr_name in mesh.attributes:
        mesh.attributes.remove(mesh.attributes[attr_name])
    color_attr = mesh.attributes.new(name=attr_name, type="FLOAT_COLOR", domain="CORNER")
    z_coords = [v.co.z for v in mesh.vertices]
    z_min, z_max = min(z_coords), max(z_coords)
    z_range = max(z_max - z_min, 0.001)
    low_c = mathutils.Color(low_color)
    high_c = mathutils.Color(high_color)
    for poly in mesh.polygons:
        for loop_idx in poly.loop_indices:
            vert_idx = mesh.loops[loop_idx].vertex_index
            v = mesh.vertices[vert_idx]
            h = (v.co.z - z_min) / z_range
            ny = v.normal.z
            slope = max(0.0, 1.0 - ny)
            amount = 0.0
            if h > threshold:
                amount = (h - threshold) / blend
                amount *= (1.0 - slope * 0.8)
                amount = min(1.0, max(0.0, amount))
            c = mathutils.Color((
                low_c.r * (1.0 - amount) + high_c.r * amount,
                low_c.g * (1.0 - amount) + high_c.g * amount,
                low_c.b * (1.0 - amount) + high_c.b * amount,
            ))
            color_attr.data[loop_idx].color = (c.r, c.g, c.b, 1.0)
    _sync_scene()


def _create_pbr_material(name, base_color, roughness=0.8, metallic=0.0,
                         use_vertex_color=False, coat=0.0,
                         subsurface=0.0,
                         emission=(0, 0, 0), emission_strength=0.0):
    """Create a Principled BSDF material (Blender 4.x socket names)."""
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*base_color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Coat Weight"].default_value = coat
    bsdf.inputs["Coat Roughness"].default_value = 0.2
    bsdf.inputs["Subsurface Weight"].default_value = subsurface
    if emission_strength > 0:
        if "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = (*emission, 1.0)
        elif "Emission" in bsdf.inputs:
            bsdf.inputs["Emission"].default_value = (*emission, 1.0)
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    if use_vertex_color:
        vcol_node = nodes.new(type="ShaderNodeVertexColor")
        vcol_node.layer_name = "Color"
        links.new(vcol_node.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def _assign_mat(obj, mat):
    """Assign material to object (clear existing)."""
    if isinstance(obj, str):
        obj = _fuzzy_find(obj)
    if not obj or obj.type != "MESH":
        return
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    _sync_scene()


def _create_landscape(name, size_x, size_y, max_height,
                      noise_type="ridged_multi_fractal",
                      H=1.0, lacunarity=2.0, octaves=8,
                      offset=1.0, gain=1.0,
                      falloff="0", water_level=0.0,
                      subdivisions=200, noise_scale=None):
    """Create a displaced plane using mathutils.noise for terrain."""
    if noise_scale is None:
        noise_scale = 3.0 / max(size_x, size_y)
    _ensure_object_mode()
    bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, 0))
    obj = bpy.context.active_object
    obj.name = name
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.subdivide(number_cuts=subdivisions)
    bpy.ops.object.mode_set(mode="OBJECT")
    obj.scale = (size_x / 2.0, size_y / 2.0, 1.0)
    bpy.ops.object.transform_apply(scale=True)
    mesh = obj.data
    mesh.update()
    max_r = math.sqrt((size_x / 2.0) ** 2 + (size_y / 2.0) ** 2)
    raw = []
    for v in mesh.vertices:
        pos = mathutils.Vector((v.co.x * noise_scale, v.co.y * noise_scale, 0.0))
        if noise_type == "ridged_multi_fractal":
            h = mathutils.noise.ridged_multi_fractal(pos, H, lacunarity, octaves, offset, gain, noise_basis="BLENDER")
        elif noise_type == "multi_fractal":
            h = mathutils.noise.multi_fractal(pos, H, lacunarity, octaves, noise_basis="BLENDER")
        elif noise_type == "fractal":
            h = mathutils.noise.fractal(pos, H, lacunarity, octaves, noise_basis="BLENDER")
        elif noise_type == "hybrid_multi_fractal":
            h = mathutils.noise.hybrid_multi_fractal(pos, H, lacunarity, octaves, offset, gain, noise_basis="BLENDER")
        else:
            h = mathutils.noise.noise(pos, noise_basis="BLENDER")
        raw.append(h)
    r_min = min(raw)
    r_max = max(raw)
    r_range = max(r_max - r_min, 0.001)
    for v, h in zip(mesh.vertices, raw):
        norm = (h - r_min) / r_range
        z = norm * max_height + water_level
        if falloff == "2":
            dist = math.sqrt(v.co.x ** 2 + v.co.y ** 2)
            f = max(0.0, 1.0 - (dist / max_r) ** 2)
            z *= f
        v.co.z = z
    mesh.update()
    _sync_scene()
    return obj


def _export_glb(filepath):
    """Export current scene as GLB."""
    bpy.ops.export_scene.gltf(
        filepath=filepath,
        export_format="GLB",
        export_yup=True,
        export_materials="EXPORT",
        export_image_format="AUTO",
        use_mesh_edges=False,
        use_mesh_vertices=False,
        export_draco_mesh_compression_enable=False,
        export_apply=True,
    )
    print(f"[EXPORTED] {filepath}")
    return filepath


# ═════════════════════════════════════════════════════════════════════════════
# HELPER DOCS — included in the system prompt
# ═════════════════════════════════════════════════════════════════════════════

HELPER_DOCS = """
Helper functions available in your namespace (no need to import):

BASIC:
  create_cube(name="Cube", location=(0,0,0), size=2.0) -> obj
  create_sphere(name="Sphere", location=(0,0,0), radius=1.0) -> obj
  create_cylinder(name="Cylinder", location=(0,0,0), radius=1.0, depth=2.0) -> obj
  create_camera(name="Camera", location=(7,-7,5), rotation=(1.1,0,0.8), lens=50) -> obj
  create_light(name="Light", type="POINT", location=(0,0,5), energy=1000, color=(1,1,1)) -> obj
  create_material(name="Material", color=(0.8,0.8,0.8), roughness=0.5, metallic=0.0) -> mat
  assign_material(obj_name, mat_name) -> obj
  move(name, location) -> obj
  rotate(name, rotation) -> obj    # radians
  scale(name, scale) -> obj
  delete(name) -> bool
  select(name) -> obj
  get_scene_info() -> dict
  get_object_info(name) -> dict
  get_objects() -> list
  add_modifier(obj_name, mod_type, name=None) -> mod_name
  apply_modifier(obj_name, mod_name) -> bool
  set_resolution(x, y)
  set_engine(engine)               # "CYCLES", "BLENDER_EEVEE_NEXT", "BLENDER_WORKBENCH"
  render(filepath) -> filepath
  save(filepath=None) -> filepath
  clear_scene()
  set_viewport_shading(mode)       # "WIREFRAME", "SOLID", "MATERIAL", "RENDERED"
  set_material_color(obj, color) -> mat

TERRAIN & LANDSCAPE:
  create_landscape(name, size_x, size_y, max_height,
                   noise_type="ridged_multi_fractal",
                   H=1.0, lacunarity=2.0, octaves=8,
                   offset=1.0, gain=1.0,
                   falloff="0", water_level=0.0,
                   subdivisions=200, noise_scale=None) -> obj
    # noise_type: "ridged_multi_fractal", "multi_fractal", "fractal", "hybrid_multi_fractal"
    # falloff="2" creates radial island shape

  thermal_erosion(obj, iterations=12, talus_angle=0.6)
    # Smooths steep slopes into talus angles using bmesh

  paint_vertex_colors_by_height(obj, low_color, high_color, threshold=0.55, blend=0.25)
    # Paints face-corner colors based on height + slope

  add_displace_modifier(obj, strength=0.3, scale=15.0, seed=0)
    # Adds Clouds texture displace for micro-detail

  shade_smooth(obj)
    # Enables smooth shading + 30 deg auto-smooth

  compute_vertex_normals(obj)
    # Recalculates normals after displacement edits

MATERIALS:
  create_pbr_material(name, base_color, roughness=0.8, metallic=0.0,
                      use_vertex_color=False, coat=0.0,
                      subsurface=0.0, emission=(0,0,0), emission_strength=0.0) -> mat
    # Full Principled BSDF with vertex color mixing, clearcoat, emission

  assign_mat(obj, mat)
    # Clears existing slots and assigns material

EXPORT:
  export_glb(filepath)

COLOR CONSTANTS (exact RGB tuples — use these, never guess):
  RED=(1.0,0.0,0.0)  GREEN=(0.0,1.0,0.0)  BLUE=(0.0,0.0,1.0)
  YELLOW=(1.0,0.92,0.016)  ORANGE=(1.0,0.5,0.0)  WHITE=(1.0,1.0,1.0)
  BLACK=(0.0,0.0,0.0)  GREY=(0.5,0.5,0.5)  SILVER=(0.8,0.8,0.8)
  GOLD=(1.0,0.84,0.0)  CYAN=(0.0,1.0,1.0)  MAGENTA=(1.0,0.0,1.0)
  PURPLE=(0.5,0.0,0.5)  PINK=(1.0,0.75,0.8)  BROWN=(0.6,0.3,0.1)

CRITICAL RULES:
  - NEVER use vertex paint for color. ALWAYS create a Principled BSDF material.
  - ALWAYS call set_viewport_shading("MATERIAL") after assigning materials.
  - Use color constants (RED, GREEN, etc.) instead of guessing RGB values.

You also have direct access to: bpy, context, scene, data, ops, mathutils, bmesh, math
"""


def execute_blender_python(code: str, allow_dangerous: bool = False) -> dict:
    """Execute Python code inside Blender with a rich helper namespace.
    Captures scene state before/after and reports what changed."""
    ok, reason = validate_code(code, allow_dangerous)
    if not ok:
        return {"status": "error", "message": reason}

    namespace = {
        "__builtins__": SAFE_BUILTINS,
        "bpy": bpy,
        "context": bpy.context,
        "scene": bpy.context.scene,
        "data": bpy.data,
        "ops": bpy.ops,
        "mathutils": mathutils,
        "bmesh": bmesh,
        "math": math,
        # Basic helpers
        "get_scene_info": _get_scene_info,
        "get_objects": _get_objects,
        "get_object_info": _get_object_info,
        "select": _select,
        "create_cube": _create_cube,
        "create_sphere": _create_sphere,
        "create_cylinder": _create_cylinder,
        "create_camera": _create_camera,
        "create_light": _create_light,
        "create_material": _create_material,
        "assign_material": _assign_material,
        "move": _move,
        "rotate": _rotate,
        "scale": _scale,
        "delete": _delete,
        "add_modifier": _add_modifier,
        "apply_modifier": _apply_modifier,
        "set_resolution": _set_resolution,
        "set_engine": _set_engine,
        "render": _render,
        "save": _save,
        "clear_scene": _clear_scene,
        # Advanced helpers
        "shade_smooth": _shade_smooth,
        "add_displace_modifier": _add_displace_modifier,
        "compute_vertex_normals": _compute_vertex_normals,
        "thermal_erosion": _thermal_erosion,
        "paint_vertex_colors_by_height": _paint_vertex_colors_by_height,
        "create_pbr_material": _create_pbr_material,
        "assign_mat": _assign_mat,
        "create_landscape": _create_landscape,
        "export_glb": _export_glb,
        "set_viewport_shading": _set_viewport_shading,
        "set_material_color": _set_material_color,
        # Color constants
        "RED": (1.0, 0.0, 0.0),
        "GREEN": (0.0, 1.0, 0.0),
        "BLUE": (0.0, 0.0, 1.0),
        "YELLOW": (1.0, 0.92, 0.016),
        "ORANGE": (1.0, 0.5, 0.0),
        "WHITE": (1.0, 1.0, 1.0),
        "BLACK": (0.0, 0.0, 0.0),
        "GREY": (0.5, 0.5, 0.5),
        "SILVER": (0.8, 0.8, 0.8),
        "GOLD": (1.0, 0.84, 0.0),
        "CYAN": (0.0, 1.0, 1.0),
        "MAGENTA": (1.0, 0.0, 1.0),
        "PURPLE": (0.5, 0.0, 0.5),
        "PINK": (1.0, 0.75, 0.8),
        "BROWN": (0.6, 0.3, 0.1),
    }

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    state_before = _get_scene_state()
    try:
        class Tee:
            def __init__(self, *streams):
                self.streams = streams
            def write(self, data):
                for s in self.streams:
                    s.write(data)
                    if hasattr(s, 'flush'):
                        s.flush()
            def flush(self):
                for s in self.streams:
                    if hasattr(s, 'flush'):
                        s.flush()

        tee_stdout = Tee(stdout_buf, __import__('sys').stdout)
        tee_stderr = Tee(stderr_buf, __import__('sys').stderr)

        with redirect_stdout(tee_stdout), redirect_stderr(tee_stderr):
            exec(code, namespace)

        _sync_scene()
        state_after = _get_scene_state()
        changes = _diff_state(state_before, state_after)

        return {
            "status": "success",
            "stdout": stdout_buf.getvalue(),
            "stderr": stderr_buf.getvalue(),
            "scene_changes": changes,
        }
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[Kimi Terminal] Code execution error: {e}")
        print(tb)
        return {
            "status": "error",
            "message": str(e),
            "traceback": tb,
            "stdout": stdout_buf.getvalue(),
            "stderr": stderr_buf.getvalue(),
        }
