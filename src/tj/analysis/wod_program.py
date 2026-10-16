"""Текст доски WOD -> блоки -> аннотация раундов / шаблон результатов. Детерминированно."""
from __future__ import annotations

import re

from .. import ontology
from . import benchmarks
from . import wod_notation as N

_WARMUP = re.compile(r"актив|размин|warm", re.IGNORECASE)
_HEADER_KW = re.compile(r"\b(та|wo{1,2}d|amrap|табата|tabata|death\s*by|метком|meton)\b", re.IGNORECASE)
_BULLET = re.compile(r"^\s*[-•*–]\s*")
_LEAD_NUM = re.compile(r"^\s*[\d①-⑩]+\s*[).:]?\s*")
_MOVE_QTY = re.compile(r"^\s*(?:[-•*–]\s*)?\d+\s*(?:(?:мин|кал|сек|м)(?=[\s.]|$))?\.?\s*")
_WOD = r"(?<![a-zа-яё0-9])wo{1,2}d(?=$|[^a-zа-яё]|n[º°o]?\s*\d|№)"

_SEC_WARMUP = re.compile(r"размин|разогрев|актив|суставн|мобильн|общ|warm", re.IGNORECASE)
_SEC_METCON = re.compile(r"комплекс|метком|меткон|кондиц|metcon|" + _WOD, re.IGNORECASE)
_SEC_STRENGTH = re.compile(r"\bсил|strength|\bт[ая]\b|тяж\w*\s*атлет", re.IGNORECASE)
_REST_LINE = re.compile(r"отд[ыий]х|\brest\b", re.IGNORECASE)
# «40 сек работа 20 отдых», «40 сек работы / 20 сек отдыха», «40 on 20 off», «40/20 сек» -> интервальный блок
_SEC_UNIT = r"(?:сек\w*|с\b|sec\w*|s\b)"
_INTERVAL = re.compile(
    rf"(\d{{1,3}})\s*{_SEC_UNIT}?\s*(?:работ\w*|on\b|work\w*)[\s,/и]*(\d{{1,3}})\s*{_SEC_UNIT}?\s*(?:отдых\w*|off\b|rest\w*)"
    rf"|(\d{{1,3}})\s*/\s*(\d{{1,3}})\s*{_SEC_UNIT}",
    re.IGNORECASE)
# «Фронтальный присед 5×5», «5x5 присед», «- Присед 5х5 80%» (x латинская, × и русская х)
_XS = r"[x×хХX]"
_STRENGTH_LINE = re.compile(
    rf"^\s*(?:[-•*–]\s*)?(?P<name>[^\d\s].*?)\s+(?P<n>\d{{1,2}})\s*{_XS}\s*(?P<r>\d{{1,3}})"
    rf"(?:\s*(?:@|на|at)?\s*\d{{1,3}}\s*%)?\s*$", re.IGNORECASE)
_STRENGTH_LINE_REV = re.compile(
    rf"^\s*(?:[-•*–]\s*)?(?P<n>\d{{1,2}})\s*{_XS}\s*(?P<r>\d{{1,3}})\s+(?P<name>[^\d\s].*?)\s*$",
    re.IGNORECASE)
# «Wod ×2», «Круг x3», «Раунд×4» -> заголовок повторяемого списка станций
_REPEAT_HEADER = re.compile(
    rf"^\s*(?P<name>wod|вод|воd|комплекс|раунд\w*|круг\w*|round\w*|set|сет\w*)\s*[#№]?\s*\d*\s*{_XS}\s*(?P<n>\d{{1,2}})\s*:?\s*$",
    re.IGNORECASE)
_WOD_LINE = re.compile(_WOD, re.IGNORECASE)
_ROUNDS_WORD = re.compile(r"(\d{1,2})\s*(?:раунд\w*|круг\w*|round\w*)", re.IGNORECASE)
# строка станции: начинается с числа («15 кал байк», «100 м толкание саней»)
_NUM_LINE = re.compile(r"^\s*(?:[-•*–]\s*)?\d")
_STATION_WEIGHT = re.compile(r"гир|гантел|штанг|кластер|выпад|thruster|трастер|kettlebell|dumbbell", re.IGNORECASE)
# кардио: ккал, метры ИЛИ время — единицу выбирает атлет (в шаблоне только значение по умолчанию)
_STATION_CAL = re.compile(r"лыж|\bski|байк|bike|гребл|\brow|assault|эйр|air\s*bike", re.IGNORECASE)
_STATION_RUN = re.compile(r"челнок|\bбег\w*|\brun\w*|\bshuttle|скакалк\w*\s*бег", re.IGNORECASE)
# сани: вес (кг) И дистанция (м)
# сюда же переноски и волокуши: снаряд с весом везут/несут на дистанцию
_STATION_SLED = re.compile(
    r"\bсан\w*|\bсанк\w*|sled|волокуш\w*|\bdrag\b|\bcarr(?:y|ies)\b|\byoke\b|"
    r"переноск\w*|перенос\w*|прогулк\w*\s+фермера|farmer", re.IGNORECASE)
_STATIC = re.compile(r"планк|plank|стойк[аи]\s+на|hold|вис\b", re.IGNORECASE)
# «Найти ПМ в кластере» / «до максимума в приседе» -> отдельное силовое поле (макс)
_FINDMAX = re.compile(
    r"(?:найти\s+)?(?:1\s*)?пм\s+в\s+(.+?)(?:\s+за\s+.+)?$"
    r"|(?:работа\s+)?до\s+макс\w*\s+(?:в\s+)?(.+?)(?:\s+за\s+.+)?$", re.IGNORECASE)


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
    rounds = notation.get("rounds")
    if rounds and rounds > 8 and not notation.get("reps"):
        # «EMOM x20» с одним упражнением: это минуты работы, а не 20 силовых подходов — одно поле
        return {"header": "EMOM", "format": "stations", "rounds": None, "reps": None, "emom_total": rounds,
                "work_min": None, "rest_min": None, "has_cap": False,
                "movements": [mv], "benchmark": None, "scheme": None}
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


def _interval_spec(line: str):
    """Строка с «работа/отдых» -> (label, work_sec, rest_sec) | None. label — текст вокруг
    интервалов без скобок («Wod#2 (40 сек работа 20 отдых)» -> «Wod#2»)."""
    m = _INTERVAL.search(line)
    if not m:
        return None
    work = int(m.group(1) or m.group(3))
    rest = int(m.group(2) or m.group(4))
    if not (5 <= work <= 600 and 0 <= rest <= 600):
        return None
    label = re.sub(r"\(.*?\)", " ", line[:m.start()] + " " + line[m.end():])
    label = re.sub(r"[\s:,;.\-–]+$", "", label.strip()).strip(" :")
    return (label or "Интервалы"), work, rest


def _strength_line(line: str, aliases):
    """«Фронтальный присед 5×5» -> силовой блок (подходы×повторы). Только штанга
    (barbell): «Wall ball 4x15» и подобное силовым блоком не становится."""
    m = _STRENGTH_LINE.match(line) or _STRENGTH_LINE_REV.match(line)
    if not m:
        return None
    sets, reps = int(m.group("n")), int(m.group("r"))
    if not (1 <= sets <= 12 and 1 <= reps <= 30):
        return None
    mv = _movement(m.group("name").strip(" -•*–:"), aliases)
    if not mv.get("canon") or ontology.category(mv["canon"]) != "barbell":
        return None
    mv["name"] = m.group("name").strip(" -•*–:")
    return {"header": mv["name"], "format": "strength", "rounds": sets, "reps": reps,
            "work_min": None, "rest_min": None, "has_cap": False,
            "movements": [mv], "benchmark": None, "scheme": None}


def parse_program(text: str, aliases: dict | None = None, sex: str = "m") -> list[dict]:
    blocks = _parse_blocks(text, aliases, sex, skip_warmup=True)
    if not blocks and (text or "").strip():
        alt = _parse_blocks(text, aliases, sex, skip_warmup=False)
        if alt:
            return alt
    return blocks


def _parse_blocks(text: str, aliases: dict | None, sex: str, skip_warmup: bool) -> list[dict]:
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
            q = cur.pop("_q", True)
            if (cur["format"] == "for_time" and not q and len(cur["movements"]) >= 2
                    and not cur.get("scheme") and not cur.get("rounds")):
                # список станций без количеств («Бег / Лыжи / Гребля»): поле на каждую станцию + общее время
                cur["format"] = "stations"
                cur["once"] = True
            blocks.append(cur)
        cur = None

    def open_block(header, fmt, **kw):
        nonlocal cur
        close()
        cur = {"header": header, "format": fmt, "rounds": None, "reps": None,
               "work_min": None, "rest_min": None, "has_cap": False,
               "movements": [], "benchmark": None, "scheme": None}
        cur.update(kw)

    all_lines = (text or "").splitlines()

    def list_follows(i: int) -> bool:
        """После строки i идёт список (>=2 подряд строк до пустой строки или нового заголовка)?"""
        n = 0
        for nxt in all_lines[i + 1:]:
            if not nxt.strip():
                if n:
                    break
                continue
            if N.parse_notation(nxt) or _section(nxt) or _interval_spec(nxt) or _is_header(nxt):
                break                  # дальше начался другой блок
            n += 1
        return n >= 2

    for li, raw in enumerate(all_lines):
        line = raw.strip()
        if not line:
            continue

        rh = _REPEAT_HEADER.match(line)
        if rh and not (warmup and skip_warmup):
            close()
            strength_notation = strength_move = None
            section, section_title = "metcon", line
            open_block(line, "stations", rounds=int(rh.group("n")))
            continue

        iv = _interval_spec(line)
        if iv and not (warmup and skip_warmup):
            label, work, rest = iv
            close()
            strength_notation = strength_move = None
            section, section_title = "metcon", label
            open_block(label, "stations", work_sec=work, rest_sec=rest)
            continue

        sec = _section(line)
        if sec:
            close()
            strength_notation = strength_move = None
            section, section_title = sec
            section_idx = 0
            warmup = (section == "warmup")
            if section == "metcon" and _WOD_LINE.search(line):
                if N.parse_notation(line):
                    pass               # «WOD 21-15-9», «WOD 2 раунда»: дальше разберёт нотация строки
                else:
                    # «WOD», «WOD:», «WOD: For time»: заголовок всегда открывает блок,
                    # движения под ним — его станции; нотация ниже заменит блок на свой формат
                    rest = _WOD_LINE.sub(" ", line)
                    rest_n = N.parse_notation(rest)
                    if rest_n and rest_n.get("scheme"):          # «Wod 21-15-9» в одной строке
                        open_block(line.strip(" :"), "ladder", scheme=rest_n["scheme"], rounds=rest_n["rounds"])
                    else:
                        rm = _ROUNDS_WORD.search(line)
                        open_block(line.strip(" :"), "for_time", rounds=int(rm.group(1)) if rm else None,
                                   has_cap=N.has_cap(line))
                    continue
            else:
                continue

        if warmup and skip_warmup:
            continue

        bench = benchmarks.expand(_LEAD_NUM.sub("", _BULLET.sub("", line)).strip(), sex)
        if bench:
            close()
            strength_notation = strength_move = None
            blocks.extend(bench)
            continue

        sl = _strength_line(line, aliases)
        if sl:
            close()
            strength_notation = strength_move = None
            blocks.append(sl)
            continue

        notation = N.parse_notation(line)

        if notation and notation.get("format") == "emom_strength" and strength_move is None and list_follows(li):
            # EMOM со списком упражнений («E12MOM x2» + строки «15 кал байк»…) — станции, не силовой
            close()
            strength_notation = None
            section, section_title = "metcon", line
            # «EMOM x20»: 20 интервалов, упражнения идут по очереди (строка = своя минута)
            open_block(line, "stations", emom_total=notation.get("rounds"))
            continue

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

        fm = _FINDMAX.match(name)
        if fm:
            phrase = (fm.group(1) or fm.group(2) or "").strip()
            mvx = _movement(phrase, aliases)
            if mvx.get("canon") and mvx.get("weighted"):
                mvx["name"] = ontology.base_ru(mvx["canon"]) or mvx["name"]
                blocks.append({"header": "Найти ПМ", "format": "strength", "rounds": 1,
                               "reps": None, "work_min": None, "rest_min": None,
                               "has_cap": False, "movements": [mvx],
                               "benchmark": None, "scheme": None})
                continue

        mv = _movement(name, aliases)
        if cur is not None and cur.get("format") == "stations" and not cur.get("work_sec"):
            # список станций («15 кал байк»): в подписи поля оставляем норматив из доски
            mv["name"] = _BULLET.sub("", line).strip() or mv["name"]

        if cur is not None:
            if re.search(r"\d", line):
                cur["_q"] = True
            else:
                cur.setdefault("_q", False)
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


_NOTE_RE = re.compile(r"(?:\s*\(\s*\d+\s+раунд\w*[^)]*\))+\s*$")


def annotate(text: str, aliases: dict | None = None) -> str:
    """Тот же разбор, но возвращает исходный текст с дописанными скобками
    «(N раундов[ по M повторений])» у строк-нотаций. Идемпотентна: прежний
    «(… раунд…)»-хвост срезается перед добавлением, повторный прогон не копит."""
    out = []
    for raw in (text or "").splitlines():
        base = _NOTE_RE.sub("", raw.rstrip())
        n = N.parse_notation(base)
        if n and n.get("scheme"):
            scheme = n["scheme"]
            word = _plural(len(scheme), "раунд", "раунда", "раундов")
            note = f" ({len(scheme)} {word}: {', '.join(str(x) for x in scheme)})"
            out.append(base + note)
        elif n and n.get("rounds") and n["rounds"] >= 2:
            r = n["rounds"]
            rw = _plural(r, "раунд", "раунда", "раундов")
            if n.get("reps"):
                pw = _plural(n["reps"], "повторение", "повторения", "повторений")
                note = f" ({r} {rw} по {n['reps']} {pw})"
            else:
                note = f" ({r} {rw})"
            out.append(base + note)
        else:
            out.append(base)
    return "\n".join(out)


_WEIGHT_HINT = re.compile(r"\d\s*кг|\bкг\b", re.IGNORECASE)
_GYM_XN = re.compile(r"[x×хX]\s*(\d+)")


def _weighted_names(block) -> list[str]:
    return [m["name"] for m in block["movements"]
            if m.get("weighted") or _WEIGHT_HINT.search(m.get("name") or "")]


def _gym_unit(canon: str | None) -> str:
    """Существительное-«штука» для гимнастики: выходы у мясли-апов, иначе повторы."""
    return "выходов" if canon in ("bar_muscle_up", "muscle_up") else "повторов"


def _gym_per_set(m: dict) -> int | None:
    """«Bar Muscle-Up ×5» -> 5 повторов за подход (тогда спросим число кругов)."""
    mm = _GYM_XN.search(m.get("name") or "")
    return int(mm.group(1)) if mm else None


def _is_gym_skill(b) -> bool:
    """Блок без веса/времени/кэпа целиком из гимнастики -> скилл, меряем в штуках."""
    movs = b.get("movements") or []
    return bool(movs) and all(
        ontology.category(m.get("canon")) == "gymnastics" for m in movs)


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

    if fmt == "stations":
        work, rest = b.get("work_sec"), b.get("rest_sec")
        head = f"{title} ({work}/{rest} сек):" if work else f"{title}:"
        lines.append(head)
        total = b.get("emom_total")
        movs = b.get("movements", [])
        if not total and not b.get("once"):
            lines.append("  кругов: ___")
        for m in movs:
            if total and movs:      # EMOM: интервалов поровну на каждую строку списка
                each = max(1, round(total / len(movs)))
                lines.append(f"{m['name']} ({each} {_plural(each, 'раунд', 'раунда', 'раундов')}):")
            else:
                lines.append(f"{m['name']}:")
            nm = m.get("name") or ""
            if _STATIC.search(nm):
                lines.append("  удержание, сек: ___")
            elif _STATION_SLED.search(nm):
                lines.append("  вес и дистанция: ___")
            elif _STATION_CAL.search(nm) or ontology.category(m.get("canon")) == "cardio":
                lines.append("  кардио, ккал: ___")
            elif _STATION_RUN.search(nm):
                lines.append("  кардио, м: ___")
            elif m.get("weighted") or _STATION_WEIGHT.search(nm):
                lines.append("  результат (вес×повторы): ___")
            else:
                lines.append("  повторы, вес по желанию: ___")
        if b.get("once"):
            lines.append("время (мм:сс): ___")
        return lines

    scheme = N.parse_scheme(b.get("scheme")) if fmt == "ladder" else None
    if scheme:
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

    if _is_gym_skill(b):
        movs = b["movements"]
        lines.append(f"{title}:")
        single = len(movs) == 1
        for m in movs:
            unit = _gym_unit(m.get("canon"))
            per = _gym_per_set(m)
            head = "" if single else f"{m['name']} — "
            if per:
                lines.append(f"  {head}кругов (по {per} {unit}): ___")
            else:
                lines.append(f"  {head}выполнено {unit}: ___")
        return lines

    lines.append(f"{title}:")
    lines.append("  результат: ___")
    return lines


def render_block(block) -> list[str]:
    """Строки шаблона одного блока (публичная обёртка: форма результата строится из них)."""
    return _render_block(block)


def render_template(blocks) -> str | None:
    out: list[str] = []
    for b in blocks or []:
        if not isinstance(b, dict):
            continue
        out += _render_block(b)
    return "\n".join(out).replace(" ___", "") if out else None
