"""Детерминированный разбор нотации тренера (одна строка) в формат/раунды/повторы.
Без LLM. Кириллица/латиница, интервалы 2 / 1,5 / 1.5.
Гомоглиф-толерантный слой: латиница и кириллица, визуально совпадающие буквы,
покрываются едиными символьными классами (М/M, О/O, Е/E, х/x и т.д.)."""
from __future__ import annotations

import math
import re

A = "[аaАA]"
B = "[вbВB]"
E = "[еeЕEэЭ]"
K = "[кkКK]"
M = "[мmМM]"
N = "[нnНHh]"
O = "[оoОO]"
P = "[рpРPпП]"
C = "[сcСC]"
T = "[тtТT]"
U = "[уyУYuU]"
X = "[хxХX×*·]"
I = "[иiИI]"
L = "[лlЛ]"
R = "[рrРR]"
D = "[дdДD]"
S = "[сsСS]"
G = "[гgГG]"
DASH = "[-–—]"

_MOM = f"{M}{O}{M}"
_IV = r"[0-9.,zZзЗoOоОlLIi|sSбБgGтТbB]"
_DIGIT_FIX = str.maketrans({
    "z": "2", "Z": "2", "з": "3", "З": "3", "o": "0", "O": "0", "о": "0", "О": "0",
    "l": "1", "L": "1", "I": "1", "i": "1", "|": "1", "s": "5", "S": "5",
    "б": "6", "Б": "6", "g": "9", "G": "9", "т": "7", "Т": "7", "b": "8", "B": "8",
})
_EMOM = re.compile(
    rf"{E}\s*((?:{_IV})+)\s*{_MOM}|{E}{_MOM}",
    re.IGNORECASE,
)
_XNUM = re.compile(rf"{X}\s*(\d+)\s*(%?)")
_LEAD_X = re.compile(rf"^\s*(\d+)\s*{X}")
_AMRAP = re.compile(rf"{A}{M}{R}{A}{P}", re.IGNORECASE)
_PAREN_NX = re.compile(rf"\(\s*(\d+)\s*{X}\s*(\d+)\s*{M}{I}{N}", re.IGNORECASE)
_MIN = re.compile(rf"(\d+(?:[.,]\d+)?)\s*{M}{I}{N}", re.IGNORECASE)
_Y = "[ыy]"
_REST = re.compile(rf"(\d+(?:[.,]\d+)?)\s*{M}{I}{N}\w*\s*{O}{T}{D}{_Y}{X}", re.IGNORECASE)
_RND_VOWEL = "[аaАAоoОO]"
_SETS = re.compile(
    rf"(\d+)\s*(?:{S}{E}{T}|{R}{_RND_VOWEL}{U}{N}{D}|{K}{R}{U}{G}|rnd)\w*",
    re.IGNORECASE,
)
_CAP = re.compile(
    rf"{K}{E}{P}|{C}{A}{P}|{L}{I}{M}{I}{T}",
    re.IGNORECASE,
)
_WR = re.compile(rf"^(\d+(?:[.,]\d+)?)(?:\s*{X}\s*(\d+))?$")
_SCHEME_LEAD = re.compile(r"^\s*(?:[-•*–]\s*)?(?:\(?\s*[0-9①-⑩]{1,2}\s*\)?[\s.]+)?")
_SCHEME_BODY = re.compile(rf"\d+(?:\s*{DASH}\s*\d+)+")


def _f(s: str) -> float:
    return float(s.replace(",", "."))


def _digitize(s: str) -> str:
    return s.translate(_DIGIT_FIX)


def has_cap(text: str) -> bool:
    return bool(_CAP.search(text or ""))


def parse_weight_reps(s: str):
    s = (s or "").strip().lower().replace("кг", "").strip()
    if not s or set(s) <= {"_"}:
        return None
    m = _WR.match(s)
    if not m:
        return None
    w = _f(m.group(1))
    reps = int(m.group(2)) if m.group(2) else 1
    return (w, reps) if w > 0 and reps >= 1 else None


def parse_scheme(value) -> list[int] | None:
    """Схема лесенки к единому типу: список положительных int (>= 2 элементов).
    Принимает и список, и строку «21-15-9» (Claude-верификация присылает строкой).
    Всё, что не разбирается, -> None."""
    if isinstance(value, str):
        s = value.strip()
        if not _SCHEME_BODY.fullmatch(s):
            s = _SCHEME_LEAD.sub("", value).strip()
        if not _SCHEME_BODY.fullmatch(s):
            return None
        items = re.split(DASH, re.sub(r"\s", "", s))
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        return None
    nums: list[int] = []
    for x in items:
        if isinstance(x, bool):
            return None
        if isinstance(x, int):
            n = x
        elif isinstance(x, float) and math.isfinite(x) and x == int(x):
            n = int(x)
        elif isinstance(x, str) and x.strip().isdigit():
            n = int(x.strip())
        else:
            return None
        if n <= 0:
            return None
        nums.append(n)
    return nums if len(nums) >= 2 else None


def parse_notation(line: str) -> dict | None:
    t = line or ""
    out = {"format": None, "rounds": None, "reps": None,
           "work_min": None, "rest_min": None, "scheme": None}

    m = _EMOM.search(t)
    if m:
        interval = 1.0
        if m.group(1):
            try:
                v = _f(_digitize(m.group(1)))
            except ValueError:
                v = 0.0
            if v > 0:
                interval = v
        tail = t[m.end():]
        dur = _MIN.search(tail)
        if dur:
            out["rounds"] = max(1, round(_f(dur.group(1)) / interval)) if interval else 1
        else:
            lead = _LEAD_X.match(tail)
            xs = _XNUM.findall(tail)
            if lead:
                out["rounds"] = int(lead.group(1))
                for num, pct in xs:
                    if pct == "":
                        out["reps"] = int(num)
                        break
            elif xs:
                out["rounds"] = int(xs[0][0])
                if len(xs) > 1 and xs[1][1] == "":
                    out["reps"] = int(xs[1][0])
        out["format"] = "emom_strength"
        return out

    if _AMRAP.search(t):
        pm = _PAREN_NX.search(t)
        if pm:
            out["rounds"] = int(pm.group(1))
            out["work_min"] = _f(pm.group(2))
        else:
            xs = _XNUM.findall(t)
            if xs:
                out["rounds"] = int(xs[0][0])
            mins = _MIN.findall(t)
            if mins:
                out["work_min"] = _f(mins[0])
        rest = _REST.search(t)
        if rest:
            out["rest_min"] = _f(rest.group(1))
        out["format"] = "amrap_interval" if (out["rounds"] or 1) > 1 else "amrap"
        if out["format"] == "amrap":
            out["rounds"] = out["rounds"] or 1
        return out

    if "%" not in t:
        s = _SCHEME_LEAD.sub("", t).strip()
        if _SCHEME_BODY.fullmatch(s):
            nums = [int(x) for x in re.split(DASH, re.sub(r"\s", "", s))]
            if len(nums) >= 2:
                out["format"] = "ladder"
                out["scheme"] = nums
                out["rounds"] = len(nums)
                return out

    sm = _SETS.search(t)
    if sm:
        out["rounds"] = int(sm.group(1))
        out["format"] = None
        return out

    return None
