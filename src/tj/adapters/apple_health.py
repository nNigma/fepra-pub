"""
AppleHealthAdapter — JSON из приложения Health Auto Export (SPEC §8).

Труба надёжнее Гармина (не зависит от SSO), но HealthKit нормализует и теряет
гарминоспецифику (body battery, readiness). Capabilities это отражают.
"""
from __future__ import annotations

from datetime import date

from .base import Capabilities
from ..models import Activity, DailyMetrics


class AppleHealthAdapter:
    name = "apple_health"
    capabilities = Capabilities(
        daily=True,
        activities=True,
        metrics={"hrv", "resting_hr", "sleep"},   # без body_battery/readiness
    )

    def __init__(self, export_dir: str, tz: str):
        self._export_dir = export_dir   # папка, куда приложение льёт JSON
        self._tz = tz

    def fetch_daily(self, day: date) -> DailyMetrics | None:
        raise NotImplementedError("AppleHealthAdapter.fetch_daily")

    def fetch_activities(self, start: date, end: date) -> list[Activity]:
        raise NotImplementedError("AppleHealthAdapter.fetch_activities")
