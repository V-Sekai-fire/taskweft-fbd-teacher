"""The plan family: the taskweft planner as a diagram source.

For every domain and every goal it admits, with seeded argument values, the door's
`mix taskweft_acp.plan_sgd` plans the goal and writes the guest; the compiler lifts
the guest into the text form (a step program for chores, a triggered controller for
set-and-hold reactions). rank1 is the lifted plan; rank3 drops the last step or
swaps a literal; rank5 hands the lift a kind it refuses. The effect check is
differential against rank1, as the harness family's is.

The mix invocation carries the desk's build environment (llvm-mingw, make, Git's
usr/bin) because the door's NIF is compiled on first use; set TASKWEFT_ACP_DIR to
the checkout.
"""
from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
from pathlib import Path

from react_templates import ReactRow

HERE = Path(__file__).resolve().parent.parent
ACP = Path(os.environ.get("TASKWEFT_ACP_DIR", HERE.parents[1] / "1-transport" / "transport-taskweft-acp"))
PLAN_CACHE = HERE / "work" / "plans"

WORDS = ["alder", "birch", "cedar", "dune", "ember", "fjord", "glade", "heath", "islet", "juniper",
         "kelp", "larch", "moss", "nettle", "orchid", "pine", "quartz", "reed", "sedge", "thistle"]

# (domain file, goal, argument makers, intent frames)
GOALS: list[tuple[str, str, list, list[str]]] = [
    ("repo_chores.ex", "tests_pass", [], ["make the tests pass", "get the build green and the tests passing", "build then test"]),
    ("repo_chores.ex", "tests_pass; git_commit {msg}", ["msg"], ["commit with the message {msg}", "make the tests pass and commit as {msg}", "build, test, then commit {msg}"]),
    ("repo_chores.ex", "formatted", [], ["format the repository", "run the formatter", "make the sources formatted"]),
    ("file_layout.ex", "configured {dir} {text}", ["dir", "text"], ["set up {dir} with a config saying {text} and check it", "make the directory {dir}, write {text} into its config, confirm the file", "configure {dir}: {text}"]),
    ("file_layout.ex", "populated {dir} {text}", ["dir", "text"], ["put data {text} in {dir} and count the files there", "create {dir}, write {text} to its data file, count what is in it", "populate {dir} with {text} and report the file count"]),
    ("file_layout.ex", "archived {dir} {text}", ["dir", "text"], ["populate {dir} with {text}, count it, and write a listing", "make {dir} with data {text}, then archive its listing", "archive the listing of {dir} after filling it with {text}"]),
    ("avatar_reactions.ex", "greet", [], ["greet: face the stick, wave, hold two seconds, stop", "when triggered, wave for two seconds then idle", "a greeting sequence on the trigger"]),
    ("session_reactions.ex", "acknowledge", [], ["acknowledge the speaker", "show you heard them", "a nod or a raised hand on the trigger"]),
    ("session_reactions.ex", "decline", [], ["decline the request", "wave it off or shake your head", "a refusal gesture on the trigger"]),
    ("session_reactions.ex", "take_seat", [], ["settle down and sit", "calm for two seconds, then sit", "take a seat once calm"]),
]


def _mix_env() -> dict:
    home = Path.home()
    env = dict(os.environ)
    extra = [home / "llvm-mingw" / "llvm-mingw-20260826-ucrt-x86_64" / "bin", home / "scoop" / "apps" / "make" / "current" / "bin",
             Path("C:/Program Files/Git/usr/bin"), home / "scoop" / "shims", home / "scoop" / "apps" / "elixir" / "current" / "bin",
             home / "scoop" / "apps" / "erlang" / "current" / "bin"]
    env["PATH"] = os.pathsep.join(str(p) for p in extra) + os.pathsep + env.get("PATH", "")
    env.update({"CC": "clang", "CXX": "clang++", "MAKE": str(home / "scoop" / "apps" / "make" / "current" / "bin" / "make.exe"),
                "VCINSTALLDIR": "", "MIX_ENV": "dev"})
    return env


def plan_guest(domain: str, todo: str, key: str) -> Path:
    """Plan once per (domain, todo); the guest is cached under work/plans."""
    PLAN_CACHE.mkdir(parents=True, exist_ok=True)
    out = PLAN_CACHE / f"{key}.sgd"
    if out.is_file():
        return out
    # CreateProcess resolves the executable against the parent's PATH, not the child's.
    mix = str(Path.home() / "scoop" / "apps" / "elixir" / "current" / "bin" / "mix.bat") if os.name == "nt" else "mix"
    cmd = [mix, "taskweft_acp.plan_sgd", "--domain", f"priv/domains/{domain}", "--out", str(out)]
    for t in todo.split(";"):
        cmd += ["--todo", t.strip()]
    r = subprocess.run(cmd, cwd=ACP, env=_mix_env(), capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or not out.is_file():
        raise RuntimeError(f"plan_sgd failed for {domain} {todo}: {r.stderr[-800:]}")
    return out


def lift(compiler: Path, guest: Path) -> str:
    r = subprocess.run([str(compiler), "to-dsl", str(guest)], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"lift refused {guest}: {r.stderr}")
    return r.stdout


def _args(seed: int, names: list[str]) -> dict:
    rng = random.Random(seed)
    vals = {}
    for n in names:
        if n == "msg":
            vals[n] = f"{rng.choice(WORDS)}_{rng.randint(1, 99)}"
        elif n == "dir":
            vals[n] = f"{rng.choice(WORDS)}_{rng.randint(1, 999)}"
        elif n == "text":
            # one token: the door splits a todo on spaces
            vals[n] = "_".join(rng.choice(WORDS) for _ in range(rng.randint(1, 3)))
    return vals


def _mutate_steps(text: str) -> str:
    """rank3 for a step program: drop the last RUN/WRITE/READ block and its write."""
    lines = text.splitlines()
    idx = [i for i, l in enumerate(lines) if re.match(r"^\w+ = (RUN|WRITE_FILE|READ_FILE)\(", l)]
    if len(idx) < 2:
        m = re.search(r'(TEXT|ARGS)="([^"]*)"', text)
        return text.replace(m.group(0), f'{m.group(1)}="{m.group(2)} x"', 1) if m else text
    last = lines[idx[-1]].split(" = ")[0]
    prev = lines[idx[-2]].split(" = ")[0]
    kept = [l for i, l in enumerate(lines) if i != idx[-1]]
    return "\n".join(l.replace(f"{last}.ENO", f"{prev}.ENO") for l in kept) + "\n"


def _mutate_react(text: str) -> str:
    """rank3 for a controller: halve the first hold, or swap a set's literal."""
    m = re.search(r"PT=(\d+\.\d+)", text)
    if m:
        return text.replace(m.group(0), f"PT={float(m.group(1)) * 2}", 1)
    m = re.search(r"IN1=(\d+)\)", text)
    if m:
        return text.replace(m.group(0), f"IN1={int(m.group(1)) + 1})", 1)
    return text.replace("IN1=TRUE", "IN1=FALSE", 1)


def _refuse(text: str) -> str:
    return re.sub(r"= (RUN|WRITE_FILE|READ_FILE|SEL|TON|R_TRIG)\(", "= EXEC(", text, count=1)


def plan_row(goal_index: int, seed: int, compiler: Path) -> ReactRow:
    domain, goal, arg_names, frames = GOALS[goal_index]
    vals = _args(seed, arg_names)
    # The planner runs once per goal with placeholder arguments; the seed's values are
    # substituted into the lifted text, which is the same diagram with other literals.
    canonical = {n: f"ARG_{n.upper()}" for n in arg_names}
    todo = goal.format(**canonical)
    key = re.sub(r"[^A-Za-z0-9_]+", "_", f"{domain[:-3]}_{todo}")
    guest = plan_guest(domain, todo, key)
    text = lift(compiler, guest)
    for n, v in vals.items():
        text = text.replace(canonical[n], v)
    is_react = "in trigger : BOOL" in text
    rank3 = _mutate_react(text) if is_react else _mutate_steps(text)
    if rank3 == text:
        raise ValueError(f"{key}: no mutation found")
    fid = seed % len(frames)
    intent = frames[fid].format(**vals)
    traces = [json.dumps({"dt": 0.125, "ticks": [{"trigger": i == 1} for i in range(24)]})] if is_react else []
    goal_name = goal.split(";")[-1].strip().split()[0]
    return ReactRow(f"plan_{domain[:-3]}_{goal_name}", seed, intent, text, rank3, _refuse(text), traces, None, fid)




if __name__ == "__main__":
    compiler = Path(sys.argv[1])
    for i in range(len(GOALS)):
        r = plan_row(i, 0, compiler)
        print(r.template_id, "|", r.intent)
        print(r.rank1)
