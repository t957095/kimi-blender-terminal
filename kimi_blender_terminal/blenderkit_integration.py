"""
BlenderKit Integration — search, download, and import free assets from BlenderKit.

BlenderKit is a massive library of 3D models, materials, HDRIs, and scenes.
This module provides tools for the assistant to find and use them.

API Flow:
  1. Search: GET /api/v1/search/?query=<keywords>+is_free:true
  2. Get download metadata: GET /api/v1/downloads/<id>/?scene_uuid=<uuid>
  3. Download file: GET <filePath from metadata>
  4. Import: bpy.ops.import_scene.gltf(filepath=...)
"""

import bpy
import json
import os
import tempfile
import uuid

try:
    import requests
except ImportError:
    requests = None

from . import tool_registry


class _MissingRequests:
    @staticmethod
    def get(*args, **kwargs):
        raise RuntimeError(
            "The 'requests' package is required for BlenderKit integration. "
            "Install it in Blender's Python: "
            "import subprocess, sys; subprocess.run([sys.executable, '-m', 'pip', 'install', 'requests'])"
        )


if requests is None:
    requests = _MissingRequests()

BLENDERKIT_API = "https://www.blenderkit.com/api/v1"
DEFAULT_HEADERS = {"User-Agent": "kimi-blender-terminal/2.2"}


def _scene_uuid():
    """Generate or retrieve a scene UUID for BlenderKit tracking."""
    scene = bpy.context.scene
    if "uuid" not in scene:
        scene["uuid"] = str(uuid.uuid4())
    return scene["uuid"]


def _search(query_str: str, page_size: int = 10):
    """Raw search against BlenderKit API."""
    url = f"{BLENDERKIT_API}/search/"
    params = {
        "query": query_str,
        "page_size": page_size,
        "dict_parameters": 1,
    }
    try:
        r = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=15)
        if r.status_code == 200:
            return r.json()
        return {"error": f"HTTP {r.status_code}", "details": r.text[:200]}
    except Exception as e:
        return {"error": str(e)}


def _get_download_url(file_info: dict) -> str:
    """Get actual download URL for a file from BlenderKit."""
    dl_url = file_info.get("downloadUrl")
    if not dl_url:
        return None
    try:
        meta = requests.get(
            dl_url,
            params={"scene_uuid": _scene_uuid()},
            headers=DEFAULT_HEADERS,
            timeout=30,
        )
        if meta.status_code == 200:
            data = meta.json()
            return data.get("filePath")
        return None
    except Exception:
        return None


def _download_file(url: str) -> bytes:
    """Download file bytes from URL."""
    r = requests.get(url, headers=DEFAULT_HEADERS, timeout=120)
    if r.status_code == 200:
        return r.content
    return None


def _import_glb(filepath: str):
    """Import a GLB/GLTF file into the current Blender scene."""
    before = set(o.name for o in bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=filepath)
    after = set(o.name for o in bpy.context.scene.objects)
    new_objects = list(after - before)
    return new_objects


@tool_registry.tool(
    name="search_blenderkit",
    description="Search BlenderKit for free 3D assets (models, materials, HDRIs, scenes).",
    params={
        "type": "object",
        "properties": {
            "keywords": {"type": "string", "description": "Search keywords, e.g. 'modern chair'"},
            "asset_type": {"type": "string", "enum": ["model", "material", "hdr", "scene", "brush", "nodegroup", "printable"], "description": "Filter by asset type"},
            "category": {"type": "string", "description": "Category slug, e.g. 'chair', 'vehicle'"},
            "page_size": {"type": "integer", "default": 10, "description": "Number of results (1-20)"},
            "free_only": {"type": "boolean", "default": True, "description": "Only free assets"},
        },
        "required": ["keywords"],
    }
)
def search_blenderkit(keywords: str, asset_type: str = None, category: str = None,
                       page_size: int = 10, free_only: bool = True):
    """Search BlenderKit and return formatted results."""
    query = keywords
    if free_only:
        query += " is_free:true"
    if asset_type:
        query += f" asset_type:{asset_type}"
    if category:
        query += f" category:{category}"

    data = _search(query, max(1, min(page_size, 20)))
    if "error" in data:
        return {"status": "error", "message": data["error"]}

    results = []
    for item in data.get("results", []):
        thumb = item.get("thumbnailMiddleUrl", "")
        results.append({
            "id": item.get("id"),
            "name": item.get("name"),
            "asset_type": item.get("assetType"),
            "category": item.get("category"),
            "author": item.get("author", {}).get("fullName", "Unknown"),
            "is_free": item.get("isFree"),
            "license": item.get("license"),
            "thumbnail": thumb,
            "can_download": item.get("canDownload"),
        })

    return {
        "status": "success",
        "total": data.get("count", 0),
        "returned": len(results),
        "results": results,
    }


@tool_registry.tool(
    name="download_blenderkit_asset",
    description="Download and import a BlenderKit asset into the scene by asset ID. Uses GLB format for fastest import.",
    params={
        "type": "object",
        "properties": {
            "asset_id": {"type": "string", "description": "BlenderKit asset ID (from search results)"},
            "location": {"type": "array", "items": {"type": "number"}, "description": "[x, y, z] placement location"},
            "scale": {"type": "number", "default": 1.0, "description": "Uniform scale factor"},
        },
        "required": ["asset_id"],
    }
)
def download_blenderkit_asset(asset_id: str, location: list = None, scale: float = 1.0):
    """Download a BlenderKit asset and import it as GLB."""
    # First get the asset details
    search_data = _search(f"asset_base_id:{asset_id}", page_size=1)
    if "error" in search_data or not search_data.get("results"):
        return {"status": "error", "message": f"Asset not found: {asset_id}"}

    asset = search_data["results"][0]
    files = asset.get("files", [])

    # Prefer GLB, then .blend
    glb_file = next((f for f in files if f.get("fileType") == "gltf"), None)
    blend_file = next((f for f in files if f.get("fileType") == "blend"), None)

    target_file = glb_file or blend_file
    if not target_file:
        return {"status": "error", "message": "No downloadable file found for this asset"}

    # Get actual download URL
    file_url = _get_download_url(target_file)
    if not file_url:
        return {"status": "error", "message": "Could not resolve download URL"}

    # Download
    file_bytes = _download_file(file_url)
    if not file_bytes:
        return {"status": "error", "message": "Download failed"}

    # Save to temp
    ext = ".glb" if glb_file else ".blend"
    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    tmp.write(file_bytes)
    tmp.close()

    # Import
    try:
        before = set(o.name for o in bpy.context.scene.objects)
        if glb_file:
            bpy.ops.import_scene.gltf(filepath=tmp.name)
        else:
            # For .blend, append objects from the file
            with bpy.data.libraries.load(tmp.name, link=False) as (data_from, data_to):
                data_to.objects = data_from.objects
            for obj in data_to.objects:
                if obj is not None:
                    bpy.context.scene.collection.objects.link(obj)

        after = set(o.name for o in bpy.context.scene.objects)
        new_objects = list(after - before)

        # Apply location and scale
        loc = tuple(location) if location else (0, 0, 0)
        for name in new_objects:
            obj = bpy.data.objects.get(name)
            if obj:
                obj.location = loc
                if scale != 1.0:
                    obj.scale = (scale, scale, scale)

        return {
            "status": "success",
            "imported_objects": new_objects,
            "asset_name": asset.get("name"),
            "format": "glb" if glb_file else "blend",
        }
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}
    finally:
        try:
            os.unlink(tmp.name)
        except:
            pass


@tool_registry.tool(
    name="get_blenderkit_categories",
    description="Get available BlenderKit asset categories for a given asset type.",
    params={
        "type": "object",
        "properties": {
            "asset_type": {"type": "string", "enum": ["model", "material", "hdr", "scene"]},
        },
        "required": ["asset_type"],
    }
)
def get_blenderkit_categories(asset_type: str):
    """Fetch categories from BlenderKit API."""
    try:
        url = f"{BLENDERKIT_API}/categories/{asset_type}/"
        r = requests.get(url, headers=DEFAULT_HEADERS, timeout=15)
        if r.status_code == 200:
            cats = r.json()
            return {"status": "success", "categories": cats}
        return {"status": "error", "message": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
