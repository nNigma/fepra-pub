"""
Шаблоны frontmatter под типы заметок (SPEC §5, §11).

Каждый билдер возвращает (base, owned):
  base  — ключи заголовка, которые ставятся при создании заметки;
  owned — поля, которыми владеет адаптер (часы) и которые он вправе обновлять.
Разделение нужно upsert_note, чтобы не затирать ручной ввод (SPEC §4).
"""
from __future__ import annotations

from datetime import date

from ..models import Activity, Competition, DailyMetrics


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def daily_frontmatter(day: date, metrics: DailyMetrics | None) -> tuple[dict, dict]:
    """Дневная заметка type: training-day — readiness-блок из DailyMetrics."""
    base = {"date": day.isoformat(), "type": "training-day"}
    owned: dict = {}
    if metrics is not None:
        owned = _clean({
            "sleep_h": metrics.sleep_h,
            "resting_hr": metrics.resting_hr,
            "hrv": metrics.hrv,
            "body_battery": metrics.body_battery,
            "readiness": metrics.readiness,
            "stress_avg": metrics.stress_avg,
            "weight_kg": metrics.weight_kg,
        })
    return base, owned


def workout_frontmatter(activity: Activity) -> tuple[dict, dict]:
    """
    Заметка тренировки. Наши (часы): watch + endurance.
    Кроссфит wod(prescription)/performed заполняется вручную — здесь НЕ трогаем.
    """
    day = activity.start.date().isoformat()
    base = {"date": day, "type": "workout", "sport": activity.sport.value}

    watch = _clean({
        "source": activity.source,
        "duration_min": activity.duration_min,
        "avg_hr": activity.avg_hr,
        "max_hr": activity.max_hr,
        "calories": activity.calories,
    })
    owned: dict = {"watch": watch} if watch else {}

    if activity.endurance is not None:
        e = activity.endurance
        endurance = _clean({
            "distance_km": e.distance_km,
            "avg_pace_s_per_km": e.avg_pace_s_per_km,
            "avg_power_w": e.avg_power_w,
            "elevation_gain_m": e.elevation_gain_m,
            "series_ref": e.series_ref,
        })
        if endurance:
            owned["endurance"] = endurance
    return base, owned


def competition_frontmatter(comp: Competition) -> tuple[dict, dict]:
    """Старт — собственный тренерский шаблон (SPEC §5)."""
    base = {
        "date": comp.day.isoformat(),
        "type": "competition",
        "sport": comp.sport.value,
        "name": comp.name,
    }
    owned = _clean({
        "goal": comp.goal,
        "result": comp.result,
        "place": comp.place,
        "conditions": comp.conditions,
        "splits": comp.splits or None,
        "reflection": comp.reflection,
    })
    return base, owned


# --- имена файлов ------------------------------------------------------------

def daily_filename(day: date) -> str:
    return f"{day:%Y/%m}/{day.isoformat()}.md"


def workout_filename(activity: Activity) -> str:
    """Детерминированно по activity_id, чтобы повторный seed не плодил дубли.
    Раскладка YYYY/MM/<день>-<спорт>-<id>.md (iter_notes ходит рекурсивно)."""
    day = activity.start.date()
    stem = f"{day.isoformat()}-{activity.sport.value}"
    name = f"{stem}-{activity.activity_id}" if activity.activity_id else stem
    return f"{day:%Y/%m}/{name}.md"
