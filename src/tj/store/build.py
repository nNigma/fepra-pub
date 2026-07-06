"""
build: заметки -> SQLite/DuckDB (SPEC §6).
БД — ПЕРЕСОБИРАЕМЫЙ кэш: при каждом запуске таблицы пересоздаются из заметок.
Удалил -> пересобрал из заметок. Тяжёлые ряды (parquet) сюда не грузим —
читаются по series_ref при анализе (SPEC §4).

Бэкенд (sqlite | duckdb) — из config [store]. Оба используют '?'-плейсхолдеры и
типы TEXT/INTEGER/DOUBLE, поэтому SQL общий. Идентификаторы колонок в кавычках,
чтобы не споткнуться о зарезервированные слова DuckDB.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from ..config import default_env_path, load_dotenv
from ..vault.notes import iter_notes, read_note


def _resolve_owner_id() -> int:
    """ID владельца из env (OWNER_TG_ID) — личный id не хардкодим в коде."""
    v = os.environ.get("OWNER_TG_ID")
    if not v:
        try:
            v = load_dotenv(default_env_path()).get("OWNER_TG_ID")
        except Exception:
            v = None
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


OWNER_TG_ID = _resolve_owner_id()

_DDL = {
    "daily": '''CREATE TABLE daily (
        "day" TEXT, "sleep_h" DOUBLE, "resting_hr" INTEGER, "hrv" INTEGER,
        "body_battery" INTEGER, "readiness" INTEGER, "stress_avg" INTEGER, "weight_kg" DOUBLE,
        "extra" TEXT, "tg_id" INTEGER,
        PRIMARY KEY ("tg_id","day") )''',
    "activities": '''CREATE TABLE activities (
        "note" TEXT, "day" TEXT, "sport" TEXT, "activity_id" TEXT, "source" TEXT,
        "duration_min" DOUBLE, "avg_hr" INTEGER, "max_hr" INTEGER, "calories" INTEGER,
        "distance_km" DOUBLE, "avg_pace_s_per_km" DOUBLE, "avg_power_w" INTEGER, "elevation_gain_m" INTEGER,
        "series_ref" TEXT, "wod_name" TEXT, "wod_format" TEXT,
        "perf_scaling" TEXT, "perf_load_kg" DOUBLE, "perf_score" TEXT, "perf_rpe" INTEGER,
        "extra" TEXT, "tg_id" INTEGER )''',
    "competitions": '''CREATE TABLE competitions (
        "day" TEXT, "name" TEXT, "sport" TEXT, "goal" TEXT, "result" TEXT,
        "place" INTEGER, "conditions" TEXT, "reflection" TEXT )''',
}

_COLS = {
    "daily": ["day", "sleep_h", "resting_hr", "hrv", "body_battery", "readiness",
              "stress_avg", "weight_kg", "extra", "tg_id"],
    "activities": ["note", "day", "sport", "activity_id", "source", "duration_min",
                   "avg_hr", "max_hr", "calories", "distance_km", "avg_pace_s_per_km",
                   "avg_power_w", "elevation_gain_m", "series_ref", "wod_name",
                   "wod_format", "perf_scaling", "perf_load_kg", "perf_score", "perf_rpe",
                   "extra", "tg_id"],
    "competitions": ["day", "name", "sport", "goal", "result", "place", "conditions",
                     "reflection"],
}


def build(vault_dir: Path, db_path: Path, backend: str = "duckdb", tg_id: int = OWNER_TG_ID) -> dict:
    """Пересобрать кэш из всех заметок vault. Возвращает {таблица: число строк}."""
    rows = {"daily": [], "activities": [], "competitions": []}
    for note in iter_notes(Path(vault_dir)):
        try:
            meta, _body = read_note(note)
        except Exception:
            continue
        ntype = meta.get("type")
        if ntype == "training-day":
            rows["daily"].append(_row_daily(meta, tg_id))
        elif ntype == "workout":
            rows["activities"].append(_row_activity(meta, note, tg_id))
        elif ntype == "competition":
            rows["competitions"].append(_row_competition(meta))

    con, kind = _connect(Path(db_path), backend)
    try:
        for table, ddl in _DDL.items():
            con.execute(f"DROP TABLE IF EXISTS {table}")
            con.execute(ddl)
            data = rows[table]
            if data:
                ph = ", ".join(["?"] * len(_COLS[table]))
                con.executemany(f"INSERT INTO {table} VALUES ({ph})", data)
        if kind == "sqlite":
            con.commit()
    finally:
        con.close()
    return {t: len(r) for t, r in rows.items()}


def _connect(db_path: Path, backend: str):
    backend = (backend or "duckdb").lower()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if backend == "sqlite":
        import sqlite3
        return sqlite3.connect(str(db_path)), "sqlite"
    try:
        import duckdb
    except ImportError as e:
        raise RuntimeError("backend=duckdb, но duckdb не установлен (pip install -e .)") from e
    return duckdb.connect(str(db_path)), "duckdb"


def _get(d, *path):
    """Вложенное d[a][b]..., None если по пути что-то не dict/отсутствует."""
    cur = d
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _day(meta):
    v = meta.get("date") if meta.get("date") is not None else meta.get("day")
    return str(v) if v is not None else None


def _row_daily(meta, tg_id):
    return [_day(meta), meta.get("sleep_h"), meta.get("resting_hr"), meta.get("hrv"),
            meta.get("body_battery"), meta.get("readiness"), meta.get("stress_avg"),
            meta.get("weight_kg"), json.dumps(meta.get("extra") or {}, ensure_ascii=False), tg_id]


def _row_activity(meta, note, tg_id):
    return [
        str(note), _day(meta), meta.get("sport"), _activity_id(note),
        _get(meta, "watch", "source"), _get(meta, "watch", "duration_min"),
        _get(meta, "watch", "avg_hr"), _get(meta, "watch", "max_hr"),
        _get(meta, "watch", "calories"),
        _get(meta, "endurance", "distance_km"), _get(meta, "endurance", "avg_pace_s_per_km"),
        _get(meta, "endurance", "avg_power_w"), _get(meta, "endurance", "elevation_gain_m"),
        _get(meta, "endurance", "series_ref"),
        _get(meta, "wod", "name"), _get(meta, "wod", "format"),
        _get(meta, "performed", "scaling"), _get(meta, "performed", "load_kg"),
        _get(meta, "performed", "score"), _get(meta, "performed", "rpe"),
        json.dumps(meta.get("extra") or {}, ensure_ascii=False), tg_id,
    ]


def _row_competition(meta):
    return [_day(meta), meta.get("name"), meta.get("sport"), meta.get("goal"),
            meta.get("result"), meta.get("place"), meta.get("conditions"),
            meta.get("reflection")]


def _activity_id(note: Path):
    """Из имени <day>-<sport>-<activity_id>.md вытащить activity_id, иначе None."""
    parts = note.stem.rsplit("-", 1)
    return parts[1] if len(parts) == 2 and parts[1].isdigit() else None
