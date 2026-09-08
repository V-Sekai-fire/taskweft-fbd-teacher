"""The Godot family: the engine surface as the sandbox exposes it, one CALL block per
call, scored by what the engine returned.

Every template is a short program of CALL blocks over `sigs/godot_engine_single.sigs`
performed on the API fixture scene by `api_runner.gd`; the effect check reads the
returns back (a position set then read, a label's text, a determinant) against the
numbers the intent names. rank3 carries a wrong argument, rank5 a signature outside
the table. Eight entries of the table have no row, by name in `UNCOVERED`: a Callable
has no literal form, `unreference` frees its target, the five virtual callbacks
are what a guest implements, not what a plan calls, and `OS.get_ticks_msec` is
not in Godot 4.
"""
from __future__ import annotations

import math
import random
import re

from react_templates import ReactRow

FIX = "/root/Fixture"
EPS = 1e-4
WORDS = ["hello", "ready", "walk", "idle", "north", "seven", "amber", "quiet", "delta", "opal"]
NODES = {"Body": "Node3D", "Label": "Label", "Button": "Button", "Timer": "Timer", "Flat": "Node2D",
         "Camera": "Camera3D", "Rigid": "RigidBody3D", "Area": "Area3D", "Anim": "AnimationPlayer"}

UNCOVERED = {
    "Object.connect": "a Callable has no literal form the plan can carry",
    "RefCounted.unreference": "it frees the target when the count reaches zero",
    "Node._process": "a virtual callback the engine calls; not callable on a plain node",
    "Node._physics_process": "a virtual callback the engine calls; not callable on a plain node",
    "Node._enter_tree": "a virtual callback the engine calls; not callable on a plain node",
    "Node._exit_tree": "a virtual callback the engine calls; not callable on a plain node",
    "MainLoop._process": "a virtual callback the engine calls; not callable on the tree",
    "OS.get_ticks_msec": "removed in Godot 4; Time.get_ticks_msec is the call the engine has",
}


def _f(x: float) -> str:
    s = f"{x:.3f}".rstrip("0")
    return s + "0" if s.endswith(".") else s


def _nums(s: str | None) -> list[float]:
    # a digit glued to a letter is a type name (Vector3, Transform3D), not a value
    return [float(m) for m in re.findall(r"(?<![A-Za-z0-9_])-?\d+(?:\.\d+)?(?:e[-+]?\d+)?", s or "")]


def _close(a: float, b: float) -> bool:
    return abs(float(a) - float(b)) <= EPS


def _same(got: list[float], want: list[float]) -> bool:
    return len(got) == len(want) and all(_close(g, w) for g, w in zip(got, want))


def _str(s: str | None) -> str:
    # a StringName prints as &"name"
    return (s or "").lstrip("&").strip('"')


def _ret(res: list[dict], i: int) -> str | None:
    return res[i]["ret"] if i < len(res) and res[i].get("ok") else None


def call(_blk: str, _sig: str, _target: str, _en: str | None, **args: str) -> str:
    # an argument naming an earlier block's RET is a wire, not a literal
    pins = ([f"EN={_en}"] if _en else []) + [f"TARGET={_target}"] + [
        f"{k}={v}" if re.fullmatch(r"[A-Za-z_]\w*\.RET", v) else f'{k}="{v}"' for k, v in args.items()]
    return f"{_blk} = CALL[{_sig}](" + ", ".join(pins) + ")"


def prog(pid: str, steps: list[tuple]) -> str:
    """steps: (name, key, target, args). EN chains each block to the one before, so the
    plan's order is the list's."""
    lines = [f"program {pid}", "var done : BOOL"]
    prev = None
    for name, key, target, args in steps:
        lines.append(call(name, key, target, f"{prev}.ENO" if prev else None, **args))
        prev = name
    lines.append(f"done = {prev}.ENO")
    return "\n".join(lines) + "\n"


def q(s: str) -> str:
    return '"' + s + '"'


def node(path: str) -> str:
    return q(f"{FIX}/{path}")


def refuse(text: str) -> str:
    """rank5: a signature the table does not have."""
    return re.sub(r"CALL\[[A-Za-z0-9_]+\.[A-Za-z0-9_]+\]", "CALL[Node3D.set_scale]", text, count=1)


# ---- templates ---------------------------------------------------------------

def t_move_body(seed: int) -> ReactRow:
    rng = random.Random(seed)
    x, y, z = (rng.randint(-5, 5) + rng.choice([0.0, 0.5]) for _ in range(3))
    v = f"Vector3({_f(x)}, {_f(y)}, {_f(z)})"
    w = f"Vector3({_f(x + 1)}, {_f(y)}, {_f(z)})"

    def p(vec: str) -> str:
        return prog("move_body", [
            ("n", "Node.get_node", q(FIX), {"path": "Body"}),
            ("s", "Node3D.set_position", "n.RET", {"position": vec}),
            ("g", "Node3D.get_position", "n.RET", {}),
        ])

    def expect(res: list[dict]) -> bool:
        return _same(_nums(_ret(res, 2)), [x, y, z])

    frames = [f"move the body node to ({_f(x)}, {_f(y)}, {_f(z)}) and read its position back",
              f"put Body at x {_f(x)}, y {_f(y)}, z {_f(z)}, then get the position",
              f"set the body's position to ({_f(x)}, {_f(y)}, {_f(z)}) and confirm it"]
    fid = seed % len(frames)
    return ReactRow("godot_move_body", seed, frames[fid], p(v), p(w), refuse(p(v)), [], expect, fid, host="godot")


def t_transform_body(seed: int) -> ReactRow:
    rng = random.Random(seed)
    tx, ty, tz = (rng.randint(-4, 4) + rng.choice([0.0, 0.25]) for _ in range(3))

    def t(dx: float) -> str:
        return f"Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, {_f(tx + dx)}, {_f(ty)}, {_f(tz)})"

    def p(tr: str) -> str:
        return prog("transform_body", [
            ("n", "Node.get_node", q(FIX), {"path": "Body"}),
            ("s", "Node3D.set_transform", "n.RET", {"local": tr}),
            ("g", "Node3D.get_transform", "n.RET", {}),
        ])

    def expect(res: list[dict]) -> bool:
        got = _nums(_ret(res, 2))
        return len(got) == 12 and _same(got[9:], [tx, ty, tz]) and _same(got[:9], [1, 0, 0, 0, 1, 0, 0, 0, 1])

    frames = [f"give the body an identity basis at origin ({_f(tx)}, {_f(ty)}, {_f(tz)}) and read the transform back",
              f"set Body's transform to a translation of ({_f(tx)}, {_f(ty)}, {_f(tz)}), then get it",
              f"move Body by transform to ({_f(tx)}, {_f(ty)}, {_f(tz)}) with no rotation and confirm"]
    fid = seed % len(frames)
    return ReactRow("godot_transform_body", seed, frames[fid], p(t(0)), p(t(1)), refuse(p(t(0))), [], expect, fid, host="godot")


def t_object_set(seed: int) -> ReactRow:
    rng = random.Random(seed)
    x, y, z = (rng.randint(-3, 3) for _ in range(3))
    v = f"Vector3({x}, {y}, {z})"
    w = f"Vector3({x}, {y + 2}, {z})"

    def p(vec: str) -> str:
        return prog("object_set", [
            ("n", "Node.get_node", q(FIX), {"path": "Body"}),
            ("c", "Object.get_class", "n.RET", {}),
            ("s", "Object.set", "n.RET", {"property": "position", "value": vec}),
            ("g", "Object.get", "n.RET", {"property": "position"}),
            ("h", "Node3D.get_position", "n.RET", {}),
        ])

    def expect(res: list[dict]) -> bool:
        return (_str(_ret(res, 1)) == "Node3D" and _same(_nums(_ret(res, 3)), [x, y, z])
                and _same(_nums(_ret(res, 4)), [x, y, z]))

    frames = [f"set the body's position property to ({x}, {y}, {z}) through Object.set and read it back both ways",
              f"through the generic property setter, put Body at ({x}, {y}, {z}); confirm with get and get_position",
              f"Body: class name, then position := ({x}, {y}, {z}) by property, then read it back"]
    fid = seed % len(frames)
    return ReactRow("godot_object_set", seed, frames[fid], p(v), p(w), refuse(p(v)), [], expect, fid, host="godot")


def t_ui_text(seed: int) -> ReactRow:
    rng = random.Random(seed)
    a, b = rng.sample(WORDS, 2)
    wrong = rng.choice([w for w in WORDS if w not in (a, b)])

    def p(la: str, bt: str) -> str:
        return prog("ui_text", [
            ("l", "Node.get_node", q(FIX), {"path": "Label"}),
            ("s", "Label.set_text", "l.RET", {"text": la}),
            ("g", "Object.get", "l.RET", {"property": "text"}),
            ("b", "Node.get_node", q(FIX), {"path": "Button"}),
            ("t", "Button.set_text", "b.RET", {"text": bt}),
            ("h", "Object.get", "b.RET", {"property": "text"}),
        ])

    def expect(res: list[dict]) -> bool:
        return _str(_ret(res, 2)) == a and _str(_ret(res, 5)) == b

    frames = [f"set the label's text to '{a}' and the button's to '{b}', reading each back",
              f"label says {a}, button says {b}; confirm both texts",
              f"write '{a}' on the Label and '{b}' on the Button, then get the text properties"]
    fid = seed % len(frames)
    return ReactRow("godot_ui_text", seed, frames[fid], p(a, b), p(a, wrong), refuse(p(a, b)), [], expect, fid, host="godot")


def t_flat_node(seed: int) -> ReactRow:
    rng = random.Random(seed)
    x, y = rng.randint(-100, 100), rng.randint(-100, 100)
    r = round(rng.uniform(-3.0, 3.0), 2)

    def p(px: int, rot: float) -> str:
        return prog("flat_node", [
            ("n", "Node.get_node", q(FIX), {"path": "Flat"}),
            ("s", "Node2D.set_position", "n.RET", {"position": f"Vector2({px}, {y})"}),
            ("r", "Node2D.set_rotation", "n.RET", {"radians": _f(rot)}),
            ("g", "Object.get", "n.RET", {"property": "position"}),
            ("h", "Object.get", "n.RET", {"property": "rotation"}),
        ])

    def expect(res: list[dict]) -> bool:
        return _same(_nums(_ret(res, 3)), [x, y]) and _same(_nums(_ret(res, 4)), [r])

    frames = [f"move the 2D node to ({x}, {y}) and rotate it {_f(r)} radians, then read both back",
              f"Flat: position ({x}, {y}), rotation {_f(r)} rad; confirm",
              f"place the flat node at pixel ({x}, {y}) turned by {_f(r)} radians and get the properties"]
    fid = seed % len(frames)
    return ReactRow("godot_flat_node", seed, frames[fid], p(x, r), p(x + 7, r), refuse(p(x, r)), [], expect, fid, host="godot")


def t_rigid_mass(seed: int) -> ReactRow:
    rng = random.Random(seed)
    m = round(rng.uniform(0.5, 20.0), 2)

    def p(mass: float) -> str:
        return prog("rigid_mass", [
            ("n", "Node.get_node", q(FIX), {"path": "Rigid"}),
            ("s", "RigidBody3D.set_mass", "n.RET", {"mass": _f(mass)}),
            ("g", "Object.get", "n.RET", {"property": "mass"}),
            ("c", "Object.get_class", "n.RET", {}),
        ])

    def expect(res: list[dict]) -> bool:
        return _same(_nums(_ret(res, 2)), [m]) and _str(_ret(res, 3)) == "RigidBody3D"

    frames = [f"give the rigid body a mass of {_f(m)} and read it back",
              f"set Rigid's mass to {_f(m)} kg, confirm the property and the class",
              f"the rigid body weighs {_f(m)}; set it and check"]
    fid = seed % len(frames)
    return ReactRow("godot_rigid_mass", seed, frames[fid], p(m), p(m + 0.5), refuse(p(m)), [], expect, fid, host="godot")


def t_timer_run(seed: int) -> ReactRow:
    rng = random.Random(seed)
    t = round(rng.uniform(0.25, 9.0), 2)

    def p(wait: float) -> str:
        return prog("timer_run", [
            ("n", "Node.get_node", q(FIX), {"path": "Timer"}),
            ("s", "Timer.start", "n.RET", {"time_sec": _f(wait)}),
            ("w", "Object.get", "n.RET", {"property": "wait_time"}),
            ("a", "Object.call", "n.RET", {"method": "is_stopped"}),
            ("x", "Timer.stop", "n.RET", {}),
            ("b", "Object.call", "n.RET", {"method": "is_stopped"}),
        ])

    def expect(res: list[dict]) -> bool:
        return _same(_nums(_ret(res, 2)), [t]) and _ret(res, 3) == "false" and _ret(res, 5) == "true"

    frames = [f"start the timer for {_f(t)} seconds, check it runs, stop it, check it stopped",
              f"Timer: start at {_f(t)} s, is_stopped false, stop, is_stopped true",
              f"run the timer with a {_f(t)} second wait and then stop it, confirming each state"]
    fid = seed % len(frames)
    return ReactRow("godot_timer_run", seed, frames[fid], p(t), p(t + 0.5), refuse(p(t)), [], expect, fid, host="godot")


def t_vector_math(seed: int) -> ReactRow:
    rng = random.Random(seed)
    a = [rng.randint(-4, 4) for _ in range(3)]
    b = [rng.randint(-4, 4) for _ in range(3)]
    px, py = rng.randint(1, 5), rng.randint(-5, 5)

    def p(a0: int) -> str:
        va = f"Vector3({a0}, {a[1]}, {a[2]})"
        vb = f"Vector3({b[0]}, {b[1]}, {b[2]})"
        return prog("vector_math", [
            ("l", "Vector3.length", q(va), {}),
            ("d", "Vector3.dot", q(va), {"with": vb}),
            ("c", "Vector3.cross", q(va), {"with": vb}),
            ("g", "Vector2.angle", q(f"Vector2({px}, {py})"), {}),
            ("m", "Vector2.length", q(f"Vector2({px}, {py})"), {}),
        ])

    cross = [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]

    def expect(res: list[dict]) -> bool:
        return (_same(_nums(_ret(res, 0)), [math.sqrt(sum(v * v for v in a))])
                and _same(_nums(_ret(res, 1)), [sum(x * y for x, y in zip(a, b))])
                and _same(_nums(_ret(res, 2)), cross)
                and _same(_nums(_ret(res, 3)), [math.atan2(py, px)])
                and _same(_nums(_ret(res, 4)), [math.hypot(px, py)]))

    frames = [f"length, dot and cross of ({a[0]}, {a[1]}, {a[2]}) with ({b[0]}, {b[1]}, {b[2]}), then the angle and length of ({px}, {py})",
              f"vector arithmetic: |a|, a.b, a x b for a=({a[0]}, {a[1]}, {a[2]}), b=({b[0]}, {b[1]}, {b[2]}); angle and length of ({px}, {py})",
              f"compute the norm of ({a[0]}, {a[1]}, {a[2]}), its dot and cross with ({b[0]}, {b[1]}, {b[2]}), and the 2D angle and norm of ({px}, {py})"]
    fid = seed % len(frames)
    return ReactRow("godot_vector_math", seed, frames[fid], p(a[0]), p(a[0] + 1), refuse(p(a[0])), [], expect, fid, host="godot")


def t_transform_math(seed: int) -> ReactRow:
    rng = random.Random(seed)
    tx, ty, tz = (rng.randint(-5, 5) for _ in range(3))
    s = rng.choice([2, 3, 4])
    da, db, dc = (rng.choice([1, 2, 3, -1, -2]) for _ in range(3))
    qz, qw = rng.choice([1, 2, 3]), rng.choice([1, 2, 4])
    n = math.hypot(qz, qw)

    def p(t0: int) -> str:
        return prog("transform_math", [
            ("i", "Transform3D.inverse", q(f"Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, {t0}, {ty}, {tz})"), {}),
            ("o", "Transform3D.orthonormalized", q(f"Transform3D({s}, 0, 0, 0, {s}, 0, 0, 0, {s}, 0, 0, 0)"), {}),
            ("d", "Basis.determinant", q(f"Basis({da}, 0, 0, 0, {db}, 0, 0, 0, {dc})"), {}),
            ("n", "Quaternion.normalized", q(f"Quaternion(0, 0, {qz}, {qw})"), {}),
        ])

    def expect(res: list[dict]) -> bool:
        inv = _nums(_ret(res, 0))
        ortho = _nums(_ret(res, 1))
        return (len(inv) == 12 and _same(inv[9:], [-tx, -ty, -tz])
                and len(ortho) == 12 and _same(ortho[:9], [1, 0, 0, 0, 1, 0, 0, 0, 1])
                and _same(_nums(_ret(res, 2)), [da * db * dc])
                and _same(_nums(_ret(res, 3)), [0, 0, qz / n, qw / n]))

    frames = [f"invert a translation by ({tx}, {ty}, {tz}), orthonormalize a uniform scale of {s}, the determinant of diag({da}, {db}, {dc}), and normalize the quaternion (0, 0, {qz}, {qw})",
              f"transform math: inverse of a ({tx}, {ty}, {tz}) translation; orthonormalized scale {s}; det diag({da}, {db}, {dc}); unit quaternion from (0, 0, {qz}, {qw})",
              f"the inverse of moving by ({tx}, {ty}, {tz}), a scale-{s} basis made orthonormal, determinant {da}*{db}*{dc}, and (0, 0, {qz}, {qw}) normalized"]
    fid = seed % len(frames)
    return ReactRow("godot_transform_math", seed, frames[fid], p(tx), p(tx + 1), refuse(p(tx)), [], expect, fid, host="godot")


def t_values(seed: int) -> ReactRow:
    rng = random.Random(seed)
    r, g, b = (rng.choice([0.0, 0.25, 0.5, 0.75, 1.0]) for _ in range(3))
    word = rng.choice(WORDS)
    other = rng.choice([w for w in WORDS if w != word])
    n = rng.randint(1, 6)
    keys = sorted(rng.sample(range(1, 9), 3))
    probe = rng.choice(keys)
    bytes_n = rng.randint(1, 7)
    argb = (255 << 24) | (round(r * 255) << 16) | (round(g * 255) << 8) | round(b * 255)

    def p(rr: float) -> str:
        arr = "[" + ", ".join(str(i) for i in range(n)) + "]"
        dic = "{" + ", ".join(f"{k}: {k * 10}" for k in keys) + "}"
        # the form var_to_str writes, which str_to_var reads back
        pba = "PackedByteArray(" + ", ".join(str(i) for i in range(bytes_n)) + ")"
        return prog("values", [
            ("c", "Color.to_argb32", q(f"Color({_f(rr)}, {_f(g)}, {_f(b)}, 1)"), {}),
            ("l", "String.length", q(word), {}),
            ("h", "StringName.hash", q("sn:" + word), {}),
            ("i", "StringName.hash", q("sn:" + other), {}),
            ("a", "Array.size", q(arr), {}),
            ("p", "Array.push_back", q(arr), {"value": "9"}),
            ("d", "Dictionary.size", q(dic), {}),
            ("k", "Dictionary.has", q(dic), {"key": str(probe)}),
            ("m", "Dictionary.has", q(dic), {"key": "99"}),
            ("y", "PackedByteArray.size", q(pba), {}),
        ])

    def expect(res: list[dict]) -> bool:
        return (_nums(_ret(res, 0)) == [argb] and _nums(_ret(res, 1)) == [len(word)]
                and len(_nums(_ret(res, 2))) == 1 and _ret(res, 2) != _ret(res, 3)
                and _nums(_ret(res, 4)) == [n] and _nums(_ret(res, 6)) == [3]
                and _ret(res, 7) == "true" and _ret(res, 8) == "false" and _nums(_ret(res, 9)) == [bytes_n])

    frames = [f"pack Color({_f(r)}, {_f(g)}, {_f(b)}) to ARGB32, the length of '{word}', hashes of two names, sizes of an array of {n}, a dictionary of 3 with key {probe}, and {bytes_n} bytes",
              f"builtin values: argb of ({_f(r)}, {_f(g)}, {_f(b)}); '{word}' has {len(word)} characters; two name hashes; array {n} long; dictionary has {probe} and not 99; {bytes_n} bytes",
              f"read back the ARGB32 of ({_f(r)}, {_f(g)}, {_f(b)}), the character count of {word}, name hashes, and the sizes of an array ({n}), a dictionary (3, key {probe}) and a byte array ({bytes_n})"]
    fid = seed % len(frames)
    wrong = 0.0 if r == 1.0 else r + 0.25
    return ReactRow("godot_values", seed, frames[fid], p(r), p(wrong), refuse(p(r)), [], expect, fid, host="godot")


def t_resources(seed: int) -> ReactRow:
    rng = random.Random(seed)
    groups = [("Shape", "Shape2", "shape", "CollisionShape3D.set_shape", "BoxShape3D"),
              ("Mesh", "Mesh2", "mesh", "MeshInstance3D.set_mesh", "BoxMesh"),
              ("Sprite", "Sprite2", "texture", "Sprite2D.set_texture", "PlaceholderTexture2D")]
    rng.shuffle(groups)

    def p(readback: str) -> str:
        steps = [
            ("g", "Object.get", node("Shape"), {"property": "shape"}),
            ("r", "Resource.get_path", "g.RET", {}),
            ("d", "Resource.duplicate", "g.RET", {"subresources": "true"}),
            ("c", "Object.get_class", "d.RET", {}),
            ("f", "RefCounted.reference", "d.RET", {}),
            ("n", "RefCounted.get_reference_count", "d.RET", {}),
        ]
        for i, (src, dst, prop, setter, _) in enumerate(groups):
            steps += [
                (f"s{i}", "Object.get", node(src), {"property": prop}),
                (f"t{i}", setter, node(dst), {prop: f"s{i}.RET"}),
                (f"b{i}", "Object.get", node(dst), {"property": readback if i == 0 else prop}),
            ]
        return prog("resources", steps)

    def expect(res: list[dict]) -> bool:
        if _str(_ret(res, 1)) != "res://api_fixture.tscn::BoxShape3D_a" or _str(_ret(res, 3)) != "BoxShape3D":
            return False
        if _ret(res, 4) != "true" or not _nums(_ret(res, 5)):
            return False
        for i, (_, _, _, _, cls) in enumerate(groups):
            if _ret(res, 8 + 3 * i) != f"Object:{cls}":
                return False
        return True

    order = ", ".join(g[2] for g in groups)
    frames = [f"read the box shape's path, duplicate it and count its references, then hand the {order} from each source node to its twin and read them back",
              f"resources: path of Shape's shape, a duplicate's class and refcount, and copy {order} across node pairs",
              f"copy the {order} resources to the second nodes after inspecting the shape resource"]
    fid = seed % len(frames)
    # rank3 reads the wrong property back on the first pair: a bool where an object is meant
    return ReactRow("godot_resources", seed, frames[fid], p(groups[0][2]), p("visible" if groups[0][2] != "shape" else "disabled"),
                    refuse(p(groups[0][2])), [], expect, fid, host="godot")


def t_tree_ops(seed: int) -> ReactRow:
    rng = random.Random(seed)
    name, cls = rng.choice(list(NODES.items()))
    other = rng.choice([n for n in NODES if NODES[n] != cls])
    children = 15

    def p(which: str) -> str:
        return prog("tree_ops", [
            ("r", "SceneTree.get_root", q("SceneTree"), {}),
            ("c", "Object.get_class", "r.RET", {}),
            ("k", "Object.call", q(FIX), {"method": "get_child_count"}),
            ("d", "Object.call", node(which), {"method": "duplicate"}),
            ("a", "Node.add_child", q(FIX), {"node": "d.RET", "force_readable_name": "true", "internal": "0"}),
            ("m", "Object.call", q(FIX), {"method": "get_child_count"}),
            ("x", "Object.get_class", "d.RET", {}),
            ("f", "Node.queue_free", "d.RET", {}),
            ("z", "Object.call", "d.RET", {"method": "is_queued_for_deletion"}),
        ])

    def expect(res: list[dict]) -> bool:
        return (_str(_ret(res, 1)) == "Window" and _nums(_ret(res, 2)) == [children]
                and _nums(_ret(res, 5)) == [children + 1] and _str(_ret(res, 6)) == cls
                and _ret(res, 8) == "true")

    frames = [f"get the tree root's class, count the fixture's children, duplicate {name} into the fixture, count again, then free the copy",
              f"tree ops: root is a Window; {children} children; add a copy of {name} (a {cls}); {children + 1}; queue it free",
              f"duplicate the {name} node under the fixture and confirm the child count rose by one before freeing it"]
    fid = seed % len(frames)
    return ReactRow("godot_tree_ops", seed, frames[fid], p(name), p(other), refuse(p(name)), [], expect, fid, host="godot")


def t_lifecycle(seed: int) -> ReactRow:
    rng = random.Random(seed)
    name, cls = rng.choice(list(NODES.items()))
    other = rng.choice([n for n in NODES if NODES[n] != cls])

    def p(which: str) -> str:
        return prog("lifecycle", [
            ("n", "Node.get_node", q(FIX), {"path": which}),
            ("k", "Object.get_class", "n.RET", {}),
            ("m", "Object.call", "n.RET", {"method": "get_name"}),
            ("t", "Engine.get_physics_ticks_per_second", q("Engine"), {}),
            ("c", "Object.call", q(FIX), {"method": "get_child_count"}),
        ])

    def expect(res: list[dict]) -> bool:
        return (_str(_ret(res, 1)) == cls and _str(_ret(res, 2)) == name
                and _nums(_ret(res, 3)) == [60] and _nums(_ret(res, 4)) == [15])

    frames = [f"find {name}, report its class and name, the physics rate, and how many children the fixture has",
              f"{name} is a {cls}; read the class and the name back, then the ticks per second and the fixture's child count",
              f"introspect the node named {name}: class, name, engine physics rate, fixture children"]
    fid = seed % len(frames)
    return ReactRow("godot_lifecycle", seed, frames[fid], p(name), p(other), refuse(p(name)), [], expect, fid, host="godot")


def t_loader(seed: int) -> ReactRow:
    rng = random.Random(seed)
    hint = rng.choice(["", "PackedScene"])
    mode = rng.choice([0, 1, 2])

    def p(path: str) -> str:
        return prog("loader", [
            ("l", "ResourceLoader.load", q("ResourceLoader"), {"path": path, "type_hint": hint, "cache_mode": str(mode)}),
            ("c", "Object.get_class", "l.RET", {}),
            ("r", "Resource.get_path", "l.RET", {}),
            ("s", "SceneTree.change_scene_to_file", q("SceneTree"), {"path": path}),
        ])

    def expect(res: list[dict]) -> bool:
        return (_str(_ret(res, 1)) == "PackedScene" and _str(_ret(res, 2)) == "res://api_fixture.tscn"
                and _nums(_ret(res, 3)) == [0])

    frames = [f"load the fixture scene (cache mode {mode}), confirm it is a PackedScene at its path, then switch the tree to it",
              f"ResourceLoader.load res://api_fixture.tscn with hint '{hint}' and cache mode {mode}; class, path, change_scene_to_file returns OK",
              f"fetch the api fixture as a resource, check its class and path, and change scene to it"]
    fid = seed % len(frames)
    return ReactRow("godot_loader", seed, frames[fid], p("res://api_fixture.tscn"), p("res://scripts/api_runner.gd"),
                    refuse(p("res://api_fixture.tscn")), [], expect, fid, host="godot")


def t_camera_input(seed: int) -> ReactRow:
    rng = random.Random(seed)
    sx, sy = rng.randint(0, 1000), rng.randint(0, 600)
    speed = rng.choice([0.5, 1.0, 2.0])

    def p(anim: str) -> str:
        return prog("camera_input", [
            ("c", "Node.get_node", q(FIX), {"path": "Camera"}),
            ("r", "Camera3D.project_ray_normal", "c.RET", {"screen_point": f"Vector2({sx}, {sy})"}),
            ("u", "Camera3D.unproject_position", "c.RET", {"world_point": "Vector3(0, 0, -5)"}),
            ("o", "Area3D.get_overlapping_bodies", node("Area"), {}),
            ("z", "Array.size", "o.RET", {}),
            ("i", "Input.is_action_pressed", q("Input"), {"action": "ui_accept", "exact_match": "false"}),
            ("w", "Time.get_ticks_msec", q("Time"), {}),
            ("p", "AnimationPlayer.play", node("Anim"), {"name": anim, "custom_blend": "-1", "custom_speed": _f(speed), "from_end": "false"}),
            ("a", "Object.get", node("Anim"), {"property": "current_animation"}),
        ])

    def expect(res: list[dict]) -> bool:
        ray = _nums(_ret(res, 1))
        return (len(ray) == 3 and _close(math.sqrt(sum(v * v for v in ray)), 1.0)
                and len(_nums(_ret(res, 2))) == 2 and _nums(_ret(res, 4)) == [0] and _ret(res, 5) == "false"
                and len(_nums(_ret(res, 6))) == 1 and _str(_ret(res, 8)) == "idle")

    frames = [f"cast a ray through screen point ({sx}, {sy}), unproject a world point, count overlapping bodies, poll ui_accept, read the tick clock, and play idle at speed {_f(speed)}",
              f"camera and input: ray normal at ({sx}, {sy}); unproject (0, 0, -5); no overlaps; ui_accept not pressed; the tick clock; play 'idle' x{_f(speed)}",
              f"project a ray from ({sx}, {sy}), read the clock and the input, then play the idle animation at {_f(speed)} and confirm it is current"]
    fid = seed % len(frames)
    return ReactRow("godot_camera_input", seed, frames[fid], p("idle"), p("walk"), refuse(p("idle")), [], expect, fid, host="godot")


GODOT_TEMPLATES = {
    "godot_move_body": t_move_body,
    "godot_transform_body": t_transform_body,
    "godot_object_set": t_object_set,
    "godot_ui_text": t_ui_text,
    "godot_flat_node": t_flat_node,
    "godot_rigid_mass": t_rigid_mass,
    "godot_timer_run": t_timer_run,
    "godot_vector_math": t_vector_math,
    "godot_transform_math": t_transform_math,
    "godot_values": t_values,
    "godot_resources": t_resources,
    "godot_tree_ops": t_tree_ops,
    "godot_lifecycle": t_lifecycle,
    "godot_loader": t_loader,
    "godot_camera_input": t_camera_input,
}


def godot_row_for(template_id: str, seed: int) -> ReactRow:
    return GODOT_TEMPLATES[template_id](seed)


def signatures_of(text: str) -> list[str]:
    return re.findall(r"CALL\[([A-Za-z0-9_]+\.[A-Za-z0-9_]+)\]", text)


if __name__ == "__main__":
    import sys
    seen: set[str] = set()
    for tid, fn in GODOT_TEMPLATES.items():
        row = fn(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
        seen |= set(signatures_of(row.rank1))
        print(tid, "|", row.intent)
    print(len(seen), "signature(s) covered")
