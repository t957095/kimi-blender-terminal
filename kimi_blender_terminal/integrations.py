"""
External service integrations — PolyHaven, Sketchfab, Hyper3D, Hunyuan3D.
Ported and adapted from fishys-blender-mcp reference implementation.
"""

import bpy
import json
import os
import tempfile
import urllib.request

try:
    import requests
except ImportError:
    requests = None

from . import tool_registry


class _MissingRequests:
    @staticmethod
    def get(*args, **kwargs):
        raise RuntimeError(
            "The 'requests' package is required for external asset downloads. "
            "Install it in Blender's Python: "
            "import subprocess, sys; subprocess.run([sys.executable, '-m', 'pip', 'install', 'requests'])"
        )


if requests is None:
    requests = _MissingRequests()

REQ_HEADERS = {"User-Agent": "kimi-blender-terminal/2.0"}
try:
    REQ_HEADERS = requests.utils.default_headers()
    REQ_HEADERS.update({"User-Agent": "kimi-blender-terminal/2.0"})
except Exception:
    pass

# ── Poly Haven ──

@tool_registry.tool(
    name="get_polyhaven_status",
    description="Check if Poly Haven integration is enabled. Returns status message.",
    params={"type": "object", "properties": {}}
)
def get_polyhaven_status():
    return {"enabled": True, "message": "Poly Haven is available for HDRIs, textures, and models."}


@tool_registry.tool(
    name="get_polyhaven_categories",
    description="Get asset categories from Poly Haven.",
    params={
        "type": "object",
        "properties": {"asset_type": {"type": "string", "enum": ["hdris", "textures", "models", "all"], "default": "all"}},
    }
)
def get_polyhaven_categories(asset_type: str = "all"):
    try:
        url = f"https://api.polyhaven.com/categories/{asset_type}"
        r = requests.get(url, headers=REQ_HEADERS, timeout=15)
        if r.status_code == 200:
            return {"categories": r.json()}
        return {"error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"error": str(e)}


@tool_registry.tool(
    name="search_polyhaven_assets",
    description="Search Poly Haven assets.",
    params={
        "type": "object",
        "properties": {
            "asset_type": {"type": "string", "enum": ["hdris", "textures", "models", "all"], "default": "all"},
            "categories": {"type": "string", "description": "Comma-separated categories"},
        },
    }
)
def search_polyhaven_assets(asset_type: str = "all", categories: str = None):
    try:
        params = {}
        if asset_type and asset_type != "all":
            params["type"] = asset_type
        if categories:
            params["categories"] = categories
        r = requests.get("https://api.polyhaven.com/assets", params=params, headers=REQ_HEADERS, timeout=15)
        if r.status_code == 200:
            assets = r.json()
            limited = {}
            for i, (k, v) in enumerate(assets.items()):
                if i >= 20:
                    break
                limited[k] = v
            return {"assets": limited, "total_count": len(assets), "returned_count": len(limited)}
        return {"error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"error": str(e)}


@tool_registry.tool(
    name="download_polyhaven_asset",
    description="Download and import a Poly Haven asset into Blender.",
    params={
        "type": "object",
        "properties": {
            "asset_id": {"type": "string"},
            "asset_type": {"type": "string", "enum": ["hdris", "textures", "models"]},
            "resolution": {"type": "string", "default": "1k"},
            "file_format": {"type": "string"},
        },
        "required": ["asset_id", "asset_type"],
    }
)
def download_polyhaven_asset(asset_id: str, asset_type: str, resolution: str = "1k", file_format: str = None):
    try:
        files_r = requests.get(f"https://api.polyhaven.com/files/{asset_id}", headers=REQ_HEADERS, timeout=30)
        if files_r.status_code != 200:
            return {"error": f"Failed to get files: {files_r.status_code}"}
        files_data = files_r.json()

        if asset_type == "hdris":
            fmt = file_format or "hdr"
            if "hdri" in files_data and resolution in files_data["hdri"] and fmt in files_data["hdri"][resolution]:
                url = files_data["hdri"][resolution][fmt]["url"]
                tmp = tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False)
                dl = requests.get(url, headers=REQ_HEADERS, timeout=60)
                tmp.write(dl.content)
                tmp.close()
                if not bpy.data.worlds:
                    bpy.data.worlds.new("World")
                world = bpy.data.worlds[0]
                world.use_nodes = True
                nt = world.node_tree
                for n in nt.nodes:
                    nt.nodes.remove(n)
                tc = nt.nodes.new(type="ShaderNodeTexCoord")
                tc.location = (-800, 0)
                mp = nt.nodes.new(type="ShaderNodeMapping")
                mp.location = (-600, 0)
                env = nt.nodes.new(type="ShaderNodeTexEnvironment")
                env.location = (-400, 0)
                env.image = bpy.data.images.load(tmp.name)
                bg = nt.nodes.new(type="ShaderNodeBackground")
                bg.location = (-200, 0)
                out = nt.nodes.new(type="ShaderNodeOutputWorld")
                out.location = (0, 0)
                nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
                nt.links.new(mp.outputs["Vector"], env.inputs["Vector"])
                nt.links.new(env.outputs["Color"], bg.inputs["Color"])
                nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
                bpy.context.scene.world = world
                return {"success": True, "message": f"HDRI {asset_id} imported", "image": env.image.name}
            return {"error": "Resolution/format not available"}

        elif asset_type == "textures":
            fmt = file_format or "jpg"
            maps = {}
            for map_type in files_data:
                if map_type in ["blend", "gltf"]:
                    continue
                if resolution in files_data[map_type] and fmt in files_data[map_type][resolution]:
                    url = files_data[map_type][resolution][fmt]["url"]
                    tmp = tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False)
                    dl = requests.get(url, headers=REQ_HEADERS, timeout=60)
                    tmp.write(dl.content)
                    tmp.close()
                    img = bpy.data.images.load(tmp.name)
                    img.name = f"{asset_id}_{map_type}.{fmt}"
                    img.pack()
                    maps[map_type] = img
            if not maps:
                return {"error": "No texture maps found"}
            mat = bpy.data.materials.new(name=asset_id)
            mat.use_nodes = True
            nodes = mat.node_tree.nodes
            links = mat.node_tree.links
            for n in nodes:
                nodes.remove(n)
            out = nodes.new(type="ShaderNodeOutputMaterial")
            out.location = (300, 0)
            bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
            bsdf.location = (0, 0)
            links.new(bsdf.outputs[0], out.inputs[0])
            tc = nodes.new(type="ShaderNodeTexCoord")
            tc.location = (-800, 0)
            mp = nodes.new(type="ShaderNodeMapping")
            mp.location = (-600, 0)
            mp.vector_type = "TEXTURE"
            links.new(tc.outputs["UV"], mp.inputs["Vector"])
            x, y = -400, 300
            for map_type, img in maps.items():
                tex = nodes.new(type="ShaderNodeTexImage")
                tex.location = (x, y)
                tex.image = img
                links.new(mp.outputs["Vector"], tex.inputs["Vector"])
                if map_type.lower() in ["color", "diffuse", "albedo"]:
                    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
                elif map_type.lower() in ["roughness", "rough"]:
                    links.new(tex.outputs["Color"], bsdf.inputs["Roughness"])
                elif map_type.lower() in ["metallic", "metalness", "metal"]:
                    links.new(tex.outputs["Color"], bsdf.inputs["Metallic"])
                elif map_type.lower() in ["normal", "nor"]:
                    nm = nodes.new(type="ShaderNodeNormalMap")
                    nm.location = (x + 200, y)
                    links.new(tex.outputs["Color"], nm.inputs["Color"])
                    links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
                y -= 250
            return {"success": True, "message": f"Texture {asset_id} imported", "material": mat.name, "maps": list(maps.keys())}

        elif asset_type == "models":
            fmt = file_format or "gltf"
            if fmt in files_data and resolution in files_data[fmt]:
                url = files_data[fmt][resolution][fmt]["url"]
                temp_dir = tempfile.mkdtemp()
                main_name = url.split("/")[-1]
                main_path = os.path.join(temp_dir, main_name)
                dl = requests.get(url, headers=REQ_HEADERS, timeout=60)
                with open(main_path, "wb") as f:
                    f.write(dl.content)
                if "include" in files_data[fmt][resolution][fmt]:
                    for inc_path, inc_info in files_data[fmt][resolution][fmt]["include"].items():
                        inc_url = inc_info["url"]
                        inc_file = os.path.join(temp_dir, inc_path)
                        os.makedirs(os.path.dirname(inc_file), exist_ok=True)
                        inc_dl = requests.get(inc_url, headers=REQ_HEADERS, timeout=60)
                        with open(inc_file, "wb") as f:
                            f.write(inc_dl.content)
                if fmt in ["gltf", "glb"]:
                    bpy.ops.import_scene.gltf(filepath=main_path)
                elif fmt == "fbx":
                    bpy.ops.import_scene.fbx(filepath=main_path)
                elif fmt == "obj":
                    bpy.ops.import_scene.obj(filepath=main_path)
                else:
                    return {"error": f"Unsupported format: {fmt}"}
                imported = [o.name for o in bpy.context.selected_objects]
                return {"success": True, "message": f"Model {asset_id} imported", "imported_objects": imported}
            return {"error": "Resolution/format not available"}

        return {"error": "Unknown asset type"}
    except Exception as e:
        return {"error": str(e)}


# ── Sketchfab ──

SKETCHFAB_API = "https://api.sketchfab.com/v3"


@tool_registry.tool(
    name="get_sketchfab_status",
    description="Check Sketchfab integration status.",
    params={"type": "object", "properties": {}}
)
def get_sketchfab_status():
    return {"enabled": True, "message": "Sketchfab search and preview are available. Download requires a Sketchfab account token."}


@tool_registry.tool(
    name="search_sketchfab_models",
    description="Search Sketchfab models.",
    params={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "categories": {"type": "string"},
            "count": {"type": "integer", "default": 20},
            "downloadable": {"type": "boolean", "default": True},
        },
        "required": ["query"],
    }
)
def search_sketchfab_models(query: str, categories: str = None, count: int = 20, downloadable: bool = True):
    try:
        params = {"q": query, "count": min(count, 24), "downloadable": str(downloadable).lower()}
        if categories:
            params["categories"] = categories
        r = requests.get(f"{SKETCHFAB_API}/search", params=params, headers=REQ_HEADERS, timeout=15)
        if r.status_code == 200:
            data = r.json()
            models = data.get("results", []) or []
            return {"results": models, "count": len(models)}
        return {"error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"error": str(e)}


@tool_registry.tool(
    name="get_sketchfab_model_preview",
    description="Get a preview thumbnail URL for a Sketchfab model.",
    params={
        "type": "object",
        "properties": {"uid": {"type": "string"}},
        "required": ["uid"],
    }
)
def get_sketchfab_model_preview(uid: str):
    try:
        r = requests.get(f"{SKETCHFAB_API}/models/{uid}", headers=REQ_HEADERS, timeout=15)
        if r.status_code == 200:
            data = r.json()
            thumbs = data.get("thumbnails", {}).get("images", [])
            if thumbs:
                return {"preview_url": thumbs[0].get("url"), "model_name": data.get("name", "Unknown")}
            return {"preview_url": None, "model_name": data.get("name", "Unknown")}
        return {"error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"error": str(e)}


@tool_registry.tool(
    name="download_sketchfab_model",
    description="Download and import a Sketchfab model by UID. Requires authentication token in preferences.",
    params={
        "type": "object",
        "properties": {
            "uid": {"type": "string"},
            "target_size": {"type": "number", "description": "Target size in meters for largest dimension"},
        },
        "required": ["uid", "target_size"],
    }
)
def download_sketchfab_model(uid: str, target_size: float):
    try:
        prefs = bpy.context.preferences.addons["kimi_blender_terminal"].preferences
        token = getattr(prefs, "sketchfab_token", "")
        if not token:
            return {"error": "No Sketchfab token configured. Add it in Preferences > Add-ons > Kimi Blender Terminal"}
        headers = dict(REQ_HEADERS)
        headers["Authorization"] = f"Token {token}"
        dl_r = requests.get(f"{SKETCHFAB_API}/models/{uid}/download", headers=headers, timeout=15)
        if dl_r.status_code != 200:
            return {"error": f"Download request failed: {dl_r.status_code}. Model may not be downloadable."}
        gltf_url = dl_r.json().get("gltf", {}).get("url")
        if not gltf_url:
            return {"error": "No glTF download URL available"}
        tmp = tempfile.NamedTemporaryFile(suffix=".gltf", delete=False)
        data = requests.get(gltf_url, timeout=120)
        tmp.write(data.content)
        tmp.close()
        bpy.ops.import_scene.gltf(filepath=tmp.name)
        imported = [o.name for o in bpy.context.selected_objects]
        # Normalize scale
        if imported:
            obj = bpy.data.objects[imported[0]]
            if obj.type == "MESH" and obj.data:
                dims = obj.dimensions
                max_dim = max(dims)
                if max_dim > 0:
                    scale = target_size / max_dim
                    obj.scale = (scale, scale, scale)
        return {"success": True, "imported_objects": imported}
    except Exception as e:
        return {"error": str(e)}


# ── Hyper3D Rodin (status + stubs for extensibility) ──

@tool_registry.tool(
    name="get_hyper3d_status",
    description="Check Hyper3D Rodin integration status.",
    params={"type": "object", "properties": {}}
)
def get_hyper3d_status():
    return {"enabled": False, "message": "Hyper3D Rodin requires API key configuration in preferences (future extension)."}


# ── Hunyuan3D (status + stubs for extensibility) ──

@tool_registry.tool(
    name="get_hunyuan3d_status",
    description="Check Hunyuan3D integration status.",
    params={"type": "object", "properties": {}}
)
def get_hunyuan3d_status():
    return {"enabled": False, "message": "Hunyuan3D requires API key configuration in preferences (future extension)."}
