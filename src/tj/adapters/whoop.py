"""Whoop v2: чистые мапперы в канон + транспорт (SPEC §8, спека whoop-integration).

Ренормировка recovery: полосы Whoop (red 0-33 / yellow 34-66 / green 67-100)
переводятся в наши пороги verdict (45/65), сырой процент — в extra.recovery_pct.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

import httpx

from ..models import Activity, DailyMetrics, EnduranceDetails, Sport

AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
SCOPES = "read:recovery read:cycles read:sleep read:workout read:profile read:body_measurement offline"

_KCAL_PER_KJ = 0.239
_ENDURANCE = {Sport.RUN, Sport.BIKE, Sport.SWIM}


def api_base() -> str:
    return os.environ.get("WHOOP_API_BASE", "https://api.prod.whoop.com/developer/v2").rstrip("/")


def renorm_recovery(score) -> int | None:
    if score is None:
        return None
    s = max(0.0, min(100.0, float(score)))
    if s <= 33:
        return round(s / 33 * 44)
    if s <= 66:
        return round(45 + (s - 34) / 32 * 19)
    return round(65 + (s - 67) / 33 * 35)


def _tzoff(off: str | None) -> timezone | None:
    if not off:
        return None
    try:
        sign = -1 if off.startswith("-") else 1
        hh, mm = off.lstrip("+-").split(":")
        return timezone(sign * timedelta(hours=int(hh), minutes=int(mm)))
    except (ValueError, AttributeError):
        return None


def _dt(iso: str | None, off: str | None) -> datetime | None:
    try:
        d = datetime.fromisoformat((iso or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        return None
    tz = _tzoff(off)
    return d.astimezone(tz) if tz else d


def _score(rec: dict) -> dict:
    return (rec.get("score") or {}) if rec.get("score_state") == "SCORED" else {}


def map_daily(sleeps: list, recoveries: list) -> list[DailyMetrics]:
    rec_by_sleep = {r.get("sleep_id"): r for r in recoveries if isinstance(r, dict)}
    out: dict[date, DailyMetrics] = {}
    for s in sleeps:
        if not isinstance(s, dict) or s.get("nap"):
            continue
        end = _dt(s.get("end"), s.get("timezone_offset"))
        if end is None:
            continue
        day = end.date()
        m = out.get(day) or DailyMetrics(day=day)
        sc = _score(s)
        st = sc.get("stage_summary") or {}
        ms = [st.get(k) for k in ("total_light_sleep_time_milli",
                                  "total_slow_wave_sleep_time_milli",
                                  "total_rem_sleep_time_milli")]
        ms = [v for v in ms if isinstance(v, (int, float))]
        if ms:
            m.sleep_h = round(sum(ms) / 3_600_000, 1)
        deep = st.get("total_slow_wave_sleep_time_milli")
        rem = st.get("total_rem_sleep_time_milli")
        if isinstance(deep, (int, float)):
            m.extra["sleep_deep_h"] = round(deep / 3_600_000, 1)
        if isinstance(rem, (int, float)):
            m.extra["sleep_rem_h"] = round(rem / 3_600_000, 1)
        if sc.get("sleep_performance_percentage") is not None:
            m.extra["sleep_score"] = round(sc["sleep_performance_percentage"])
        if sc.get("respiratory_rate") is not None:
            m.extra["respiration_rest"] = round(sc["respiratory_rate"], 1)
        rs = _score(rec_by_sleep.get(s.get("id")) or {})
        if rs:
            m.readiness = renorm_recovery(rs.get("recovery_score"))
            if rs.get("recovery_score") is not None:
                m.extra["recovery_pct"] = round(rs["recovery_score"])
            if rs.get("hrv_rmssd_milli") is not None:
                m.hrv = round(rs["hrv_rmssd_milli"])
            if rs.get("resting_heart_rate") is not None:
                m.resting_hr = round(rs["resting_heart_rate"])
            if rs.get("spo2_percentage") is not None:
                m.extra["spo2_avg"] = round(rs["spo2_percentage"], 1)
            if rs.get("skin_temp_celsius") is not None:
                m.extra["skin_temp"] = round(rs["skin_temp_celsius"], 1)
        out[day] = m
    return [out[d] for d in sorted(out)]


def _sport(name) -> Sport:
    n = str(name or "").lower()
    for sub, sp in (("run", Sport.RUN), ("cycl", Sport.BIKE), ("bik", Sport.BIKE), ("swim", Sport.SWIM)):
        if sub in n:
            return sp
    return Sport.OTHER


def map_workouts(workouts: list) -> list[Activity]:
    out: list[Activity] = []
    for w in workouts:
        if not isinstance(w, dict):
            continue
        start = _dt(w.get("start"), w.get("timezone_offset"))
        end = _dt(w.get("end"), w.get("timezone_offset"))
        if start is None:
            continue
        sc = _score(w)
        sport = _sport(w.get("sport_name"))
        dist = sc.get("distance_meter")
        elev = sc.get("altitude_gain_meter")
        endurance = None
        if sport in _ENDURANCE:
            endurance = EnduranceDetails(
                distance_km=round(dist / 1000, 2) if isinstance(dist, (int, float)) else None,
                elevation_gain_m=round(elev) if isinstance(elev, (int, float)) else None)
        extra = {}
        if sc.get("strain") is not None:
            extra["strain"] = round(sc["strain"], 1)
        zd = sc.get("zone_durations")
        if isinstance(zd, dict):
            zones = [zd.get(f"zone_{n}_milli") for n in
                     ("one", "two", "three", "four", "five")]
            if any(isinstance(z, (int, float)) for z in zones):
                extra["time_in_zones"] = [round((z or 0) / 1000) for z in zones]
        kj = sc.get("kilojoule")
        out.append(Activity(
            source="whoop", sport=sport, start=start,
            duration_min=round((end - start).total_seconds() / 60, 1) if end else None,
            avg_hr=round(sc["average_heart_rate"]) if sc.get("average_heart_rate") is not None else None,
            max_hr=round(sc["max_heart_rate"]) if sc.get("max_heart_rate") is not None else None,
            calories=int(kj * _KCAL_PER_KJ) if isinstance(kj, (int, float)) else None,
            endurance=endurance,
            activity_id=f"whoop-{w.get('id')}" if w.get("id") else None,
            extra=extra))
    return out


class WhoopClient:
    """load_tokens/save_tokens — коллбэки поверх БД: перечитка перед refresh закрывает
    гонку крон-vs-кнопка (refresh-токен Whoop одноразовый, ротируется)."""

    def __init__(self, creds: tuple[str, str], load_tokens, save_tokens,
                 http: httpx.Client | None = None):
        self._cid, self._sec = creds
        self._load = load_tokens
        self._save = save_tokens
        self._http = http or httpx.Client(timeout=30)
        self._tokens = dict(load_tokens() or {})

    def collection(self, path: str, start_iso: str, end_iso: str) -> list[dict]:
        out: list[dict] = []
        token = None
        while True:
            params = {"start": start_iso, "end": end_iso, "limit": 25}
            if token:
                params["nextToken"] = token
            data = self._get(api_base() + path, params)
            out += [x for x in (data.get("records") or []) if isinstance(x, dict)]
            token = data.get("next_token")
            if not token:
                return out

    def delete(self, path: str) -> bool:
        try:
            r = self._http.delete(api_base() + path, headers=self._auth_header())
            return r.status_code < 300
        except httpx.HTTPError:
            return False

    def _auth_header(self) -> dict:
        return {"Authorization": f"Bearer {self._tokens.get('access_token', '')}"}

    def _get(self, url: str, params: dict) -> dict:
        for attempt in (0, 1):
            r = self._http.get(url, params=params, headers=self._auth_header())
            if r.status_code == 401 and attempt == 0:
                self._tokens = dict(self._load() or self._tokens)
                self._refresh()
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError("unreachable")

    def _refresh(self) -> None:
        r = self._http.post(TOKEN_URL, data={
            "grant_type": "refresh_token",
            "refresh_token": self._tokens.get("refresh_token", ""),
            "client_id": self._cid, "client_secret": self._sec,
            "scope": "offline"})
        r.raise_for_status()
        d = r.json()
        self._tokens = {
            "access_token": d["access_token"],
            "refresh_token": d.get("refresh_token") or self._tokens.get("refresh_token", ""),
            "expires_at": (datetime.now(timezone.utc)
                           + timedelta(seconds=int(d.get("expires_in", 3600)))).isoformat(timespec="seconds")}
        self._save(self._tokens)
