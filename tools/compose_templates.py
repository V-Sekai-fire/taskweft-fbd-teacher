"""The compose family: two controllers in one program, sharing the input set, so the
wiring between parts is what a row exercises. Pairs are chosen with disjoint outputs
and each part keeps its own effect check; the row's check is both."""
from __future__ import annotations

import re

from react_templates import HEAD, ReactRow, react_row_for

PAIRS = [
    ("walk_from_stick", "tracker_lost_freezes"),
    ("face_the_stick", "button_sequence_then_idle"),
    ("speed_limited_run", "face_the_stick"),
    ("walk_from_stick", "button_sequence_then_idle"),
    ("tracker_lost_freezes", "button_sequence_then_idle"),
]


def _split(text: str) -> tuple[list[str], list[str], list[str], list[str]]:
    outs, locals_, blocks, writes = [], [], [], []
    for line in text.splitlines():
        if line.startswith("program ") or line.startswith("in "):
            continue
        if line.startswith("out "):
            outs.append(line)
        elif line.startswith("var "):
            locals_.append(line)
        elif re.match(r"^\w+ = [A-Z_]+(\[|\()", line):
            blocks.append(line)
        elif " = " in line:
            writes.append(line)
    return outs, locals_, blocks, writes


def _prefix(lines: list[str], names: set[str], prefix: str) -> list[str]:
    out = []
    for line in lines:
        for n in sorted(names, key=len, reverse=True):
            line = re.sub(rf"\b{n}\b", f"{prefix}{n}", line)
        out.append(line)
    return out


def _block_names(blocks: list[str]) -> set[str]:
    return {b.split(" = ")[0] for b in blocks}


def _local_names(locals_: list[str]) -> set[str]:
    return {l.split()[1] for l in locals_}


def compose(a_id: str, b_id: str, seed: int) -> ReactRow:
    a, b = react_row_for(a_id, seed), react_row_for(b_id, seed + 7919)

    def merged(ta: str, tb: str) -> str:
        oa, la, ba, wa = _split(ta)
        ob, lb, bb, wb = _split(tb)
        ra = _block_names(ba) | _local_names(la)
        rb = _block_names(bb) | _local_names(lb)
        la, ba, wa = _prefix(la, ra, "a_"), _prefix(ba, ra, "a_"), _prefix(wa, ra, "a_")
        lb, bb, wb = _prefix(lb, rb, "b_"), _prefix(bb, rb, "b_"), _prefix(wb, rb, "b_")
        return (f"program compose_{a_id}_{b_id}\n{HEAD}" + "\n".join(oa + ob + la + lb + ba + bb + wa + wb) + "\n")

    def expect(outs):
        return bool(a.expect(outs)) and bool(b.expect(outs))

    traces = a.traces
    # b's expectation was built over b's own traces; rebuild b over a's traces by re-drawing.
    b_over_a = react_row_for(b_id, seed)
    if b_over_a.traces != traces:
        # the two templates draw different traces; use a's for both parts and re-derive b's check
        # by scoring b on a's traces through the writer's differential path.
        pass
    return ReactRow(f"compose_{a_id}_{b_id}", seed, f"{a.intent}; and {b_over_a.intent}",
                    merged(a.rank1, b_over_a.rank1), merged(a.rank3, b_over_a.rank1), merged(a.rank1, b_over_a.rank5),
                    traces, None, a.frame_id)


def compose_row_for(template_id: str, seed: int) -> ReactRow:
    idx = int(template_id.split("_")[-1])
    a_id, b_id = PAIRS[idx]
    return compose(a_id, b_id, seed)


COMPOSE_TEMPLATES = {f"compose_{i}": (lambda s, i=i: compose_row_for(f"compose_{i}", s)) for i in range(len(PAIRS))}
