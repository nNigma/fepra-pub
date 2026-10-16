"""Разбор заполненного шаблона результатов метконов: сумма кругов AMRAP, время, счёт.

Шаблон сгенерён нами (tj.analysis.wod_program), поэтому метки строк известны —
разбор детерминированный, без LLM. Веса силовых в уровни идут отдельно (parse_lifts)."""
from __future__ import annotations

import re

from .wod_notation import parse_weight_reps

_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")
_NUM_RE = re.compile(r"\d+")


def _time_sec(s: str) -> int | None:
    m = _TIME_RE.search(s or "")
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def _fmt_time(sec: int) -> str:
    return f"{sec // 60}:{sec % 60:02d}"


def _rounds(s: str):
    """«5+3» / «5 кругов + 3» -> (rounds, reps). Первое число — круги, второе — довесок."""
    nums = _NUM_RE.findall(s or "")
    if not nums:
        return None
    return int(nums[0]), (int(nums[1]) if len(nums) > 1 else 0)


def _sections(text: str) -> dict:
    """Заполненный текст -> {заголовок_lower: [строки-значения раунда]}."""
    out: dict[str, list[str]] = {}
    cur = None
    for raw in (text or "").splitlines():
        if not raw.strip():
            continue
        if not raw.startswith((" ", "\t")) and raw.rstrip().endswith(":"):
            cur = raw.strip()[:-1].strip().lower()
            out[cur] = []
        elif cur is not None and "раунд" in raw.lower() and ":" in raw:
            out[cur].append(raw.split(":", 1)[1].strip())
    return out


def _sections_full(text: str) -> list[tuple[str, list[tuple[str, str]]]]:
    """Заполненный текст -> [(title, [(label_lower, value), ...]), ...] по порядку.
    Секция начинается с невложенной строки, оканчивающейся ':'. Тело — вложенные
    строки «label: value»."""
    out: list[tuple[str, list[tuple[str, str]]]] = []
    body: list[tuple[str, str]] | None = None
    for raw in (text or "").splitlines():
        if not raw.strip():
            continue
        if not raw.startswith((" ", "\t")) and raw.rstrip().endswith(":"):
            title = raw.strip()[:-1].strip()
            body = []
            out.append((title, body))
        elif body is not None and ":" in raw:
            label, val = raw.split(":", 1)
            body.append((label.strip().lower(), val.strip()))
    return out


def extract_maxes(blocks, text: str) -> list[dict]:
    """Силовые блоки заполненного шаблона -> [{movement, weight_kg, reps}] (лучший подход).
    Только strength/emom_strength. Веса меткона/AMRAP игнорируются."""
    sections = _sections(text)
    out = []
    for b in blocks or []:
        if not isinstance(b, dict) or b.get("format") not in ("strength", "emom_strength"):
            continue
        if not b.get("movements"):
            continue
        name = b["movements"][0]["name"]
        best = None   # (weight, reps)
        for val in sections.get(name.strip().lower(), []):
            wr = parse_weight_reps(val)
            if not wr:
                continue
            if best is None or wr[0] > best[0]:
                best = wr
        if best:
            out.append({"movement": name, "weight_kg": best[0], "reps": best[1]})
    return out


def strength_work(blocks, text: str) -> list[dict]:
    """Силовые блоки заполненного шаблона -> по движению: все подходы, топ-вес,
    сумма повторов, тоннаж. Для предметного разбора работы (не только макс)."""
    sections = _sections(text)
    out = []
    for b in blocks or []:
        if not isinstance(b, dict) or b.get("format") not in ("strength", "emom_strength"):
            continue
        if not b.get("movements"):
            continue
        name = b["movements"][0]["name"]
        sets = []
        for val in sections.get(name.strip().lower(), []):
            wr = parse_weight_reps(val)
            if wr:
                sets.append([wr[0], wr[1]])
        if not sets:
            continue
        out.append({
            "movement": name,
            "sets": sets,
            "top_kg": max(w for w, _ in sets),
            "reps_total": sum(r for _, r in sets),
            "tonnage_kg": round(sum(w * r for w, r in sets), 1),
        })
    return out


def _val(body: list[tuple[str, str]], needle: str, *, prefix: bool = False):
    """Первое значение из тела секции по метке (contains / startswith), пустое -> None."""
    for label, val in body:
        hit = label.startswith(needle) if prefix else needle in label
        if hit and val and not set(val) <= {"_"}:
            return val
    return None


def _is_filled(val: str) -> bool:
    return bool(val) and not set(val) <= {"_"}


_TIME_FORMATS = ("for_time", "chipper", "rounds_for_time", "ladder")


def summarize_filled(blocks, text: str) -> tuple[dict, list[str]]:
    """Заполненный шаблон + структура блоков -> (data для extra, строки-сводки для чата).
    Строки-сводки помечены заголовком блока: каждый метконовый блок -> одна строка.
    Пустые (___) и незаполненные строки игнорируются."""
    sections = _sections_full(text)
    used = [False] * len(sections)

    def take(header: str):
        h = (header or "").strip().lower()
        if not h:
            return None
        for i, (title, body) in enumerate(sections):
            if used[i]:
                continue
            t = title.strip().lower()
            if t.startswith(h) or h in t:
                used[i] = True
                return body
        return None

    data: dict = {}
    lines: list[str] = []
    all_rounds: list[tuple[int, int]] = []
    all_times: list[int] = []

    for b in blocks or []:
        if not isinstance(b, dict):
            continue
        fmt = b.get("format") or b.get("kind")
        if fmt in ("strength", "emom_strength"):
            continue
        header = b.get("header") or b.get("name") or ""
        body = take(header)
        if body is None:
            continue
        if fmt == "ladder":
            # у лесенки поля лежат в секциях упражнений (время — в последней): склеиваем их
            for m in b.get("movements") or []:
                mb = take(m.get("name") or "")
                if mb:
                    body = body + mb

        if fmt in _TIME_FORMATS:
            v = _val(body, "время", prefix=True)
            if v:
                sec = _time_sec(v)
                if sec is not None:
                    all_times.append(sec)
                    line = f"{header} — время: {_fmt_time(sec)}"
                    cap = _val(body, "не уложился в кэп")
                    if cap:
                        line += f" (не в кэпе: {cap} повт.)"
                    lines.append(line)
        elif fmt == "amrap_interval":
            rounds = [_rounds(v) for _, v in body
                      if "круги, амрап" in _ and _is_filled(v)]
            rounds = [r for r in rounds if r]
            if rounds:
                total = sum(r for r, _ in rounds)
                extra = sum(x for _, x in rounds)
                all_rounds.extend(rounds)
                parts = ", ".join((f"{r}+{x}" if x else str(r)) for r, x in rounds)
                lines.append(f"{header} — суммарно {total} кругов ({parts})")
        elif fmt == "amrap":
            rv = _val(body, "кругов", prefix=True)
            pv = _val(body, "повторов (неполный круг)")
            if rv:
                n = _NUM_RE.search(rv)
                r = int(n.group()) if n else 0
                reps = 0
                if pv:
                    pn = _NUM_RE.search(pv)
                    reps = int(pn.group()) if pn else 0
                all_rounds.append((r, reps))
                line = f"{header} — {r} кругов" + (f" +{reps}" if reps else "")
                lines.append(line)
        elif fmt == "stations":
            # интервальный круг «N сек работа / M отдых»: круги + результат по каждой станции
            parts, st = [], []
            for m in b.get("movements") or []:
                mbody = take(m.get("name") or "")
                if not mbody:
                    continue
                for label, val in mbody:
                    if not _is_filled(val):
                        continue
                    # значения новых типов уже несут единицы в тексте («22 ккал», «100 кг, 20 м»)
                    own_unit = label.startswith(("кардио", "вес и дистанция"))
                    unit = ("" if own_unit or "вес×повторы" in label
                            else "сек" if label.startswith("удержание")
                            else "м" if label.startswith("метров")
                            else "ккал" if "ккал" in label
                            else "" if label.startswith("повторы, вес") and "x" in val
                            else "повт")
                    parts.append(f"{m['name']} {val}{(' ' + unit) if unit else ''}")
                    st.append({"movement": m["name"], "value": val, "unit": unit or None})
            rv = _val(body, "кругов", prefix=True)
            if rv or parts:
                line = f"{header}"
                if rv:
                    line += f" — {rv} кругов"
                if parts:
                    line += (" — " if not rv else "; ") + "; ".join(parts)
                lines.append(line)
                data.setdefault("stations", []).append(
                    {"header": header, "rounds": rv, "results": st})
        elif fmt == "death_by":
            mv = _val(body, "дошёл до минуты")
            if mv:
                pv = _val(body, "повторов в незавершённой")
                line = f"{header} — до минуты {mv}"
                if pv:
                    line += f" (+{pv} повт.)"
                lines.append(line)
        else:
            sv = _val(body, "счёт", prefix=True)
            if sv:
                lines.append(f"{header} — счёт: {sv}")
            mv = _val(body, "выполнено минут")
            if mv:
                lines.append(f"{header} — минут: {mv}")
            # гимнастический скилл: «выполнено выходов/повторов: N» или «кругов (по M …): N»
            rv = _val(body, "кругов", prefix=True)
            gv = _val(body, "выполнено выходов") or _val(body, "выполнено повторов")
            if rv:
                lines.append(f"{header} — {rv} кругов")
            elif gv:
                lines.append(f"{header} — выполнено: {gv}")

    if all_rounds:
        tr = sum(r for r, _ in all_rounds)
        trr = sum(x for _, x in all_rounds)
        data["amrap"] = {"rounds": all_rounds, "total_rounds": tr, "total_reps": trr}
    if all_times:
        data["times_sec"] = all_times

    benches = [b.get("benchmark") for b in (blocks or [])
               if isinstance(b, dict) and b.get("benchmark")]
    if benches:
        data["benchmarks"] = benches
        lines.append("Бенчмарк: " + ", ".join(str(b) for b in benches))
    return data, lines
