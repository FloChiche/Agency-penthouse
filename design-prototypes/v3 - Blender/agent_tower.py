"""Agent Tower — construit la tour dans Blender et rend les vues avec Cycles.

Lancer :
  blender -b -P agent_tower.py -- [samples] [pourcentage_resolution] [camera1,camera2,...]
Ouvrir ensuite agent_tower.blend pour explorer la scène dans Blender.

Convention : les positions s'écrivent comme dans les protos web (x à droite, y en haut,
z vers la caméra) et sont converties en axes Blender (z en haut, -y vers la caméra).
"""
import bpy, math, os, random, sys, time
from mathutils import Vector

random.seed(7)
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "renders")
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SAMPLES = int(argv[0]) if len(argv) > 0 else 512
PCT = int(argv[1]) if len(argv) > 1 else 100
ONLY = set(argv[2].split(",")) if len(argv) > 2 else None

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
coll = scene.collection


# ---------------------------------------------------------------- matériaux
def lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hexc(h, a=1.0):
    h = h.lstrip("#")
    return tuple(lin(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4)) + (a,)


_mats = {}


def mat(color, rough=0.5, metal=0.0, coat=0.0, transm=0.0, ior=1.45, emit=None, es=0.0, alpha=1.0):
    key = (color, rough, metal, coat, transm, emit, es, alpha)
    if key in _mats:
        return _mats[key]
    m = bpy.data.materials.new(f"m_{color}")
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = hexc(color)
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metal
    p.inputs["Coat Weight"].default_value = coat
    p.inputs["Transmission Weight"].default_value = transm
    p.inputs["IOR"].default_value = ior
    p.inputs["Alpha"].default_value = alpha
    if emit:
        p.inputs["Emission Color"].default_value = hexc(emit)
        p.inputs["Emission Strength"].default_value = es
    _mats[key] = m
    return m


def E(color, strength=6):
    return mat("#000000", 1.0, emit=color, es=strength)


def beam_mat(color, strength=0.6):
    m = bpy.data.materials.new("beam")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    add = nt.nodes.new("ShaderNodeAddShader")
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = hexc(color)
    em.inputs["Strength"].default_value = strength
    nt.links.new(tr.outputs[0], add.inputs[0])
    nt.links.new(em.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs[0])
    return m


GLASS = mat("#cfe3ee", 0.02, coat=1.0, alpha=0.14)     # verre « fin » : reflets sans bruit de réfraction
TINT = mat("#0d1626", 0.04, metal=0.9)                 # vitrages teintés (voitures)
DARK = mat("#16181e", 0.28, metal=1.0)
WHITE = mat("#f2f0eb", 0.3, coat=0.3)


def _ramp(nt, a, b, pa=0.0, pb=1.0):
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].color, cr.color_ramp.elements[0].position = hexc(a), pa
    cr.color_ramp.elements[1].color, cr.color_ramp.elements[1].position = hexc(b), pb
    return cr


def wood_mat(c1, c2, scale=5.0, rough=0.32, coat=0.35):
    """bois procédural : veines (Wave) + variations (Noise)"""
    m = bpy.data.materials.new("wood")
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1, 8, 1)                # fibres allongées
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.inputs["Scale"].default_value = scale
    wave.inputs["Distortion"].default_value = 7
    wave.inputs["Detail"].default_value = 4
    cr = _ramp(nt, c1, c2, 0.15, 0.85)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], wave.inputs["Vector"])
    nt.links.new(wave.outputs["Fac"], cr.inputs["Fac"])
    nt.links.new(cr.outputs["Color"], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = rough
    p.inputs["Coat Weight"].default_value = coat
    return m


def marble_mat(base, vein, rough=0.08):
    """marbre procédural : bruit turbulent → veines fines"""
    m = bpy.data.materials.new("marble")
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 1.6
    nz.inputs["Detail"].default_value = 14
    nz.inputs["Distortion"].default_value = 3.5
    cr = nt.nodes.new("ShaderNodeValToRGB")
    els = cr.color_ramp.elements
    els[0].color, els[0].position = hexc(base), 0.0
    els[1].color, els[1].position = hexc(base), 0.47
    e = els.new(0.5)
    e.color = hexc(vein)
    e = els.new(0.53)
    e.color = hexc(base)
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    nt.links.new(nz.outputs["Fac"], cr.inputs["Fac"])
    nt.links.new(cr.outputs["Color"], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = rough
    p.inputs["Coat Weight"].default_value = 0.7
    return m


MARBLE = marble_mat("#ece8e1", "#9a948c")
BLACKMARBLE = marble_mat("#141416", "#c9a96a", 0.06)
WOOD = wood_mat("#6b4529", "#8d6240")
WALNUT = wood_mat("#2e1c12", "#55351f", scale=4.0, rough=0.25, coat=0.6)
GOLD = mat("#d4a64a", 0.18, metal=1.0)
LEATHER = mat("#7a3e1d", 0.45, coat=0.3)
FROSTED = mat("#eef1f4", 0.5, alpha=0.62)
BLACKGLOSS = mat("#0b0b0f", 0.08, coat=1.0)
CHROME = mat("#d8dce2", 0.08, metal=1.0)


def window_material(name="facade", base="#1a2130", strength=2.2, lit=0.22, metal=0.7):
    """Façades d'immeubles : verre sombre + fenêtres éclairées aléatoires (image générée)."""
    N, cell = 256, 16
    img = bpy.data.images.new("windows_" + name, N, N)
    px = [0.0] * (N * N * 4)
    for wy in range(N // cell):
        for wx in range(N // cell):
            r = random.random()
            col = (1.0, 0.72, 0.42) if r < lit else (0.65, 0.78, 1.0) if r < lit + 0.08 else (0.012, 0.014, 0.02)
            for y in range(wy * cell + 3, wy * cell + cell - 2):
                for x in range(wx * cell + 3, wx * cell + cell - 3):
                    i = (y * N + x) * 4
                    px[i:i + 4] = [*col, 1.0]
    img.pixels = px
    img.pack()
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = hexc(base)
    p.inputs["Roughness"].default_value = 0.08
    p.inputs["Metallic"].default_value = metal
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1 / 26, 1 / 26, 1 / 60)   # cellule ≈ 1,6 m × 3,7 m
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.projection = "BOX"
    tex.interpolation = "Closest"
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], p.inputs["Emission Color"])
    p.inputs["Emission Strength"].default_value = strength
    return m


FACADE = window_material()
WTC = window_material("wtc", base="#9db8d8", strength=0.9, lit=0.12, metal=0.95)


# ---------------------------------------------------------------- géométrie
def B(x, y, z):
    """coordonnées « web » → Blender"""
    return Vector((x, -z, y))


def link(ob, p):
    coll.objects.link(ob)
    if p:
        ob.parent = p
    return ob


def empty(name, x=0, y=0, z=0, p=None, rot=0.0):
    ob = bpy.data.objects.new(name, None)
    ob.location = B(x, y, z)
    ob.rotation_euler = (0, 0, rot)
    return link(ob, p)


def box(w, h, d, m, x, y, z, p=None, bevel=0.0, name="box"):
    me = bpy.data.meshes.new(name)
    hw, hd = w / 2, d / 2
    v = [(-hw, -hd, 0), (hw, -hd, 0), (hw, hd, 0), (-hw, hd, 0), (-hw, -hd, h), (hw, -hd, h), (hw, hd, h), (-hw, hd, h)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    me.from_pydata(v, [], f)
    me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    ob.location = B(x, y, z)
    if bevel:
        for poly in me.polygons:
            poly.use_smooth = True
        mod = ob.modifiers.new("bevel", "BEVEL")
        mod.width = min(bevel, w / 2.05, h / 2.05, d / 2.05)
        mod.segments = 4
        mod.harden_normals = True
    return link(ob, p)


def _prim(op, m, loc, p, smooth=True, **kw):
    op(location=(0, 0, 0), **kw)
    ob = bpy.context.active_object
    coll_from = ob.users_collection[0]
    if coll_from != coll:
        coll_from.objects.unlink(ob)
        coll.objects.link(ob)
    ob.data.materials.append(m)
    if smooth:
        for poly in ob.data.polygons:
            poly.use_smooth = True
    if p:
        ob.parent = p
    ob.location = loc
    return ob


def cyl(rt, rb, h, m, x, y, z, p=None, seg=40, axis=None):
    ob = _prim(bpy.ops.mesh.primitive_cone_add, m, B(x, y + h / 2, z), p, smooth=False,
               vertices=seg, radius1=rb, radius2=rt, depth=h)
    for poly in ob.data.polygons:                       # lisse les flancs, garde les capots nets
        poly.use_smooth = abs(poly.normal.z) < 0.5
    if axis == "z":                                      # axe le long de la profondeur (roues)
        ob.rotation_euler = (math.pi / 2, 0, 0)
        ob.location = B(x, y, z)
    return ob


def sphere(r, m, x, y, z, p=None):
    return _prim(bpy.ops.mesh.primitive_uv_sphere_add, m, B(x, y, z), p, radius=r, segments=32, ring_count=16)


def capsule(r, length, m, x, y, z, p=None):
    ob = sphere(r, m, x, y + r, z, p)
    for v in ob.data.vertices:
        if v.co.z > 0:
            v.co.z += length
    return ob


def text(body, size, m, x, y, z, p=None, align="LEFT"):
    cu = bpy.data.curves.new("txt", "FONT")
    cu.body = body
    cu.size = size
    cu.extrude = 0.01
    cu.align_x = align
    ob = bpy.data.objects.new("txt", cu)
    ob.data.materials.append(m)
    ob.rotation_euler = (math.pi / 2, 0, 0)
    ob.location = B(x, y, z)
    return link(ob, p)


def area(energy, color, x, y, z, sx, sy, p=None):
    l = bpy.data.lights.new("area", "AREA")
    l.shape = "RECTANGLE"
    l.size, l.size_y = sx, sy
    l.energy = energy
    l.color = hexc(color)[:3]
    ob = bpy.data.objects.new("area", l)
    ob.location = B(x, y, z)
    return link(ob, p)


def point(energy, color, x, y, z, p=None, radius=0.2):
    l = bpy.data.lights.new("pt", "POINT")
    l.energy = energy
    l.color = hexc(color)[:3]
    l.shadow_soft_size = radius
    ob = bpy.data.objects.new("pt", l)
    ob.location = B(x, y, z)
    return link(ob, p)


# ---------------------------------------------------------------- agents (petits robots)
HEAD = mat("#f4f4f2", 0.25, coat=0.8)


def agent(color, x, y, z, p=None, sit=False, rot=0.0):
    g = empty("agent", x, y, z, p, rot)
    body = mat(color, 0.35, coat=0.6)
    lift = 0.06 if sit else 0.08
    capsule(0.2, 0.36, body, 0, lift, 0, g)
    sphere(0.2, HEAD, 0, lift + 0.76 + 0.2, 0, g)
    box(0.28, 0.07, 0.06, E(color, 12), 0, lift + 0.96, 0.17, g, bevel=0.025)
    return g


# ---------------------------------------------------------------- voitures
TYRE = mat("#0c0c0e", 0.7)


def wheels(g, r, xs, zs, rim=CHROME):
    for a in xs:
        for b in zs:
            cyl(r, r, 0.24, TYRE, a, r, b, g, axis="z")
            cyl(r * 0.62, r * 0.62, 0.25, rim, a, r, b, g, seg=24, axis="z")


def supercar(color, kind, x, y, z, p=None, rot=0.0):
    g = empty("car", x, y, z, p, rot)
    paint = mat(color, 0.18, metal=0.55, coat=1.0)
    box(2.9, 0.42, 1.4, paint, 0, 0.14, 0, g, bevel=0.16)
    box(0.95, 0.2, 1.3, paint, 0.95, 0.5, 0, g, bevel=0.09)
    box(1.35, 0.34, 1.15, TINT, -0.15, 0.52, 0, g, bevel=0.15)
    if kind == "wing":
        box(0.3, 0.05, 1.35, BLACKGLOSS, -1.35, 0.86, 0, g, bevel=0.02)
        for s in (-0.45, 0.45):
            box(0.06, 0.28, 0.06, BLACKGLOSS, -1.3, 0.58, s, g)
    elif kind == "two":
        box(1.5, 0.43, 1.42, mat("#0e1116", 0.2, metal=0.7, coat=1), -0.65, 0.14, 0, g, bevel=0.16)
    elif kind == "gt":
        box(1.1, 0.3, 1.25, paint, -0.85, 0.5, 0, g, bevel=0.13)
    wheels(g, 0.31, (-0.95, 0.95), (-0.64, 0.64))
    box(0.04, 0.05, 0.5, E("#eaf3ff", 25), 1.46, 0.42, 0.4, g)
    box(0.04, 0.05, 0.5, E("#eaf3ff", 25), 1.46, 0.42, -0.4, g)
    box(0.04, 0.05, 1.15, E("#ff1f33", 15), -1.46, 0.45, 0, g)
    return g


MODELS = os.path.join(HERE, "modeles", "voitures")
MODEL_EXT = (".glb", ".gltf", ".fbx", ".obj")


def model_files():
    if not os.path.isdir(MODELS):
        return []
    return sorted(os.path.join(MODELS, f) for f in os.listdir(MODELS) if f.lower().endswith(MODEL_EXT))


# longueurs réelles (m) pour garder les proportions entre voitures ; 4,6 m ↔ 3,3 unités de scène
REAL_LENGTH = {"clio": 3.81, "porsche": 4.29, "g63": 4.87, "bugatti": 4.54, "lamborghini": 4.52,
               "f40": 4.36, "mclaren": 4.74, "458": 4.53}


def car_length(path):
    name = os.path.basename(path).lower()
    real = next((v for k, v in REAL_LENGTH.items() if k in name), 4.6)
    return 3.3 * real / 4.6


def import_car(path, p, length=3.3):
    """Importe un vrai modèle 3D, le pose au sol, centré, l'aligne sur X et le met à l'échelle."""
    before = set(bpy.data.objects)
    ext = os.path.splitext(path)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    else:
        bpy.ops.wm.obj_import(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    for o in [o for o in new if o.type in ("CAMERA", "LIGHT")]:
        new.remove(o)
        bpy.data.objects.remove(o)
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in new if o.type == "MESH" for c in o.bound_box]
    if not pts:
        return None
    mn = Vector((min(v.x for v in pts), min(v.y for v in pts), min(v.z for v in pts)))
    mx = Vector((max(v.x for v in pts), max(v.y for v in pts), max(v.z for v in pts)))
    size = mx - mn
    inner = bpy.data.objects.new("model_offset", None)
    coll.objects.link(inner)
    for o in new:
        if o.parent is None:
            mw = o.matrix_world.copy()
            o.parent = inner
            o.matrix_world = mw
    inner.location = (-(mn.x + mx.x) / 2, -(mn.y + mx.y) / 2, -mn.z)
    root = bpy.data.objects.new("car_" + os.path.basename(path), None)
    link(root, p)
    inner.parent = root
    root.scale = [length / max(size.x, size.y)] * 3
    if size.y > size.x:
        root.rotation_euler = (0, 0, math.pi / 2)
    return root


FURN = os.path.join(HERE, "modeles", "mobilier")
_assets = {}


def _load_asset(aid):
    """Importe une fois un modèle Poly Haven dans sa propre collection, posé au sol et centré."""
    if aid in _assets:
        return _assets[aid]
    d = os.path.join(FURN, aid)
    files = [n for n in os.listdir(d) if n.endswith(".gltf")] if os.path.isdir(d) else []
    if not files:
        _assets[aid] = None
        return None
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(d, files[0]))
    new = [o for o in bpy.data.objects if o not in before]
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in new if o.type == "MESH" for c in o.bound_box]
    mn = Vector((min(v.x for v in pts), min(v.y for v in pts), min(v.z for v in pts)))
    mx = Vector((max(v.x for v in pts), max(v.y for v in pts), max(v.z for v in pts)))
    off = bpy.data.objects.new("offset_" + aid, None)
    coll.objects.link(off)
    for o in new:
        if o.parent is None:
            mw = o.matrix_world.copy()
            o.parent = off
            o.matrix_world = mw
    off.location = (-(mn.x + mx.x) / 2, -(mn.y + mx.y) / 2, -mn.z)
    col = bpy.data.collections.new("asset_" + aid)
    for o in new + [off]:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        col.objects.link(o)
    _assets[aid] = (col, mx - mn)
    return _assets[aid]


def asset(aid, x, y, z, p=None, rot=0.0, fit=None, hang=False):
    """Place une instance d'un modèle (échelle réelle, ou `fit` = plus grande largeur visée).
    hang=True : y désigne le haut de l'objet (suspensions). Renvoie None si le modèle manque."""
    info = _load_asset(aid)
    if not info:
        return None
    col, size = info
    s = fit / max(size.x, size.y) if fit else 1.0
    inst = bpy.data.objects.new(aid, None)
    inst.instance_type = "COLLECTION"
    inst.instance_collection = col
    inst.scale = (s, s, s)
    inst.rotation_euler = (0, 0, rot)
    inst.location = B(x, y - (size.z * s if hang else 0), z)
    return link(inst, p)


def taxi(x, z, rot):
    g = empty("taxi", x, 0, z, None, rot)
    y = mat("#f5c000", 0.3, coat=0.8)
    box(2.4, 0.55, 1.1, y, 0, 0.18, 0, g, bevel=0.14)
    box(1.35, 0.42, 1.0, y, -0.1, 0.72, 0, g, bevel=0.12)
    box(1.37, 0.3, 1.02, TINT, -0.1, 0.77, 0, g, bevel=0.1)
    box(0.5, 0.12, 0.25, E("#fff3c8", 4), -0.1, 1.15, 0, g, bevel=0.03)
    wheels(g, 0.24, (-0.75, 0.75), (-0.52, 0.52), rim=mat("#777777", 0.3, metal=1))
    box(0.04, 0.08, 0.75, E("#fff3d6", 20), 1.2, 0.45, 0, g)


# ---------------------------------------------------------------- monde & ville
w = bpy.data.worlds.new("world")
scene.world = w
w.use_nodes = True
sky = w.node_tree.nodes.new("ShaderNodeTexSky")
sky.sky_type = "NISHITA"
sky.sun_disc = False
sky.sun_elevation = math.radians(3.5)
sky.sun_rotation = math.radians(205)
sky.altitude = 200
sky.dust_density = 2.0
w.node_tree.links.new(sky.outputs["Color"], w.node_tree.nodes["Background"].inputs["Color"])
w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.32

sun = bpy.data.lights.new("sun", "SUN")
sun.energy = 1.6
sun.color = hexc("#ffb27a")[:3]
sun.angle = math.radians(2)
so = bpy.data.objects.new("sun", sun)
so.rotation_euler = (math.radians(84), 0, math.radians(205))
coll.objects.link(so)


def building(x, z, wd, dp, h):
    box(wd, h, dp, FACADE, x, 0, z)
    box(wd + 0.4, 0.6, dp + 0.4, DARK, x, h, z)
    if random.random() < 0.3:
        sphere(0.25, E("#ff2030", 40), x, h + 1.2, z)


def one_wtc(x, z, s):
    """fût à base carrée dont le sommet est un carré tourné de 45° → 8 facettes triangulaires"""
    H, rb, rt, base = 100 * s, 11 * s, 6.2 * s, 14 * s
    Bk = lambda k: (math.cos(math.pi / 4 + k * math.pi / 2) * rb, math.sin(math.pi / 4 + k * math.pi / 2) * rb, base)
    Tk = lambda k: (math.cos(k * math.pi / 2) * rt, math.sin(k * math.pi / 2) * rt, base + H)
    verts, faces = [], []
    for k in range(4):
        for tri in ((Bk(k), Bk(k + 1), Tk(k + 1)), (Tk(k + 1), Bk(k + 1), Tk(k + 2))):
            i = len(verts)
            verts += tri
            faces.append((i, i + 1, i + 2))
    me = bpy.data.meshes.new("one_wtc")
    me.from_pydata(verts, [], faces)
    me.materials.append(WTC)
    ob = bpy.data.objects.new("one_wtc", me)
    ob.location = B(x, 0, z)
    coll.objects.link(ob)
    podium = box(rb * 1.42, base, rb * 1.42, mat("#c9d2dc", 0.3, metal=0.6), x, 0, z)
    podium.rotation_euler = (0, 0, math.pi / 4)
    box(rt * 1.42, 3 * s, rt * 1.42, mat("#d9e1ea", 0.3, metal=0.5), x, base + H, z).rotation_euler = (0, 0, math.pi / 4)
    cyl(0.25 * s, 0.6 * s, 40 * s, mat("#e8ecf2", 0.2, metal=1), x, base + H + 3 * s, z, seg=12)
    sphere(0.9 * s, E("#ffffff", 80), x, base + H + 43 * s, z)


_sky_before = set(bpy.data.objects)                     # la skyline est recréée côté web
one_wtc(-150, -170, 1.25)
for i in range(110):
    bx, bz = -230 + random.random() * 420, -55 - random.random() * 190
    if math.hypot(bx + 150, bz + 170) < 35 or (abs(bx - bz * 0.45) < 38 and bz > -120):
        continue
    near = 0.5 if bz > -90 else 1.0
    building(bx, bz, 8 + random.random() * 12, 8 + random.random() * 12, (12 + random.random() * 34) * near)
for bx, bz, wd, dp, h in [(-30, -4, 10, 8, 15), (26, -6, 10, 8, 12), (-46, -10, 10, 10, 19)]:
    building(bx, bz, wd, dp, h)
SKYLINE = set(bpy.data.objects) - _sky_before

# terrain en coupe, garage souterrain, rue
GX, GZ0, GZ1, GD = 10.5, -4.2, 13.0, 4.4
SOIL = mat("#1d1c20", 0.9)
box(500, 0.4, 500, mat("#2a2c33", 0.6), 0, -0.4, -250 + GZ0 - 0.01)
box(200 - GX, GD + 0.4, GZ1 - GZ0, SOIL, -(GX + (200 - GX) / 2), -GD - 0.4, (GZ0 + GZ1) / 2)
box(200 - GX, GD + 0.4, GZ1 - GZ0, SOIL, (GX + (200 - GX) / 2), -GD - 0.4, (GZ0 + GZ1) / 2)
box(2 * GX, 0.4, GZ1 - GZ0, mat("#2c2f37", 0.12, metal=0.3, coat=0.8), 0, -GD - 0.4, (GZ0 + GZ1) / 2)
box(2 * GX, GD, 0.3, mat("#24262d", 0.6), 0, -GD, GZ0)
box(2 * GX, 0.45, GZ1 - GZ0, mat("#26282f", 0.8), 0, -0.45, (GZ0 + GZ1) / 2)
box(400, 0.12, 2, mat("#3b3e47", 0.6), 0, 0, 4.6)
box(400, 0.04, 6.4, mat("#121318", 0.18, metal=0.2, coat=0.6), 0, 0, 8.8)       # bitume mouillé
box(400, 0.12, 1.2, mat("#3b3e47", 0.6), 0, 0, 12.4)
for i in range(-100, 100, 4):
    box(1.8, 0.05, 0.14, E("#f1dca0", 1.2), i, 0, 8.8)
for i in (-1, 0, 1):
    box(0.08, 0.04, GZ1 - GZ0 - 1, E("#e4eeff", 18), i * 6.5, -0.55, (GZ0 + GZ1) / 2)
    area(220, "#e4eeff", i * 6.5, -0.7, (GZ0 + GZ1) / 2, 0.3, GZ1 - GZ0 - 1)
cars = [(-7.2, -1.5, "#93cc0f", "wing"), (-2.4, -1.5, "#f29a0c", "wing"), (2.4, -1.5, "#1a4ca8", "two"), (7.2, -1.5, "#c9ccd3", "gt"),
        (-7.2, 5.5, "#b0101d", "gt"), (-2.4, 5.5, "#101114", "wing"), (2.4, 5.5, "#ececf0", "gt"), (7.2, 5.5, "#6a2c91", "two")]
real_cars = model_files()
print(f"[agent_tower] modèles de voitures trouvés : {len(real_cars)}", flush=True)
for n, (cx, cz, c, k) in enumerate(cars):
    tt = empty("turntable", cx, -GD, cz)
    cyl(1.95, 1.95, 0.06, mat("#33363f", 0.2, metal=0.8), 0, 0, 0, tt, seg=64)
    ring = bpy.ops.mesh.primitive_torus_add(major_radius=1.95, minor_radius=0.025, location=(0, 0, 0))
    r = bpy.context.active_object
    r.data.materials.append(E(c, 10))
    r.parent = tt
    r.location = B(0, 0.07, 0)
    turn = (0 if cz < 0 else math.pi) + 0.45
    if n < len(real_cars):                               # un vrai modèle remplace la silhouette
        holder = empty("car_holder", 0, 0.06, 0, tt, turn)
        if import_car(real_cars[n], holder, length=car_length(real_cars[n])):
            continue
    supercar(c, k, 0, 0.06, 0, tt, rot=turn)
text("-1  GARAGE", 0.55, E("#ffffff", 6), -GX + 0.4, -1.4, GZ1 - 0.2)
for tx, tz, tr in [(-38, 7.4, 0), (16, 10.2, math.pi), (-14, 7.4, 0), (44, 10.2, math.pi)]:
    taxi(tx, tz, tr)
for lx in (-16, -8, 16, 24):
    if not asset("street_lamp_01", lx, 0, 4.0, rot=math.pi / 2):
        box(0.12, 4.2, 0.12, DARK, lx, 0, 4.0)
        box(0.7, 0.1, 0.25, E("#ffd28a", 20), lx, 4.2, 4.3)
    point(180, "#ffb85c", lx, 3.9, 4.6, radius=0.3)

# ---------------------------------------------------------------- la tour
FH, TW, TD = 3.6, 12.0, 7.0
TOP = 9                      # niveau du toit (0 = lobby, 8 = bureau de FLO)
W2, D2, F = TW / 2, TD / 2, 0.3


def shell(level, name, color, floor=WOOD, warm="#ffe7c8", light=320):
    f = empty(f"etage_{level}", 0, level * FH, 0)
    box(TW, F, TD, floor, 0, 0, 0, f)
    box(TW, 0.02, TD, mat("#e9e6e0", 0.8), 0, FH - 0.02, 0, f)  # plafond
    box(TW, FH - F, 0.04, GLASS, 0, F, -D2, f)
    for x in range(-6, 7, 2):
        box(0.06, FH - F, 0.1, DARK, x, F, -D2, f)
    box(0.2, FH - F, TD, mat("#2a2c33", 0.5), -W2, F, 0, f)
    box(0.04, FH - F, TD, GLASS, W2, F, 0, f)
    box(TW + 0.02, 0.05, 0.05, E(color, 14), 0, 0.12, D2 + 0.03, f)
    box(TW - 1, 0.03, 0.1, E(warm, 6), 0, FH - 0.08, -1, f)
    area(light, warm, 0, FH - 0.12, 0, TW - 1.5, TD - 1.5, f)
    label = f"{level}   {name.upper()}" if level else f"0   {name.upper()}"
    text(label, 0.42, E("#ffffff", 5), -W2 - 4.6, 1.4, D2, f)
    box(0.18, 0.18, 0.02, E(color, 20), -W2 - 4.9, 1.52, D2, f, bevel=0.06)
    wall_plaque(f, level, name, color)
    return f


def wall_plaque(f, level, name, color):
    """plaque signalétique sur le mur plein de gauche, lisible depuis l'intérieur de l'étage"""
    px, py, pz, w = -W2 + 0.2, F + 1.55, 1.7, 2.6
    box(0.04, 0.62, w, mat("#2a2c31", 0.35, metal=1.0), px, py, pz, f, bevel=0.015)    # alu brossé foncé
    box(0.045, 0.62, 0.08, E(color, 10), px + 0.005, py, pz + w / 2 - 0.04, f)          # liseré couleur de l'app
    num = text(str(level), 0.34, E(color, 8), px + 0.03, py + 0.16, pz + w / 2 - 0.35, f, align="CENTER")
    num.rotation_euler = (math.pi / 2, 0, math.pi / 2)
    t = text(name.upper(), 0.2 if len(name) < 14 else 0.16, E("#ffffff", 5), px + 0.03, py + 0.22, pz - 0.2, f, align="CENTER")
    t.rotation_euler = (math.pi / 2, 0, math.pi / 2)


def plant(f, x, z, s=1.0):
    cyl(0.24 * s, 0.2 * s, 0.5 * s, WHITE, x, F, z, f)
    sphere(0.5 * s, mat("#3c7a46", 0.7), x, F + 1.05 * s, z, f)


def fabric(color):
    m = mat(color, 0.92)
    m.node_tree.nodes["Principled BSDF"].inputs["Sheen Weight"].default_value = 0.5
    return m


def modern_sofa(f, cx, z, w, color, rot=math.pi):
    """canapé modulaire bas : coussins séparés, accoudoirs pleins, pieds fins en métal"""
    g = empty("sofa", cx, F, z, f, rot)
    fab = fabric(color)
    n = max(2, round(w / 0.95))
    cw = w / n
    box(w + 0.4, 0.14, 0.95, mat("#1c1d22", 0.4), 0, 0.08, 0, g, bevel=0.04)
    for i in range(n):
        x = -w / 2 + cw * (i + 0.5)
        box(cw - 0.03, 0.2, 0.86, fab, x, 0.22, 0.04, g, bevel=0.08)
        box(cw - 0.03, 0.5, 0.24, fab, x, 0.36, -0.34, g, bevel=0.11)
    for s in (-1, 1):
        box(0.2, 0.46, 0.95, fab, s * (w / 2 + 0.1), 0.08, 0, g, bevel=0.08)
        for zz in (-0.38, 0.38):
            cyl(0.02, 0.02, 0.08, CHROME, s * (w / 2 + 0.05), 0, zz, g, seg=12)
    return g


def app_floor(level, name, color, working, sofa, game, couch, tv):
    f = shell(level, name, color)
    # bureau
    box(2.8, 0.05, 1.1, WHITE, -3.8, F + 0.74, -2.4, f, bevel=0.02)
    for x in (-5.1, -2.5):
        box(0.05, 0.74, 1.0, DARK, x, F, -2.4, f)
    scr = E(color, 6) if working else mat("#0c0d12", 0.15, coat=1)
    for x in (-4.5, -3.1):
        box(1.15, 0.68, 0.04, DARK, x, F + 0.9, -2.75, f, bevel=0.02)
        box(1.07, 0.6, 0.02, scr, x, F + 0.94, -2.72, f)
    box(0.6, 0.5, 0.6, mat("#15161b", 0.6), -3.8, F, -1.5, f, bevel=0.1)
    if working:
        agent(color, -3.8, F + 0.1, -1.45, f, sit=True, rot=math.pi)
        point(40, color, -3.8, F + 1.3, -2.1, f)
    # salon
    box(4.2, 0.02, 3.2, mat("#d9d2c8", 0.95), 0.6, F, -0.6, f)
    box(3.4, 1.7, 0.12, mat("#22242b", 0.4), 0.6, F + 0.2, -3.36, f)
    box(2.7, 1.35, 0.03, E(tv, 3.5), 0.6, F + 0.55, -3.29, f)
    box(3, 0.35, 0.5, mat("#1f2128", 0.3, coat=0.6), 0.6, F, -3.05, f, bevel=0.03)
    modern_sofa(f, 0.6, 0.65, 2.8, couch)
    seat = F + 0.32
    if not asset("modern_coffee_table_01", 0.6, F, -0.9, f):
        box(1.2, 0.3, 0.6, MARBLE, 0.6, F, -1.0, f, bevel=0.04)
    asset("desk_lamp_arm_01", -2.75, F + 0.79, -2.65, f, rot=-2.4)
    asset("gaming_console", 1.75, F + 0.35, -3.0, f)
    for i in range(sofa):
        agent(color, -0.15 + i * 0.75, seat, 0.55, f, sit=True, rot=math.pi)
    # coin jeu
    box(0.8, 1.8, 0.7, mat("#121019", 0.3, coat=1), 5.1, F, -2.8, f, bevel=0.04)
    box(0.6, 0.48, 0.03, E("#7cf2d0", 6), 5.1, F + 1.05, -2.44, f)
    box(1.5, 0.75, 0.8, WOOD, 4.0, F, 0.9, f, bevel=0.03)
    box(1.3, 0.05, 0.6, mat("#2a7a45", 0.9), 4.0, F + 0.75, 0.9, f)
    for i in range(game):
        agent(color, 3.6 + i * 0.8, F, 1.65, f, rot=math.pi)
    if not asset("potted_plant_02", 5.3, F, 2.8, f):
        plant(f, 5.4, 2.8)


# 0 · Lobby + café
lobby = shell(0, "Lobby & Café", "#c8a36a", floor=MARBLE, warm="#ffe0b0", light=380)
box(3, 1.05, 0.8, WHITE, -3.8, F, 0.9, lobby, bevel=0.04)
box(3, 0.04, 0.04, E("#c8a36a", 12), -3.8, F + 0.5, 1.32, lobby)
text("AGENT TOWER", 0.36, E("#e8c27a", 8), -1.0, F + 2.2, -3.3, lobby, align="CENTER")
agent("#c8a36a", -3.8, F, 0.15, lobby)


def toilettes(f, x0, x1, z0, z1, floor_mat, sign=True, walls=("x1", "z1")):
    """bloc sanitaires : cloisons en verre dépoli, WC suspendu, vasque, miroir rétro-éclairé.
    walls choisit les cloisons ; sans « z1 » le bloc reste ouvert vers la caméra (vue en coupe)."""
    w, d = x1 - x0, z1 - z0
    box(w, 0.02, d, floor_mat, (x0 + x1) / 2, F, (z0 + z1) / 2, f)
    if "x0" in walls:
        box(0.06, FH - F, d, FROSTED, x0, F, (z0 + z1) / 2, f)
    if "x1" in walls:
        box(0.06, FH - F, d, FROSTED, x1, F, (z0 + z1) / 2, f)
    if "z0" in walls:
        box(w, FH - F, 0.06, mat("#2a2a2e", 0.3, coat=0.5), (x0 + x1) / 2, F, z0, f)
    if "z1" in walls:
        box(w - 0.9, FH - F, 0.06, FROSTED, x0 + (w - 0.9) / 2, F, z1, f)      # cloison avant, porte à droite
        box(0.9, 0.1, 0.06, FROSTED, x1 - 0.45, FH - 0.6, z1, f)
    wx = x0 + 0.55
    box(0.42, 0.38, 0.62, WHITE, wx, F + 0.38, z0 + 0.42, f, bevel=0.16)          # WC suspendu
    box(0.5, 0.75, 0.12, WHITE, wx, F + 0.75, z0 + 0.1, f, bevel=0.03)            # bâti
    box(0.18, 0.1, 0.02, CHROME, wx, F + 1.15, z0 + 0.17, f, bevel=0.01)          # plaque de commande
    vx = x0 + w * 0.62
    box(1.2, 0.12, 0.5, BLACKMARBLE if floor_mat is not BLACKMARBLE else MARBLE, vx, F + 0.78, z0 + 0.3, f, bevel=0.02)
    cyl(0.2, 0.15, 0.12, WHITE, vx, F + 0.9, z0 + 0.3, f, seg=40)                 # vasque à poser
    cyl(0.015, 0.015, 0.28, GOLD, vx, F + 0.9, z0 + 0.1, f, seg=12)              # robinet
    box(0.02, 0.02, 0.12, GOLD, vx, F + 1.16, z0 + 0.15, f)
    mir = cyl(0.36, 0.36, 0.02, mat("#cfd6dc", 0.02, metal=1.0), vx, F + 1.65, z0 + 0.03, f, seg=64, axis="z")
    ring = cyl(0.38, 0.38, 0.015, E("#ffe9c8", 8), vx, F + 1.65, z0 + 0.02, f, seg=64, axis="z")
    point(25, "#ffe6c4", (x0 + x1) / 2, FH - 0.4, (z0 + z1) / 2, f)
    if sign:
        text("WC", 0.2, E("#ffffff", 6), x1 - 0.45, 2.05, z1 + 0.04, f, align="CENTER")
    return mir, ring


toilettes(lobby, -5.9, -3.0, -3.45, -1.4, BLACKMARBLE)
box(4, 1.0, 0.7, mat("#2a2420", 0.4), 3, F, -2.6, lobby, bevel=0.03)
box(4.05, 0.05, 0.75, MARBLE, 3, F + 1.0, -2.6, lobby)
box(0.8, 0.5, 0.45, CHROME, 2.0, F + 1.05, -2.7, lobby, bevel=0.05)
box(4, 1.0, 0.06, E("#ffcf8a", 2.2), 3, F + 1.6, -3.38, lobby)
agent("#6b4a32", 3.2, F, -3.15, lobby)
for tx, tz in ((1.4, 0.8), (3.6, 1.2), (5.0, -0.4)):
    cyl(0.42, 0.42, 0.04, MARBLE, tx, F + 0.74, tz, lobby)
    cyl(0.05, 0.22, 0.74, DARK, tx, F, tz, lobby)
    cyl(0.06, 0.05, 0.11, WHITE, tx + 0.15, F + 0.78, tz, lobby)
agent("#5cb27a", 0.75, F, 0.8, lobby, rot=math.pi / 2)
agent("#4f8fd9", 4.25, F, 1.2, lobby, rot=-math.pi / 2)
for bx in (1.6, 2.8, 4.0):                                        # tabourets au comptoir
    asset("bar_chair_round_01", bx, F, -1.85, lobby, rot=math.pi)
asset("potted_plant_01", -0.2, F, 2.9, lobby)
asset("potted_plant_01", 5.5, F, 2.9, lobby)
asset("mid_century_lounge_chair", -1.6, F, 2.2, lobby, rot=math.pi * 0.8)

app_floor(1, "ChatGPT", "#10a37f", False, 2, 1, "#e9e4da", "#5fe3b8")
app_floor(2, "Claude", "#d4a27f", True, 1, 1, "#2f3a52", "#f0c49c")
app_floor(3, "n8n", "#ea4b71", False, 1, 0, "#e7e2dd", "#ff7a9a")
app_floor(4, "Claude Code", "#d97757", True, 1, 2, "#3a2f2a", "#ffb08a")

# 5 · Casino
cas = shell(5, "Casino", "#e5b84b", floor=mat("#3e0b17", 0.95), warm="#ffd98a", light=260)
felt, wood = mat("#1d6a44", 0.95), mat("#3a2416", 0.3, coat=0.8)
box(2.6, 0.8, 1.2, wood, -3.6, F, -0.9, cas, bevel=0.06)
box(2.4, 0.03, 1.0, felt, -3.3, F + 0.8, -0.9, cas)
cyl(0.5, 0.5, 0.12, wood, -4.55, F + 0.8, -0.9, cas, seg=48)
cyl(0.36, 0.36, 0.02, mat("#a8162a", 0.3, coat=1), -4.55, F + 0.92, -0.9, cas, seg=37)
cyl(0.06, 0.06, 0.12, CHROME, -4.55, F + 0.92, -0.9, cas)
agent("#151515", -3.6, F, -1.8, cas)
agent("#5cb27a", -3.3, F, 0.1, cas, rot=math.pi)
bj = _prim(bpy.ops.mesh.primitive_cylinder_add, felt, B(0.6, F + 0.84, -1.6), cas, vertices=48, radius=1.2, depth=0.08)
for v in bj.data.vertices:                              # demi-lune : on écrase la moitié arrière
    if v.co.y > 0:
        v.co.y = 0
cyl(0.25, 0.35, 0.8, wood, 0.6, F, -1.3, cas)
agent("#151515", 0.6, F, -2.6, cas)
agent("#4f8fd9", 0.0, F + 0.1, -0.25, cas, sit=True, rot=math.pi)
agent("#5cb27a", 1.2, F + 0.1, -0.25, cas, sit=True, rot=math.pi)
for i in range(5):
    cyl(0.08, 0.08, 0.04 * (i + 2), mat(["#e5b84b", "#c81e3c", "#1f5fd6"][i % 3], 0.3, coat=1), -0.2 + i * 0.4, F + 0.88, -1.1, cas, seg=20)
pk = cyl(1.0, 1.0, 0.08, felt, 4, F + 0.8, -0.8, cas, seg=64)
pk.scale = (1.5, 1, 1)
rail = cyl(1.08, 1.08, 0.07, wood, 4, F + 0.76, -0.8, cas, seg=64)
rail.scale = (1.5, 1, 1)
cyl(0.3, 0.4, 0.78, wood, 4, F, -0.8, cas)
for (ax, az, r), c in zip([(2.6, -0.8, math.pi / 2), (4, 0.35, math.pi), (5.4, -0.8, -math.pi / 2), (4, -1.95, 0)],
                          ["#d97757", "#ea4b71", "#151515", "#4f8fd9"]):
    agent(c, ax, F + 0.1, az, cas, sit=True, rot=r)
for i, c in enumerate(["#ffd06a", "#ff5a8a", "#6ae0ff"]):
    box(0.7, 1.7, 0.6, mat("#1b1224", 0.3, coat=1), -1.6 + i * 0.9, F, 2.7, cas, bevel=0.05)
    box(0.5, 0.5, 0.03, E(c, 6), -1.6 + i * 0.9, F + 1.05, 2.39, cas)
if not asset("Chandelier_01", 0.6, FH, -1.4, cas, hang=True):
    for i in range(18):
        sphere(0.07, E("#ffe2a8", 25), 0.5 + math.cos(i) * 0.75, FH - 0.5 - (i % 3) * 0.18, -0.5 + math.sin(i) * 0.75, cas)
asset("Chandelier_02", 4.0, FH, -0.8, cas, hang=True)
asset("sofa_02", 4.0, F, 2.7, cas, rot=math.pi)                  # salon Chesterfield noir du casino
asset("Chandelier_03", -3.6, FH, -0.9, cas, hang=True)
point(40, "#ffd9a0", 0.6, FH - 0.9, -1.4, cas)

# 6 · Nightclub
club = shell(6, "Nightclub", "#b06cff", floor=BLACKGLOSS, warm="#b06cff", light=60)
palette = ["#ff00aa", "#00e5ff", "#b06cff", "#ffe14d", "#00ff9c"]
for i in range(6):
    for j in range(4):
        box(0.76, 0.04, 0.76, E(palette[(i + j * 2) % 5], 5), -2 + i * 0.8, F, -1.6 + j * 0.8, club)
box(2.6, 1.1, 0.8, mat("#111216", 0.2, metal=0.8), 0, F, -3.0, club, bevel=0.04)
box(2.6, 0.05, 0.04, E("#00e5ff", 20), 0, F + 0.7, -2.58, club)
agent("#e5e5e5", 0, F, -3.15, club)
for sx in (-2.9, 2.9):
    box(0.9, 1.6, 0.9, mat("#0d0d10", 0.5), sx, F, -2.9, club, bevel=0.04)
box(0.9, 1.05, 4.2, mat("#16161c", 0.15, metal=0.6), -5.0, F, 0.3, club, bevel=0.04)
box(0.06, 1.4, 4.0, E("#ff4fa3", 4), -5.78, F + 1.3, 0.3, club)
agent("#e5e5e5", -5.45, F, 0.3, club, rot=math.pi / 2)
for k, (ax, az) in enumerate([(-1.4, -0.9), (-0.2, -0.3), (0.9, -1.1), (1.6, 0.3), (-0.9, 0.6), (0.5, 0.9)]):
    agent(["#d97757", "#ea4b71", "#4f8fd9", "#5cb27a", "#e5b84b", "#ea4b71"][k], ax, F + 0.04 + (k % 2) * 0.15, az, club, rot=math.pi + (k - 3) * 0.3)
for k, bx in enumerate((-2.5, 0, 2.5)):
    c = ["#ff3dbb", "#3df0ff", "#b06cff"][k]
    cone = _prim(bpy.ops.mesh.primitive_cone_add, beam_mat(c), B(bx, FH - 1.6, -0.5), club,
                 vertices=32, radius1=0.95, radius2=0.03, depth=3.0, end_fill_type="NOTHING")
    cone.rotation_euler = (0, (k - 1) * 0.35, 0)
    point(120, c, bx, FH - 0.3, -0.5, club)

# 7 · Penthouse QG
ph = shell(7, "Penthouse · QG", "#e5c27a", floor=MARBLE, warm="#ffe7c2", light=300)
for i, c in enumerate(["#d97757", "#ea4b71", "#4f8fd9", "#5cb27a", "#e5b84b", "#b06cff"]):
    box(1.25, 0.75, 0.04, DARK, -3.2 + i * 1.3, F + 1.0, -3.3, ph, bevel=0.02)
    box(1.17, 0.67, 0.02, E(c, 4), -3.2 + i * 1.3, F + 1.04, -3.27, ph)
box(4.2, 0.05, 1.2, BLACKGLOSS, -0.2, F + 0.74, -1.6, ph, bevel=0.02)
for lx in (-1.8, 1.4):
    cyl(0.08, 0.3, 0.74, CHROME, lx, F, -1.6, ph)
agent("#e5c27a", -0.2, F, -2.5, ph)
box(0.25, 1.0, 2.2, mat("#2b2e38", 0.4), -5.8, F + 0.4, 0.4, ph)
box(0.05, 0.3, 1.8, E("#ff8a3a", 18), -5.66, F + 0.6, 0.4, ph)
modern_sofa(ph, 3.3, 1.05, 3.2, "#ece6dc")
agent("#d97757", 2.9, F + 0.32, 1.0, ph, sit=True, rot=math.pi)
asset("modern_coffee_table_02", 3.3, F, -0.2, ph)
for cx in (-1.5, -0.2, 1.1):                                      # fauteuils autour de la grande table
    asset("modern_arm_chair_01", cx, F, -0.6, ph, rot=math.pi)
asset("modern_ceiling_lamp_01", -0.2, FH, -1.6, ph, hang=True)
if not asset("potted_plant_04", 5.3, F, -2.9, ph):
    plant(ph, 5.4, -2.9, 1.3)

# 8 · Bureau de FLO — le plus beau de la tour
flo = shell(8, "Bureau de FLO", "#d4a64a", floor=WALNUT, warm="#ffe2b5", light=260)
ONYX = mat("#f0c27a", 0.15, coat=1.0, emit="#ff9d3a", es=0.9)
box(0.06, FH - F - 0.2, TD - 0.8, ONYX, -5.86, F + 0.1, 0, flo)                    # mur en onyx rétro-éclairé
fl = text("FLO", 0.9, GOLD, -5.78, F + 1.4, -0.9, flo, align="CENTER")
fl.rotation_euler = (math.pi / 2, 0, math.pi / 2)
fl.data.extrude = 0.05
box(6.6, 0.015, 4.2, mat("#e8dfd0", 0.95), -0.6, F, -0.5, flo)                    # grand tapis
# bureau en marbre noir veiné d'or, piètement monolithe
box(3.4, 0.09, 1.3, BLACKMARBLE, -2.4, F + 0.74, -1.9, flo, bevel=0.03)
box(0.5, 0.74, 1.1, BLACKMARBLE, -3.75, F, -1.9, flo, bevel=0.02)
box(1.6, 0.6, 0.05, WALNUT, -1.6, F + 0.12, -2.45, flo)
box(3.4, 0.012, 0.012, GOLD, -2.4, F + 0.83, -1.25, flo)
for i, c in enumerate(["#d97757", "#4f8fd9", "#ea4b71"]):                         # 3 écrans fins
    sx = -3.3 + i * 0.95
    box(0.92, 0.55, 0.03, DARK, sx, F + 1.02, -2.4, flo, bevel=0.01)
    box(0.86, 0.49, 0.01, E(c, 5), sx, F + 1.05, -2.38, flo)
    cyl(0.02, 0.02, 0.2, CHROME, sx, F + 0.83, -2.42, flo, seg=12)
# fauteuil de direction en cuir cognac
cyl(0.32, 0.32, 0.03, CHROME, -2.35, F, -0.95, flo, seg=5)
cyl(0.03, 0.03, 0.42, CHROME, -2.35, F, -0.95, flo)
box(0.62, 0.14, 0.6, LEATHER, -2.35, F + 0.44, -0.95, flo, bevel=0.07)
box(0.62, 0.85, 0.14, LEATHER, -2.35, F + 0.58, -0.62, flo, bevel=0.07)
fa = agent("#141414", -2.35, F + 0.12, -0.98, flo, sit=True, rot=math.pi)
for o in fa.children:
    if o.type == "MESH" and o.dimensions.x < 0.3 and o.dimensions.z < 0.1:     # visière dorée
        o.data.materials[0] = E("#ffc35a", 14)
fa.scale = (1.12, 1.12, 1.12)
# suspension linéaire dorée au-dessus du bureau
box(2.6, 0.04, 0.06, GOLD, -2.4, FH - 1.0, -1.9, flo)
box(2.5, 0.015, 0.04, E("#fff0d0", 14), -2.4, FH - 1.02, -1.9, flo)
for sx in (-3.5, -1.3):
    box(0.008, 0.95, 0.008, GOLD, sx, FH - 0.98, -1.9, flo)
# coin salon : deux fauteuils lounge cuir + table basse marbre
for lx, r in ((0.2, 0.5), (1.9, -0.5)):
    if asset("mid_century_lounge_chair", lx, F, 0.45, flo, rot=r + math.pi):
        continue
    ch = empty("lounge", lx, F, 0.4, flo, r + math.pi)
    box(0.8, 0.06, 0.8, CHROME, 0, 0.32, 0, ch)
    box(0.74, 0.16, 0.74, LEATHER, 0, 0.38, 0, ch, bevel=0.08)
    bk = box(0.74, 0.7, 0.16, LEATHER, 0, 0.5, 0.36, ch, bevel=0.08)
    bk.rotation_euler = (math.radians(-12), 0, 0)
    for a in (-0.38, 0.38):
        box(0.03, 0.34, 0.75, CHROME, a, 0, 0, ch)
asset("Ottoman_01", 1.05, F, 1.35, flo)
asset("ceramic_vase_01", 5.45, F + 1.0, -0.15, flo)
asset("ceramic_vase_02", -1.0, F + 0.83, -2.25, flo)
cyl(0.5, 0.5, 0.05, BLACKMARBLE, 1.05, F + 0.4, -0.6, flo, seg=64)
cyl(0.06, 0.25, 0.4, GOLD, 1.05, F, -0.6, flo, seg=24)
# aquarium intégré
box(3.0, 1.5, 0.6, GLASS, 3.6, F + 0.5, -3.05, flo)
box(2.92, 1.35, 0.52, mat("#1a8fc9", 0.05, transm=0.85, ior=1.33, emit="#0f7fd0", es=1.6), 3.6, F + 0.55, -3.05, flo)
box(3.1, 0.5, 0.7, WALNUT, 3.6, F, -3.05, flo, bevel=0.02)
for k in range(9):
    fx = sphere(0.05, E(["#ff8a3a", "#ffd34a", "#ff4fa3"][k % 3], 4), 2.4 + k * 0.28, F + 0.8 + (k * 37 % 9) * 0.1, -3.05 + ((k % 2) - 0.5) * 0.25, flo)
    fx.scale = (1.8, 0.7, 1)
# bar à whisky
box(0.55, 1.0, 1.6, WALNUT, 5.5, F, -1.0, flo, bevel=0.02)
box(0.04, 0.6, 1.5, E("#ffbf6a", 3), 5.78, F + 1.1, -1.0, flo)
for k in range(5):
    cyl(0.05, 0.06, 0.28, mat("#b5651d", 0.05, transm=0.8), 5.45, F + 1.0, -1.6 + k * 0.3, flo, seg=16)
# sculpture + grande plante
cyl(0.25, 0.25, 0.9, WHITE, -5.2, F, 2.6, flo, seg=6)
sphere(0.3, GOLD, -5.2, F + 1.2, 2.6, flo)
if not asset("potted_plant_04", -4.4, F, -2.9, flo):
    plant(flo, -4.2, -3.0, 1.5)
# salle de bain privée (toilettes de FLO) dans l'angle avant droit
toilettes(flo, 3.3, 5.95, 0.5, 3.45, BLACKMARBLE, sign=False, walls=("x0", "z0"))
box(1.05, 2.1, 0.03, GLASS, 5.42, F, 2.2, flo)                                     # paroi de douche
box(0.3, 0.02, 0.3, CHROME, 5.45, FH - 0.5, 2.85, flo)                             # pommeau de pluie
box(0.012, FH - F - 0.5, 0.012, CHROME, 5.9, F + 0.1, 2.85, flo)
box(0.9, 0.01, 0.06, BLACKGLOSS, 5.45, F + 0.02, 3.3, flo)                          # caniveau de douche
text("FLO PRIVÉ", 0.16, E("#ffd28a", 6), 4.6, 2.85, 3.49, flo, align="CENTER")
point(30, "#ffd8a8", -2.4, FH - 1.2, -1.2, flo)

# toit : terrasse + piscine
roof = empty("toit", 0, TOP * FH, 0)
box(TW + 0.4, F, TD + 0.4, mat("#cfc6b8", 0.5), 0, 0, 0, roof)
box(TW + 0.4, 0.05, 0.05, E("#3fe0ff", 14), 0, 0.12, D2 + 0.23, roof)
for z in (-D2 - 0.15, D2 + 0.15):
    box(TW + 0.4, 1.1, 0.03, GLASS, 0, F, z, roof)
for x in (-W2 - 0.15, W2 + 0.15):
    box(0.03, 1.1, TD + 0.4, GLASS, x, F, 0, roof)
box(7.4, 0.55, 3.4, WHITE, -1.6, F, 0.9, roof, bevel=0.03)
water = mat("#36c6e6", 0.03, transm=0.9, ior=1.33, emit="#0ab8e6", es=1.2)
box(7.0, 0.05, 3.0, water, -1.6, F + 0.52, 0.9, roof)
area(150, "#5fe0ff", -1.6, F + 0.3, 0.9, 6.5, 2.6, roof).rotation_euler = (math.pi, 0, 0)  # lumière de fond de bassin
for lx, lz in ((3.4, -1.2), (4.6, -1.2), (3.4, 1.4)):
    box(0.7, 0.3, 1.8, WHITE, lx, F, lz, roof, bevel=0.08)
agent("#ea4b71", 3.4, F + 0.3, -1.2, roof, sit=True, rot=math.pi)
cyl(0.04, 0.04, 2.2, DARK, 4.0, F, 0.1, roof)
cyl(0.02, 1.4, 0.45, mat("#f3eee6", 0.8), 4.0, F + 2.1, 0.1, roof, seg=48)
box(2.4, 1.0, 0.7, mat("#2a2420", 0.35, coat=0.6), -3.4, F, -2.8, roof, bevel=0.04)
box(2.4, 0.04, 0.06, E("#3fe0ff", 12), -3.4, F + 0.5, -2.42, roof)
agent("#e5c27a", -3.4, F, -3.2, roof)
for px, pz in ((-5.6, -3.0), (5.6, -3.0), (5.6, 3.0)):
    if not asset("potted_plant_01", px, F, pz, roof):
        plant(roof, px, pz, 1.3)
text("T   TOIT · PISCINE", 0.42, E("#ffffff", 5), -W2 - 4.6, 1.4, D2, roof)
box(0.18, 0.18, 0.02, E("#3fe0ff", 20), -W2 - 4.9, 1.52, D2, roof, bevel=0.06)
point(60, "#ffe0b0", 4.0, F + 1.6, 0.1, roof)

# structure + ascenseur panoramique
for cx, cz in ((-W2, -D2), (W2, -D2), (-W2, D2), (W2, D2)):
    box(0.22, TOP * FH, 0.22, DARK, cx, 0, cz)
box(0.4, 3, 0.4, DARK, 4.5, TOP * FH + F, -2.8)
sphere(0.15, E("#ff2030", 60), 4.5, TOP * FH + F + 3.15, -2.8)
SX = W2 + 1.15
box(1.7, TOP * FH + GD + 1.2, 1.9, GLASS, SX, -GD, -1.9)
for a in (-0.85, 0.85):
    for b in (-0.95, 0.95):
        box(0.06, TOP * FH + GD + 1.2, 0.06, DARK, SX + a, -GD, -1.9 + b)
cab = empty("cabine", SX, 3 * FH + 0.4, -1.9)
box(1.45, 0.12, 1.65, DARK, 0, 0, 0, cab)
box(1.45, 0.06, 1.65, E("#ffe7c2", 6), 0, 2.4, 0, cab)
agent("#ea4b71", 0, 0.12, 0, cab, rot=math.pi / 2)

# ---------------------------------------------------------------- caméras
cams = {}


def camera(name, pos, target, fov=35, fstop=None):
    c = bpy.data.cameras.new(name)
    c.sensor_fit = "VERTICAL"
    c.angle = math.radians(fov)
    c.clip_end = 1500
    if fstop:                                            # profondeur de champ (gros plans)
        c.dof.use_dof = True
        c.dof.focus_distance = (B(*target) - B(*pos)).length
        c.dof.aperture_fstop = fstop
    ob = bpy.data.objects.new(name, c)
    ob.location = B(*pos)
    ob.rotation_euler = (B(*target) - B(*pos)).to_track_quat("-Z", "Y").to_euler()
    coll.objects.link(ob)
    cams[name] = ob


def floor_cam(name, level, fov=25):
    y = level * FH + 1.6
    camera(name, (8.5, y + 0.9, 15.5), (0.3, y + 0.05, -0.8), fov, fstop=4.0)


camera("00-vue-ensemble", (34, 16, 74), (-4, 14, 0))
camera("01-vue-rue", (24, 1.7, 40), (-3, 13, 0), 42)
camera("02-sous-sol-garage", (8, -1.0, 22), (0, -3.4, 2), 38)
camera("02b-garage-plateau-1", (-3.2, -2.7, 4.2), (-7.2, -4.0, -1.5), 40, fstop=2.8)
camera("02c-garage-rangee-avant", (5.5, -3.0, 12.2), (-2.5, -3.9, 4.5), 40, fstop=5.0)
floor_cam("03-lobby-cafe", 0)
floor_cam("04-etage-claude-code", 4)
floor_cam("05-casino", 5)
floor_cam("06-nightclub", 6)
floor_cam("07-penthouse-qg", 7)
floor_cam("09-bureau-de-flo", 8)
camera("10-salle-de-bain-flo", (4.9, 8 * FH + 1.9, 9.0), (4.6, 8 * FH + 1.2, 1.5), 34, fstop=3.2)
camera("11-toit-piscine", (9, TOP * FH + 5.5, 12), (-0.5, TOP * FH + 0.5, 0), 36)

# ---------------------------------------------------------------- rendu
r = scene.render
r.engine = "CYCLES"
r.resolution_x, r.resolution_y, r.resolution_percentage = 2560, 1440, PCT
r.image_settings.color_depth = "16"                     # PNG 16 bits : dégradés sans bandes
prefs = bpy.context.preferences.addons["cycles"].preferences
for dev in ("OPTIX", "CUDA"):
    try:
        prefs.compute_device_type = dev
        prefs.get_devices()
        if any(d.type == dev for d in prefs.devices):
            break
    except TypeError:
        continue
for d in prefs.devices:
    d.use = d.type != "CPU"
scene.cycles.device = "GPU"
scene.cycles.samples = SAMPLES
scene.cycles.use_denoising = True
scene.cycles.denoiser = "OPENIMAGEDENOISE"           # plus fidèle qu'OptiX (pas d'effet « aquarelle »)
scene.cycles.denoising_prefilter = "ACCURATE"
scene.cycles.denoising_quality = "HIGH"
scene.cycles.denoising_use_gpu = True
scene.cycles.adaptive_threshold = 0.005
scene.cycles.max_bounces = 8
scene.cycles.transparent_max_bounces = 16
scene.cycles.caustics_reflective = scene.cycles.caustics_refractive = False
scene.cycles.light_sampling_threshold = 0.01
scene.view_settings.view_transform = "AgX"
for look in ("AgX - Medium High Contrast", "AgX - Punchy"):
    try:
        scene.view_settings.look = look
        break
    except TypeError:
        pass
scene.view_settings.exposure = 0.3

scene.use_nodes = True
nt = scene.node_tree
nt.nodes.clear()
rl = nt.nodes.new("CompositorNodeRLayers")
gl = nt.nodes.new("CompositorNodeGlare")
gl.glare_type = "FOG_GLOW"
gl.quality = "HIGH"
gl.threshold = 2.5
gl.size = 7
gl.mix = -0.55
comp = nt.nodes.new("CompositorNodeComposite")
nt.links.new(rl.outputs["Image"], gl.inputs["Image"])
nt.links.new(gl.outputs["Image"], comp.inputs["Image"])

def export_web(path):
    """Version allégée pour le site : sans skyline (recréée en JS), sans agents (animés en JS),
    instances réalisées, textes en maillages, matériaux procéduraux aplatis, gros maillages décimés."""
    def drop(ob):
        for c in list(ob.children):
            drop(c)
        bpy.data.objects.remove(ob)

    for name in [o.name for o in SKYLINE]:
        if name in bpy.data.objects:
            drop(bpy.data.objects[name])
    for name in [o.name for o in bpy.data.objects]:
        if name not in bpy.data.objects:
            continue
        ob = bpy.data.objects[name]
        beam = ob.type == "MESH" and ob.data.materials and ob.data.materials[0] and ob.data.materials[0].name.startswith("beam")
        if ob.type in ("CAMERA", "LIGHT") or ob.name.startswith("agent") or beam:
            drop(ob)
    bpy.ops.object.select_all(action="DESELECT")
    inst = [o for o in bpy.data.objects if o.instance_type == "COLLECTION"]
    for o in inst:
        o.select_set(True)
    if inst:
        bpy.context.view_layer.objects.active = inst[0]
        bpy.ops.object.duplicates_make_real(use_base_parent=True, use_hierarchy=True)
    bpy.ops.object.select_all(action="DESELECT")
    fonts = [o for o in bpy.data.objects if o.type == "FONT"]
    for o in fonts:
        o.select_set(True)
    if fonts:
        bpy.context.view_layer.objects.active = fonts[0]
        bpy.ops.object.convert(target="MESH")
    for m in bpy.data.materials:                        # bois/marbre procéduraux → couleur moyenne
        if not m.use_nodes or "Principled BSDF" not in m.node_tree.nodes:
            continue
        bc = m.node_tree.nodes["Principled BSDF"].inputs["Base Color"]
        if bc.is_linked and bc.links[0].from_node.type == "VALTORGB":
            els = bc.links[0].from_node.color_ramp.elements
            avg = [sum(e.color[i] for e in els) / len(els) for i in range(4)]
            m.node_tree.links.remove(bc.links[0])
            bc.default_value = avg
    for o in bpy.data.objects:
        if o.type == "MESH" and len(o.data.polygons) > 60000:
            d = o.modifiers.new("decimate", "DECIMATE")
            d.ratio = max(0.08, 60000 / len(o.data.polygons))
    for img in bpy.data.images:
        if img.size[0] > 1024:
            k = 1024 / img.size[0]
            img.scale(1024, max(1, int(img.size[1] * k)))
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", export_apply=True, export_lights=False,
                              export_cameras=False, export_image_format="AUTO",
                              export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=6)
    print(f"[agent_tower] export web : {path} ({os.path.getsize(path) / 1e6:.1f} Mo)", flush=True)


EXPORT = os.environ.get("AGENT_TOWER_EXPORT")
if EXPORT:
    export_web(EXPORT)
    cams = {}                                            # rien à rendre en mode export
else:
    scene.camera = cams["00-vue-ensemble"]
    os.makedirs(OUT, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "agent_tower.blend"))
    print(f"[agent_tower] device={prefs.compute_device_type} samples={SAMPLES} pct={PCT}", flush=True)

for name, cam in cams.items():
    if ONLY and name not in ONLY:
        continue
    t0 = time.time()
    scene.camera = cam
    r.filepath = os.path.join(OUT, name + ".png")
    bpy.ops.render.render(write_still=True)
    print(f"[agent_tower] {name}: {time.time() - t0:.1f}s", flush=True)
