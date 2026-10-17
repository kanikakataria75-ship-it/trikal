"""A small, safe screening language over the KASAUTI panel (no eval).

    roce > 20% and pe < 25 and sector = 'Information Technology'
    score >= 70 and not (pledge_pct > 0) and playbook in ('banks', 'nbfc_hfc')
    quality > 80 or name contains 'bank'

Rules: percent signs divide by 100 (metrics such as ROCE are stored as ratios), text compares case-insensitively, and a field that has no value
for a company is UNKNOWN: three-valued logic means an unknown comparison never passes, and `not` of an unknown stays unknown, so a company is
never selected on data it does not have."""

from __future__ import annotations

import re
from dataclasses import dataclass

TOKEN = re.compile(r"\s*(?:(?P<num>\d+(?:\.\d+)?)(?P<pct>%?)|(?P<str>'[^']*'|\"[^\"]*\")|(?P<op>>=|<=|==|!=|=|>|<|\(|\)|,)|(?P<id>[A-Za-z_][A-Za-z0-9_]*))")
KEYWORDS = {"and", "or", "not", "in", "contains"}


class ScreenError(ValueError):
    pass


@dataclass
class Tok:
    kind: str       # num | str | op | id | kw
    val: object
    pos: int


def tokenize(text: str) -> list[Tok]:
    out, i = [], 0
    while i < len(text):
        if text[i].isspace():
            i += 1
            continue
        m = TOKEN.match(text, i)
        if not m or m.end() == i:
            raise ScreenError(f"unexpected character {text[i]!r} at position {i + 1}")
        if m.group("num") is not None:
            v = float(m.group("num"))
            out.append(Tok("num", v / 100 if m.group("pct") else v, m.start()))
        elif m.group("str") is not None:
            out.append(Tok("str", m.group("str")[1:-1], m.start()))
        elif m.group("op") is not None:
            out.append(Tok("op", m.group("op"), m.start()))
        else:
            w = m.group("id")
            out.append(Tok("kw" if w.lower() in KEYWORDS else "id", w.lower() if w.lower() in KEYWORDS else w, m.start()))
        i = m.end()
    return out


class Parser:
    def __init__(self, text: str, fields: set[str]) -> None:
        self.t, self.i, self.fields, self.text = tokenize(text), 0, {f.lower() for f in fields}, text

    def peek(self) -> Tok | None:
        return self.t[self.i] if self.i < len(self.t) else None

    def take(self) -> Tok:
        tok = self.peek()
        if tok is None:
            raise ScreenError("the condition ends too early")
        self.i += 1
        return tok

    def accept(self, kind: str, val: object = None) -> bool:
        tok = self.peek()
        if tok and tok.kind == kind and (val is None or tok.val == val):
            self.i += 1
            return True
        return False

    def parse(self):
        if not self.t:
            return ("true",)
        e = self.or_()
        if self.peek() is not None:
            raise ScreenError(f"unexpected {self.peek().val!r} at position {self.peek().pos + 1}")
        return e

    def or_(self):
        e = self.and_()
        while self.accept("kw", "or"):
            e = ("or", e, self.and_())
        return e

    def and_(self):
        e = self.not_()
        while self.accept("kw", "and"):
            e = ("and", e, self.not_())
        return e

    def not_(self):
        if self.accept("kw", "not"):
            return ("not", self.not_())
        return self.cmp()

    def operand(self):
        tok = self.take()
        if tok.kind in ("num", "str"):
            return ("lit", tok.val)
        if tok.kind == "id":
            if tok.val.lower() not in self.fields:
                raise ScreenError(f"unknown field {tok.val!r}; fields: {', '.join(sorted(self.fields))}")
            return ("field", tok.val.lower())
        raise ScreenError(f"expected a field or a value at position {tok.pos + 1}")

    def cmp(self):
        if self.accept("op", "("):
            e = self.or_()
            if not self.accept("op", ")"):
                raise ScreenError("missing )")
            return e
        left = self.operand()
        tok = self.peek()
        if tok is None:
            raise ScreenError("a comparison is incomplete (for example: roce > 20%)")
        if tok.kind == "kw" and tok.val == "in":
            self.take()
            if not self.accept("op", "("):
                raise ScreenError("in needs a list: in ('a', 'b')")
            vals = [self.operand()]
            while self.accept("op", ","):
                vals.append(self.operand())
            if not self.accept("op", ")"):
                raise ScreenError("missing ) after the list")
            return ("in", left, vals)
        if tok.kind == "kw" and tok.val == "contains":
            self.take()
            return ("contains", left, self.operand())
        if tok.kind == "op" and tok.val in (">", ">=", "<", "<=", "==", "=", "!="):
            self.take()
            return ("cmp", "==" if tok.val == "=" else tok.val, left, self.operand())
        raise ScreenError(f"expected a comparison after {left[1]!r} at position {tok.pos + 1}")


def _val(node, row):
    return node[1] if node[0] == "lit" else row.get(node[1])


def _norm(v):
    return v.lower() if isinstance(v, str) else v


def evaluate(node, row: dict):
    """True / False / None (unknown)."""
    k = node[0]
    if k == "true":
        return True
    if k == "and":
        a, b = evaluate(node[1], row), evaluate(node[2], row)
        return False if (a is False or b is False) else (None if (a is None or b is None) else True)
    if k == "or":
        a, b = evaluate(node[1], row), evaluate(node[2], row)
        return True if (a is True or b is True) else (None if (a is None or b is None) else False)
    if k == "not":
        a = evaluate(node[1], row)
        return None if a is None else not a
    if k == "cmp":
        a, b = _norm(_val(node[2], row)), _norm(_val(node[3], row))
        if a is None or b is None:
            return None
        if isinstance(a, str) != isinstance(b, str):
            raise ScreenError("a text field cannot be compared with a number")
        op = node[1]
        if isinstance(a, str) and op not in ("==", "!="):
            raise ScreenError("text can only be compared with = or !=")
        return {"==": a == b, "!=": a != b, ">": a > b, ">=": a >= b, "<": a < b, "<=": a <= b}[op]
    if k == "in":
        a = _norm(_val(node[1], row))
        if a is None:
            return None
        return a in [_norm(_val(v, row)) for v in node[2]]
    if k == "contains":
        a, b = _norm(_val(node[1], row)), _norm(_val(node[2], row))
        if a is None or b is None:
            return None
        return str(b) in str(a)
    raise ScreenError(f"bad node {k}")


def compile_screen(text: str, fields: set[str]):
    return Parser(text, fields).parse()


def run(text: str, rows: list[dict], fields: set[str]) -> list[dict]:
    tree = compile_screen(text, fields)
    return [r for r in rows if evaluate(tree, r) is True]
