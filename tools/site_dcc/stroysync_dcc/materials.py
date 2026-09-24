"""Procedural PBR library for Cycles / EEVEE.

Each material is a full node tree: albedo layers, micro/macro normals,
roughness, metallic, AO, displacement. Maps are 4K-equivalent through
procedural evaluation at render (Cycles samples the noise at shading rate).
Bake to 4K/8K PNG via bake_all() when you need bitmaps for Unreal/Unity.
"""
from __future__ import annotations

import bpy


CHANNELS = ("albedo", "normal", "roughness", "metallic", "ao", "displacement")


def _nt(mat: bpy.types.Material) -> bpy.types.NodeTree:
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    return nt


def _out(nt: bpy.types.NodeTree) -> bpy.types.Node:
    n = nt.nodes.new("ShaderNodeOutputMaterial")
    n.location = (900, 0)
    return n


def _principled(nt: bpy.types.NodeTree) -> bpy.types.Node:
    n = nt.nodes.new("ShaderNodeBsdfPrincipled")
    n.location = (560, 0)
    n.inputs["IOR"].default_value = 1.45
    return n


def _tex_coord(nt: bpy.types.NodeTree) -> bpy.types.Node:
    n = nt.nodes.new("ShaderNodeTexCoord")
    n.location = (-980, 0)
    return n


def _mapping(nt: bpy.types.NodeTree, scale: tuple[float, float, float], loc=(-760, 0)) -> bpy.types.Node:
    n = nt.nodes.new("ShaderNodeMapping")
    n.location = loc
    n.inputs["Scale"].default_value = scale
    return n


def _noise(nt: bpy.types.NodeTree, scale: float, detail: float, loc, roughness: float = 0.55) -> bpy.types.Node:
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.location = loc
    n.inputs["Scale"].default_value = scale
    n.inputs["Detail"].default_value = detail
    n.inputs["Roughness"].default_value = roughness
    return n


def _voronoi(nt: bpy.types.NodeTree, scale: float, loc, feature: str = "F1") -> bpy.types.Node:
    n = nt.nodes.new("ShaderNodeTexVoronoi")
    n.location = loc
    n.feature = feature
    n.inputs["Scale"].default_value = scale
    return n


def _ramp(nt: bpy.types.NodeTree, loc, stops: list[tuple[float, tuple[float, float, float, float]]]) -> bpy.types.Node:
    n = nt.nodes.new("ShaderNodeValToRGB")
    n.location = loc
    while len(n.color_ramp.elements) > 2:
        n.color_ramp.elements.remove(n.color_ramp.elements[0])
    n.color_ramp.elements[0].position = stops[0][0]
    n.color_ramp.elements[0].color = stops[0][1]
    n.color_ramp.elements[-1].position = stops[-1][0]
    n.color_ramp.elements[-1].color = stops[-1][1]
    for pos, col in stops[1:-1]:
        el = n.color_ramp.elements.new(pos)
        el.color = col
    return n


def _bump(nt: bpy.types.NodeTree, strength: float, loc) -> bpy.types.Node:
    n = nt.nodes.new("ShaderNodeBump")
    n.location = loc
    n.inputs["Strength"].default_value = strength
    return n


def _link(nt, a, a_out, b, b_in) -> None:
    nt.links.new(a.outputs[a_out], b.inputs[b_in])


def _base(name: str) -> tuple[bpy.types.Material, bpy.types.NodeTree, bpy.types.Node, bpy.types.Node]:
    mat = bpy.data.materials.new(name)
    mat.cycles.displacement_method = "BOTH"
    nt = _nt(mat)
    out = _out(nt)
    bsdf = _principled(nt)
    _link(nt, bsdf, "BSDF", out, "Surface")
    return mat, nt, out, bsdf


def concrete_formwork() -> bpy.types.Material:
    mat, nt, out, bsdf = _base("M_ConcreteFormwork")
    coord = _tex_coord(nt)
    map1 = _mapping(nt, (4.2, 4.2, 4.2), (-760, 80))
    map2 = _mapping(nt, (38, 38, 38), (-760, -160))
    _link(nt, coord, "Object", map1, "Vector")
    _link(nt, coord, "Object", map2, "Vector")
    n1 = _noise(nt, 6.0, 12.0, (-520, 80), 0.62)
    n2 = _voronoi(nt, 55.0, (-520, -160), "DISTANCE_TO_EDGE")
    _link(nt, map1, "Vector", n1, "Vector")
    _link(nt, map2, "Vector", n2, "Vector")
    mix = nt.nodes.new("ShaderNodeMixRGB")
    mix.location = (-260, 40)
    mix.blend_type = "MULTIPLY"
    mix.inputs["Fac"].default_value = 0.35
    _link(nt, n1, "Fac", mix, "Color1")
    _link(nt, n2, "Distance", mix, "Color2")
    ramp = _ramp(nt, (0, 40), [
        (0.0, (0.42, 0.40, 0.37, 1)),
        (0.45, (0.62, 0.60, 0.56, 1)),
        (0.72, (0.70, 0.68, 0.64, 1)),
        (1.0, (0.78, 0.76, 0.72, 1)),
    ])
    _link(nt, mix, "Color", ramp, "Fac")
    _link(nt, ramp, "Color", bsdf, "Base Color")
    bsdf.inputs["Roughness"].default_value = 0.78
    bsdf.inputs["Specular IOR Level"].default_value = 0.35
    bump = _bump(nt, 0.18, (280, -220))
    _link(nt, mix, "Color", bump, "Height")
    _link(nt, bump, "Normal", bsdf, "Normal")
    disp = nt.nodes.new("ShaderNodeDisplacement")
    disp.location = (560, -280)
    disp.inputs["Scale"].default_value = 0.012
    _link(nt, mix, "Color", disp, "Height")
    _link(nt, disp, "Displacement", out, "Displacement")
    return mat


def wet_asphalt() -> bpy.types.Material:
    mat, nt, out, bsdf = _base("M_WetAsphalt")
    coord = _tex_coord(nt)
    map1 = _mapping(nt, (8, 8, 8), (-760, 40))
    _link(nt, coord, "Object", map1, "Vector")
    n = _noise(nt, 14.0, 10.0, (-520, 40), 0.7)
    _link(nt, map1, "Vector", n, "Vector")
    puddle = _noise(nt, 2.4, 4.0, (-520, -180), 0.4)
    _link(nt, map1, "Vector", puddle, "Vector")
    ramp = _ramp(nt, (-240, 40), [
        (0.0, (0.03, 0.03, 0.035, 1)),
        (0.55, (0.07, 0.07, 0.08, 1)),
        (1.0, (0.12, 0.12, 0.13, 1)),
    ])
    _link(nt, n, "Fac", ramp, "Fac")
    _link(nt, ramp, "Color", bsdf, "Base Color")
    mixr = nt.nodes.new("ShaderNodeMixRGB")
    mixr.location = (200, -80)
    mixr.blend_type = "MIX"
    mixr.inputs["Color1"].default_value = (0.85, 0.85, 0.85, 1)
    mixr.inputs["Color2"].default_value = (0.12, 0.12, 0.12, 1)
    _link(nt, puddle, "Fac", mixr, "Fac")
    _link(nt, mixr, "Color", bsdf, "Roughness")
    bsdf.inputs["Metallic"].default_value = 0.02
    bump = _bump(nt, 0.12, (280, -260))
    _link(nt, n, "Fac", bump, "Height")
    _link(nt, bump, "Normal", bsdf, "Normal")
    return mat


def rusty_steel() -> bpy.types.Material:
    mat, nt, out, bsdf = _base("M_RustySteel")
    coord = _tex_coord(nt)
    map1 = _mapping(nt, (3.5, 3.5, 3.5), (-760, 40))
    _link(nt, coord, "Object", map1, "Vector")
    rust = _noise(nt, 7.0, 11.0, (-520, 80), 0.58)
    _link(nt, map1, "Vector", rust, "Vector")
    streak = nt.nodes.new("ShaderNodeTexNoise")
    streak.location = (-520, -140)
    streak.noise_dimensions = "2D"
    streak.inputs["Scale"].default_value = 18
    streak.inputs["Detail"].default_value = 6
    _link(nt, map1, "Vector", streak, "Vector")
    mixm = nt.nodes.new("ShaderNodeMixRGB")
    mixm.location = (-200, 40)
    mixm.inputs["Color1"].default_value = (0.38, 0.40, 0.42, 1)
    mixm.inputs["Color2"].default_value = (0.36, 0.16, 0.07, 1)
    _link(nt, rust, "Fac", mixm, "Fac")
    _link(nt, mixm, "Color", bsdf, "Base Color")
    inv = nt.nodes.new("ShaderNodeMath")
    inv.location = (40, -80)
    inv.operation = "SUBTRACT"
    inv.inputs[0].default_value = 0.82
    _link(nt, rust, "Fac", inv, 1)
    _link(nt, inv, "Value", bsdf, "Metallic")
    bsdf.inputs["Roughness"].default_value = 0.48
    bump = _bump(nt, 0.22, (280, -240))
    _link(nt, rust, "Fac", bump, "Height")
    _link(nt, bump, "Normal", bsdf, "Normal")
    return mat


def cat_paint() -> bpy.types.Material:
    mat, nt, out, bsdf = _base("M_CatPaint")
    coord = _tex_coord(nt)
    map1 = _mapping(nt, (2.2, 2.2, 2.2), (-760, 40))
    _link(nt, coord, "Object", map1, "Vector")
    dust = _noise(nt, 5.5, 8.0, (-520, 40), 0.5)
    chips = _voronoi(nt, 42.0, (-520, -160), "DISTANCE_TO_EDGE")
    _link(nt, map1, "Vector", dust, "Vector")
    _link(nt, map1, "Vector", chips, "Vector")
    mix = nt.nodes.new("ShaderNodeMixRGB")
    mix.location = (-200, 40)
    mix.inputs["Color1"].default_value = (0.72, 0.55, 0.18, 1)
    mix.inputs["Color2"].default_value = (0.55, 0.45, 0.22, 1)
    _link(nt, dust, "Fac", mix, "Fac")
    _link(nt, mix, "Color", bsdf, "Base Color")
    bsdf.inputs["Roughness"].default_value = 0.42
    bsdf.inputs["Metallic"].default_value = 0.12
    bsdf.inputs["Coat Weight"].default_value = 0.18
    bsdf.inputs["Coat Roughness"].default_value = 0.35
    bump = _bump(nt, 0.08, (280, -200))
    _link(nt, chips, "Distance", bump, "Height")
    _link(nt, bump, "Normal", bsdf, "Normal")
    return mat


def timber() -> bpy.types.Material:
    mat, nt, out, bsdf = _base("M_Timber")
    coord = _tex_coord(nt)
    map1 = _mapping(nt, (1.2, 8.0, 1.2), (-760, 40))
    _link(nt, coord, "Object", map1, "Vector")
    grain = _noise(nt, 18.0, 9.0, (-520, 40), 0.65)
    knot = _voronoi(nt, 6.0, (-520, -160))
    _link(nt, map1, "Vector", grain, "Vector")
    _link(nt, map1, "Vector", knot, "Vector")
    ramp = _ramp(nt, (-220, 40), [
        (0.0, (0.22, 0.13, 0.07, 1)),
        (0.5, (0.42, 0.26, 0.12, 1)),
        (1.0, (0.55, 0.36, 0.18, 1)),
    ])
    _link(nt, grain, "Fac", ramp, "Fac")
    _link(nt, ramp, "Color", bsdf, "Base Color")
    bsdf.inputs["Roughness"].default_value = 0.72
    bump = _bump(nt, 0.28, (280, -200))
    _link(nt, grain, "Fac", bump, "Height")
    _link(nt, bump, "Normal", bsdf, "Normal")
    return mat


def brickwork() -> bpy.types.Material:
    mat, nt, out, bsdf = _base("M_Brickwork")
    coord = _tex_coord(nt)
    brick = nt.nodes.new("ShaderNodeTexBrick")
    brick.location = (-480, 40)
    brick.offset = 0.5
    brick.inputs["Scale"].default_value = 4.5
    brick.inputs["Mortar Size"].default_value = 0.018
    brick.inputs["Color1"].default_value = (0.42, 0.22, 0.16, 1)
    brick.inputs["Color2"].default_value = (0.50, 0.28, 0.18, 1)
    brick.inputs["Mortar"].default_value = (0.62, 0.58, 0.52, 1)
    _link(nt, coord, "Object", brick, "Vector")
    _link(nt, brick, "Color", bsdf, "Base Color")
    bsdf.inputs["Roughness"].default_value = 0.82
    bump = _bump(nt, 0.35, (280, -180))
    _link(nt, brick, "Color", bump, "Height")
    _link(nt, bump, "Normal", bsdf, "Normal")
    return mat


def dirt_ground() -> bpy.types.Material:
    mat, nt, out, bsdf = _base("M_DirtGround")
    coord = _tex_coord(nt)
    map1 = _mapping(nt, (6, 6, 6), (-760, 40))
    _link(nt, coord, "Object", map1, "Vector")
    n = _noise(nt, 9.0, 14.0, (-520, 40), 0.7)
    peb = _voronoi(nt, 28.0, (-520, -160))
    _link(nt, map1, "Vector", n, "Vector")
    _link(nt, map1, "Vector", peb, "Vector")
    mix = nt.nodes.new("ShaderNodeMixRGB")
    mix.location = (-200, 20)
    mix.inputs["Color1"].default_value = (0.22, 0.16, 0.10, 1)
    mix.inputs["Color2"].default_value = (0.32, 0.24, 0.14, 1)
    _link(nt, n, "Fac", mix, "Fac")
    _link(nt, mix, "Color", bsdf, "Base Color")
    bsdf.inputs["Roughness"].default_value = 0.95
    bump = _bump(nt, 0.45, (280, -200))
    _link(nt, peb, "Distance", bump, "Height")
    _link(nt, bump, "Normal", bsdf, "Normal")
    disp = nt.nodes.new("ShaderNodeDisplacement")
    disp.location = (560, -280)
    disp.inputs["Scale"].default_value = 0.06
    _link(nt, n, "Fac", disp, "Height")
    _link(nt, disp, "Displacement", out, "Displacement")
    return mat


def glass_cab() -> bpy.types.Material:
    mat, nt, out, bsdf = _base("M_CabGlass")
    bsdf.inputs["Base Color"].default_value = (0.55, 0.64, 0.70, 1)
    bsdf.inputs["Metallic"].default_value = 0.0
    bsdf.inputs["Roughness"].default_value = 0.06
    bsdf.inputs["Transmission Weight"].default_value = 0.86
    bsdf.inputs["IOR"].default_value = 1.52
    mat.blend_method = "BLEND"
    mat.use_screen_refraction = True
    mat.refraction_depth = 0.12
    return mat


def hi_vis() -> bpy.types.Material:
    mat, nt, out, bsdf = _base("M_HiVis")
    bsdf.inputs["Base Color"].default_value = (0.72, 0.58, 0.12, 1)
    bsdf.inputs["Roughness"].default_value = 0.62
    bsdf.inputs["Sheen Weight"].default_value = 0.35
    return mat


def rubber() -> bpy.types.Material:
    mat, nt, out, bsdf = _base("M_Rubber")
    coord = _tex_coord(nt)
    n = _noise(nt, 40.0, 6.0, (-480, 0), 0.45)
    _link(nt, coord, "Object", n, "Vector")
    bsdf.inputs["Base Color"].default_value = (0.03, 0.03, 0.03, 1)
    bsdf.inputs["Roughness"].default_value = 0.88
    bump = _bump(nt, 0.4, (280, -160))
    _link(nt, n, "Fac", bump, "Height")
    _link(nt, bump, "Normal", bsdf, "Normal")
    return mat


LIBRARY = {
    "concrete": concrete_formwork,
    "asphalt": wet_asphalt,
    "steel": rusty_steel,
    "paint": cat_paint,
    "wood": timber,
    "brick": brickwork,
    "dirt": dirt_ground,
    "glass": glass_cab,
    "hivis": hi_vis,
    "rubber": rubber,
}


def build_library() -> dict[str, bpy.types.Material]:
    return {key: fn() for key, fn in LIBRARY.items()}


def assign(obj: bpy.types.Object, mat: bpy.types.Material) -> None:
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)


def _bake_image(name: str, res: int, data: bool) -> bpy.types.Image:
    img = bpy.data.images.new(name, width=res, height=res, alpha=False, float_buffer=False)
    img.colorspace_settings.name = "Non-Color" if data else "sRGB"
    return img


def _active_image_node(nt: bpy.types.NodeTree, img: bpy.types.Image) -> bpy.types.Node:
    node = nt.nodes.new("ShaderNodeTexImage")
    node.image = img
    for n in nt.nodes:
        n.select = False
    node.select = True
    nt.nodes.active = node
    return node


def _emit_hijack(nt: bpy.types.NodeTree, src, src_socket: str) -> tuple:
    """Temporarily route a value into Emission so Cycles can bake EMIT."""
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    emit = nt.nodes.new("ShaderNodeEmission")
    emit.inputs["Strength"].default_value = 1.0
    if src.outputs[src_socket].type == "VALUE":
        comb = nt.nodes.new("ShaderNodeCombineRGB")
        nt.links.new(src.outputs[src_socket], comb.inputs["R"])
        nt.links.new(src.outputs[src_socket], comb.inputs["G"])
        nt.links.new(src.outputs[src_socket], comb.inputs["B"])
        nt.links.new(comb.outputs["Image"], emit.inputs["Color"])
        extra = [comb]
    else:
        nt.links.new(src.outputs[src_socket], emit.inputs["Color"])
        extra = []
    surface_links = [lnk for lnk in nt.links if lnk.to_node == out and lnk.to_socket.name == "Surface"]
    for lnk in surface_links:
        nt.links.remove(lnk)
    nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    return emit, extra, surface_links


def bake_all(folder: str, res: int = 4096) -> None:
    """Bake albedo, normal, roughness, metallic, AO, displacement to PNG."""
    import os
    os.makedirs(folder, exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    scene.cycles.samples = 32
    scene.render.bake.use_pass_direct = False
    scene.render.bake.use_pass_indirect = False
    scene.render.bake.margin = 16
    scene.render.bake.use_selected_to_active = False

    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=1.0, location=(80, 80, 80))
    cage = bpy.context.view_layer.objects.active
    cage.name = "_bake_cage"
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.uv.smart_project(angle_limit=66, island_margin=0.04)
    bpy.ops.object.mode_set(mode="OBJECT")

    passes = (
        ("DIFFUSE", "albedo", False),
        ("NORMAL", "normal", True),
        ("ROUGHNESS", "roughness", True),
        ("AO", "ao", True),
    )
    for mat in list(bpy.data.materials):
        if not mat.name.startswith("M_"):
            continue
        cage.data.materials.clear()
        cage.data.materials.append(mat)
        bpy.ops.object.select_all(action="DESELECT")
        cage.select_set(True)
        bpy.context.view_layer.objects.active = cage
        nt = mat.node_tree
        bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
        for btype, suffix, is_data in passes:
            img = _bake_image(f"{mat.name}_{suffix}", res, is_data)
            node = _active_image_node(nt, img)
            try:
                bpy.ops.object.bake(type=btype)
            except Exception as ex:
                print(f"bake skip {mat.name} {btype}: {ex}")
            img.filepath_raw = os.path.join(folder, f"{mat.name}_{suffix}.png")
            img.file_format = "PNG"
            img.save()
            nt.nodes.remove(node)

        if bsdf:
            for socket, suffix in (("Metallic", "metallic"),):
                img = _bake_image(f"{mat.name}_{suffix}", res, True)
                node = _active_image_node(nt, img)
                emit, extra, restored = _emit_hijack(nt, bsdf, socket)
                try:
                    bpy.ops.object.bake(type="EMIT")
                except Exception as ex:
                    print(f"bake skip {mat.name} {suffix}: {ex}")
                img.filepath_raw = os.path.join(folder, f"{mat.name}_{suffix}.png")
                img.file_format = "PNG"
                img.save()
                nt.nodes.remove(node)
                nt.nodes.remove(emit)
                for n in extra:
                    nt.nodes.remove(n)
                out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
                if bsdf:
                    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

        disp = next((n for n in nt.nodes if n.type == "DISPLACEMENT"), None)
        if disp:
            img = _bake_image(f"{mat.name}_displacement", res, True)
            node = _active_image_node(nt, img)
            src = disp.inputs["Height"].links[0].from_node if disp.inputs["Height"].links else None
            sock = disp.inputs["Height"].links[0].from_socket.name if disp.inputs["Height"].links else None
            if src and sock:
                emit, extra, _rest = _emit_hijack(nt, src, sock)
                try:
                    bpy.ops.object.bake(type="EMIT")
                except Exception as ex:
                    print(f"bake skip {mat.name} displacement: {ex}")
                nt.nodes.remove(emit)
                for n in extra:
                    nt.nodes.remove(n)
                out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
                if bsdf:
                    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
            img.filepath_raw = os.path.join(folder, f"{mat.name}_displacement.png")
            img.file_format = "PNG"
            img.save()
            nt.nodes.remove(node)

    bpy.data.objects.remove(cage, do_unlink=True)
    print(f"baked maps → {folder}")
