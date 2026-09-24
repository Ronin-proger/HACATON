"""
StroySync cinematic construction site — Blender 4.2+ / Cycles.

    blender --background --python tools/site_dcc/generate_site.py -- --res 64 --export

Writes:
  tools/site_dcc/output/stroysync_site.blend
  tools/site_dcc/output/stroysync_site.glb
  tools/site_dcc/output/preview.png
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import bpy  # noqa: E402
from stroysync_dcc.assemble import assemble  # noqa: E402


def reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.engine = "CYCLES"
    bpy.context.scene.cycles.device = "GPU"
    bpy.context.scene.cycles.samples = 128
    bpy.context.scene.cycles.use_denoising = True
    bpy.context.scene.view_settings.view_transform = "Filmic"
    bpy.context.scene.view_settings.look = "Medium High Contrast"
    bpy.context.scene.view_settings.exposure = -0.15
    bpy.context.scene.render.resolution_x = 2560
    bpy.context.scene.render.resolution_y = 1440
    bpy.context.scene.render.filepath = os.path.join(ROOT, "output", "preview.png")
    cam = bpy.data.cameras.new("hero")
    cam.lens = 32
    cam.dof.use_dof = True
    cam.dof.aperture_fstop = 5.6
    cam_obj = bpy.data.objects.new("hero", cam)
    cam_obj.location = (26, 28, 13.2)
    cam_obj.rotation_euler = (1.05, 0, 3.7)
    bpy.context.collection.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj


def export_glb(path: str) -> None:
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format="GLB",
        export_apply=True,
        export_texcoords=True,
        export_normals=True,
        export_tangents=True,
        export_materials="EXPORT",
        export_cameras=False,
        export_lights=False,
    )


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    p = argparse.ArgumentParser()
    p.add_argument("--res", type=int, default=64, help="unused grid hint, kept for batch scripts")
    p.add_argument("--export", action="store_true")
    p.add_argument("--render", action="store_true")
    p.add_argument("--bake", action="store_true")
    args = p.parse_args(argv)

    out = os.path.join(ROOT, "output")
    os.makedirs(out, exist_ok=True)
    reset_scene()
    assemble()
    blend = os.path.join(out, "stroysync_site.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    if args.export:
        export_glb(os.path.join(out, "stroysync_site.glb"))
    if args.bake:
        from stroysync_dcc.materials import bake_all
        bake_all(os.path.join(out, "maps"), 4096)
    if args.render:
        bpy.ops.render.render(write_still=True)
    print(f"saved {blend}")


if __name__ == "__main__":
    main()
