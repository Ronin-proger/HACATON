"""Mesh operators: never leave a raw primitive as a final object.

Every solid goes through bevel → weighted normals → optional displace →
weld beads / fasteners. Topology stays quads on bevel segments.
"""
from __future__ import annotations

import math
import random
from typing import Iterable, Sequence

import bpy
from mathutils import Vector


def _obj(name: str) -> bpy.types.Object:
    obj = bpy.context.view_layer.objects.active
    obj.name = name
    obj.data.name = name
    return obj


def shade_smooth(obj: bpy.types.Object, angle: float = 40.0) -> None:
    mesh = obj.data
    for poly in mesh.polygons:
        poly.use_smooth = True
    if hasattr(mesh, "use_auto_smooth"):
        mesh.use_auto_smooth = True
        mesh.auto_smooth_angle = math.radians(angle)
        return
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(angle), keep_sharp_edges=True)
    except Exception:
        bpy.ops.object.shade_smooth()


def apply_bevel(
    obj: bpy.types.Object,
    width: float = 0.018,
    segments: int = 3,
    angle_limit: float = 40.0,
) -> None:
    bev = obj.modifiers.new("Bevel", "BEVEL")
    bev.width = width
    bev.segments = segments
    bev.limit_method = "ANGLE"
    bev.angle_limit = math.radians(angle_limit)
    bev.miter_outer = "MITER_ARC"
    bev.harden_normals = True
    bev.offset_type = "WIDTH"


def apply_weighted_normal(obj: bpy.types.Object) -> None:
    wn = obj.modifiers.new("WN", "WEIGHTED_NORMAL")
    wn.mode = "FACE_AREA_WITH_ANGLE"
    wn.keep_sharp = True
    wn.weight = 50


def apply_displace(obj: bpy.types.Object, strength: float, scale: float, seed: int) -> None:
    if strength <= 0:
        return
    tex = bpy.data.textures.new(f"{obj.name}_disp", "CLOUDS")
    tex.noise_scale = scale
    tex.noise_depth = 2
    tex.nabla = 0.03
    rng = random.Random(seed)
    tex.noise_basis = "ORIGINAL_PERLIN"
    disp = obj.modifiers.new("MicroDisplace", "DISPLACE")
    disp.texture = tex
    disp.strength = strength
    disp.mid_level = 0.5
    disp.texture_coords = "LOCAL"
    disp.direction = "NORMAL"


def apply_all_mods(obj: bpy.types.Object) -> None:
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    for mod in list(obj.modifiers):
        bpy.ops.object.modifier_apply(modifier=mod.name)


def finish(
    obj: bpy.types.Object,
    bevel: float = 0.016,
    segments: int = 3,
    displace: float = 0.0,
    disp_scale: float = 0.35,
    seed: int = 0,
    apply: bool = True,
) -> bpy.types.Object:
    apply_bevel(obj, bevel, segments)
    apply_weighted_normal(obj)
    apply_displace(obj, displace, disp_scale, seed)
    shade_smooth(obj)
    if apply:
        apply_all_mods(obj)
    return obj


def cube(
    name: str,
    size: Sequence[float],
    location: Sequence[float] = (0, 0, 0),
    bevel: float = 0.02,
    displace: float = 0.002,
    seed: int = 1,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = _obj(name)
    obj.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finish(obj, bevel=min(bevel, min(size) * 0.12), displace=displace, seed=seed)


def cylinder(
    name: str,
    radius: float,
    depth: float,
    location: Sequence[float] = (0, 0, 0),
    vertices: int = 32,
    bevel: float = 0.008,
    seed: int = 2,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(
        radius=radius, depth=depth, vertices=vertices, location=location
    )
    obj = _obj(name)
    return finish(obj, bevel=bevel, segments=2, displace=0.0015, seed=seed)


def ico(
    name: str,
    radius: float,
    location: Sequence[float],
    subdivisions: int = 2,
    seed: int = 3,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_ico_sphere_add(
        radius=radius, subdivisions=subdivisions, location=location
    )
    obj = _obj(name)
    return finish(obj, bevel=0.004, segments=2, displace=radius * 0.08, disp_scale=0.4, seed=seed)


def extrude_profile(
    name: str,
    points: Sequence[Sequence[float]],
    depth: float,
    location: Sequence[float] = (0, 0, 0),
    bevel: float = 0.012,
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    verts = [(p[0], p[1], 0.0) for p in points]
    faces = [list(range(len(verts)))]
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.extrude_region_move(TRANSFORM_OT_translate={"value": (0, 0, depth)})
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    obj.location = location
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY")
    return finish(obj, bevel=bevel, segments=3, displace=0.001, seed=hash(name) % 999)


def i_beam(name: str, length: float, h: float = 0.4, w: float = 0.22, tf: float = 0.018, tw: float = 0.012) -> bpy.types.Object:
    pts = [
        (-w / 2, -h / 2),
        (w / 2, -h / 2),
        (w / 2, -h / 2 + tf),
        (tw / 2, -h / 2 + tf),
        (tw / 2, h / 2 - tf),
        (w / 2, h / 2 - tf),
        (w / 2, h / 2),
        (-w / 2, h / 2),
        (-w / 2, h / 2 - tf),
        (-tw / 2, h / 2 - tf),
        (-tw / 2, -h / 2 + tf),
        (-w / 2, -h / 2 + tf),
    ]
    obj = extrude_profile(name, pts, length, bevel=0.004)
    obj.rotation_euler[0] = math.radians(90)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return obj


def add_bolts(parent: bpy.types.Object, positions: Iterable[Sequence[float]], radius: float = 0.018) -> None:
    for i, loc in enumerate(positions):
        bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=radius * 0.7, vertices=10, location=loc)
        cap = _obj(f"{parent.name}_bolt_{i}")
        finish(cap, bevel=0.002, segments=2, displace=0, apply=True)
        bpy.ops.mesh.primitive_cylinder_add(
            radius=radius * 1.35, depth=radius * 0.22, vertices=6, location=(loc[0], loc[1], loc[2] + radius * 0.4)
        )
        nut = _obj(f"{parent.name}_nut_{i}")
        finish(nut, bevel=0.0015, segments=1, displace=0, apply=True)
        cap.parent = parent
        nut.parent = parent


def weld_bead(parent: bpy.types.Object, a: Sequence[float], b: Sequence[float], radius: float = 0.01) -> bpy.types.Object:
    dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    length = math.sqrt(dx * dx + dy * dy + dz * dz) or 0.01
    bpy.ops.mesh.primitive_cylinder_add(
        radius=radius, depth=length, vertices=8,
        location=((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2),
    )
    obj = _obj(f"{parent.name}_weld")
    obj.rotation_euler = Vector((dx, dy, dz)).to_track_quat("Z", "Y").to_euler()
    finish(obj, bevel=0.002, displace=0.003, disp_scale=0.05, seed=11)
    obj.parent = parent
    return obj


def make_lods(obj: bpy.types.Object, angles: Sequence[float] = (5.0, 12.0)) -> list[bpy.types.Object]:
    """Planar-dissolve LOD1/LOD2. Keep LOD0 as the source mesh."""
    out = []
    for i, ang in enumerate(angles, start=1):
        dup = obj.copy()
        dup.data = obj.data.copy()
        dup.name = f"{obj.name}_LOD{i}"
        bpy.context.collection.objects.link(dup)
        bpy.context.view_layer.objects.active = dup
        dup.select_set(True)
        dec = dup.modifiers.new("LOD", "DECIMATE")
        dec.decimate_type = "DISSOLVE"
        dec.angle_limit = math.radians(ang)
        bpy.ops.object.modifier_apply(modifier="LOD")
        out.append(dup)
    return out


def set_collection(obj: bpy.types.Object, name: str) -> None:
    col = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if col.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(col)
    if obj.name not in col.objects:
        col.objects.link(obj)
    if obj.name in bpy.context.scene.collection.objects:
        bpy.context.scene.collection.objects.unlink(obj)
