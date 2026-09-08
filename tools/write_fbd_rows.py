"""Write the EditScore-shaped FBD corpus: root, candidates and scores, three ZStandard
parquets in Essential Tuple Normal Form, plus the joined view the dataset viewer reads.

Every row is constructed from a template and a seed, so the labels are true by
construction: the compiler (taskweft-fbd-compiler `check` and `plan`) and a runner
that performs the plan's steps in a scratch directory score every candidate, and the
controls are asserted on every row before anything is written. A holdout of one row
in ten is written apart and never trains.

    python tools/write_fbd_rows.py --rows 5000 --out work/stage
    python tools/write_fbd_rows.py --rows 20 --out work/smoke --negative-control
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fbd_templates import TEMPLATES, Row, row_for  # noqa: E402
from react_templates import REACT_TEMPLATES, ReactRow, react_row_for  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
CANDIDATES = [("rank1", 1), ("rank3", 3), ("rank5", 5)]
STUB = ("fbd", "intent_to_fbd", "instruction_following", "input_intent", "text")
REACT_STUB = ("react", "intent_to_controller", "instruction_following", "input_intent", "text")


def find_compiler(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    env = os.environ.get("FBD_COMPILER")
    if env:
        return Path(env)
    exe = "taskweft_fbd_compiler.exe" if os.name == "nt" else "taskweft_fbd_compiler"
    p = HERE.parent / "taskweft-fbd-compiler" / ".lake" / "build" / "bin" / exe
    if not p.is_file():
        sys.exit(f"FAIL: no compiler at {p}; build taskweft-fbd-compiler or pass --compiler")
    return p


def compiler_sha(compiler: Path) -> str:
    repo = compiler.parents[3]
    try:
        return subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=30).stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def compile_one(compiler: Path, xml: Path) -> tuple[bool, bool, dict | None, str]:
    """(parses, compiles, plan, refusal). compiles means check and plan both answered."""
    chk = subprocess.run([str(compiler), "check", str(xml)], capture_output=True, text=True, timeout=60)
    if chk.returncode != 0:
        return False, False, None, chk.stderr.strip() or chk.stdout.strip()
    pl = subprocess.run([str(compiler), "plan", str(xml)], capture_output=True, text=True, timeout=60)
    if pl.returncode != 0:
        return True, False, None, pl.stderr.strip() or pl.stdout.strip()
    return True, True, json.loads(pl.stdout), ""


def perform(plan: dict, scratch: Path) -> tuple[bool, int, str]:
    """Perform the plan's steps the way the host scene does; stop at the first failure."""
    lines: list[str] = []
    done = 0
    for step in plan["steps"]:
        kind = step["kind"]
        code = 1
        if kind == "write":
            target = scratch / step["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(step["content"], encoding="utf-8")
            code = 0
        elif kind == "read":
            code = 0 if (scratch / step["path"]).is_file() else 1
        elif kind == "terminal":
            command = sys.executable if step["command"] == "python" else step["command"]
            try:
                run = subprocess.run([command, *step["args"]], cwd=scratch, capture_output=True,
                                     text=True, timeout=30)
                code = run.returncode
                if run.stdout:
                    lines.append(run.stdout.rstrip("\n"))
            except (OSError, subprocess.TimeoutExpired) as e:
                lines.append(f"{step['action']} failed to start: {e}")
                code = 1
        lines.append(f"{step['action']} exit {code}")
        if code != 0:
            return False, done, "\n".join(lines)
        done += 1
    return True, done, "\n".join(lines)


def score_candidate(compiler: Path, row: Row, name: str, xml: Path, negative_control: bool) -> dict:
    t0 = time.perf_counter()
    parses, compiles, plan, refusal = compile_one(compiler, xml)
    runs, steps, effect = False, 0, False
    if compiles and plan is not None:
        scratch = Path(tempfile.mkdtemp(prefix="fbd_"))
        try:
            runs, steps, out = perform(plan, scratch)
            effect = runs and row.expect(scratch, out)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
    wall_ms = int((time.perf_counter() - t0) * 1000)
    # The negative control on the writer: hand rank5's verdict to rank1 and the
    # controls below must refuse the emit, or they certify nothing.
    if negative_control and name == "rank1":
        parses, compiles, runs, effect = False, False, False, False
    return {"candidate": name, "parses": parses, "compiles": compiles, "runs": runs,
            "effect_matches": effect, "steps": steps, "wall_ms": wall_ms, "refusal": refusal}


def assert_controls(key: str, scores: dict[str, dict]) -> None:
    r1, r3, r5 = scores["rank1"], scores["rank3"], scores["rank5"]
    if not (r1["compiles"] and r1["runs"] and r1["effect_matches"]):
        raise SystemExit(f"identity control failed on {key}: rank1 {r1}")
    if not r3["compiles"] or r3["effect_matches"]:
        raise SystemExit(f"effect control failed on {key}: rank3 must compile and miss the effect, got {r3}")
    if r5["compiles"]:
        raise SystemExit(f"negative control failed on {key}: rank5 compiled: {r5}")


def build_row(compiler: Path, out: Path, template_id: str, seed: int, negative_control: bool) -> dict:
    row = row_for(template_id, seed)
    key = f"fbd/{template_id}/{seed}"
    row_dir = out / "rows" / template_id / str(seed)
    row_dir.mkdir(parents=True, exist_ok=True)
    scores: dict[str, dict] = {}
    cands = []
    for name, rank in CANDIDATES:
        xml_path = row_dir / f"{name}.plcopen.xml"
        xml_path.write_text(getattr(row, name), encoding="utf-8")
        scores[name] = score_candidate(compiler, row, name, xml_path, negative_control)
        cands.append({"candidate": name, "rank": rank,
                      "fbd_xml": str(xml_path.relative_to(out)).replace(os.sep, "/"),
                      "fbd_sha": hashlib.sha256(getattr(row, name).encode("utf-8")).hexdigest(),
                      "provenance": f"constructed:{template_id}:seed:{seed}"})
    assert_controls(key, scores)
    return {"key": key, "intent": row.intent, "template_id": template_id, "seed": seed,
            "candidates": cands, "scores": [scores[n] for n, _ in CANDIDATES]}


def run_compiler(compiler: Path, *args: str) -> tuple[int, str, str]:
    p = subprocess.run([str(compiler), *args], capture_output=True, text=True, timeout=120)
    return p.returncode, p.stdout, p.stderr


def score_react(compiler: Path, row: ReactRow, name: str, fbd: Path, traces: list[Path], negative_control: bool) -> dict:
    """A controller: parses (the text form reads), compiles (the netlist builds), runs (the
    reference scan finishes every trace without a fault), effect (its outputs are the
    numbers the intent implies), steps = ticks simulated."""
    t0 = time.perf_counter()
    code, xml, err = run_compiler(compiler, "to-xml", str(fbd))
    parses = code == 0
    refusal = "" if parses else (err.strip() or "to-xml refused")
    compiles, runs, effect, steps = False, False, False, 0
    if parses:
        fbd.with_suffix(".plcopen.xml").write_text(xml, encoding="utf-8")
        code, _, err = run_compiler(compiler, "check", str(fbd))
        compiles = code == 0
        if not compiles:
            refusal = err.strip()
    if compiles:
        outs: list[list[dict]] = []
        runs = True
        for trace in traces:
            code, out, err = run_compiler(compiler, "sim", str(fbd), str(trace))
            lines = [json.loads(l) for l in out.splitlines() if l.strip()]
            if code != 0 or any("fault" in l for l in lines):
                runs = False
                refusal = err.strip() or next((l["fault"] for l in lines if "fault" in l), "")
                break
            outs.append([l["out"] for l in lines])
            steps += len(lines)
        effect = runs and row.expect(outs)
    wall_ms = int((time.perf_counter() - t0) * 1000)
    if negative_control and name == "rank1":
        parses, compiles, runs, effect = False, False, False, False
    return {"candidate": name, "parses": parses, "compiles": compiles, "runs": runs,
            "effect_matches": effect, "steps": steps, "wall_ms": wall_ms, "refusal": refusal}


def build_react_row(compiler: Path, out: Path, template_id: str, seed: int, negative_control: bool) -> dict:
    row = react_row_for(template_id, seed)
    key = f"react/{template_id}/{seed}"
    row_dir = out / "rows" / template_id / str(seed)
    row_dir.mkdir(parents=True, exist_ok=True)
    traces = []
    for k, text in enumerate(row.traces):
        tp = row_dir / f"trace_{k}.json"
        tp.write_text(text + "\n", encoding="utf-8")
        traces.append(tp)
    scores: dict[str, dict] = {}
    cands = []
    for name, rank in CANDIDATES:
        fbd = row_dir / f"{name}.fbd"
        fbd.write_text(getattr(row, name), encoding="utf-8")
        scores[name] = score_react(compiler, row, name, fbd, traces, negative_control)
        cands.append({"candidate": name, "rank": rank,
                      "fbd_text": str(fbd.relative_to(out)).replace(os.sep, "/"),
                      "fbd_sha": hashlib.sha256(getattr(row, name).encode("utf-8")).hexdigest(),
                      "traces": len(traces),
                      "provenance": f"constructed:{template_id}:seed:{seed}"})
    assert_controls(key, scores)
    return {"key": key, "intent": row.intent, "template_id": template_id, "seed": seed,
            "candidates": cands, "scores": [scores[n] for n, _ in CANDIDATES]}


def tables(rows: list[dict], stub: tuple = STUB) -> tuple[pa.Table, pa.Table, pa.Table, pa.Table]:
    task_type, dimension, input_column, input_asset_kind = stub[1], stub[2], stub[3], stub[4]
    root = pa.table({
        "key": [r["key"] for r in rows],
        "task_type": [task_type] * len(rows),
        "dimension": [dimension] * len(rows),
        "input_column": [input_column] * len(rows),
        "input_asset_kind": [input_asset_kind] * len(rows),
        "intent": [r["intent"] for r in rows],
        "template_id": [r["template_id"] for r in rows],
        "seed": pa.array([r["seed"] for r in rows], pa.int64()),
        "provenance": ["constructed:template"] * len(rows),
    })
    cand_rows = [{"row_key": r["key"], **c} for r in rows for c in r["candidates"]]
    candidates = pa.Table.from_pylist(cand_rows)
    score_rows = [{"row_key": r["key"], **s} for r in rows for s in r["scores"]]
    scores = pa.Table.from_pylist(score_rows)
    joined = pa.Table.from_pylist([{
        "key": r["key"], "intent": r["intent"], "template_id": r["template_id"], "seed": r["seed"],
        "candidates": [{**c, "scores": s} for c, s in zip(r["candidates"], r["scores"])],
    } for r in rows])
    return root, candidates, scores, joined


def write_stage(stage: Path, rows: list[dict], split: str, family: str = "fbd") -> dict:
    stub = REACT_STUB if family == "react" else STUB
    root, candidates, scores, joined = tables(rows, stub)
    counts = {}
    for name, table in [(f"{family}_root", root), (f"{family}_candidates", candidates), (f"{family}_scores", scores), (family, joined)]:
        for col in table.column_names:
            n = table.column(col).null_count
            if n:
                raise SystemExit(f"FAIL: {name}.{col} carries {n} null(s); ETNF forbids them")
        d = stage / "data" / name
        d.mkdir(parents=True, exist_ok=True)
        pq.write_table(table, d / f"{split}-00000-of-00001.parquet", compression="zstd")
        counts[name] = table.num_rows
    return counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=5000)
    ap.add_argument("--out", type=Path, default=HERE / "work" / "stage")
    ap.add_argument("--compiler", default=None)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--family", choices=["fbd", "react"], default="fbd",
                    help="fbd: the operating-system step programs; react: the per-frame controllers")
    ap.add_argument("--negative-control", action="store_true",
                    help="hand rank5's verdict to rank1; the controls must refuse the emit")
    args = ap.parse_args()

    compiler = find_compiler(args.compiler)
    out: Path = args.out
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    family = args.family
    template_ids = list(REACT_TEMPLATES if family == "react" else TEMPLATES)
    builder = build_react_row if family == "react" else build_row
    jobs = [(template_ids[(i // 10) % len(template_ids)], i) for i in range(args.rows)]

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(lambda j: builder(compiler, out, j[0], j[1], args.negative_control), jobs))
    wall = time.perf_counter() - t0

    train = [r for r in rows if r["seed"] % 10 != 0]
    holdout = [r for r in rows if r["seed"] % 10 == 0]
    counts = {"train": write_stage(out, train, "train", family), "holdout": write_stage(out / "holdout", holdout, "holdout", family)}
    manifest = {
        "stub": REACT_STUB if family == "react" else STUB, "family": family, "rows": len(rows), "train_rows": len(train), "holdout_rows": len(holdout),
        "templates": {t: sum(1 for r in rows if r["template_id"] == t) for t in template_ids},
        "controls": "rank1 compiles, runs and matches; rank3 compiles and misses; rank5 is refused; asserted on every row",
        "compiler": str(compiler), "compiler_sha": compiler_sha(compiler),
        "wall_s": round(wall, 1), "counts": counts,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
