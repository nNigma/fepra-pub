"""Текст доски WOD -> блоки -> аннотация раундов / шаблон результатов. Детерминированно."""
from __future__ import annotations

import re

from .. import ontology
from . import benchmarks
from . import wod_notation as N

_WARMUP = re.compile(r"актив|размин|warm", re.IGNORECASE)
_HEADER_KW = re.compile(r"\b(та|wod|amrap|табата|tabata|death\s*by|метком|meton)\b", re.IGNORECASE)
_BULLET = re.compile(r"^\s*[-•*–]\s*")
_LEAD_NUM = re.compile(r"^\s*\d+\s*[).:]?\s*")
_MOVE_QTY = re.compile(r"^\s*(?:[-•*–]\s*)?\d+\s*(?:(?:мин|кал|сек|м)(?=[\s.]|$))?\.?\s*")

_SEC_WARMUP = re.compile(r"размин|разогрев|актив|суставн|мобильн|общ|warm", re.IGNORECASE)
_SEC_METCON = re.compile(r"комплекс|метком|меткон|кондиц|\bwod\b|metcon", re.IGNORECASE)
_SEC_STRENGTH = re.compile(r"\bсил|strength|\bта\b|тяж\w*\s*атлет", re.IGNORECASE)
_REST_LINE = re.compile(r"отд[ыий]х|\brest\b", re.IGNORECASE)


def _section(line: str):
    """Строка-заголовок секции -> (kind, title) | None. Заголовки короткие (<=4 слов)."""
    s = _LEAD_NUM.sub("", line.strip()).strip()
    if not s or len(s.split()) > 4:
        return None
    if _SEC_WARMUP.search(s):
        return "warmup", s
    if _SEC_METCON.search(s):
        return "metcon", s
    if _SEC_STRENGTH.search(s):
        return "strength", s
    return None


def _strength_block(mv: dict, notation: dict) -> dict:
    return {"header": "ТА", "format": "emom_strength",
            "rounds": notation.get("rounds"), "reps": notation.get("reps"),
            "work_min": None, "rest_min": None, "has_cap": False,
            "movements": [mv], "benchmark": None, "scheme": None}


def _clean_move(line: str) -> str:
    s = _BULLET.sub("", line).strip()
    s = _MOVE_QTY.sub("", s).strip()
    return s


def _is_header(line: str) -> bool:
    return bool(_HEADER_KW.search(line) or N.parse_notation(line))


def _header_label(line: str) -> str | None:
    m = _HEADER_KW.search(line)
    if m:
        return m.group(1).upper()
    return None


def _format_for(header_line: str, notation: dict | None) -> str:
    if notation and notation.get("format"):
        return notation["format"]
    low = (header_line or "").lower()
    if "amrap" in low:
        return "amrap"
    if "табата" in low or "tabata" in low:
        return "tabata"
    if "death" in low:
        return "death_by"
    return "for_time"


def _movement(name: str, aliases):
    name = name.strip()
    found = ontology.find(name, aliases)
    canon = ontology.resolve(name, aliases) or (found[-1] if found else None)
    # все каноны строки (напр. «50 ДП или 75 ОП» -> double_under + single_under)
    canons = list(dict.fromkeys(([canon] if canon else []) + found))
    return {"name": name, "canon": canon, "canons": canons,
            "weighted": ontology.is_weighted(canon)}


def parse_program(text: str, aliases: dict | None = None, sex: str = "m") -> list[dict]:
    blocks: list[dict] = []
    cur = None
    warmup = False
    section = None            # 'warmup' | 'strength' | 'metcon' | None
    section_title = None
    section_idx = 0
    strength_notation = None  # EMOM ждёт движение (нотация раньше движения)
    strength_move = None      # движение ждёт EMOM (движение раньше нотации)

    def close():
        nonlocal cur
        if cur and cur["movements"]:
            blocks.append(cur)
        cur = None

    def open_block(header, fmt, **kw):
        nonlocal cur
        close()
        cur = {"header": header, "format": fmt, "rounds": None, "reps": None,
               "work_min": None, "rest_min": None, "has_cap": False,
               "movements": [], "benchmark": None, "scheme": None}
        cur.update(kw)

    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue

        sec = _section(line)
        if sec:
            close()
            strength_notation = strength_move = None
            section, section_title = sec
            section_idx = 0
            warmup = (section == "warmup")
            continue

        if warmup:
            continue

        bench = benchmarks.expand(_LEAD_NUM.sub("", _BULLET.sub("", line)).strip(), sex)
        if bench:
            close()
            strength_notation = strength_move = None
            blocks.extend(bench)
            continue

        notation = N.parse_notation(line)

        if notation and notation.get("format") == "emom_strength":
            close()
            if strength_move is not None:
                blocks.append(_strength_block(strength_move, notation))
                strength_move = None
            else:
                strength_notation = notation
            continue

        if notation and notation.get("format") in ("amrap", "amrap_interval"):
            open_block("AMRAP", notation["format"], rounds=notation["rounds"],
                       reps=notation["reps"], work_min=notation["work_min"],
                       rest_min=notation["rest_min"], has_cap=N.has_cap(line))
            continue

        if notation and notation.get("scheme"):
            open_block(section_title or "Блок", "ladder",
                       scheme=notation["scheme"], rounds=notation["rounds"])
            continue

        if notation and notation.get("rounds"):
            section_idx += 1
            hdr = f"{section_title} {section_idx}" if section == "metcon" else "WOD"
            open_block(hdr, "for_time", rounds=notation["rounds"], has_cap=N.has_cap(line))
            continue

        if _REST_LINE.search(line):
            continue

        name = _clean_move(line)
        if not name:
            continue
        mv = _movement(name, aliases)

        if cur is not None:
            cur["movements"].append(mv)
        elif section == "strength" or strength_notation is not None:
            if strength_notation is not None:
                blocks.append(_strength_block(mv, strength_notation))
                strength_notation = None
            else:
                strength_move = mv

    close()
    return blocks


def movements_of(blocks):
    """Блоки -> (canon: список канон-движений без повторов, unknown: имена без канона)."""
    canon, unknown = [], []
    for b in blocks or []:
        for m in b.get("movements", []):
            cs = m.get("canons")
            if cs is None:
                cs = [m["canon"]] if m.get("canon") else []
            if cs:
                for c in cs:
                    if c and c not in canon:
                        canon.append(c)
            else:
                nm = (m.get("name") or "").strip()
                if nm and nm not in unknown:
                    unknown.append(nm)
    return canon, unknown


def _plural(n: int, one: str, few: str, many: str) -> str:
    m = abs(n) % 100
    if 11 <= m <= 14:
        return many
    d = m % 10
    if d == 1:
        return one
    if 2 <= d <= 4:
        return few
    return many


def annotate(text: str, aliases: dict | None = None) -> str:
    """Тот же разбор, но возвращает исходный текст с дописанными скобками
    «(N раундов[ по M повторений])» у строк-нотаций. Для подтверждения доски."""
    out = []
    for raw in (text or "").splitlines():
        n = N.parse_notation(raw)
        if n and n.get("scheme"):
            scheme = n["scheme"]
            word = _plural(len(scheme), "раунд", "раунда", "раундов")
            note = f" ({len(scheme)} {word}: {', '.join(str(x) for x in scheme)})"
            out.append(raw.rstrip() + note)
        elif n and n.get("rounds") and n["rounds"] >= 2:
            r = n["rounds"]
            rw = _plural(r, "раунд", "раунда", "раундов")
            if n.get("reps"):
                pw = _plural(n["reps"], "повторение", "повторения", "повторений")
                note = f" ({r} {rw} по {n['reps']} {pw})"
            else:
                note = f" ({r} {rw})"
            out.append(raw.rstrip() + note)
        else:
            out.append(raw)
    return "\n".join(out)


_WEIGHT_HINT = re.compile(r"\d\s*кг|\bкг\b", re.IGNORECASE)


def _weighted_names(block) -> list[str]:
    return [m["name"] for m in block["movements"]
            if m.get("weighted") or _WEIGHT_HINT.search(m.get("name") or "")]


def _render_block(b) -> list[str]:
    fmt = b.get("format")
    title = b.get("header") or (b["movements"][0]["name"] if b.get("movements") else "Блок")
    lines: list[str] = []

    if fmt in ("strength", "emom_strength"):
        name = b["movements"][0]["name"] if b.get("movements") else title
        rounds = b.get("rounds") or 1
        lines.append(f"{name}:")
        lines += [f"  раунд {i} (вес×повторы): ___" for i in range(1, rounds + 1)]
        return lines

    if fmt == "ladder" and b.get("scheme"):
        scheme = b["scheme"]
        title = b.get("header") or "Блок"
        lines.append(f"{title} ({'-'.join(str(x) for x in scheme)}):")
        for m in b.get("movements", []):
            lines.append(f"{m['name']}:")
            cat = ontology.category(m.get("canon"))
            for i, reps in enumerate(scheme, 1):
                if m.get("weighted"):
                    lines.append(f"  раунд {i} - {reps} повт, вес: ___")
                elif cat == "cardio":
                    lines.append(f"  раунд {i} - {reps} ккал: ___")
                else:
                    lines.append(f"  раунд {i} - {reps} повт: ___")
        lines.append("  время (мм:сс): ___")
        return lines

    if fmt in ("for_time", "chipper", "rounds_for_time", "ladder"):
        lines.append(f"{title}:")
        lines += [f"  вес «{w}»: ___" for w in _weighted_names(b)]
        lines.append("  время (мм:сс): ___")
        if b.get("has_cap"):
            lines.append("  не уложился в кэп — сделано повторов: ___")
        return lines

    if fmt == "amrap_interval":
        rounds = b.get("rounds") or 1
        wm = b.get("work_min")
        head = f"{title} ({rounds}×{int(wm) if wm and wm == int(wm) else wm}мин):" if wm else f"{title}:"
        lines.append(head)
        for i in range(1, rounds + 1):
            lines.append(f"  круги, амрап {i}: ___")
            lines += [f"  вес «{w}»: ___" for w in _weighted_names(b)]
        return lines

    if fmt == "amrap":
        lines.append(f"{title}:")
        lines += [f"  вес «{w}»: ___" for w in _weighted_names(b)]
        lines.append("  кругов: ___")
        lines.append("  повторов (неполный круг): ___")
        return lines

    if fmt == "death_by":
        lines.append(f"{title}:")
        lines.append("  дошёл до минуты: ___")
        lines.append("  повторов в незавершённой: ___")
        return lines

    lines.append(f"{title}:")
    lines.append("  результат: ___")
    return lines


def render_template(blocks) -> str | None:
    out: list[str] = []
    for b in blocks or []:
        if not isinstance(b, dict):
            continue
        out += _render_block(b)
    return "\n".join(out) if out else None
