"""
Слой 0: единый интерфейс адаптеров источников (SPEC §8).

Каждый источник (Garmin, Apple Health, Polar, Whoop...) реализует Adapter.
Чего источник не умеет — отражаем в Capabilities; мёрдж нескольких источников
идёт ПО МЕТРИКАМ (не по источнику целиком), по приоритету из config [merge].
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import date
from typing import Protocol

from ..models import Activity, DailyMetrics


@dataclass
class Capabilities:
    """Что источник реально умеет отдавать."""
    daily: bool = False          # сон/HRV/readiness/...
    activities: bool = False     # сеансы
    metrics: set[str] = field(default_factory=set)  # {"hrv","body_battery",...}


class Adapter(Protocol):
    """Тонкий контракт. Сырой ответ адаптер сам кладёт в raw/ (bronze)."""
    name: str
    capabilities: Capabilities

    def fetch_daily(self, day: date) -> DailyMetrics | None: ...
    def fetch_activities(self, start: date, end: date) -> list[Activity]: ...


# Поле DailyMetrics -> группа приоритета из config [merge] (ключи группы грубее полей).
_FIELD_GROUP = {
    "sleep_h": "sleep",
    "resting_hr": "hr",
    "stress_avg": "hr",
    "body_battery": "hr",
    "readiness": "hr",
    "weight_kg": "hr",
    "hrv": "hrv",
}


def merge_daily(
    candidates: list[tuple[str, DailyMetrics]],
    priority: dict[str, list[str]],
) -> DailyMetrics:
    """
    Свести DailyMetrics из нескольких источников ПО МЕТРИКАМ по приоритету (SPEC §8).
    candidates: [(source_name, metrics), ...]
    priority:   {"hrv": ["garmin","apple_health"], ...}  # из config [merge]

    На каждое поле берём первый источник по приоритету, где значение не None.
    Поля без явного приоритета — в порядке появления источников.
    """
    if not candidates:
        raise ValueError("merge_daily: пустой список кандидатов")
    by_source = {name: m for name, m in candidates}
    default_order = [name for name, _ in candidates]
    out = DailyMetrics(day=candidates[0][1].day)
    for f in fields(DailyMetrics):
        if f.name == "day":
            continue
        order = priority.get(_FIELD_GROUP.get(f.name, ""), default_order)
        for src in order:
            m = by_source.get(src)
            if m is not None and getattr(m, f.name) is not None:
                setattr(out, f.name, getattr(m, f.name))
                break
    return out
