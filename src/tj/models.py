"""
Каноническая схема (vendor-agnostic). Сердце проекта — см. SPEC §5.

Свои сущности, не зависящие от вендора. Каждый адаптер маппит свои поля сюда;
чего источник не даёт — None. БД и frontmatter строятся из этих моделей.

Черновик на dataclasses ради минимума зависимостей. Когда понадобится валидация
и сериализация — кандидат на переезд в pydantic v2 (см. SPEC §13).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum


class Sport(str, Enum):
    CROSSFIT = "crossfit"
    RUN = "run"
    BIKE = "bike"
    SWIM = "swim"
    OTHER = "other"


class Scaling(str, Enum):
    RX = "rx"
    SCALED = "scaled"


class WodFormat(str, Enum):
    FOR_TIME = "for-time"
    AMRAP = "amrap"
    EMOM = "emom"
    ROUNDS = "rounds"
    OTHER = "other"


# --- Дневная биометрия -------------------------------------------------------

@dataclass
class DailyMetrics:
    """Состояние дня: сон, восстановление. Источник: часы / Apple Health."""
    day: date
    sleep_h: float | None = None
    resting_hr: int | None = None
    hrv: int | None = None
    body_battery: int | None = None
    readiness: int | None = None     # training readiness, если источник даёт
    stress_avg: int | None = None
    weight_kg: float | None = None
    extra: dict = field(default_factory=dict)


# --- Активность и её расширения ----------------------------------------------

@dataclass
class EnduranceDetails:
    """Расширение Activity для бега/вела/плавания. Источник: часы."""
    distance_km: float | None = None
    avg_pace_s_per_km: float | None = None
    avg_power_w: int | None = None
    elevation_gain_m: int | None = None
    # Тяжёлые ряды (сплиты/трек) НЕ здесь — ссылка на sidecar parquet (SPEC §4).
    series_ref: str | None = None    # напр. "data/<activity_id>.parquet"


@dataclass
class WodPrescription:
    """Что ЗАДАНО. Источник: фото доски. Одинаково на всю группу. (SPEC §3)"""
    name: str | None = None          # имя бенчмарка, если есть (Fran, Grace...)
    format: WodFormat = WodFormat.OTHER
    raw_text: str | None = None      # сырой текст с доски
    # Структурированные движения — позже, через онтологию (ontology.py).
    movements: list[str] = field(default_factory=list)


@dataclass
class WodPerformed:
    """Что ты СДЕЛАЛ. Источник: только ты (бот/заметка). (SPEC §3)"""
    scaling: Scaling | None = None
    load_kg: float | None = None     # рабочий вес; None если bodyweight
    score: str | None = None         # "4:12" (for-time) или "5+12" (amrap)
    rpe: int | None = None           # 1..10, субъективно
    notes: str | None = None


@dataclass
class StrengthWodDetails:
    """Расширение Activity для кроссфита. РАСЩЕПЛЕНО (SPEC §5)."""
    prescription: WodPrescription = field(default_factory=WodPrescription)
    performed: WodPerformed = field(default_factory=WodPerformed)


@dataclass
class Activity:
    """Общий сеанс. start хранится с таймзоной; 'день' = по локальной tz (SPEC §5)."""
    source: str                      # "garmin" | "apple_health" | "manual" ...
    sport: Sport
    start: datetime                  # timezone-aware
    duration_min: float | None = None
    avg_hr: int | None = None
    max_hr: int | None = None
    calories: int | None = None
    hr_zones_min: dict[int, float] | None = None   # {зона: минуты}

    # ровно одно из расширений, по виду спорта
    endurance: EnduranceDetails | None = None
    strength: StrengthWodDetails | None = None

    activity_id: str | None = None   # стабильный id для sidecar/мёрджа
    extra: dict = field(default_factory=dict)


# --- Субъективка и соревнования ----------------------------------------------

@dataclass
class SubjectiveLog:
    """То, чего часы не видят — и в этом весь смысл дневника (SPEC §1)."""
    day: date
    feeling: int | None = None       # 1..5 общее самочувствие
    motivation: int | None = None    # 1..5
    soreness: int | None = None      # 1..5
    sleep_quality: int | None = None # 1..5 по ощущениям (не часы)
    note: str | None = None


@dataclass
class Competition:
    """Старт. Собственный шаблон — это тренерский лог, а не просто запись."""
    day: date
    name: str
    sport: Sport
    goal: str | None = None
    result: str | None = None
    place: int | None = None
    conditions: str | None = None    # погода/трасса/зал
    splits: list[str] = field(default_factory=list)
    reflection: str | None = None    # что зашло / что нет / выводы
