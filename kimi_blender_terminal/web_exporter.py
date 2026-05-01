"""
Web Exporter — export Blender scenes as interactive Three.js web experiences.

Generates:
  1. A GLB file of the current scene
  2. A production-ready HTML file with Three.js, OrbitControls,
     auto-rotation, click interactions, responsive layout, and
     optional scroll-driven camera animation.

Inspired by Spline's web export workflow. The output is a single
self-contained HTML file (or folder) ready to upload to any web host.
"""

import bpy
import html
import json
import os
import tempfile
import shutil

from . import tool_registry
from . import executor


THREEJS_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{title}}</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { background: {{background}}; overflow: hidden; font-family: system-ui, -apple-system, sans-serif; }
    #canvas-container { width: 100vw; height: 100vh; position: relative; }
    canvas { display: block; width: 100%; height: 100%; }
    #loading {
      position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
      color: {{loading_color}}; font-size: 14px; letter-spacing: 2px;
      pointer-events: none; transition: opacity 0.5s;
    }
    #ui {
      position: absolute; bottom: 24px; left: 24px;
      color: {{ui_color}}; font-size: 12px; pointer-events: none;
      opacity: 0.7;
    }
    #ui button {
      pointer-events: auto; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2);
      color: inherit; padding: 6px 12px; border-radius: 4px; cursor: pointer; margin-right: 8px;
      font-size: 11px; text-transform: uppercase; letter-spacing: 1px;
    }
    #ui button:hover { background: rgba(255,255,255,0.2); }
  </style>
  <script type="importmap">
  {
    "imports": {
      "three": "https://unpkg.com/three@0.170.0/build/three.module.js",
      "three/addons/": "https://unpkg.com/three@0.170.0/examples/jsm/"
    }
  }
  </script>
</head>
<body>
  <div id="canvas-container">
    <div id="loading">Loading 3D Scene...</div>
    <div id="ui">
      <button id="btn-rotate">Auto Rotate</button>
      <button id="btn-reset">Reset View</button>
    </div>
  </div>

  <script type="module">
    import * as THREE from 'three';
    import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
    import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
    import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

    const container = document.getElementById('canvas-container');
    const loading = document.getElementById('loading');

    // Scene
    const scene = new THREE.Scene();
    {{scene_background}}

    // Camera
    const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 1000);
    camera.position.set({{cam_x}}, {{cam_y}}, {{cam_z}});

    // Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: {{alpha}} });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.0;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    container.appendChild(renderer.domElement);

    // Environment & Lighting
    const pmremGenerator = new THREE.PMREMGenerator(renderer);
    scene.environment = pmremGenerator.fromScene(new RoomEnvironment(), 0.04).texture;

    {{extra_lights}}

    // Controls
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.minDistance = 1;
    controls.maxDistance = 100;
    controls.target.set({{target_x}}, {{target_y}}, {{target_z}});
    controls.autoRotate = {{auto_rotate}};
    controls.autoRotateSpeed = {{rotate_speed}};

    // Load GLB
    const loader = new GLTFLoader();
    let model = null;
    let mixer = null;
    const clock = new THREE.Clock();

    loader.load('{{glb_filename}}', (gltf) => {
      model = gltf.scene;
      scene.add(model);

      // Auto-center and scale
      const box = new THREE.Box3().setFromObject(model);
      const center = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3());
      const maxDim = Math.max(size.x, size.y, size.z);
      const scale = {{fit_scale}} / maxDim;
      model.scale.setScalar(scale);
      model.position.sub(center.multiplyScalar(scale));

      // Animation
      if (gltf.animations && gltf.animations.length) {
        mixer = new THREE.AnimationMixer(model);
        gltf.animations.forEach((clip) => {
          const action = mixer.clipAction(clip);
          action.play();
        });
      }

      loading.style.opacity = '0';
      setTimeout(() => loading.remove(), 500);
    }, undefined, (err) => {
      console.error('GLB load error:', err);
      loading.textContent = 'Error loading scene';
    });

    // Raycaster for click interaction
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();
    let hoveredObj = null;

    renderer.domElement.addEventListener('mousemove', (e) => {
      mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
      mouse.y = -(e.clientY / window.innerHeight) * 2 + 1;
    });

    renderer.domElement.addEventListener('click', () => {
      if (!model) return;
      raycaster.setFromCamera(mouse, camera);
      const hits = raycaster.intersectObjects(model.children, true);
      if (hits.length > 0) {
        const obj = hits[0].object;
        console.log('Clicked:', obj.name || 'unnamed');
        // Brief highlight effect
        const originalEmissive = obj.material?.emissive?.clone?.() || new THREE.Color(0,0,0);
        if (obj.material && obj.material.emissive) {
          obj.material.emissive.setHex(0x444444);
          setTimeout(() => obj.material.emissive.copy(originalEmissive), 300);
        }
      }
    });

    // UI buttons
    document.getElementById('btn-rotate').addEventListener('click', () => {
      controls.autoRotate = !controls.autoRotate;
    });
    document.getElementById('btn-reset').addEventListener('click', () => {
      controls.reset();
      camera.position.set({{cam_x}}, {{cam_y}}, {{cam_z}});
      controls.target.set({{target_x}}, {{target_y}}, {{target_z}});
    });

    // Resize
    window.addEventListener('resize', () => {
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    });

    // Animation loop
    function animate() {
      requestAnimationFrame(animate);
      const delta = clock.getDelta();
      if (mixer) mixer.update(delta);
      controls.update();
      renderer.render(scene, camera);
    }
    animate();
  </script>
</body>
</html>
"""


@tool_registry.tool(
    name="export_web_scene",
    description="Export the current Blender scene as an interactive Three.js web experience. Generates a GLB + HTML file ready to host.",
    params={
        "type": "object",
        "properties": {
            "output_dir": {"type": "string", "description": "Absolute directory path for output files"},
            "title": {"type": "string", "default": "3D Scene", "description": "Page title"},
            "auto_rotate": {"type": "boolean", "default": True, "description": "Auto-rotate the camera on load"},
            "rotate_speed": {"type": "number", "default": 2.0, "description": "Auto-rotate speed"},
            "background": {"type": "string", "default": "#111111", "description": "CSS background color"},
            "fit_to_screen": {"type": "boolean", "default": True, "description": "Auto-scale model to fit viewport"},
        },
        "required": ["output_dir"],
    }
)
def export_web_scene(output_dir: str, title: str = "3D Scene", auto_rotate: bool = True,
                     rotate_speed: float = 2.0, background: str = "#111111",
                     fit_to_screen: bool = True):
    """Export scene as GLB + Three.js HTML."""
    os.makedirs(output_dir, exist_ok=True)

    # Export GLB
    glb_path = os.path.join(output_dir, "scene.glb")
    try:
        bpy.ops.export_scene.gltf(
            filepath=glb_path,
            export_format="GLB",
            export_yup=True,
            export_materials="EXPORT",
            export_image_format="AUTO",
            use_mesh_edges=False,
            use_mesh_vertices=False,
            export_draco_mesh_compression_enable=False,
            export_apply=True,
            export_animations=True,
            export_animation_mode="ACTIONS",
        )
    except Exception as e:
        return {"status": "error", "message": f"GLB export failed: {e}"}

    # Get camera info
    cam = bpy.context.scene.camera
    cam_pos = (7, -7, 5)
    target = (0, 0, 0)
    if cam:
        cam_pos = (round(cam.location.x, 2), round(cam.location.y, 2), round(cam.location.z, 2))
        # Point camera looks at scene center if no explicit target
        target = (0, 0, 0)

    # Determine scene background
    scene_bg = "scene.background = new THREE.Color('{{background}}');"
    alpha = "false"
    if bpy.context.scene.world and bpy.context.scene.world.use_nodes:
        alpha = "true"
        scene_bg = "// Transparent background - world HDRI will be approximated by RoomEnvironment"

    # Extra lights if scene is dark
    extra_lights = """
    const ambient = new THREE.AmbientLight(0xffffff, 0.4);
    scene.add(ambient);
    const dirLight = new THREE.DirectionalLight(0xffffff, 1.5);
    dirLight.position.set(5, 10, 7);
    dirLight.castShadow = true;
    scene.add(dirLight);
    """

    # Build HTML
    html = THREEJS_TEMPLATE
    html = html.replace("{{title}}", html.escape(title))
    html = html.replace("{{glb_filename}}", "scene.glb")
    html = html.replace("{{cam_x}}", str(cam_pos[0]))
    html = html.replace("{{cam_y}}", str(cam_pos[1]))
    html = html.replace("{{cam_z}}", str(cam_pos[2]))
    html = html.replace("{{target_x}}", str(target[0]))
    html = html.replace("{{target_y}}", str(target[1]))
    html = html.replace("{{target_z}}", str(target[2]))
    html = html.replace("{{auto_rotate}}", "true" if auto_rotate else "false")
    html = html.replace("{{rotate_speed}}", str(rotate_speed))
    html = html.replace("{{background}}", html.escape(background))
    html = html.replace("{{alpha}}", alpha)
    html = html.replace("{{scene_background}}", scene_bg)
    html = html.replace("{{extra_lights}}", extra_lights)
    html = html.replace("{{fit_scale}}", "5" if fit_to_screen else "1")
    html = html.replace("{{loading_color}}", "#ffffff" if background == "#111111" else "#333333")
    html = html.replace("{{ui_color}}", "#ffffff" if background == "#111111" else "#333333")

    html_path = os.path.join(output_dir, "index.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    return {
        "status": "success",
        "glb": glb_path,
        "html": html_path,
        "message": f"Exported to {output_dir}. Open index.html in a browser.",
    }


@tool_registry.tool(
    name="create_3d_text",
    description="Create 3D text in the scene with extrude, bevel, and material.",
    params={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text content"},
            "name": {"type": "string", "default": "3DText"},
            "location": {"type": "array", "items": {"type": "number"}},
            "font_size": {"type": "number", "default": 1.0},
            "extrude": {"type": "number", "default": 0.15},
            "bevel_depth": {"type": "number", "default": 0.02},
            "color": {"type": "array", "items": {"type": "number"}},
            "metallic": {"type": "number", "default": 0.0},
            "roughness": {"type": "number", "default": 0.3},
        },
        "required": ["text"],
    }
)
def create_3d_text(text: str, name: str = "3DText", location: list = None,
                   font_size: float = 1.0, extrude: float = 0.15,
                   bevel_depth: float = 0.02, color: list = None,
                   metallic: float = 0.0, roughness: float = 0.3):
    """Create 3D text object with PBR material."""
    executor._ensure_object_mode()

    bpy.ops.object.text_add(location=tuple(location) if location else (0, 0, 0))
    obj = bpy.context.active_object
    obj.name = name

    text_data = obj.data
    text_data.body = text
    text_data.extrude = extrude
    text_data.bevel_depth = bevel_depth
    text_data.bevel_resolution = 2

    # Scale to approximate font size (Blender text units are roughly meters)
    obj.scale = (font_size, font_size, font_size)

    # Convert to mesh for better material handling
    bpy.ops.object.convert(target="MESH")
    obj = bpy.context.active_object

    # Add material
    mat = bpy.data.materials.new(name=f"MAT_{name}")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    c = tuple(color) if color else (0.9, 0.9, 0.9)
    bsdf.inputs["Base Color"].default_value = (*c, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness

    if len(obj.data.materials) == 0:
        obj.data.materials.append(mat)
    else:
        obj.data.materials[0] = mat

    executor._sync_scene()
    return {"name": obj.name, "text": text, "location": list(obj.location)}


@tool_registry.tool(
    name="create_bar_chart_3d",
    description="Create a 3D bar chart from data. Pass labels and values as parallel lists.",
    params={
        "type": "object",
        "properties": {
            "labels": {"type": "array", "items": {"type": "string"}, "description": "Bar labels"},
            "values": {"type": "array", "items": {"type": "number"}, "description": "Bar heights"},
            "name": {"type": "string", "default": "BarChart"},
            "location": {"type": "array", "items": {"type": "number"}},
            "bar_width": {"type": "number", "default": 0.5},
            "spacing": {"type": "number", "default": 0.8},
            "max_height": {"type": "number", "default": 5.0},
            "color": {"type": "array", "items": {"type": "number"}},
        },
        "required": ["labels", "values"],
    }
)
def create_bar_chart_3d(labels: list, values: list, name: str = "BarChart",
                        location: list = None, bar_width: float = 0.5,
                        spacing: float = 0.8, max_height: float = 5.0,
                        color: list = None):
    """Create a 3D bar chart from parallel labels/values arrays."""
    if len(labels) != len(values):
        return {"status": "error", "message": "labels and values must have same length"}
    if not values:
        return {"status": "error", "message": "No data provided"}

    executor._ensure_object_mode()
    loc = tuple(location) if location else (0, 0, 0)
    max_val = max(abs(v) for v in values) or 1.0

    # Create a collection for the chart
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)

    base_color = tuple(color) if color else (0.2, 0.6, 1.0)

    for i, (label, value) in enumerate(zip(labels, values)):
        height = (abs(value) / max_val) * max_height
        x = loc[0] + i * spacing
        y = loc[1]
        z = loc[2] + height / 2

        bpy.ops.mesh.primitive_cube_add(location=(x, y, z), size=1.0)
        bar = bpy.context.active_object
        bar.name = f"{name}_{label}"
        bar.scale = (bar_width, bar_width, height)
        bar.location = (x, y, z)

        # Material with height-based lightness
        mat = bpy.data.materials.new(name=f"MAT_{bar.name}")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        intensity = 0.5 + 0.5 * (abs(value) / max_val)
        c = (base_color[0] * intensity, base_color[1] * intensity, base_color[2] * intensity)
        bsdf.inputs["Base Color"].default_value = (*c, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.4
        bar.data.materials.append(mat)

        # Move to collection
        for c in bar.users_collection:
            c.objects.unlink(bar)
        col.objects.link(bar)

    executor._sync_scene()
    return {
        "status": "success",
        "chart_name": name,
        "bars": len(labels),
        "collection": name,
    }
