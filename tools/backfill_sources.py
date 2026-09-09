"""Put every candidate's source into the parquet, where a path used to point.

A runner wrapping nothing: this is a one-shot repair of stages already written.

The writer kept each candidate's diagram under `rows/` and stored the *path* in
`fbd_text`. `publish_fbd.py` uploads with `ignore_patterns=["rows/**"]` and
deletes any `rows/` already on the Hub, so every published path dangled and the
corpus carried no diagram at all. This reads the stage's `rows/` tree and
rewrites the candidate, root and joined tables with the text itself: the FBD
text form, the PLCopen XML, the plan the compiler produced, the result the
runner wrote, and the row's traces.

    python tools/backfill_sources.py --stage work/stage_udon
    python tools/backfill_sources.py --stage work/stage_udon --check
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

SPLITS = [("train", "data"), ("test", "test/data"), ("evaluation", "evaluation/data")]
RANKS = ["rank1", "rank3", "rank5"]


def read(path: Path) -> str:
    """A missing artefact is an empty string, which is a value; ETNF forbids the null."""
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def row_dir(stage: Path, template_id: str, seed: int) -> Path:
    return stage / "rows" / template_id / str(seed)


def sources_for(stage: Path, template_id: str, seed: int, candidate: str) -> dict:
    d = row_dir(stage, template_id, seed)
    text = read(d / f"{candidate}.fbd")
    xml = read(d / f"{candidate}.plcopen.xml")
    return {
        "fbd_text": text,
        "fbd_xml": xml,
        "plan_json": read(d / f"{candidate}.plan.json"),
        "result_json": read(d / f"{candidate}.result.json"),
        "fbd_path": f"rows/{template_id}/{seed}/{candidate}",
    }


def traces_for(stage: Path, template_id: str, seed: int) -> list[str]:
    d = row_dir(stage, template_id, seed)
    if not d.is_dir():
        return []
    return [p.read_text(encoding="utf-8") for p in sorted(d.glob("trace_*.json"))]


def key_parts(key: str) -> tuple[str, int]:
    _family, template_id, seed = key.split("/")
    return template_id, int(seed)


def sha_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def table_dir(stage: Path, split_dir: str, name: str) -> Path:
    return stage / split_dir / name


def load(path: Path) -> list[dict] | None:
    files = sorted(path.glob("*.parquet")) if path.is_dir() else []
    if not files:
        return None
    return pq.read_table(files[0]).to_pylist()


def write(path: Path, split: str, rows: list[dict]) -> int:
    for f in path.glob("*.parquet"):
        f.unlink()
    t = pa.Table.from_pylist(rows)
    for col in t.column_names:
        n = t.column(col).null_count
        if n:
            sys.exit(f"FAIL: {path.name}.{col} carries {n} null(s); ETNF forbids them")
    pq.write_table(t, path / f"{split}-00000-of-00001.parquet", compression="zstd")
    return t.num_rows


def backfill_split(stage: Path, family: str, split: str, split_dir: str, check: bool) -> dict:
    root = load(table_dir(stage, split_dir, f"{family}_root"))
    cands = load(table_dir(stage, split_dir, f"{family}_candidates"))
    scores = load(table_dir(stage, split_dir, f"{family}_scores"))
    if root is None or cands is None or scores is None:
        return {}

    missing = []
    for c in cands:
        template_id, seed = key_parts(c["row_key"])
        src = sources_for(stage, template_id, seed, c["candidate"])
        if not src["fbd_text"] and not src["fbd_xml"]:
            missing.append(f"{c['row_key']}/{c['candidate']}")
        if src["fbd_text"] and c.get("fbd_sha") and sha_of(src["fbd_text"]) != c["fbd_sha"]:
            sys.exit(f"FAIL: {c['row_key']}/{c['candidate']} text does not match its recorded sha")
        c.pop("traces", None)
        c.update(src)

    by_key = {}
    for r in root:
        template_id, seed = key_parts(r["key"])
        r["traces"] = traces_for(stage, template_id, seed)
        by_key[r["key"]] = r

    scores_by = {}
    for s in scores:
        scores_by.setdefault(s["row_key"], {})[s["candidate"]] = {
            k: v for k, v in s.items() if k != "row_key"
        }

    joined = []
    for r in root:
        mine = [c for c in cands if c["row_key"] == r["key"]]
        joined.append(
            {
                "key": r["key"],
                "intent": r["intent"],
                "template_id": r["template_id"],
                "seed": r["seed"],
                "traces": r["traces"],
                "candidates": [
                    {**{k: v for k, v in c.items() if k != "row_key"},
                     "scores": scores_by[r["key"]][c["candidate"]]}
                    for c in sorted(mine, key=lambda c: c["rank"])
                ],
            }
        )

    if check:
        return {"missing": missing, "rows": len(root), "candidates": len(cands)}

    counts = {
        f"{family}_root": write(table_dir(stage, split_dir, f"{family}_root"), split, root),
        f"{family}_candidates": write(table_dir(stage, split_dir, f"{family}_candidates"), split, cands),
        family: write(table_dir(stage, split_dir, family), split, joined),
    }
    return {"missing": missing, "counts": counts}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", type=Path, required=True)
    ap.add_argument("--check", action="store_true", help="report what is missing and write nothing")
    args = ap.parse_args()

    stage: Path = args.stage
    manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
    family = manifest["family"]

    if not (stage / "rows").is_dir():
        sys.exit(f"FAIL: {stage}/rows is absent, so the sources cannot be recovered")

    total_missing = []
    for split, split_dir in SPLITS:
        out = backfill_split(stage, family, split, split_dir, args.check)
        if not out:
            continue
        total_missing += out.get("missing", [])
        print(f"{split}: {out.get('counts') or out}")

    if total_missing:
        print(f"WARN: {len(total_missing)} candidate(s) have no diagram on disk: {total_missing[:5]}")


if __name__ == "__main__":
    main()
