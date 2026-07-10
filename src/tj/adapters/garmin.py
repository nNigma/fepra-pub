"""
GarminAdapter — неофициальный доступ через garminconnect (SPEC §8–9).

Оговорки (SPEC §9):
- авторизация хрупкая, периодически ломается -> ТОКЕН сохраняем и переиспользуем;
- точные сигнатуры методов смотреть в demo.py репозитория cyberjunky/python-garminconnect;
- таймзону применяем при маппинге start (SPEC §5): канон хранит start с tz,
  «день» считается по локальной tz пользователя.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from .base import Adapter, Capabilities
from ..models import (
    Activity,
    DailyMetrics,
    EnduranceDetails,
    Sport,
    StrengthWodDetails,
)

# typeKey Garmin -> канон Sport (SPEC §5)
_SPORT_MAP = {
    "running": Sport.RUN,
    "trail_running": Sport.RUN,
    "treadmill_running": Sport.RUN,
    "track_running": Sport.RUN,
    "cycling": Sport.BIKE,
    "road_biking": Sport.BIKE,
    "mountain_biking": Sport.BIKE,
    "indoor_cycling": Sport.BIKE,
    "virtual_ride": Sport.BIKE,
    "lap_swimming": Sport.SWIM,
    "open_water_swimming": Sport.SWIM,
    "strength_training": Sport.CROSSFIT,
    "indoor_cardio": Sport.CROSSFIT,
    "fitness_equipment": Sport.CROSSFIT,
    "hiit": Sport.CROSSFIT,
}
_ENDURANCE = {Sport.RUN, Sport.BIKE, Sport.SWIM}


class GarminAdapter:
    name = "garmin"
    capabilities = Capabilities(
        daily=True,
        activities=True,
        metrics={"hrv", "body_battery", "readiness", "resting_hr", "sleep", "stress"},
    )

    def __init__(self, email, password, tokenstore, tz, raw_dir="raw", data_dir="data", prompt_mfa=None):
        self._email = email
        self._password = password
        self._tokenstore = str(tokenstore)
        self._tz = tz
        self._raw_dir = Path(raw_dir)
        self._data_dir = Path(data_dir)
        self._client = None
        self._prompt_mfa = prompt_mfa or (lambda: input("Garmin MFA-код: ").strip())

    # --- авторизация (garminconnect 0.3.x, SPEC §9) ---------------------
    def _login(self):
        """
        В 0.3.x один вызов login(tokenstore) делает всё: резюмирует из сохранённого
        токена, иначе логинится по кредам (MFA — через колбэк prompt_mfa) и САМ
        сохраняет токен в tokenstore. Переиспользование токена снижает шанс
        словить блок при частых логинах (SPEC §9).
        """
        if self._client is not None:
            return self._client
        from garminconnect import Garmin  # ленивый импорт: тяжёлая зависимость

        Path(self._tokenstore).expanduser().mkdir(parents=True, exist_ok=True)

        client = Garmin(email=self._email, password=self._password, prompt_mfa=self._prompt_mfa)
        client.login(self._tokenstore)
        self._client = client
        return client

    # --- daily (SPEC §5, §8) --------------------------------------------
    def fetch_daily(self, day: date) -> DailyMetrics | None:
        client = self._login()
        iso = day.isoformat()

        def safe(fn, *a):
            try:
                return fn(*a)
            except Exception:
                return None

        raw = {
            "date": iso,
            "stats": safe(client.get_stats, iso),
            "sleep": safe(client.get_sleep_data, iso),
            "hrv": safe(client.get_hrv_data, iso),
            "training_readiness": safe(client.get_training_readiness, iso),
            "body_battery": safe(client.get_body_battery, iso),
            "max_metrics": safe(client.get_max_metrics, iso),
            "training_status": safe(client.get_training_status, iso),
            "spo2": safe(client.get_spo2_data, iso),
        }
        self._dump_raw("daily", iso, raw)

        if not any(raw[k] for k in ("stats", "sleep", "hrv", "training_readiness", "body_battery")):
            return None
        return self._map_daily(day, raw)

    def _map_daily(self, day, raw):
        stats = raw.get("stats") or {}
        sleep = raw.get("sleep") or {}
        hrv = raw.get("hrv") or {}
        readiness = raw.get("training_readiness") or []
        bb = raw.get("body_battery") or []

        sleep_dto = sleep.get("dailySleepDTO") if isinstance(sleep, dict) else None
        sleep_s = self._g(sleep_dto or {}, "sleepTimeSeconds")
        sleep_h = round(sleep_s / 3600, 2) if sleep_s else None

        hrv_sum = hrv.get("hrvSummary") if isinstance(hrv, dict) else None
        hrv_val = self._g(hrv_sum or {}, "lastNightAvg", "weeklyAvg")

        rd = None
        if isinstance(readiness, list) and readiness:
            rd = self._g(readiness[0], "score")
        elif isinstance(readiness, dict):
            rd = self._g(readiness, "score")

        weight_g = self._g(stats, "weight")
        weight_kg = round(weight_g / 1000, 1) if weight_g else None

        sd = sleep_dto or {}
        scores = sd.get("sleepScores") or {}
        max_m = raw.get("max_metrics") or []
        ts = raw.get("training_status") or {}
        # фраза статуса лежит уровнем глубже (mostRecentTrainingStatus); старый
        # плоский вариант оставлен фолбэком
        mrts = ts.get("mostRecentTrainingStatus") or ts
        latest = mrts.get("latestTrainingStatusData") or {}
        ts_obj = next(iter(latest.values()), {}) if isinstance(latest, dict) else {}

        def _secs_to_h(x):
            return round(x / 3600, 2) if isinstance(x, (int, float)) and x > 0 else None

        bb_hi = self._g(stats, "bodyBatteryHighestValue")
        bb_lo = self._g(stats, "bodyBatteryLowestValue")
        vo2 = None
        if isinstance(max_m, list) and max_m:
            vo2 = self._g(max_m[0].get("generic") or {}, "vo2MaxPreciseValue", "vo2MaxValue")

        spo = raw.get("spo2") or {}
        resp_rest = self._g(sd, "averageRespirationValue")
        if resp_rest is None:
            resp_rest = self._g(sleep.get("respiration") or {}, "avgSleepRespirationValue")

        extra = {
            "spo2_avg": self._int(self._g(spo, "averageSpO2", "averageSpo2")),
            "spo2_lowest": self._int(self._g(spo, "lowestSpO2", "lowestSpo2")),
            "sleep_score": self._int(self._g(scores.get("overall") or {}, "value")),
            "sleep_deep_h": _secs_to_h(self._g(sd, "deepSleepSeconds")),
            "sleep_rem_h": _secs_to_h(self._g(sd, "remSleepSeconds")),
            "bb_charge": (self._int(bb_hi) - self._int(bb_lo)) if (bb_hi is not None and bb_lo is not None) else None,
            "respiration_rest": self._nonneg(self._int(resp_rest)),
            "vo2max": vo2,
            "hrv_status": self._g(hrv_sum or {}, "status"),
            "recovery_h": self._int(self._g(stats, "recoveryTime")),
            "training_status": self._g(ts_obj, "trainingStatusFeedbackPhrase"),
        }
        extra = {k: v for k, v in extra.items() if v is not None}

        # Garmin для отсутствующих метрик шлёт сентинелы -1/-2 (особенно stress) — это не данные.
        return DailyMetrics(
            day=day,
            sleep_h=self._nonneg(sleep_h),
            resting_hr=self._nonneg(self._int(self._g(stats, "restingHeartRate"))),
            hrv=self._nonneg(self._int(hrv_val)),
            body_battery=self._nonneg(self._int(self._extract_bb(stats, bb))),
            readiness=self._nonneg(self._int(rd)),
            stress_avg=self._nonneg(self._int(self._g(stats, "averageStressLevel", "avgStressLevel"))),
            weight_kg=self._nonneg(weight_kg),
            extra=extra,
        )

    @staticmethod
    def _extract_bb(stats, bb):
        """Единое число body battery: высшее за день."""
        v = stats.get("bodyBatteryHighestValue") or stats.get("bodyBatteryMostRecentValue")
        if v is not None:
            return v
        best = None
        if isinstance(bb, list):
            for entry in bb:
                arr = entry.get("bodyBatteryValuesArray") if isinstance(entry, dict) else None
                if isinstance(arr, list):
                    for point in arr:
                        if isinstance(point, (list, tuple)) and len(point) >= 2 and point[1] is not None:
                            best = point[1] if best is None else max(best, point[1])
        return best

    # --- devices (для «Тюнинга часов») -----------------------------------
    def fetch_devices(self) -> list[dict]:
        """Устройства аккаунта: модель + capable-флаги + настройки (в ключе
        _settings). Любая ошибка -> [] (снапшот не критичен для синка)."""
        try:
            client = self._login()
            devs = client.get_devices() or []
        except Exception:
            return []
        out = []
        for d in devs:
            if not isinstance(d, dict):
                continue
            dev = dict(d)
            try:
                dev["_settings"] = client.get_device_settings(d.get("deviceId")) or {}
            except Exception:
                dev["_settings"] = {}
            out.append(dev)
        return out

    # --- activities (SPEC §4, §5, §8) -----------------------------------
    def fetch_activities(self, start: date, end: date, with_series: bool = False) -> list[Activity]:
        client = self._login()
        try:
            items = client.get_activities_by_date(start.isoformat(), end.isoformat())
        except Exception:
            items = []
        self._dump_raw("activities", f"{start.isoformat()}_{end.isoformat()}", items)

        out = []
        for item in items or []:
            act = self._map_activity(item)
            if act is None:
                continue
            if with_series and act.activity_id:
                ref = self._dump_series(client, act.activity_id)
                if act.sport in _ENDURANCE:
                    if ref:
                        act.endurance = act.endurance or EnduranceDetails()
                        act.endurance.series_ref = ref
                elif ref:
                    act.extra = {**act.extra, "hr_series_ref": ref}
            out.append(act)
        return out

    def _map_activity(self, item):
        if not isinstance(item, dict):
            return None
        type_key = (item.get("activityType") or {}).get("typeKey", "")
        sport = _SPORT_MAP.get(type_key, Sport.OTHER)
        start = self._to_local(item.get("startTimeGMT"))
        if start is None:
            return None
        dur = item.get("duration")
        aid = item.get("activityId")
        act = Activity(
            source=self.name,
            sport=sport,
            start=start,
            duration_min=round(dur / 60, 1) if dur else None,
            avg_hr=self._int(item.get("averageHR")),
            max_hr=self._int(item.get("maxHR")),
            calories=self._int(item.get("calories")),
            activity_id=str(aid) if aid is not None else None,
        )
        if sport in _ENDURANCE:
            dist = item.get("distance")
            speed = item.get("averageSpeed")
            act.endurance = EnduranceDetails(
                distance_km=round(dist / 1000, 3) if dist else None,
                avg_pace_s_per_km=round(1000 / speed, 1) if speed else None,
                avg_power_w=self._int(item.get("avgPower")),
                elevation_gain_m=self._int(item.get("elevationGain")),
            )
        elif sport == Sport.CROSSFIT:
            # Факт WOD (вес/счёт/RPE) Garmin не знает — заполняется вручную (SPEC §6).
            act.strength = StrengthWodDetails()
        zones = [self._int(item.get(f"hrTimeInZone_{i}")) for i in range(1, 6)]
        time_in_zones = [z or 0 for z in zones] if any(z is not None for z in zones) else None
        mod = self._int(item.get("moderateIntensityMinutes"))
        vig = self._int(item.get("vigorousIntensityMinutes"))
        extra = {
            "te_aerobic": self._nonneg(item.get("aerobicTrainingEffect")),
            "te_anaerobic": self._nonneg(item.get("anaerobicTrainingEffect")),
            "primary_benefit": item.get("trainingEffectLabel"),
            "exercise_load": self._int(item.get("activityTrainingLoad")),
            "active_cal": self._int(item.get("activeKilocalories")),
            "resting_cal": self._int(item.get("bmrKilocalories")),
            "sweat_loss_ml": self._int(item.get("waterEstimated")),
            "respiration_avg": self._int(item.get("avgRespirationRate")),
            "respiration_max": self._int(item.get("maxRespirationRate")),
            "intensity_min": ([mod, vig] if (mod is not None or vig is not None) else None),
            "time_in_zones": time_in_zones,
        }
        act.extra = {k: v for k, v in extra.items() if v is not None}
        return act

    def _dump_series(self, client, activity_id):
        """Тяжёлые ряды активности -> data/<id>.parquet, вернуть ссылку (SPEC §4)."""
        try:
            details = client.get_activity_details(activity_id)
        except Exception:
            return None
        self._dump_raw("details", str(activity_id), details)
        try:
            import pandas as pd  # ленивый импорт
        except ImportError:
            return None
        descriptors = details.get("metricDescriptors") or []
        metrics = details.get("activityDetailMetrics") or []
        cols = {
            d.get("metricsIndex"): (d.get("key") or f"m{d.get('metricsIndex')}")
            for d in descriptors
            if isinstance(d, dict)
        }
        rows = []
        for m in metrics:
            vals = m.get("metrics") if isinstance(m, dict) else None
            if isinstance(vals, list):
                rows.append({cols.get(i, f"m{i}"): v for i, v in enumerate(vals)})
        if not rows:
            return None
        self._data_dir.mkdir(parents=True, exist_ok=True)
        out = self._data_dir / f"{activity_id}.parquet"
        pd.DataFrame(rows).to_parquet(out, index=False)
        return str(out)

    # --- helpers ---------------------------------------------------------
    def _dump_raw(self, subdir, name, payload):
        out = self._raw_dir / "garmin" / subdir
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{name}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def _to_local(self, gmt_str):
        """startTimeGMT 'YYYY-MM-DD HH:MM:SS' (UTC) -> tz-aware datetime локальной tz (SPEC §5)."""
        if not gmt_str:
            return None
        try:
            dt = datetime.strptime(gmt_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
        if ZoneInfo is not None:
            try:
                return dt.astimezone(ZoneInfo(self._tz))
            except Exception:
                return dt
        return dt

    @staticmethod
    def _g(d, *keys):
        for k in keys:
            if isinstance(d, dict) and d.get(k) is not None:
                return d[k]
        return None

    @staticmethod
    def _int(v):
        try:
            return int(round(float(v))) if v is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _nonneg(v):
        """Сентинелы Garmin (-1/-2 = «нет данных») -> None; настоящие метрики неотрицательны."""
        return v if isinstance(v, (int, float)) and v >= 0 else None


_: Adapter = GarminAdapter  # type: ignore  # контроль соответствия протоколу
