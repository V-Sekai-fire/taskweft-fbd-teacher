"""Publish a written stage to the Hub, the way publish_dress_on.py does.

The token is the `hf_token` field of this desk's `agents/<cn>` row in OpenBao, read
with a cert login that stores nothing. The upload is `upload_folder` with no delete
patterns, so a rerun adds shards. The README's `configs` block gives the viewer one
config per table with the joined view as the default; without it every directory
folds into one table. Nothing leaves until the stage passes the two refusals below.

    python tools/publish_fbd.py --stage work/stage --hub chibifire/taskweft-fbd-editscore-train
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

FORBIDDEN = ("c:/users", "c:\\users", "/home/", "/private/tmp")


def refuse_if_absolute(root: Path) -> None:
    hits = []
    for p in root.rglob("*.parquet"):
        import pyarrow.parquet as pq
        t = pq.read_table(p)
        for col in t.column_names:
            if t.schema.field(col).type == "string":
                for v in t.column(col).to_pylist():
                    if isinstance(v, str) and any(m in v.lower() for m in FORBIDDEN):
                        hits.append(f"{p.relative_to(root)}:{col}")
                        break
    if hits:
        sys.exit(f"REFUSED: {len(hits)} column(s) name a local filesystem: {hits[:5]}")


def refuse_if_forbidden(root: Path) -> None:
    bad = [str(p) for p in root.rglob("*") if any(m in str(p).lower() for m in FORBIDDEN)]
    if bad:
        sys.exit(f"REFUSED: blocked marker in staged path: {bad[:5]}")


def hf_token_from_bao() -> str:
    env = dict(os.environ, BAO_ADDR="https://100.124.200.34:8200", BAO_TLS_SERVER_NAME="weftspun-bao.internal",
               BAO_CACERT=os.path.expanduser("~/.magi/ca-bundle.pem"),
               BAO_CLIENT_CERT=os.path.expanduser("~/.magi/v3-leaf-int.pem"),
               BAO_CLIENT_KEY=os.path.expanduser("~/.magi/bao-client-v3.key"))
    bao = os.path.expanduser("~/bin/bao.exe")
    tok = subprocess.run([bao, "login", "-method=cert", "-no-store", "-field=token"], env=env,
                         capture_output=True, text=True, timeout=60).stdout.strip()
    env["BAO_TOKEN"] = tok
    hf = subprocess.run([bao, "kv", "get", "-field=hf_token", "agents/magi-16739d.agents.weftspun"], env=env,
                        capture_output=True, text=True, timeout=60).stdout.strip()
    if not hf.startswith("hf_"):
        sys.exit("FAIL: no hf_token in bao agents row")
    return hf


def readme(manifest: dict) -> str:
    names = ["fbd", "fbd_root", "fbd_candidates", "fbd_scores"]
    configs = "".join(
        f"- config_name: {n}\n" + ("  default: true\n" if n == "fbd" else "")
        + f"  data_files:\n  - split: train\n    path: data/{n}/*.parquet\n  - split: holdout\n    path: holdout/data/{n}/*.parquet\n"
        for n in names)
    return f"""---
license: mit
task_categories:
- text-generation
tags:
- iec-61131-3
- function-block-diagram
- plcopen
- taskweft
- editscore
configs:
{configs}---

# taskweft-fbd-editscore-train

Intents and the IEC 61131-3 Function Block Diagrams that carry them out, as an
EditScore-shaped corpus: one root row per intent, three candidates per row (rank1 the
reference diagram, rank3 one that compiles and does the wrong thing, rank5 one the
compiler refuses), and one score row per candidate from the compiler and a runner
that performed the plan. Every row is constructed from a template and a seed, so the
labels are true by construction and the corpus regenerates from the seeds. Controls
were asserted on every row before the emit; the holdout split never trains.

Rows: {manifest["rows"]} ({manifest["train_rows"]} train, {manifest["holdout_rows"]} holdout).
Templates: {json.dumps(manifest["templates"])}. Compiler: taskweft-fbd-compiler
{manifest["compiler_sha"]}. Source: v-sekai-fabric/taskweft-fbd-teacher.
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", type=Path, required=True)
    ap.add_argument("--hub", required=True)
    ap.add_argument("--private", action="store_true")
    args = ap.parse_args()

    stage: Path = args.stage
    manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
    refuse_if_absolute(stage)
    refuse_if_forbidden(stage)
    (stage / "README.md").write_text(readme(manifest), encoding="utf-8")

    from huggingface_hub import HfApi
    api = HfApi(token=hf_token_from_bao())
    api.create_repo(args.hub, repo_type="dataset", exist_ok=True, private=args.private)
    api.upload_folder(folder_path=str(stage), repo_id=args.hub, repo_type="dataset",
                      ignore_patterns=["rows/**"] if False else None)
    files = api.list_repo_files(args.hub, repo_type="dataset")
    parquets = [f for f in files if f.endswith(".parquet")]
    print(f"published {args.hub}: {len(files)} file(s), {len(parquets)} parquet(s)")
    if not parquets:
        sys.exit("FAIL: the read-back lists no parquet")


if __name__ == "__main__":
    main()
