"""Assemble the cinematic construction site. All solids are bevelled."""
from __future__ import annotations

import math
import random

import bpy
from mathutils import Vector

from . import meshops as mo
from . import materials as mats


def _link(obj, col: str, mat=None):
    mo.set_collection(obj, col)
    if mat:
        mats.assign(obj, mat)
    return obj


def terrain(lib, rng: random.Random):
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=96, y_subdivisions=96, size=120, location=(0, 0, 0))
    ground = mo._obj("terrain_dirt")
    for v in ground.data.vertices:
        n = rng.random() * 0.35 + math.sin(v.co.x * 0.07) * 0.18 + math.cos(v.co.y * 0.06) * 0.16
        pad = abs(v.co.x) < 38 and abs(v.co.y) < 34
        v.co.z = n * (0.12 if pad else 1.0)
    ground.data.update()
    mo.finish(ground, bevel=0.0, displace=0.04, disp_scale=2.4, seed=4, apply=True)
    mats.assign(ground, lib["dirt"])
    mo.set_collection(ground, "ENV")

    bpy.ops.mesh.primitive_plane_add(size=1, location=(-22.8, 2, 0.05))
    road = mo._obj("road_asphalt")
    road.scale = (8.4, 92, 1)
    bpy.ops.object.transform_apply(scale=True)
    mo.finish(road, bevel=0.03, segments=2, displace=0.004, seed=5)
    mats.assign(road, lib["asphalt"])
    mo.set_collection(road, "ENV")
    return ground


def building(lib):
    col = "BUILDING"
    podium = mo.cube("podium", (9.3, 7.0, 0.48), (13.2, -9.2, 0.24), bevel=0.04, displace=0.004)
    _link(podium, col, lib["concrete"])
    for ix in range(-2, 3):
        for iz in range(-1, 2):
            beam = mo.i_beam(f"col_{ix}_{iz}", 7.4, h=0.38, w=0.22)
            beam.location = (13.2 + ix * 3.7, -9.2 + iz * 5.4, 4.1)
            _link(beam, col, lib["steel"])
    for f in range(2):
        y = 4.2 + f * 3.65
        girder = mo.i_beam(f"girder_{f}", 15.4, h=0.36, w=0.2)
        girder.rotation_euler[2] = math.radians(90)
        bpy.context.view_layer.objects.active = girder
        bpy.ops.object.transform_apply(rotation=True)
        girder.location = (13.2, -9.2, y)
        _link(girder, col, lib["steel"])
    wall = mo.cube("brick_starter", (8.6, 0.22, 1.35), (13.2, -16.05, 1.6), bevel=0.012, displace=0.006)
    _link(wall, col, lib["brick"])
    return podium


def tower_crane(lib):
    col = "CRANE"
    base = mo.cube("crane_base", (2.6, 2.6, 0.45), (3.2, -20.4, 0.22), bevel=0.05)
    _link(base, col, lib["steel"])
    mast = mo.cube("crane_mast", (0.22, 0.22, 15.2), (3.2, -20.4, 8.0), bevel=0.02, displace=0.002)
    _link(mast, col, lib["paint"])
    for y in [i * 1.35 for i in range(12)]:
        brace = mo.cube(f"brace_{y:.1f}", (1.85, 0.06, 0.06), (3.2, -20.4, 1.2 + y), bevel=0.008)
        _link(brace, col, lib["paint"])
    jib = mo.cube("jib", (17.0, 0.16, 0.16), (12.0, -20.4, 16.4), bevel=0.02)
    _link(jib, col, lib["paint"])
    cab = mo.cube("crane_cab", (1.2, 1.1, 1.15), (4.6, -20.4, 16.9), bevel=0.04)
    _link(cab, col, lib["steel"])
    glass = mo.cube("crane_glass", (0.9, 0.06, 0.7), (4.6, -19.82, 17.05), bevel=0.01, displace=0)
    _link(glass, col, lib["glass"])
    return base


def excavator(lib, loc, yaw):
    col = "VEHICLES"
    house = mo.extrude_profile(
        "ex_house",
        [(-1.2, 0.1), (-1.25, 0.55), (-0.4, 1.15), (0.9, 1.1), (1.35, 0.7), (1.3, 0.12)],
        2.15,
        bevel=0.03,
    )
    house.location = loc
    house.rotation_euler[2] = yaw
    _link(house, col, lib["paint"])
    cab = mo.extrude_profile(
        "ex_cab",
        [(-0.55, 0.0), (-0.6, 0.55), (-0.15, 1.15), (0.55, 1.12), (0.6, 0.08)],
        1.45,
        bevel=0.025,
    )
    cab.location = (loc[0] - 0.4, loc[1], loc[2] + 1.15)
    cab.rotation_euler[2] = yaw
    _link(cab, col, lib["steel"])
    boom = mo.cube("ex_boom", (1.85, 0.16, 0.18), (loc[0] + 1.6, loc[1], loc[2] + 1.85), bevel=0.03)
    boom.rotation_euler[1] = math.radians(-28)
    boom.rotation_euler[2] = yaw
    _link(boom, col, lib["paint"])
    stick = mo.cube("ex_stick", (1.35, 0.12, 0.14), (loc[0] + 3.1, loc[1], loc[2] + 1.15), bevel=0.025)
    stick.rotation_euler[1] = math.radians(38)
    stick.rotation_euler[2] = yaw
    _link(stick, col, lib["paint"])
    bucket = mo.ico("ex_bucket", 0.42, (loc[0] + 4.1, loc[1], loc[2] + 0.45), subdivisions=2, seed=21)
    bucket.scale = (1.3, 0.9, 0.7)
    bpy.context.view_layer.objects.active = bucket
    bpy.ops.object.transform_apply(scale=True)
    _link(bucket, col, lib["steel"])
    for s in (-1, 1):
        track = mo.cube(f"ex_track_{s}", (1.95, 0.38, 0.22), (loc[0], loc[1] + s * 1.05, loc[2] + 0.28), bevel=0.04)
        _link(track, col, lib["rubber"])
    return house


def dump_truck(lib, loc, yaw):
    col = "VEHICLES"
    cab = mo.extrude_profile(
        "dt_cab",
        [(-0.95, 0.08), (-1.02, 0.28), (-0.98, 0.85), (-0.45, 1.58), (0.05, 1.85), (0.85, 1.82), (0.92, 0.35), (0.7, 0.08)],
        2.05,
        bevel=0.035,
    )
    cab.location = (loc[0] - 2.1, loc[1], loc[2])
    cab.rotation_euler[2] = yaw
    _link(cab, col, lib["paint"])
    bed = mo.extrude_profile(
        "dt_bed",
        [(-1.9, 0.15), (-1.85, 1.25), (1.95, 1.35), (2.05, 0.15)],
        2.15,
        bevel=0.03,
    )
    bed.location = (loc[0] + 0.9, loc[1], loc[2] + 0.55)
    bed.rotation_euler[2] = yaw
    _link(bed, col, lib["paint"])
    for x, s in [(-1.7, -1), (-1.7, 1), (0.3, -1), (0.3, 1), (2.0, -1), (2.0, 1)]:
        tire = mo.cylinder(f"dt_tire_{x}_{s}", 0.48, 0.34, (loc[0] + x, loc[1] + s * 1.02, loc[2] + 0.48), vertices=24, bevel=0.012)
        tire.rotation_euler[1] = math.radians(90)
        _link(tire, col, lib["rubber"])
    return cab


def mixer(lib, loc, yaw):
    col = "VEHICLES"
    cab = mo.extrude_profile(
        "mx_cab",
        [(-0.9, 0.08), (-0.98, 0.82), (-0.4, 1.55), (0.15, 1.8), (0.82, 1.78), (0.9, 0.3), (0.7, 0.08)],
        2.0,
        bevel=0.03,
    )
    cab.location = (loc[0] - 2.2, loc[1], loc[2])
    cab.rotation_euler[2] = yaw
    _link(cab, col, lib["steel"])
    drum = mo.cylinder("mx_drum", 1.08, 3.2, (loc[0] + 0.7, loc[1], loc[2] + 1.95), vertices=32, bevel=0.02)
    drum.rotation_euler[1] = math.radians(78)
    drum.rotation_euler[2] = yaw
    _link(drum, col, lib["steel"])
    for i in range(4):
        fin = mo.cube(f"mx_fin_{i}", (1.4, 0.04, 0.12), (loc[0] + 0.7, loc[1], loc[2] + 1.95), bevel=0.008)
        fin.rotation_euler[1] = math.radians(78)
        fin.rotation_euler[2] = yaw + i * math.radians(45)
        _link(fin, col, lib["steel"])
    return cab


def props(lib, rng: random.Random):
    col = "PROPS"
    for i, loc in enumerate([(-27, -11, 1.3), (-27, -13.4, 1.3), (26.5, -18, 1.3)]):
        c = mo.cube(f"container_{i}", (3.03, 1.22, 1.3), loc, bevel=0.04, displace=0.006, seed=30 + i)
        _link(c, col, lib["paint"] if i % 2 else lib["steel"])
    cabin = mo.cube("welfare", (3.6, 1.7, 1.35), (25.2, 17.4, 1.4), bevel=0.045, displace=0.003)
    _link(cabin, col, lib["wood"])
    gen = mo.cube("generator", (0.95, 0.55, 0.72), (28.2, -1.2, 0.72), bevel=0.03, displace=0.004)
    _link(gen, col, lib["paint"])
    tank = mo.cylinder("water_tank", 1.55, 2.15, (22.8, -8, 1.1), vertices=28, bevel=0.03)
    _link(tank, col, lib["steel"])
    skip = mo.extrude_profile("skip", [(-1.1, 0), (-1.2, 1.3), (1.2, 1.3), (1.1, 0)], 1.7, (20.6, 19.4, 0), bevel=0.03)
    _link(skip, col, lib["paint"])
    comp = mo.extrude_profile("compressor", [(-0.7, 0), (-0.72, 1.05), (0.55, 1.12), (0.7, 0)], 0.85, (28.2, 1.4, 0), bevel=0.025)
    _link(comp, col, lib["paint"])
    air = mo.cylinder("air_tank", 0.35, 0.9, (27.4, 1.4, 0.55), vertices=20, bevel=0.01)
    air.rotation_euler[1] = math.radians(90)
    _link(air, col, lib["steel"])
    for i in range(8):
        plank = mo.cube(f"timber_{i}", (1.7, 0.08, 0.05), (21.5, -16.4, 0.08 + i * 0.11), bevel=0.008, displace=0.003, seed=40 + i)
        _link(plank, col, lib["wood"])
    for i in range(10):
        cone = mo.ico(f"cone_{i}", 0.16, (-22.8 + (i % 2) * 0.7, -12 + i * 1.15, 0.28), subdivisions=1, seed=50 + i)
        cone.scale = (1, 1, 1.7)
        bpy.context.view_layer.objects.active = cone
        bpy.ops.object.transform_apply(scale=True)
        _link(cone, col, lib["paint"])


def people(lib):
    col = "PEOPLE"
    spots = [(11, -6.5, 0), (15, -10, 0.95), (4.5, -15.5, 1.7), (8, 12, 0), (20, -2.8, 0)]
    for i, (x, y, z) in enumerate(spots):
        torso = mo.cube(f"worker_{i}_torso", (0.22, 0.16, 0.32), (x, y, z + 0.95), bevel=0.04, displace=0)
        _link(torso, col, lib["hivis"])
        head = mo.ico(f"worker_{i}_head", 0.11, (x, y, z + 1.32), subdivisions=2, seed=60 + i)
        _link(head, col, lib["wood"])
        helm = mo.ico(f"worker_{i}_helm", 0.125, (x, y, z + 1.4), subdivisions=2, seed=70 + i)
        _link(helm, col, lib["paint"])


def cables():
    curve = bpy.data.curves.new("temp_power", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = 0.025
    curve.bevel_resolution = 3
    spl = curve.splines.new("NURBS")
    pts = [(-29, 23.5, 8.8), (-10, 10, 6), (3.2, -20.4, 12)]
    spl.points.add(len(pts) - 1)
    for p, v in zip(spl.points, pts):
        p.co = (*v, 1)
    obj = bpy.data.objects.new("temp_cables", curve)
    bpy.context.collection.objects.link(obj)
    mo.set_collection(obj, "PROPS")


def lighting():
    sun = bpy.data.lights.new("Sun", "SUN")
    sun.energy = 6.5
    sun.angle = math.radians(0.53)
    sun.color = (1.0, 0.93, 0.82)
    sun_obj = bpy.data.objects.new("Sun", sun)
    sun_obj.rotation_euler = (math.radians(48), math.radians(12), math.radians(198))
    bpy.context.collection.objects.link(sun_obj)
    world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Color"].default_value = (0.62, 0.70, 0.78, 1)
    bg.inputs["Strength"].default_value = 0.85
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(28)
    sky.sun_rotation = math.radians(198)
    sky.air_density = 1.05
    sky.dust_density = 0.4
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])


def assemble():
    rng = random.Random(17)
    lib = mats.build_library()
    terrain(lib, rng)
    building(lib)
    tower_crane(lib)
    excavator(lib, (-7.2, 7.4, 0), 0.62)
    excavator(lib, (2.1, 1.6, 0), -0.95)
    dump_truck(lib, (-12.2, 14.2, 0), 0.38)
    mixer(lib, (1.8, 13.4, 0), -0.48)
    dump_truck(lib, (8.4, 16.6, 0), -0.22)
    excavator(lib, (6.4, -3.2, 0), 1.15)
    props(lib, rng)
    people(lib)
    cables()
    lighting()
