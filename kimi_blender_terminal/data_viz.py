"""
Data Visualization — import CSV/JSON data and create 3D charts in Blender.

Supports:
  - 3D bar charts (categorical data)
  - 3D scatter plots (x,y,z numeric data)
  - 3D line graphs (time series)
  - Pie charts as 3D cylinders

Usage: read a CSV file, specify columns, and generate a 3D chart mesh.
"""

import bpy
import csv
import json
import os

from . import tool_registry
from . import executor


@tool_registry.tool(
    name="import_csv_data",
    description="Read a CSV file and return structured data for visualization.",
    params={
        "type": "object",
        "properties": {
            "filepath": {"type": "string", "description": "Absolute path to CSV file"},
            "max_rows": {"type": "integer", "default": 100},
        },
        "required": ["filepath"],
    }
)
def import_csv_data(filepath: str, max_rows: int = 100):
    """Read CSV and return headers + rows as dicts."""
    if not os.path.isfile(filepath):
        return {"status": "error", "message": f"File not found: {filepath}"}
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            rows = []
            for i, row in enumerate(reader):
                if i >= max_rows:
                    break
                rows.append({k: v for k, v in row.items()})
            return {
                "status": "success",
                "headers": reader.fieldnames or [],
                "row_count": len(rows),
                "rows": rows,
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@tool_registry.tool(
    name="create_scatter_plot_3d",
    description="Create a 3D scatter plot from x,y,z numeric columns.",
    params={
        "type": "object",
        "properties": {
            "data": {"type": "array", "items": {"type": "object"}},
            "x_column": {"type": "string"},
            "y_column": {"type": "string"},
            "z_column": {"type": "string"},
            "color_column": {"type": "string"},
            "name": {"type": "string", "default": "ScatterPlot"},
            "location": {"type": "array", "items": {"type": "number"}},
            "point_size": {"type": "number", "default": 0.1},
            "scale_factor": {"type": "number", "default": 1.0},
        },
        "required": ["data", "x_column", "y_column", "z_column"],
    }
)
def create_scatter_plot_3d(data: list, x_column: str, y_column: str, z_column: str,
                           color_column: str = None, name: str = "ScatterPlot",
                           location: list = None, point_size: float = 0.1,
                           scale_factor: float = 1.0):
    """Create a 3D scatter plot from data rows."""
    executor._ensure_object_mode()
    loc = tuple(location) if location else (0, 0, 0)

    # Extract numeric values
    xs, ys, zs = [], [], []
    colors = []
    for row in data:
        try:
            xs.append(float(row.get(x_column, 0)))
            ys.append(float(row.get(y_column, 0)))
            zs.append(float(row.get(z_column, 0)))
            if color_column:
                colors.append(float(row.get(color_column, 0)))
        except (ValueError, TypeError):
            continue

    if not xs:
        return {"status": "error", "message": "No valid numeric data found"}

    # Normalize
    def norm(vals):
        mn, mx = min(vals), max(vals)
        return [(v - mn) / max(mx - mn, 1e-6) for v in vals]

    nx = norm(xs)
    ny = norm(ys)
    nz = norm(zs)

    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)

    for i, (x, y, z) in enumerate(zip(nx, ny, nz)):
        px = loc[0] + x * scale_factor
        py = loc[1] + y * scale_factor
        pz = loc[2] + z * scale_factor

        bpy.ops.mesh.primitive_uv_sphere_add(location=(px, py, pz), radius=point_size)
        pt = bpy.context.active_object
        pt.name = f"{name}_pt{i}"

        # Color by z-height or color column
        mat = bpy.data.materials.new(name=f"MAT_{pt.name}")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if color_column and colors:
            ci = norm(colors)[i]
            bsdf.inputs["Base Color"].default_value = (ci, 0.3, 1.0 - ci, 1.0)
        else:
            bsdf.inputs["Base Color"].default_value = (z, 0.3, 1.0 - z, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.2
        bsdf.inputs["Metallic"].default_value = 0.1
        pt.data.materials.append(mat)

        for c in pt.users_collection:
            c.objects.unlink(pt)
        col.objects.link(pt)

    executor._sync_scene()
    return {"status": "success", "points": len(xs), "collection": name}


@tool_registry.tool(
    name="create_line_graph_3d",
    description="Create a 3D line graph from ordered x,y data.",
    params={
        "type": "object",
        "properties": {
            "data": {"type": "array", "items": {"type": "object"}},
            "x_column": {"type": "string"},
            "y_column": {"type": "string"},
            "name": {"type": "string", "default": "LineGraph"},
            "location": {"type": "array", "items": {"type": "number"}},
            "scale_factor": {"type": "number", "default": 5.0},
            "line_color": {"type": "array", "items": {"type": "number"}},
            "tube_radius": {"type": "number", "default": 0.03},
        },
        "required": ["data", "x_column", "y_column"],
    }
)
def create_line_graph_3d(data: list, x_column: str, y_column: str,
                         name: str = "LineGraph", location: list = None,
                         scale_factor: float = 5.0, line_color: list = None,
                         tube_radius: float = 0.03):
    """Create a 3D line graph using curve + bevel."""
    executor._ensure_object_mode()
    loc = tuple(location) if location else (0, 0, 0)

    points = []
    for row in data:
        try:
            x = float(row.get(x_column, 0))
            y = float(row.get(y_column, 0))
            points.append((x, y))
        except (ValueError, TypeError):
            continue

    if len(points) < 2:
        return {"status": "error", "message": "Need at least 2 data points"}

    # Normalize
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)

    norm_xs = [(x - x_min) / max(x_max - x_min, 1e-6) for x in xs]
    norm_ys = [(y - y_min) / max(y_max - y_min, 1e-6) for y in ys]

    # Create curve
    curve_data = bpy.data.curves.new(name, type="CURVE")
    curve_data.dimensions = "3D"
    spline = curve_data.splines.new("NURBS")
    spline.points.add(len(points) - 1)
    for i, (nx, ny) in enumerate(zip(norm_xs, norm_ys)):
        px = loc[0] + nx * scale_factor
        py = loc[1]
        pz = loc[2] + ny * scale_factor
        spline.points[i].co = (px, py, pz, 1)
    spline.use_endpoint_u = True

    # Bevel for tube look
    curve_data.bevel_depth = tube_radius
    curve_data.bevel_resolution = 4
    curve_data.fill_mode = "FULL"

    obj = bpy.data.objects.new(name, curve_data)
    bpy.context.scene.collection.objects.link(obj)

    # Material
    mat = bpy.data.materials.new(name=f"MAT_{name}")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    c = tuple(line_color) if line_color else (0.2, 0.8, 1.0)
    bsdf.inputs["Base Color"].default_value = (*c, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.2
    bsdf.inputs["Metallic"].default_value = 0.3
    obj.data.materials.append(mat)

    executor._sync_scene()
    return {"status": "success", "points": len(points), "object": name}
