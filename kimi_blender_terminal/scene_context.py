"""
SceneContext — build a rich, compact summary of the current Blender scene.
"""

import bpy


class SceneContext:
    _cache = None
    _cache_frame = -1

    @classmethod
    def invalidate(cls):
        cls._cache = None
        cls._cache_frame = -1

    @classmethod
    def get_summary(cls, force_refresh: bool = False) -> dict:
        scene = bpy.context.scene
        if not force_refresh and cls._cache is not None and cls._cache_frame == scene.frame_current:
            return cls._cache

        ctx = {
            "scene_name": scene.name,
            "frame_current": scene.frame_current,
            "frame_start": scene.frame_start,
            "frame_end": scene.frame_end,
            "render_engine": scene.render.engine,
            "resolution": [scene.render.resolution_x, scene.render.resolution_y],
            "fps": scene.render.fps,
            "object_count": len(scene.objects),
            "objects": [],
            "selected": [],
            "active": None,
            "camera": None,
            "lights": [],
            "collections": [],
            "materials_count": len(bpy.data.materials),
            "world": None,
        }

        # Selected / active
        selected = [obj for obj in scene.objects if obj.select_get()]
        for obj in selected[:10]:
            ctx["selected"].append({
                "name": obj.name,
                "type": obj.type,
                "location": [round(obj.location.x, 3), round(obj.location.y, 3), round(obj.location.z, 3)],
            })

        active = bpy.context.active_object
        if active:
            ctx["active"] = cls._describe_object(active)

        # Camera
        cam = scene.camera
        if cam:
            ctx["camera"] = {
                "name": cam.name,
                "location": [round(cam.location.x, 2), round(cam.location.y, 2), round(cam.location.z, 2)],
                "type": cam.type,
            }
            if cam.data and cam.data.type == "PERSP":
                ctx["camera"]["lens"] = round(cam.data.lens, 1)

        # Lights
        for obj in scene.objects:
            if obj.type == "LIGHT":
                light = obj.data
                ctx["lights"].append({
                    "name": obj.name,
                    "type": light.type,
                    "energy": round(light.energy, 2),
                    "location": [round(obj.location.x, 2), round(obj.location.y, 2), round(obj.location.z, 2)],
                })
                if len(ctx["lights"]) >= 5:
                    break

        # Collections
        for col in scene.collection.children:
            ctx["collections"].append(col.name)
        if not ctx["collections"] and scene.collection.objects:
            ctx["collections"].append(scene.collection.name)

        # Representative objects (first 15)
        for obj in scene.objects:
            if len(ctx["objects"]) >= 15:
                break
            ctx["objects"].append(cls._describe_object(obj, brief=True))

        # World
        if scene.world:
            ctx["world"] = scene.world.name

        cls._cache = ctx
        cls._cache_frame = scene.frame_current
        return ctx

    @classmethod
    def _describe_object(cls, obj, brief=False):
        info = {
            "name": obj.name,
            "type": obj.type,
            "location": [round(obj.location.x, 3), round(obj.location.y, 3), round(obj.location.z, 3)],
            "visible": obj.visible_get(),
            "materials": [s.material.name for s in obj.material_slots if s.material],
        }
        if not brief:
            info["rotation"] = [round(obj.rotation_euler.x, 3), round(obj.rotation_euler.y, 3), round(obj.rotation_euler.z, 3)]
            info["scale"] = [round(obj.scale.x, 3), round(obj.scale.y, 3), round(obj.scale.z, 3)]
            info["modifiers"] = [m.name for m in obj.modifiers]
            if obj.type == "MESH" and obj.data:
                mesh = obj.data
                info["mesh"] = {
                    "vertices": len(mesh.vertices),
                    "edges": len(mesh.edges),
                    "polygons": len(mesh.polygons),
                }
        return info

    @classmethod
    def get_text_summary(cls, force_refresh: bool = False) -> str:
        data = cls.get_summary(force_refresh)
        lines = [
            f"Scene: {data['scene_name']} | Frame {data['frame_current']}/{data['frame_end']}",
            f"Render: {data['render_engine']} | Resolution: {data['resolution'][0]}x{data['resolution'][1]} | FPS: {data['fps']}",
            f"Objects: {data['object_count']} | Materials: {data['materials_count']}",
        ]
        if data["world"]:
            lines.append(f"World: {data['world']}")
        if data["camera"]:
            lines.append(f"Camera: {data['camera']['name']} at {data['camera']['location']}")
        if data["lights"]:
            lines.append(f"Lights: {', '.join(l['name'] for l in data['lights'])}")
        if data["selected"]:
            lines.append(f"Selected: {', '.join(o['name'] for o in data['selected'])}")
        if data["active"]:
            lines.append(f"Active: {data['active']['name']} ({data['active']['type']})")
            if data["active"].get("materials"):
                lines.append(f"  Materials: {', '.join(data['active']['materials'])}")
            if data["active"].get("modifiers"):
                lines.append(f"  Modifiers: {', '.join(data['active']['modifiers'])}")
        if data["collections"]:
            lines.append(f"Collections: {', '.join(data['collections'])}")
        if data["objects"]:
            names = [o["name"] for o in data["objects"]]
            lines.append(f"Objects: {', '.join(names)}")
        return "\n".join(lines)
