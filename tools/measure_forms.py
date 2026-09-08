"""Tokens per diagram in each form the compiler reads, over every rank1 candidate.

The forms are the PLCopen XML the corpus stores, the text form `to-dsl` prints, and
the SafeGDScript guest `emit` writes. The tokenizer is Gemma 4's, because that is
what a teacher pays per sampled token. Every row is enumerated (rule 5), and the
round trips are asserted on every row: text -> XML -> text is a fixed point, the
plan from the text equals the plan from the XML, and the plan from the lifted
guest equals it too. A row where any of those fails is a finding, not a skip.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent.parent
TOKENIZER_REPO = "google/gemma-4-E2B-it-qat-q4_0-unquantized"


def find_compiler(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    for c in [HERE.parent / "taskweft-fbd-compiler" / ".lake" / "build" / "bin" / "taskweft_fbd_compiler.exe",
              HERE.parent / "taskweft-fbd-compiler" / ".lake" / "build" / "bin" / "taskweft_fbd_compiler"]:
        if c.exists():
            return c
    sys.exit("FAIL: no compiler binary; build taskweft-fbd-compiler first")


def run(compiler: Path, *args: str) -> tuple[int, str, str]:
    p = subprocess.run([str(compiler), *args], capture_output=True, text=True, encoding="utf-8")
    return p.returncode, p.stdout, p.stderr


def tokenizer():
    from huggingface_hub import hf_hub_download
    from tokenizers import Tokenizer
    return Tokenizer.from_file(hf_hub_download(TOKENIZER_REPO, "tokenizer.json"))


def forms_of(compiler: Path, xml_path: Path, scratch: Path) -> dict:
    stem = scratch / xml_path.parent.name / xml_path.parent.parent.name
    stem.mkdir(parents=True, exist_ok=True)
    code, dsl, err = run(compiler, "to-dsl", str(xml_path))
    if code:
        return {"error": f"to-dsl: {err.strip()}"}
    fbd = stem / "d.fbd"
    fbd.write_text(dsl, encoding="utf-8")
    code, xml2, err = run(compiler, "to-xml", str(fbd))
    if code:
        return {"error": f"to-xml: {err.strip()}"}
    xml2_path = stem / "d.xml"
    xml2_path.write_text(xml2, encoding="utf-8")
    code, dsl2, err = run(compiler, "to-dsl", str(xml2_path))
    if code or dsl2 != dsl:
        return {"error": "text -> XML -> text is not a fixed point"}
    _, plan_xml, _ = run(compiler, "plan", str(xml_path))
    _, plan_fbd, _ = run(compiler, "plan", str(fbd))
    if plan_xml != plan_fbd:
        return {"error": "plan from the text form differs from the plan from the XML"}
    sgd = stem / "d.sgd"
    code, _, err = run(compiler, "emit", str(xml_path), str(sgd))
    if code:
        return {"error": f"emit: {err.strip()}"}
    _, plan_sgd, err = run(compiler, "plan", str(sgd))
    if plan_sgd != plan_xml:
        return {"error": f"plan from the lifted guest differs from the plan from the XML: {err.strip()}"}
    return {"xml": xml_path.read_text(encoding="utf-8"), "fbd": dsl, "sgd": sgd.read_text(encoding="utf-8")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", type=Path, required=True)
    ap.add_argument("--compiler", default=None)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    compiler = find_compiler(args.compiler)
    tok = tokenizer()
    cands = pq.read_table(args.stage / "data" / "fbd_candidates").to_pylist()
    rank1 = [c for c in cands if c["candidate"] == "rank1"]
    if not rank1:
        sys.exit("FAIL: no rank1 candidates in the stage")
    scratch = Path(tempfile.mkdtemp(prefix="measure_forms_"))
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda c: forms_of(compiler, args.stage / c["fbd_xml_path"], scratch), rank1))
    failures = [(c["row_key"], r["error"]) for c, r in zip(rank1, results) if "error" in r]
    ok = [r for r in results if "error" not in r]

    counts = {f: [len(tok.encode(r[f]).ids) for r in ok] for f in ("xml", "fbd", "sgd")}
    chars = {f: [len(r[f]) for r in ok] for f in ("xml", "fbd", "sgd")}
    table = {}
    for f in ("xml", "fbd", "sgd"):
        table[f] = {
            "rows": len(counts[f]),
            "tokens_mean": round(statistics.mean(counts[f]), 1),
            "tokens_p50": statistics.median(counts[f]),
            "tokens_max": max(counts[f]),
            "chars_mean": round(statistics.mean(chars[f]), 1),
        }
    ratio = table["xml"]["tokens_mean"] / table["fbd"]["tokens_mean"]
    report = {
        "tokenizer": TOKENIZER_REPO,
        "rank1_rows": len(rank1),
        "round_trip_ok": len(ok),
        "round_trip_failures": failures[:20],
        "forms": table,
        "xml_over_fbd_tokens": round(ratio, 2),
    }
    print(json.dumps(report, indent=2))
    if args.out:
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if failures:
        sys.exit(f"FAIL: {len(failures)} of {len(rank1)} rows broke a round trip")


if __name__ == "__main__":
    main()
