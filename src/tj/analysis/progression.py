"""
Прогрессия (SPEC §7): оценка 1RM, тренды бенчмарков like-for-like по scaling.

Требует ручного ввода performed (load_kg/reps/score/scaling) — Garmin его не знает
(SPEC §6). Пока такие заметки не заполнены, функции готовы, но данных нет.
"""
from __future__ import annotations


def epley_1rm(weight_kg, reps) -> float | None:
    """Оценка 1RM по Эпли: w · (1 + reps/30). None при пустых/некорректных входах."""
    if not weight_kg or not reps or reps < 1:
        return None
    return round(weight_kg * (1 + reps / 30), 1)


def _score_seconds(score: str):
    """'4:12' -> 252 сек; '12' -> 12; иначе None (AMRAP-счёт сюда не годится)."""
    if not isinstance(score, str):
        return None
    s = score.strip()
    try:
        if ":" in s:
            m, sec = s.split(":", 1)
            return int(m) * 60 + int(sec)
        return int(s)
    except ValueError:
        return None


def benchmark_trend(rows) -> list:
    """
    rows: [(day, score, scaling), ...] одного бенчмарка (for-time).
    Возвращает [(day, seconds, scaling), ...] отсортировано по дате,
    only для разобранных времён — сравнивать like-for-like по scaling.
    """
    out = []
    for day, score, scaling in rows:
        sec = _score_seconds(score)
        if sec is not None:
            out.append((day, sec, scaling))
    out.sort(key=lambda r: r[0])
    return out
