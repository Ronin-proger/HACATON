# StroySync Site DCC — cinematic construction twin

Пайплайн: **Blender 4.2 LTS + Cycles** (авторство) → **glTF 2.0** (realtime: Three.js / Unreal / Unity).

Примитив используется только как заготовка. Каждый меш проходит Bevel (3 сегмента, arc miter) → Weighted Normal → микро-Displace → Auto Smooth. Финальные объекты — фаски, швы, болты, грязь в шейдере.

## Структура

```
tools/site_dcc/
  generate_site.py          # вход: сцена, GLB, preview, bake
  stroysync_dcc/
    meshops.py              # bevel / I-beam / extrude / bolts / weld
    materials.py            # Principled PBR, 10 материалов
    assemble.py             # площадка, каркас, кран, техника, пропсы
    __init__.py
  output/                   # .blend .glb preview.png maps/
  README.md
```

Realtime-вьюпорт продукта: `backend/app/static/twin.js` (те же формы: extrude/lathe/I-профиль, не голые кубы).

## Материалы (Cycles Principled)

| ID | Назначение | Base | Rough | Metal | Extra |
|---|---|---|---|---|---|
| M_ConcreteFormwork | плита, подиум | 0.62/0.60/0.56 | 0.78 | 0 | form-tie noise, displacement 12 mm |
| M_WetAsphalt | дороги | 0.07 gray | 0.12–0.85 | 0.02 | лужи по Noise 2.4 |
| M_RustySteel | балки, барабан | mix steel/rust | 0.48 | 0.82→0 | streaks 2D noise |
| M_CatPaint | техника RAL 1005 | 0.72/0.55/0.18 | 0.42 | 0.12 | coat 0.18, chips Voronoi |
| M_Timber | опалубка, штабель | 0.42/0.26/0.12 | 0.72 | 0 | mapping 1×8, knots |
| M_Brickwork | стартовая кладка | Brick node | 0.82 | 0 | mortar 18 mm, bump 0.35 |
| M_DirtGround | грунт | 0.22–0.32 | 0.95 | 0 | voronoi pebbles, disp 60 mm |
| M_CabGlass | остекление | 0.55/0.64/0.70 | 0.06 | 0 | transmission 0.86, IOR 1.52 |
| M_HiVis | СИЗ | 0.72/0.58/0.12 | 0.62 | 0 | sheen 0.35 |
| M_Rubber | гусеницы, шины | 0.03 | 0.88 | 0 | tread noise 40 |

Каналы при bake 4K: albedo, normal (OpenGL), roughness, metallic, AO, displacement.

## Шейдеры realtime

Трипланар грунта:
- Three.js: `tools/site_dcc/shaders/triplanar.js` + `triplanar.glsl`
- Unreal 5: `tools/site_dcc/shaders/SiteMaster.usf` (Custom HLSL в MM_StroySync_Site)
- Unity URP: `tools/site_dcc/shaders/SiteMaster.shader`

glTF: Principled → `KHR_materials_clearcoat` / transmission на стекле. ORM pack: R roughness, G metallic, B AO.

## Сборка

Нужен Blender 4.2+ в PATH.

```powershell
cd C:\Users\N\HACATON
blender --background --python tools\site_dcc\generate_site.py -- --export --render
```

Bake карт:

```powershell
blender --background --python tools\site_dcc\generate_site.py -- --bake --export
```

Камера: 32 mm, f/5.6, Filmic Medium High Contrast, 2560×1440, Cycles 128 spp + OIDN.

Экспорт GLB: apply modifiers, tangents on. Импорт в Unreal — Datasmith не нужен, glTF importer + Master Material с ORM pack (R roughness, G metallic, B AO).

LOD (в Blender): Decimate planar 5° для LOD1, 12° для LOD2. Кран-решётка — отдельный LOD0.

## Вьюпорт StroySync

После экспорта скопируйте `output/stroysync_site.glb` в `backend/app/static/` и подключите GLTFLoader. Текущий twin.js — процедурный realtime-двойник той же площадки (экструзии кабин, I-балки, lathe-ковш, torus-шины).
