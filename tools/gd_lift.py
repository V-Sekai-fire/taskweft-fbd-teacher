"""The lift from a udon2godot method back to a diagram: the straight-line subset of
SafeGDScript a scan controller can carry, refused by reason beyond it.

A method `func Name(p: T, ...) -> R:` whose body is local assignments, arithmetic,
comparison and boolean expressions, `clampi/clampf/mini/minf/maxi/maxf`, an `if`/`else`
whose branches assign values, and a `return`, lifts to a scan program: one `in` per
parameter, `out ret` for the return, one block per operation. Everything else is
refused with a reason the census counts: loops, member access, calls outside the block
set, arrays, strings, unsupported types. The compiler checks and simulates the text;
the runtime is what the diagram is measured against.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

TYPES = {"int": "INT", "float": "REAL", "bool": "BOOL"}
BIN = {"+": "ADD", "-": "SUB", "*": "MUL", "/": "DIV", "%": "MOD",
       "==": "EQ", "!=": "NE", "<": "LT", ">": "GT", "<=": "LE", ">=": "GE", "and": "AND", "or": "OR"}
CALLS = {"clampi": "LIMIT", "clampf": "LIMIT", "mini": "MIN", "minf": "MIN", "maxi": "MAX", "maxf": "MAX",
         "min": "MIN", "max": "MAX", "clamp": "LIMIT"}
PREC = {"or": 1, "and": 2, "==": 4, "!=": 4, "<": 4, ">": 4, "<=": 4, ">=": 4, "+": 5, "-": 5, "*": 6, "/": 6, "%": 6}


class Refused(Exception):
    """A method the lift does not carry, with the reason the census counts."""


TOKEN = re.compile(r"\s*(?:(\d+\.\d*(?:e[-+]?\d+)?|\d+)|([A-Za-z_]\w*)|(==|!=|<=|>=|\+=|-=|\*=|/=|[-+*/%<>=(),:.\[\]])|(\"[^\"]*\"))")


def tokenize(line: str) -> list[str]:
    out, pos = [], 0
    while pos < len(line):
        m = TOKEN.match(line, pos)
        if not m or m.end() == pos:
            if line[pos:].strip() == "":
                break
            raise Refused(f"token: {line[pos:pos + 10]!r}")
        out.append(next(g for g in m.groups() if g is not None))
        pos = m.end()
    return out


# ---- expressions -------------------------------------------------------------

@dataclass
class Lit:
    value: str
    type: str


@dataclass
class Var:
    name: str


@dataclass
class Op:
    kind: str
    args: list


@dataclass
class Cond:
    test: object
    then: object
    other: object


class ExprParser:
    def __init__(self, toks: list[str]):
        self.t = toks
        self.i = 0

    def peek(self) -> str | None:
        return self.t[self.i] if self.i < len(self.t) else None

    def take(self) -> str:
        v = self.t[self.i]
        self.i += 1
        return v

    def parse(self):
        e = self.ternary()
        if self.peek() is not None:
            raise Refused(f"expression: trailing {self.peek()!r}")
        return e

    def ternary(self):
        e = self.binary(1)
        if self.peek() == "if":
            self.take()
            c = self.binary(1)
            if self.take() != "else":
                raise Refused("expression: ternary without else")
            o = self.ternary()
            return Cond(c, e, o)
        return e

    def binary(self, minp: int):
        left = self.unary()
        while self.peek() in PREC and PREC[self.peek()] >= minp:
            op = self.take()
            right = self.binary(PREC[op] + 1)
            left = Op(BIN[op], [left, right])
        return left

    def unary(self):
        p = self.peek()
        if p == "not":
            self.take()
            return Op("NOT", [self.unary()])
        if p == "-":
            self.take()
            inner = self.unary()
            if isinstance(inner, Lit):
                return Lit("-" + inner.value, inner.type)
            return Op("SUB", [Lit("0", "INT"), inner])
        return self.primary()

    def primary(self):
        p = self.take() if self.peek() is not None else None
        if p is None:
            raise Refused("expression: ended early")
        if p == "(":
            e = self.ternary()
            if self.take() != ")":
                raise Refused("expression: unbalanced parenthesis")
            return e
        if re.fullmatch(r"\d+\.\d*(?:e[-+]?\d+)?", p):
            return Lit(p if not p.endswith(".") else p + "0", "REAL")
        if re.fullmatch(r"\d+", p):
            return Lit(p, "INT")
        if p in ("true", "false"):
            return Lit(p.upper(), "BOOL")
        if p.startswith('"'):
            raise Refused("string literal")
        if re.fullmatch(r"[A-Za-z_]\w*", p):
            if self.peek() == "(":
                self.take()
                args = []
                while self.peek() != ")":
                    args.append(self.ternary())
                    if self.peek() == ",":
                        self.take()
                self.take()
                if p in ("float", "int"):
                    raise Refused(f"call: {p}() conversion")
                if p in ("absf", "absi", "abs"):
                    raise Refused("call: abs (no ABS block)")
                if p not in CALLS:
                    raise Refused(f"call: {p}")
                return Op(CALLS[p], args)
            if self.peek() == ".":
                raise Refused(f"member access: {p}.{self.t[self.i + 1] if self.i + 1 < len(self.t) else ''}")
            if self.peek() == "[":
                raise Refused("array index")
            return Var(p)
        raise Refused(f"expression: {p!r}")


# ---- the method --------------------------------------------------------------

@dataclass
class Method:
    name: str
    params: list[tuple[str, str]]
    ret: str | None
    body: list[str]


FUNC_RE = re.compile(r"^func (\w+)\((.*)\)(?: -> (\w+))?:\s*$")


def methods_of(text: str) -> list[Method]:
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        m = FUNC_RE.match(lines[i])
        if not m:
            i += 1
            continue
        params = []
        for p in [x.strip() for x in m.group(2).split(",") if x.strip()]:
            if ":" not in p:
                params.append((p.split("=")[0].strip(), "?"))
            else:
                n, t = p.split(":", 1)
                params.append((n.strip(), t.split("=")[0].strip()))
        body = []
        i += 1
        while i < len(lines) and (lines[i].startswith("\t") or lines[i].strip() == ""):
            if lines[i].strip():
                body.append(lines[i])
            i += 1
        out.append(Method(m.group(1), params, m.group(3), body))
    return out


@dataclass
class Lifter:
    method: Method
    lines: list[str] = field(default_factory=list)
    types: dict[str, str] = field(default_factory=dict)
    values: dict[str, object] = field(default_factory=dict)
    counter: int = 0
    used: dict[str, int] = field(default_factory=dict)

    def fresh(self) -> str:
        self.counter += 1
        return f"b{self.counter}"

    def type_of(self, e) -> str:
        if isinstance(e, Wire):
            return e.type
        if isinstance(e, Lit):
            return e.type
        if isinstance(e, Var):
            if e.name not in self.types:
                raise Refused(f"unknown name: {e.name}")
            return self.types[e.name]
        if isinstance(e, Cond):
            return self.type_of(e.then)
        if e.kind in ("EQ", "NE", "LT", "GT", "LE", "GE", "AND", "OR", "NOT"):
            return "BOOL"
        ts = [self.type_of(a) for a in e.args]
        return "REAL" if "REAL" in ts else ts[0]

    def operand(self, e) -> str:
        """The text of an input: a literal, an input name, or a wire from a block."""
        if isinstance(e, Wire):
            return e.text
        if isinstance(e, Lit):
            return e.value
        if isinstance(e, Var):
            if e.name in self.values:
                return self.operand(self.values[e.name])
            if e.name in self.types:
                return e.name
            raise Refused(f"unknown name: {e.name}")
        return self.emit(e)

    def emit(self, e) -> str:
        if isinstance(e, Cond):
            b = self.fresh()
            self.lines.append(f"{b} = SEL(G={self.operand(e.test)}, IN0={self.operand(e.other)}, IN1={self.operand(e.then)})")
            return f"{b}.OUT"
        if e.kind == "NOT":
            b = self.fresh()
            self.lines.append(f"{b} = NOT(IN={self.operand(e.args[0])})")
            return f"{b}.OUT"
        if e.kind == "LIMIT":
            if len(e.args) != 3:
                raise Refused("clamp arity")
            b = self.fresh()
            self.lines.append(f"{b} = LIMIT(MN={self.operand(e.args[1])}, IN={self.operand(e.args[0])}, MX={self.operand(e.args[2])})")
            return f"{b}.OUT"
        ins = [self.operand(a) for a in e.args]
        if e.kind in ("ADD", "MUL", "MIN", "MAX", "AND", "OR") and len(ins) > 2:
            pass
        elif len(ins) != 2:
            raise Refused(f"{e.kind} arity {len(ins)}")
        b = self.fresh()
        pins = ", ".join(f"IN{i + 1}={v}" for i, v in enumerate(ins))
        self.lines.append(f"{b} = {e.kind}({pins})")
        return f"{b}.OUT"

    def parse_expr(self, text: str):
        return ExprParser(tokenize(text)).parse()

    def assign(self, name: str, e) -> None:
        t = self.type_of(e)
        if name in self.types and self.types[name] != t and not (self.types[name] == "REAL" and t == "INT"):
            raise Refused(f"assignment changes the type of {name}")
        self.types.setdefault(name, t)
        # a computed local is emitted once and read by wire, so two uses share one block
        self.values[name] = Wire(self.emit(e), self.types[name]) if isinstance(e, (Op, Cond)) else e

    def block(self, lines: list[str], depth: int) -> str | None:
        """Lifts statements at one indentation depth; returns the returned wire, if any."""
        i = 0
        while i < len(lines):
            raw = lines[i]
            ind = len(raw) - len(raw.lstrip("\t"))
            if ind != depth:
                raise Refused("indentation")
            s = raw.strip()
            i += 1
            if s.startswith("#"):
                continue
            if s.startswith(("for ", "while ", "match ")):
                raise Refused(s.split()[0] + " loop" if not s.startswith("match") else "match")
            if s.startswith(("var ", "const ")):
                m = re.match(r"(?:var|const) (\w+)(?::\s*(\w+))?\s*=\s*(.+)$", s)
                if not m:
                    raise Refused("var without a value")
                if m.group(2) and m.group(2) not in TYPES:
                    raise Refused(f"type: {m.group(2)}")
                e = self.parse_expr(m.group(3))
                self.assign(m.group(1), e)
                if m.group(2):
                    self.types[m.group(1)] = TYPES[m.group(2)]
                continue
            if s.startswith("return"):
                rest = s[6:].strip()
                if not rest:
                    raise Refused("return without a value")
                if i < len(lines):
                    raise Refused("statements after return")
                return self.operand(self.parse_expr(rest))
            if s.startswith("if "):
                cond = self.parse_expr(s[3:].rstrip(":"))
                then_lines, else_lines = [], []
                while i < len(lines) and (len(lines[i]) - len(lines[i].lstrip("\t"))) > depth:
                    then_lines.append(lines[i])
                    i += 1
                if i < len(lines) and lines[i].strip() == "else:":
                    i += 1
                    while i < len(lines) and (len(lines[i]) - len(lines[i].lstrip("\t"))) > depth:
                        else_lines.append(lines[i])
                        i += 1
                elif i < len(lines) and lines[i].strip().startswith("elif "):
                    raise Refused("elif")
                self.branch(cond, then_lines, else_lines, depth + 1)
                continue
            m = re.match(r"(\w+)\s*(\+=|-=|\*=|/=|=)\s*(.+)$", s)
            if m:
                name, op, rhs = m.groups()
                if "." in name or "[" in name:
                    raise Refused("member assignment")
                e = self.parse_expr(rhs)
                if op != "=":
                    if name not in self.types:
                        raise Refused(f"unknown name: {name}")
                    e = Op(BIN[op[0]], [Var(name) if name not in self.values else self.values[name], e])
                self.assign(name, e)
                continue
            if re.match(r"\w+\(.*\)$", s) or "." in s:
                raise Refused(f"call statement: {s.split('(')[0]}")
            raise Refused(f"statement: {s[:20]}")
        return None

    def branch(self, cond, then_lines: list[str], else_lines: list[str], depth: int) -> None:
        """Both branches must only assign; each assigned name becomes a SEL."""
        cond_wire = self.operand(cond)
        before = dict(self.values)
        for arm in (then_lines, else_lines):
            for raw in arm:
                s = raw.strip()
                if s.startswith("return"):
                    raise Refused("return inside a branch")
                if not re.match(r"(\w+)\s*(\+=|-=|\*=|/=|=)\s*(.+)$", s) or s.startswith(("if ", "var ")):
                    raise Refused("branch is not an assignment")
        then_l = Lifter(self.method, self.lines, dict(self.types), dict(before), self.counter, self.used)
        then_l.block(then_lines, depth)
        self.counter = then_l.counter
        else_l = Lifter(self.method, self.lines, dict(self.types), dict(before), self.counter, self.used)
        if else_lines:
            else_l.block(else_lines, depth)
        self.counter = else_l.counter
        names = sorted(set(then_l.values) | set(else_l.values))
        for n in names:
            a = then_l.values.get(n, before.get(n))
            b = else_l.values.get(n, before.get(n))
            if a is None or b is None:
                raise Refused(f"{n} is assigned in one branch and undefined before the if")
            if a is b:
                continue
            self.types.setdefault(n, then_l.types.get(n) or else_l.types.get(n))
            # operands first, so blocks they emit sit above the SEL that reads them
            in0, in1 = self.operand(b), self.operand(a)
            sel = self.fresh()
            self.lines.append(f"{sel} = SEL(G={cond_wire}, IN0={in0}, IN1={in1})")
            self.values[n] = Wire(f"{sel}.OUT", self.types[n])


@dataclass
class Wire:
    """A value a block already computes; stands in for the expression behind a SEL."""
    text: str
    type: str


def lift_method(m: Method, program: str | None = None) -> str:
    """The text form of a scan controller equal to the method, or Refused."""
    if m.ret is None or m.ret == "void":
        raise Refused("void method")
    if m.ret not in TYPES:
        raise Refused(f"return type: {m.ret}")
    if not m.params:
        raise Refused("no parameters")
    lifter = Lifter(m)
    for n, t in m.params:
        if t not in TYPES:
            raise Refused(f"parameter type: {t}")
        lifter.types[n] = TYPES[t]
    ret = lifter.block(m.body, 1)
    if ret is None:
        raise Refused("no return")
    if not lifter.lines and not re.match(r"[A-Za-z_]\w*$", ret):
        raise Refused("returns a constant")
    head = [f"program {program or m.name}"] + [f"in {n} : {TYPES[t]}" for n, t in m.params] + [f"out ret : {TYPES[m.ret]}"]
    if re.match(r"[A-Za-z_]\w*$", ret) and ret in lifter.types and ret not in [n for n, _ in m.params]:
        raise Refused("returns a local never assigned")
    if re.match(r"[A-Za-z_]\w*$", ret) and ret in [n for n, _ in m.params]:
        lifter.lines.append(f"{lifter.fresh()} = MOVE(IN={ret})")
        ret = f"b{lifter.counter}.OUT"
    return "\n".join(head + lifter.lines + [f"ret = {ret}"]) + "\n"


def lift_all(text: str) -> tuple[dict[str, str], dict[str, str]]:
    """Every method of a translated class: name -> text, and name -> refusal reason."""
    lifted, refused = {}, {}
    for m in methods_of(text):
        if m.name.startswith("udon_") or m.name.startswith("_"):
            refused[m.name] = "runtime hook"
            continue
        try:
            lifted[m.name] = lift_method(m)
        except Refused as e:
            refused[m.name] = str(e)
    return lifted, refused


if __name__ == "__main__":
    import sys
    from pathlib import Path
    for path in sys.argv[1:]:
        lifted, refused = lift_all(Path(path).read_text(encoding="utf-8"))
        print(f"{Path(path).name}: {len(lifted)} lifted, {len(refused)} refused")
        for n, t in lifted.items():
            print(t)
        for n, why in refused.items():
            print(f"  refused {n}: {why}")
