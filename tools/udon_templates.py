"""The Udon family: UdonSharp C# methods and the diagrams that compute the same thing.

Constructed end to end: a seeded C# method is written, udon2godot (pinned, in WSL)
translates it to SafeGDScript, `gd_lift` lifts the method into a scan controller, and
Godot runs the translated class on the row's traces through `udon_runner.gd` to give
the reference the diagram's simulation must match tick for tick. The intent is the C#
source. rank3 is the first mutation the traces can tell apart, rank5 reads an input
the program never declared. The fixture methods udon2godot ships are the evaluation
rows: real code, out of family.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import subprocess
import zlib
from pathlib import Path

from gd_lift import Refused, lift_all, methods_of
from harness_templates import _mutations, _sim
from react_templates import ReactRow

HERE = Path(__file__).resolve().parent.parent
SANDBOX = HERE.parent / "taskweft-godot-sandbox" / "priv" / "godot_project"
GEN = SANDBOX / "udon" / "gen"
WORK = HERE / "work" / "udon"
TICKS = 12
EPS = 1e-4


def wsl(path: Path) -> str:
    p = str(path.resolve()).replace("\\", "/")
    return "/mnt/" + p[0].lower() + p[2:]


def translate(cs: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["wsl.exe", "--", "bash", wsl(HERE / "scripts" / "udon2godot.sh"), wsl(out_dir), wsl(cs)],
                       capture_output=True, text=True, timeout=300)
    sgd = out_dir / (cs.stem + ".sgd")
    if r.returncode != 0 or not sgd.is_file():
        raise RuntimeError(f"udon2godot failed on {cs.name}: {(r.stderr or r.stdout)[-400:]}")
    return sgd


def godot_reference(gd: Path, method: str, params: list[str], trace: Path, out: Path, godot: Path) -> list[str]:
    cmd = [str(godot), "--headless", "--path", str(SANDBOX), "--script", "res://scripts/udon_runner.gd", "--",
           "--script", "res://udon/gen/" + gd.name, "--method", method, "--params", ",".join(params),
           "--trace", str(trace.resolve()), "--out", str(out.resolve())]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if not re.search(r"^exit 0", r.stdout, re.M) or not out.is_file():
        raise RuntimeError(f"udon_runner failed on {gd.name}.{method}: {(r.stderr or r.stdout)[-400:]}")
    return json.loads(out.read_text(encoding="utf-8"))["results"]


# ---- the seeded C# methods ---------------------------------------------------

CS_HEAD = "using UdonSharp;\nusing UnityEngine;\n\npublic class {cls} : UdonSharpBehaviour\n{{\n"
CS_TAIL = "}\n"


def _cs(cls: str, method: str) -> str:
    body = "\n".join("    " + l for l in method.splitlines())
    return CS_HEAD.format(cls=cls) + body + "\n" + CS_TAIL


def _fl(x: float) -> str:
    s = f"{x:.3f}".rstrip("0")
    return (s + "0" if s.endswith(".") else s) + "f"


TEMPLATES: dict[str, callable] = {}


def template(fn):
    TEMPLATES["udon_" + fn.__name__] = fn
    return fn


@template
def scale_add(rng):
    k, c = rng.randint(2, 9), rng.randint(-5, 5)
    return (f"public int ScaleAdd(int a, int b)\n{{\n    return a * {k} + b - {c};\n}}",
            ["a", "b"], ["int", "int"],
            [f"scale a by {k}, add b and take away {c}", f"a times {k} plus b minus {c}", f"the integer a*{k} + b - {c}"])


@template
def blend(rng):
    return ("public float Blend(float a, float b, float t)\n{\n    return a * (1.0f - t) + b * t;\n}",
            ["a", "b", "t"], ["float", "float", "float"],
            ["linear interpolation from a to b by t", "blend a toward b by the fraction t", "a * (1 - t) + b * t"])


@template
def clamp_sum(rng):
    lo = rng.randint(-9, 0)
    hi = rng.randint(1, 9)
    return (f"public int ClampSum(int a, int b)\n{{\n    return Mathf.Clamp(a + b, {lo}, {hi});\n}}",
            ["a", "b"], ["int", "int"],
            [f"the sum of a and b clamped to [{lo}, {hi}]", f"add a and b, never below {lo} nor above {hi}", f"clamp a + b between {lo} and {hi}"])


@template
def pick(rng):
    k = round(rng.uniform(0.5, 3.0), 2)
    return (f"public float Pick(float a, float b, bool c)\n{{\n    return c ? a * {_fl(k)} : b;\n}}",
            ["a", "b", "c"], ["float", "float", "bool"],
            [f"a scaled by {k} when c holds, else b", f"if c then {k} times a, otherwise b", f"choose {k}*a or b by the flag c"])


@template
def in_band(rng):
    lo = round(rng.uniform(-5.0, 0.0), 1)
    hi = round(rng.uniform(0.5, 5.0), 1)
    return (f"public bool InBand(float x, float y)\n{{\n    return x >= {_fl(lo)} && x <= {_fl(hi)} || y < {_fl(lo)};\n}}",
            ["x", "y"], ["float", "float"],
            [f"true when x lies in [{lo}, {hi}] or y is below {lo}", f"x inside the band {lo}..{hi}, or y under {lo}", f"band test on x ({lo} to {hi}) with an escape when y < {lo}"])


@template
def branch_sum(rng):
    k = rng.randint(2, 5)
    return (f"public int BranchSum(int a, int b)\n{{\n    int s = a + b;\n    int d = a - b;\n    if (s > d)\n    {{\n        s = s * {k};\n    }}\n    else\n    {{\n        s = d;\n    }}\n    return s;\n}}",
            ["a", "b"], ["int", "int"],
            [f"the sum times {k} when it exceeds the difference, else the difference", f"if a+b > a-b then {k}*(a+b) else a-b", f"branch on sum versus difference of a and b, scaling the sum by {k}"])


@template
def speed_cap(rng):
    g = round(rng.uniform(0.5, 2.0), 2)
    return (f"public float SpeedCap(float v, float cap)\n{{\n    float s = v * {_fl(g)};\n    if (s > cap)\n    {{\n        s = cap;\n    }}\n    return s;\n}}",
            ["v", "cap"], ["float", "float"],
            [f"v scaled by {g}, never above cap", f"gain {g} on v with a ceiling at cap", f"{g} * v capped at cap"])


@template
def either(rng):
    return ("public bool Either(bool a, bool b, bool c)\n{\n    return (a || b) && !c;\n}",
            ["a", "b", "c"], ["bool", "bool", "bool"],
            ["a or b, unless c", "true when a or b holds and c does not", "(a or b) and not c"])


@template
def min_max(rng):
    return ("public float MinMax(float a, float b, float c)\n{\n    return Mathf.Max(Mathf.Min(a, b), c);\n}",
            ["a", "b", "c"], ["float", "float", "float"],
            ["the smaller of a and b, but at least c", "max(min(a, b), c)", "floor the minimum of a and b at c"])


@template
def compare_scale(rng):
    k = rng.randint(2, 6)
    return (f"public bool CompareScale(int a, int b)\n{{\n    int s = a * {k};\n    return s != b && s >= 0;\n}}",
            ["a", "b"], ["int", "int"],
            [f"true when {k}*a differs from b and is not negative", f"{k} times a is non-negative and not equal to b", f"scale a by {k}; unequal to b and at least zero"])


@template
def weighted(rng):
    w1, w2 = round(rng.uniform(0.1, 0.9), 2), round(rng.uniform(0.1, 0.9), 2)
    return (f"public float Weighted(float a, float b, bool flip)\n{{\n    float w = flip ? {_fl(w2)} : {_fl(w1)};\n    return a * w + b * (1.0f - w);\n}}",
            ["a", "b", "flip"], ["float", "float", "bool"],
            [f"weight a by {w1} (or {w2} when flipped) against b", f"a weighted average of a and b with weight {w1}, {w2} if flip", f"mix a and b; the weight is {w2} when flip else {w1}"])


def _trace(rng: random.Random, names: list[str], types: list[str]) -> dict:
    ticks = []
    for _ in range(TICKS):
        t = {}
        for n, ty in zip(names, types):
            if ty == "int":
                t[n] = rng.randint(-9, 9)
            elif ty == "float":
                t[n] = round(rng.uniform(-5.0, 5.0), 3)
            else:
                t[n] = rng.random() < 0.5
        ticks.append(t)
    return {"dt": 0.125, "ticks": ticks}


def _same(fbd_out: dict, ref: str) -> bool:
    v = fbd_out.get("ret")
    if isinstance(v, bool):
        return ref == ("true" if v else "false")
    try:
        return abs(float(v) - float(ref)) <= EPS * max(1.0, abs(float(ref)))
    except (TypeError, ValueError):
        return False


def _refuse(text: str) -> str:
    m = re.search(r"^in (\w+) : ", text, re.M)
    return re.sub(rf"=(?:{m.group(1)})\b", "=zz", text, count=1) if m else text


def udon_row(template_id: str, seed: int, compiler: Path, godot: Path) -> ReactRow:
    rng = random.Random(seed * 1000 + zlib.crc32(template_id.encode("utf-8")) % 997)
    cs_method, names, types, frames = TEMPLATES[template_id](rng)
    fid = seed % len(frames)
    cls = "U" + hashlib.sha1(f"{template_id}/{seed}".encode()).hexdigest()[:10]
    row_dir = WORK / template_id / str(seed)
    row_dir.mkdir(parents=True, exist_ok=True)
    cs = row_dir / f"{cls}.cs"
    cs.write_text(_cs(cls, cs_method), encoding="utf-8")
    sgd = translate(cs, row_dir)
    GEN.mkdir(parents=True, exist_ok=True)
    gd = GEN / f"{cls}.gd"
    gd.write_text(sgd.read_text(encoding="utf-8"), encoding="utf-8")
    method = re.search(r"public \w+ (\w+)\(", cs_method).group(1)
    lifted, refused = lift_all(sgd.read_text(encoding="utf-8"))
    if method not in lifted:
        raise Refused(f"{template_id}: {refused.get(method, 'method not translated')}")
    text = lifted[method].replace(f"program {method}", f"program {template_id}", 1)
    traces = [_trace(rng, names, types) for _ in range(3)]
    trace_paths = []
    refs = []
    for k, tr in enumerate(traces):
        tp = row_dir / f"trace_{k}.json"
        tp.write_text(json.dumps(tr), encoding="utf-8")
        trace_paths.append(tp)
        refs.append(godot_reference(gd, method, names, tp, row_dir / f"ref_{k}.json", godot))
    rank3, _ = _mutations(text), None
    rank3 = _pick_mutation(text, compiler, trace_paths, row_dir)

    def expect(outs: list[list[dict]]) -> bool:
        return all(len(o) == len(r) and all(_same(a, b) for a, b in zip(o, r)) for o, r in zip(outs, refs))

    intent = cs_method
    return ReactRow(template_id, seed, intent, text, rank3, _refuse(text), [json.dumps(t) for t in traces], expect, fid, host="udon")


def _pick_mutation(text: str, compiler: Path, traces: list[Path], work: Path) -> str:
    cands = _mutations(text)
    if not cands:
        raise Refused("no mutation")
    ref = _sim(compiler, text, traces, work)
    for c in cands:
        if _sim(compiler, c, traces, work) != ref:
            return c
    raise Refused("every mutation is invisible on the traces")


# ---- the fixture methods, real code out of family ---------------------------

def fixture_methods(udon_dir: Path) -> dict[str, tuple[Path, str, list[tuple[str, str]], str]]:
    """name -> (gd path, method, params, text) for every fixture method the lift carries."""
    out = {}
    for gd in sorted(udon_dir.glob("*.gd")):
        text = gd.read_text(encoding="utf-8")
        lifted, _ = lift_all(text)
        for m in methods_of(text):
            if m.name in lifted:
                out[f"udon_fixture_{gd.stem}_{m.name}"] = (gd, m.name, m.params, lifted[m.name])
    return out


def fixture_census(udon_dir: Path) -> dict:
    counts = {"lifted": 0, "refused": {}}
    for gd in sorted(udon_dir.glob("*.gd")):
        lifted, refused = lift_all(gd.read_text(encoding="utf-8"))
        counts["lifted"] += len(lifted)
        for why in refused.values():
            key = why.split(":")[0]
            counts["refused"][key] = counts["refused"].get(key, 0) + 1
    return counts


if __name__ == "__main__":
    import sys
    print(json.dumps(fixture_census(SANDBOX / "udon"), indent=2))
    for tid, fn in TEMPLATES.items():
        m, names, types, frames = fn(random.Random(int(sys.argv[1]) if len(sys.argv) > 1 else 0))
        print(tid, "|", frames[0])
