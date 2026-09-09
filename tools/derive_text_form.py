"""Fill a candidate's missing text form from its XML with the compiler's own converter.

A runner wrapping the compiler: `to-dsl` is one half of the text-to-XML-to-text
fixed point the compiler's tests assert, so this adds no information and loses
none. The operating-system family emitted PLCopen XML only, so its rows carried
no text form; every other family wrote both. A candidate the parser refuses
keeps an empty text form, which is what a refused diagram has.

    python tools/derive_text_form.py --stage work/stage --compiler <path>
"""
from __future__ import annotations

import argparse
import glob
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

SPLITS = [("train", "data"), ("test", "test/data"), ("evaluation", "evaluation/data")]


def to_dsl(compiler: Path, xml: str, scratch: Path) -> str:
    p = scratch / "candidate.plcopen.xml"
    p.write_text(xml, encoding="utf-8")
    r = subprocess.run([str(compiler), "to-dsl", str(p)], capture_output=True, text=True, timeout=60)
    return r.stdout if r.returncode == 0 else ""


def rewrite(path: Path, split: str, rows: list[dict]) -> int:
    for f in path.glob("*.parquet"):
        f.unlink()
    t = pa.Table.from_pylist(rows)
    pq.write_table(t, path / f"{split}-00000-of-00001.parquet", compression="zstd")
    return t.num_rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", type=Path, required=True)
    ap.add_argument("--compiler", type=Path, required=True)
    args = ap.parse_args()

    stage: Path = args.stage
    family = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))["family"]
    cache: dict[str, str] = {}
    derived = refused = 0

    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp)
        for split, split_dir in SPLITS:
            for name in (f"{family}_candidates", family):
                d = stage / split_dir / name
                files = sorted(d.glob("*.parquet")) if d.is_dir() else []
                if not files:
                    continue
                rows = pq.read_table(files[0]).to_pylist()

                def fill(c: dict) -> dict:
                    nonlocal derived, refused
                    if c.get("fbd_text") or not c.get("fbd_xml"):
                        return c
                    xml = c["fbd_xml"]
                    if xml not in cache:
                        cache[xml] = to_dsl(args.compiler, xml, scratch)
                    text = cache[xml]
                    if text:
                        derived += 1
                    else:
                        refused += 1
                    c["fbd_text"] = text
                    return c

                for r in rows:
                    if "candidates" in r:
                        r["candidates"] = [fill(c) for c in r["candidates"]]
                    else:
                        fill(r)
                rewrite(d, split, rows)
            print(f"{split}: done")

    print(f"derived {derived} text form(s); {refused} candidate(s) the parser refuses keep an empty one")


if __name__ == "__main__":
    main()
