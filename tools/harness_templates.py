"""The harness family: every block kind the compiler enumerates (`gen-scan`), with a
seeded literal, an intent in words, and the compiler's own traces.

Each of the 69 harness controllers carries an intent family that names the block's
behaviour; a seed perturbs the literal constants (a timer's preset, a limit, a
multiplier) and picks the frame. rank3 changes one literal or swaps the two inputs
of a non-commutative block; rank5 reads an input the program never declared. The
effect check is differential: the writer scores rank1's outputs on the traces as
the reference, and a candidate matches when its outputs equal them tick for tick.
"""
from __future__ import annotations

import random
import re
import subprocess
import zlib
from pathlib import Path

from react_templates import ReactRow

HERE = Path(__file__).resolve().parent.parent
GEN_DIR = HERE / "work" / "gen_h"

INTENTS: dict[str, list[str]] = {
    "and": ["true when every input is on", "only when all the buttons are held", "the AND of the inputs"],
    "or": ["true when any input is on", "when at least one button is pressed", "the OR of the inputs"],
    "xor": ["true when an odd number of inputs is on", "the exclusive or of the inputs", "on when exactly one of two is pressed"],
    "not": ["the opposite of the button", "invert the input", "off while the button is held"],
    "move": ["pass the input through unchanged", "copy the input to the output", "mirror the value"],
    "r_trig": ["a single pulse when the button goes down", "fire once on the rising edge", "the press, not the hold"],
    "f_trig": ["a single pulse when the button is released", "fire once on the falling edge", "the release, not the press"],
    "ton": ["true once the input has been on for {pt} ms", "delay the on-signal by {pt} milliseconds", "on after {pt} ms of holding"],
    "tof": ["stay on for {pt} ms after the input drops", "delay the off-signal by {pt} milliseconds", "keep the flag {pt} ms past release"],
    "tp": ["a pulse of {pt} ms on each press", "hold the flag for {pt} milliseconds after a rising edge", "a {pt} ms one-shot"],
    "sr": ["latch on with the first button, off with the second, set wins", "set-dominant latch", "remember the press until reset"],
    "rs": ["latch on with the first button, off with the second, reset wins", "reset-dominant latch", "the reset overrides the set"],
    "sel": ["pick the second value when the switch is on, else the first", "choose between two values by a flag", "a two-way selector"],
    "mux": ["pick one of the inputs by index", "select by the integer k", "a multiplexer over the inputs"],
    "limit": ["clamp the value between {lo} and {hi}", "keep the value inside [{lo}, {hi}]", "never below {lo} nor above {hi}"],
    "min": ["the smaller of the inputs", "the minimum", "whichever input is lowest"],
    "max": ["the larger of the inputs", "the maximum", "whichever input is highest"],
    "add": ["the sum of the inputs", "add the inputs together", "the total"],
    "sub": ["the first input minus the second", "the difference", "subtract the second from the first"],
    "mul": ["the product of the inputs", "multiply the inputs", "scale one input by the other"],
    "div": ["the first input divided by the second", "the quotient", "divide the first by the second"],
    "mod": ["the remainder of the first divided by the second", "the modulo", "what is left after dividing"],
    "eq": ["true when the two inputs are equal", "compare for equality", "the same value"],
    "ne": ["true when the two inputs differ", "compare for inequality", "not the same value"],
    "lt": ["true when the first is less than the second", "the first below the second", "strictly less"],
    "gt": ["true when the first is greater than the second", "the first above the second", "strictly greater"],
    "le": ["true when the first is at most the second", "less or equal", "not above"],
    "ge": ["true when the first is at least the second", "greater or equal", "not below"],
    "chain": ["count the presses", "a hold that a press starts and a timer ends", "a small chain of blocks"],
}


def ensure_generated(compiler: Path) -> None:
    if not GEN_DIR.is_dir() or not any(GEN_DIR.glob("*.fbd")):
        GEN_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.run([str(compiler), "gen-scan", str(GEN_DIR)], check=True, capture_output=True)


def harness_names() -> list[str]:
    return sorted(p.stem for p in GEN_DIR.glob("*.fbd"))


def _kind(name: str) -> str:
    for k in sorted(INTENTS, key=len, reverse=True):
        if name == k or name.startswith(k + "_"):
            return k
    return "chain"


def _perturb(text: str, rng: random.Random) -> tuple[str, dict]:
    params = {}
    def time_sub(m):
        ms = rng.choice([125, 250, 375, 500, 625, 750])
        params["pt"] = ms
        return f"T#{ms}ms"
    text = re.sub(r"T#\d+ms", time_sub, text)
    def real_sub(m):
        v = round(rng.uniform(0.25, 3.0), 2)
        return f"{v}"
    text = re.sub(r"(?<==)-?\d+\.\d+", real_sub, text)
    def int_sub(m):
        v = rng.randint(-3, 9)
        return str(v)
    text = re.sub(r"(?<==)-?\d+(?![.\d])", int_sub, text)
    lo = re.search(r"MN=(-?[\d.]+)", text)
    hi = re.search(r"MX=(-?[\d.]+)", text)
    if lo and hi:
        a, b = float(lo.group(1)), float(hi.group(1))
        if a > b:
            text = text.replace(f"MN={lo.group(1)}", f"MN={hi.group(1)}").replace(f"MX={hi.group(1)}", f"MX={lo.group(1)}")
            a, b = b, a
        params["lo"], params["hi"] = a, b
    return text, params


COMMUTATIVE = ("AND", "OR", "XOR", "ADD", "MUL", "MIN", "MAX", "EQ", "NE")
SWAP_INPUTS = {"a": "c", "b": "d", "n": "m", "m": "n", "x": "y", "y": "x", "k": "n"}


TYPE_SWAP = {
    "AND": "OR", "OR": "AND", "XOR": "OR", "NOT": "MOVE",
    "R_TRIG": "F_TRIG", "F_TRIG": "R_TRIG", "TON": "TOF", "TOF": "TON", "TP": "TON",
    "SR": "RS", "RS": "SR", "MIN": "MAX", "MAX": "MIN", "ADD": "SUB", "SUB": "ADD",
    "MUL": "ADD", "DIV": "SUB", "MOD": "SUB", "EQ": "NE", "NE": "EQ",
    "LT": "GE", "GT": "LE", "LE": "GT", "GE": "LT",
}


def _mutate(text: str, rng: random.Random) -> str:
    """rank3: swap the block for its opposite (AND for OR, TON for TOF, LT for GE), which
    differs on every trace that exercises it; else change a literal; else read a
    different input. A swap of the inputs of a commutative block changes nothing."""
    first = re.search(r"^(\w+) = ([A-Z_]+)\((.*)$", text, re.M)
    if first and first.group(2) in TYPE_SWAP:
        kind = first.group(2)
        nary = "IN3=" in first.group(3)
        # a block wired at arity three or more swaps within the n-ary family only
        swap = {"ADD": "MUL", "MUL": "ADD", "AND": "OR", "OR": "AND", "XOR": "OR", "MIN": "MAX", "MAX": "MIN"}.get(kind) if nary else TYPE_SWAP[kind]
        if swap:
            s, e = first.span(2)
            return text[:s] + swap + text[e:]
    t = re.search(r"T#(\d+)ms", text)
    if t:
        return text.replace(t.group(0), f"T#{int(t.group(1)) * 2}ms", 1)
    r = re.search(r"(?<==)(-?\d+\.\d+)", text)
    if r:
        return text[:r.start()] + f"{float(r.group(1)) + 1.0}" + text[r.end():]
    i = re.search(r"(?<==)(-?\d+)(?![.\d])", text)
    if i:
        # by span: a bare replace of "1" would hit the "1" inside "IN1="
        return text[:i.start()] + str(int(i.group(1)) + 1) + text[i.end():]
    m = re.search(r"= ([A-Z_]+)\((.*?)IN1=(\w+(?:\.\w+)?), IN2=(\w+(?:\.\w+)?)", text)
    if m and m.group(1) not in COMMUTATIVE and m.group(3) != m.group(4):
        old = f"IN1={m.group(3)}, IN2={m.group(4)}"
        return text.replace(old, f"IN1={m.group(4)}, IN2={m.group(3)}", 1)
    for pin in ("IN=", "IN1=", "IN2=", "CLK=", "S1=", "S=", "G=", "K="):
        mm = re.search(rf"{pin}([abcdnmxyk])\b", text)
        if mm and mm.group(1) in SWAP_INPUTS:
            return text.replace(f"{pin}{mm.group(1)}", f"{pin}{SWAP_INPUTS[mm.group(1)]}", 1)
    return text


def _refuse(text: str) -> str:
    """rank5: an input the program never declared."""
    return re.sub(r"=(a|n|x)\b", "=zz", text, count=1)


def harness_row(name: str, seed: int) -> ReactRow:
    # a stable hash: Python's str hash is salted per process and would unseed the corpus
    rng = random.Random(seed * 1000 + zlib.crc32(name.encode("utf-8")) % 997)
    base = (GEN_DIR / f"{name}.fbd").read_text(encoding="utf-8")
    text, params = _perturb(base, rng)
    kind = _kind(name)
    frames = INTENTS[kind]
    fid = seed % len(frames)
    intent = frames[fid].format(**{"pt": params.get("pt", 300), "lo": params.get("lo", 0), "hi": params.get("hi", 1)})
    traces = sorted(GEN_DIR.glob("trace_*.json"))
    picked = [traces[(seed + i * 5) % len(traces)] for i in range(3)]
    rank3 = _mutate(text, rng)
    if rank3 == text:
        raise ValueError(f"{name}: no mutation found")
    return ReactRow(f"harness_{name}", seed, intent, text, rank3, _refuse(text),
                    [p.read_text(encoding="utf-8") for p in picked], None, fid)
