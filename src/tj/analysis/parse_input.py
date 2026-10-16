"""Разбор пользовательского ввода результатов (без Telegram и без БД).

Вынесено из tjbot/handlers (record_result, record_workout): парсеры «вес×повторы»,
бенчмарков, RPE и метки RX/scaled, построчный список максов. Хендлеры бота
реэкспортируют эти функции, чтобы прежние импорты и тесты остались рабочими.
"""
from __future__ import annotations

import re

from tj.models import Scaling

from .progression import epley_1rm


def parse_lift(txt: str):
    s = txt.strip().lower().replace("кг", "").strip()
    m = re.match(r"^(\d+(?:[.,]\d+)?)\s*[xхXХ×* ]\s*(\d+)$", s)
    if m:
        load = float(m.group(1).replace(",", "."))
        reps = int(m.group(2))
        return (load, reps) if load > 0 and reps >= 1 else None
    m = re.match(r"^(\d+(?:[.,]\d+)?)$", s)
    if m:
        load = float(m.group(1).replace(",", "."))
        return (load, 1) if load > 0 else None
    return None


def parse_benchmark(txt: str, unit: str):
    s = txt.strip().lower()
    if unit == "rounds":
        m = re.match(r"^(\d+)", s)
        return float(m.group(1)) if m else None
    if ":" in s:
        m = re.match(r"^(\d+):(\d{1,2})$", s)
        if not m:
            return None
        mm, ss = int(m.group(1)), int(m.group(2))
        if ss >= 60:
            return None
        return float(mm * 60 + ss)
    m = re.match(r"^(\d+)$", s)
    return float(m.group(1)) if m else None


def est_1rm_for(load: float, reps: int) -> float:
    if reps <= 1:
        return round(load, 1)
    return epley_1rm(load, reps)


RPE_RE = re.compile(r"rpe\s*[:=]?\s*(\d{1,2})", re.IGNORECASE)


def parse_rpe(text: str | None) -> int | None:
    """«RPE 8» в свободном тексте результата -> 8 (как в мастере записи бота)."""
    m = RPE_RE.search(text or "")
    return int(m.group(1)) if m else None


def detect_scaling(text: str | None) -> Scaling | None:
    """Метка из свободного текста: «scaled/скейл» -> SCALED, «rx» -> RX, иначе None."""
    low = (text or "").lower()
    if "scal" in low or "скейл" in low:
        return Scaling.SCALED
    if "rx" in low:
        return Scaling.RX
    return None


def parse_lift_lines(text: str):
    """Построчный ввод максов «Движение 100x3» -> [{movement, weight_kg, reps}]."""
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        m = re.search(r"\d", line)
        if not m or m.start() == 0:
            continue
        movement = line[:m.start()].strip()
        parsed = parse_lift(line[m.start():])
        if movement and parsed:
            out.append({"movement": movement, "weight_kg": parsed[0], "reps": parsed[1]})
    return out
