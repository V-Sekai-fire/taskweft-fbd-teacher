"""Intents and the diagrams they mean, constructed so the labels are true by construction.

Each template turns a seed into an intent (what a person would type), the reference
PLCopen FBD that does it (rank1), a mutant that parses and lowers but does the wrong
thing (rank3), and a mutant the compiler must refuse (rank5). The effect check for a
template is a function of the scratch directory and the runner's captured output, so
the writer can assert that rank1 passes it and rank3 does not on every row.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

WORDS = ["alder", "birch", "cedar", "dune", "ember", "fjord", "glade", "heath", "islet",
         "juniper", "kelp", "larch", "moss", "nettle", "orchid", "pine", "quartz", "reed",
         "sedge", "thistle", "umber", "vale", "willow", "yarrow", "zephyr"]


def _name(rng: random.Random) -> str:
    return f"{rng.choice(WORDS)}_{rng.randint(1, 999)}"


def _text(rng: random.Random) -> str:
    return " ".join(rng.choice(WORDS) for _ in range(rng.randint(1, 4)))


def _lit(s: str) -> str:
    # A PLCopen STRING literal. The grammar forbids quotes, angle brackets and
    # ampersands inside, so the templates never produce them.
    if re.search(r"['<>&]", s):
        raise ValueError(f"literal carries a forbidden character: {s!r}")
    return f"'{s}'"


def _in(local_id: int, literal: str) -> str:
    return f'      <inVariable localId="{local_id}"><expression>{literal}</expression></inVariable>\n'


def _pin(formal: str, ref: int, src: str = "OUT") -> str:
    return (f'          <variable formalParameter="{formal}"><connectionPointIn>'
            f'<connection refLocalId="{ref}" formalParameter="{src}"/></connectionPointIn></variable>\n')


def _block(local_id: int, type_name: str, pins: str) -> str:
    return (f'      <block localId="{local_id}" typeName="{type_name}">\n'
            f'        <inputVariables>\n{pins}        </inputVariables>\n'
            f'        <outputVariables>\n          <variable formalParameter="ENO"/>\n'
            f'        </outputVariables>\n      </block>\n')


def _pou(name: str, body: str, out_var: str = "done", last_block: int | None = None) -> str:
    out = ""
    if last_block is not None:
        out = (f'      <outVariable localId="{last_block + 1}"><connectionPointIn>'
               f'<connection refLocalId="{last_block}" formalParameter="ENO"/></connectionPointIn>'
               f'<expression>{out_var}</expression></outVariable>\n')
    return (f'<pou name="{name}" pouType="program">\n'
            f'  <interface>\n    <localVars>\n'
            f'      <variable name="{out_var}"><type><BOOL/></type></variable>\n'
            f'    </localVars>\n  </interface>\n'
            f'  <body>\n    <FBD>\n{body}{out}    </FBD>\n  </body>\n</pou>\n')


@dataclass
class Row:
    template_id: str
    seed: int
    intent: str
    rank1: str
    rank3: str
    rank5: str
    expect: Callable[[Path, str], bool]


def t_write(seed: int) -> Row:
    rng = random.Random(seed)
    path, text = f"{_name(rng)}.txt", _text(rng)
    wrong = _text(rng) + " x"
    body = _in(1, _lit(path)) + _in(2, _lit(text)) + _block(3, "WRITE_FILE", _pin("PATH", 1) + _pin("TEXT", 2))
    body3 = _in(1, _lit(path)) + _in(2, _lit(wrong)) + _block(3, "WRITE_FILE", _pin("PATH", 1) + _pin("TEXT", 2))
    # rank5: the TEXT pin is not wired, which the lowering refuses by pin name.
    body5 = _in(1, _lit(path)) + _block(3, "WRITE_FILE", _pin("PATH", 1))
    return Row("write", seed, f"write {text} to {path}",
               _pou("write_file", body, last_block=3), _pou("write_file", body3, last_block=3),
               _pou("write_file", body5, last_block=3),
               lambda d, out: (d / path).is_file() and (d / path).read_text(encoding="utf-8") == text)


def t_write_then_read(seed: int) -> Row:
    rng = random.Random(seed)
    path, text = f"{_name(rng)}.txt", _text(rng)
    other = f"{_name(rng)}_other.txt"
    body = (_in(1, _lit(path)) + _in(2, _lit(text)) + _block(3, "WRITE_FILE", _pin("PATH", 1) + _pin("TEXT", 2))
            + _in(4, _lit(path)) + _block(5, "READ_FILE", _pin("EN", 3, "ENO") + _pin("PATH", 4)))
    # rank3 reads a file nobody wrote: the second step exits 1, so the run stops short.
    body3 = (_in(1, _lit(path)) + _in(2, _lit(text)) + _block(3, "WRITE_FILE", _pin("PATH", 1) + _pin("TEXT", 2))
             + _in(4, _lit(other)) + _block(5, "READ_FILE", _pin("EN", 3, "ENO") + _pin("PATH", 4)))
    # rank5: an EN/ENO cycle, which the ordering refuses.
    body5 = (_in(1, _lit(path)) + _in(2, _lit(text))
             + _block(3, "WRITE_FILE", _pin("EN", 5, "ENO") + _pin("PATH", 1) + _pin("TEXT", 2))
             + _in(4, _lit(path)) + _block(5, "READ_FILE", _pin("EN", 3, "ENO") + _pin("PATH", 4)))
    return Row("write_then_read", seed, f"write {text} to {path}, then check that {path} exists",
               _pou("write_then_read", body, last_block=5), _pou("write_then_read", body3, last_block=5),
               _pou("write_then_read", body5, last_block=5),
               lambda d, out: (d / path).is_file() and "READ_FILE#5 exit 0" in out)


def t_run_print(seed: int) -> Row:
    rng = random.Random(seed)
    n = rng.randint(1000, 999999)
    wrong = n + 1
    body = _in(1, _lit("python")) + _in(2, _lit(f"-c print({n})")) + _block(3, "RUN", _pin("CMD", 1) + _pin("ARGS", 2))
    body3 = _in(1, _lit("python")) + _in(2, _lit(f"-c print({wrong})")) + _block(3, "RUN", _pin("CMD", 1) + _pin("ARGS", 2))
    # rank5: a block the subset does not name.
    body5 = _in(1, _lit("python")) + _in(2, _lit(f"-c print({n})")) + _block(3, "EXEC", _pin("CMD", 1) + _pin("ARGS", 2))
    return Row("run_print", seed, f"run python and print {n}",
               _pou("run_print", body, last_block=3), _pou("run_print", body3, last_block=3),
               _pou("run_print", body5, last_block=3),
               lambda d, out: f"\n{n}\n" in "\n" + out + "\n")


def t_write_then_count(seed: int) -> Row:
    rng = random.Random(seed)
    k = rng.randint(1, 4)
    names = [f"{_name(rng)}_{i}.txt" for i in range(k)]
    body, i = "", 1
    prev = None
    for name in names:
        pins = _pin("PATH", i) + _pin("TEXT", i + 1)
        if prev is not None:
            pins = _pin("EN", prev, "ENO") + pins
        body += _in(i, _lit(name)) + _in(i + 1, _lit("x")) + _block(i + 2, "WRITE_FILE", pins)
        prev = i + 2
        i += 3
    count_pins = _pin("EN", prev, "ENO") + _pin("CMD", i) + _pin("ARGS", i + 1)
    # No single quotes: the STRING literal forbids them, and the runner passes the
    # argument without a shell, so double quotes reach Python as themselves.
    expr = 'print(len(__import__("os").listdir(".")))'
    body_ok = body + _in(i, _lit("python")) + _in(i + 1, _lit(f"-c {expr}")) + _block(i + 2, "RUN", count_pins)
    last = i + 2
    # rank3 skips one file, so the count is short by one.
    body3 = ""
    j, prev3 = 1, None
    for name in names[:-1] if k > 1 else names:
        pins = _pin("PATH", j) + _pin("TEXT", j + 1)
        if prev3 is not None:
            pins = _pin("EN", prev3, "ENO") + pins
        body3 += _in(j, _lit(name if k > 1 else name + "_x")) + _in(j + 1, _lit("x")) + _block(j + 2, "WRITE_FILE", pins)
        prev3 = j + 2
        j += 3
    body3 += _in(j, _lit("python")) + _in(j + 1, _lit(f"-c {expr}")) + _block(j + 2, "RUN", _pin("EN", prev3, "ENO") + _pin("CMD", j) + _pin("ARGS", j + 1))
    last3 = j + 2
    # rank5: the counting block names a type the subset does not have.
    body5 = body_ok.replace('typeName="RUN"', 'typeName="EXEC"', 1)
    return Row("write_then_count", seed, f"create {k} file(s) named {', '.join(names)} and count the files in the directory",
               _pou("write_then_count", body_ok, last_block=last), _pou("write_then_count", body3, last_block=last3),
               _pou("write_then_count", body5, last_block=last),
               lambda d, out: f"\n{k}\n" in "\n" + out + "\n" and all((d / n).is_file() for n in names))


TEMPLATES = {
    "write": t_write,
    "write_then_read": t_write_then_read,
    "run_print": t_run_print,
    "write_then_count": t_write_then_count,
}


def row_for(template_id: str, seed: int) -> Row:
    return TEMPLATES[template_id](seed)
