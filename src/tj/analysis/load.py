"""
Анализ нагрузки (SPEC §7): TRIMP, ACWR, monotony/strain. Чистые функции.

TRIMP (Banister) — взвешенная по ЧСС «доза» сессии.
ACWR — отношение острой (7д) к хронической (28д) нагрузке: окно риска.
Monotony/Strain (Foster) — однообразие и суммарный стресс недели.
"""
from __future__ import annotations

import math


def trimp(duration_min, avg_hr, rest_hr, max_hr, sex: str = "m") -> float:
    """
    TRIMP = t · HRr · c · e^(k·HRr),  HRr = (avg-rest)/(max-rest).
    Коэффициенты: муж. c=0.64 k=1.92, жен. c=0.86 k=1.67.
    Нет данных / некорректный диапазон ЧСС -> 0.
    """
    if None in (duration_min, avg_hr, rest_hr, max_hr) or max_hr <= rest_hr:
        return 0.0
    hrr = (avg_hr - rest_hr) / (max_hr - rest_hr)
    hrr = max(0.0, min(1.0, hrr))
    c, k = (0.64, 1.92) if sex == "m" else (0.86, 1.67)
    return duration_min * hrr * c * math.exp(k * hrr)


def acwr(daily_load: list[float], acute: int = 7, chronic: int = 28) -> float | None:
    """Acute:Chronic Workload Ratio на конец ряда. None, если истории < chronic или хрон.=0."""
    if len(daily_load) < chronic:
        return None
    a = sum(daily_load[-acute:]) / acute
    c = sum(daily_load[-chronic:]) / chronic
    return None if c == 0 else round(a / c, 2)


def monotony(window_load: list[float]) -> float | None:
    """Foster monotony = mean/std дневной нагрузки за окно (обычно 7д). None при std=0."""
    if len(window_load) < 2:
        return None
    m = sum(window_load) / len(window_load)
    sd = math.sqrt(sum((x - m) ** 2 for x in window_load) / len(window_load))
    return None if sd == 0 else round(m / sd, 2)


def strain(window_load: list[float]) -> float | None:
    """Foster strain = суммарная нагрузка окна · monotony."""
    mono = monotony(window_load)
    return None if mono is None else round(sum(window_load) * mono, 0)
