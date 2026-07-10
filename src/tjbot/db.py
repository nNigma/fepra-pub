"""training.db (SQLite) — источник правды бота.

Канон-таблицы (daily/activities/competitions) берём из tj.store.build._DDL — одна
схема с анализом, который читает БД как backend="sqlite". Поверх — таблицы бота.
Запись канона идёт через insert_activity/insert_daily из объектов tj.models.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from tj.analysis import standards as _standards
from tj.analysis.nutrition import MICRO as _MICRO
from tj.analysis.progression import epley_1rm as _epley
from tj import ontology as _ontology
from tj.models import Activity, DailyMetrics
from tj.store.build import _COLS, _DDL, OWNER_TG_ID

_BOT_DDL = {
    "users": '''CREATE TABLE IF NOT EXISTS users (
        "tg_id" INTEGER PRIMARY KEY, "nick" TEXT, "height_cm" INTEGER, "weight_kg" REAL,
        "sex" TEXT, "age" INTEGER, "gym" TEXT, "level" TEXT, "created_at" TEXT )''',
    "gyms": '''CREATE TABLE IF NOT EXISTS gyms (
        "name" TEXT PRIMARY KEY, "is_default" INTEGER DEFAULT 0,
        "source_kind" TEXT, "thread_ref" TEXT )''',
    "wod_programs": '''CREATE TABLE IF NOT EXISTS wod_programs (
        "id" INTEGER PRIMARY KEY AUTOINCREMENT, "day" TEXT, "gym" TEXT, "raw_text" TEXT,
        "format" TEXT, "movements" TEXT, "source" TEXT, "confirmed" INTEGER DEFAULT 0,
        "blocks" TEXT )''',
    "goals": '''CREATE TABLE IF NOT EXISTS goals (
        "id" INTEGER PRIMARY KEY AUTOINCREMENT, "tg_id" INTEGER, "kind" TEXT, "title" TEXT,
        "exercise" TEXT, "benchmark" TEXT, "target_value" TEXT, "metric" TEXT,
        "status" TEXT DEFAULT 'active', "created_at" TEXT )''',
    "benchmarks": '''CREATE TABLE IF NOT EXISTS benchmarks (
        "name" TEXT PRIMARY KEY, "type" TEXT, "spec" TEXT,
        "rx_male" TEXT, "rx_female" TEXT, "time_cap_min" INTEGER )''',
    "disciplines": '''CREATE TABLE IF NOT EXISTS disciplines (
        "id" TEXT PRIMARY KEY, "name_ru" TEXT, "name_en" TEXT, "kind" TEXT, "unit" TEXT,
        "better" TEXT, "basis" TEXT, "ontology" TEXT, "order_idx" INTEGER )''',
    "discipline_results": '''CREATE TABLE IF NOT EXISTS discipline_results (
        "id" INTEGER PRIMARY KEY AUTOINCREMENT, "tg_id" INTEGER, "discipline" TEXT,
        "value" REAL, "reps" INTEGER, "est_1rm" REAL, "scaling" TEXT,
        "source" TEXT, "day" TEXT, "activity_id" TEXT, "created_at" TEXT )''',
    "perf_standards": '''CREATE TABLE IF NOT EXISTS perf_standards (
        "benchmark" TEXT, "level" TEXT, "sex" TEXT, "target_value" REAL, "metric" TEXT )''',
    "planned_competitions": '''CREATE TABLE IF NOT EXISTS planned_competitions (
        "id" INTEGER PRIMARY KEY AUTOINCREMENT, "day" TEXT, "name" TEXT,
        "sport" TEXT, "goal" TEXT, "status" TEXT DEFAULT 'planned' )''',
    "comp_events": '''CREATE TABLE IF NOT EXISTS comp_events (
        "id" INTEGER PRIMARY KEY AUTOINCREMENT, "name" TEXT, "city" TEXT,
        "date_start" TEXT, "date_end" TEXT, "sport" TEXT, "format" TEXT,
        "created_by" INTEGER, "created_at" TEXT )''',
    "comp_divisions": '''CREATE TABLE IF NOT EXISTS comp_divisions (
        "id" INTEGER PRIMARY KEY AUTOINCREMENT, "event_id" INTEGER,
        "name" TEXT, "field_size" INTEGER )''',
    "comp_stages": '''CREATE TABLE IF NOT EXISTS comp_stages (
        "id" INTEGER PRIMARY KEY AUTOINCREMENT, "division_id" INTEGER, "idx" INTEGER,
        "name" TEXT, "prescription" TEXT, "movements" TEXT, "fmt" TEXT,
        "source_ref" TEXT, "stage_date" TEXT )''',
    "comp_results": '''CREATE TABLE IF NOT EXISTS comp_results (
        "id" INTEGER PRIMARY KEY AUTOINCREMENT, "stage_id" INTEGER,
        "athlete" TEXT, "value" TEXT, "place" INTEGER, "points" REAL )''',
    "comp_participants": '''CREATE TABLE IF NOT EXISTS comp_participants (
        "id" INTEGER PRIMARY KEY AUTOINCREMENT, "division_id" INTEGER, "tg_id" INTEGER,
        "athlete" TEXT, "final_place" INTEGER, "total_points" REAL,
        "confirmed_total" INTEGER DEFAULT 0 )''',
    "comp_subjective": '''CREATE TABLE IF NOT EXISTS comp_subjective (
        "id" INTEGER PRIMARY KEY AUTOINCREMENT, "participant_id" INTEGER,
        "stage_id" INTEGER, "note" TEXT )''',
    "llm_cache": '''CREATE TABLE IF NOT EXISTS llm_cache (
        "id" INTEGER PRIMARY KEY AUTOINCREMENT, "tg_id" INTEGER, "kind" TEXT,
        "ref_key" TEXT, "data_hash" TEXT, "content" TEXT, "model" TEXT, "created_at" TEXT,
        "lang" TEXT DEFAULT 'ru' )''',
    "movement_aliases": '''CREATE TABLE IF NOT EXISTS movement_aliases (
        "alias" TEXT PRIMARY KEY, "canon" TEXT, "source" TEXT, "created_at" TEXT )''',
    "llm_quota": '''CREATE TABLE IF NOT EXISTS llm_quota (
        "tg_id" INTEGER, "day" TEXT, "count" INTEGER DEFAULT 0,
        PRIMARY KEY ("tg_id","day") )''',
    "claude_review": '''CREATE TABLE IF NOT EXISTS claude_review (
        "tg_id" INTEGER, "day" TEXT, "text" TEXT, "created_at" TEXT,
        "lang" TEXT DEFAULT 'ru',
        PRIMARY KEY ("tg_id","day","lang") )''',
    "next_advice": '''CREATE TABLE IF NOT EXISTS next_advice (
        "tg_id" INTEGER, "source" TEXT, "text" TEXT, "created_at" TEXT,
        "lang" TEXT DEFAULT 'ru',
        PRIMARY KEY ("tg_id","source","lang") )''',
    "wk_narrative": '''CREATE TABLE IF NOT EXISTS wk_narrative (
        "tg_id" INTEGER, "day" TEXT, "source" TEXT, "blocks" TEXT, "created_at" TEXT,
        "lang" TEXT DEFAULT 'ru',
        PRIMARY KEY ("tg_id","day","source","lang") )''',
    "meta": '''CREATE TABLE IF NOT EXISTS meta ("key" TEXT PRIMARY KEY, "value" TEXT )''',
    "water_log": '''CREATE TABLE IF NOT EXISTS water_log (
        "tg_id" INTEGER, "day" TEXT, "liters" REAL DEFAULT 0,
        PRIMARY KEY ("tg_id","day") )''',
    "meals": '''CREATE TABLE IF NOT EXISTS meals (
        "id" INTEGER PRIMARY KEY AUTOINCREMENT, "tg_id" INTEGER, "day" TEXT,
        "ts" TEXT, "foods" TEXT, "kcal" REAL, "protein_g" REAL, "fat_g" REAL,
        "carb_g" REAL, "note" TEXT, "photo_id" TEXT, "engine" TEXT,
        "quality" INTEGER, "quality_note" TEXT )''',
    "garmin_devices": '''CREATE TABLE IF NOT EXISTS garmin_devices (
        "tg_id" INTEGER, "device_id" INTEGER, "name" TEXT, "raw" TEXT,
        "updated_at" TEXT, PRIMARY KEY ("tg_id","device_id") )''',
    "garmin_accounts": '''CREATE TABLE IF NOT EXISTS garmin_accounts (
        "tg_id" INTEGER PRIMARY KEY, "email" TEXT, "connected_at" TEXT, "status" TEXT )''',
    "action_log": '''CREATE TABLE IF NOT EXISTS action_log (
        "id" INTEGER PRIMARY KEY AUTOINCREMENT, "tg_id" INTEGER, "action" TEXT, "ts" TEXT )''',
    "coach_qa": '''CREATE TABLE IF NOT EXISTS coach_qa (
        "id" INTEGER PRIMARY KEY AUTOINCREMENT, "tg_id" INTEGER, "ts" TEXT,
        "lang" TEXT DEFAULT 'ru', "question" TEXT, "answer" TEXT, "engine" TEXT )''',
}


OWNER_ID = OWNER_TG_ID


def default_db_path() -> Path:
    override = os.environ.get("KUZ_DB_PATH")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "training.db"


def connect(path) -> sqlite3.Connection:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p))
    con.row_factory = sqlite3.Row
    return con


def _migrate_pk_add_lang(con: sqlite3.Connection, table: str) -> None:
    """Добавить lang в первичный ключ таблицы (RU/EN контент сосуществует), сохранив
    данные. Идемпотентно: если lang уже в PK — ничего не делает."""
    info = list(con.execute(f'PRAGMA table_info("{table}")'))
    if not info:
        return
    pk = [r["name"] for r in info if r["pk"]]
    if "lang" in pk:
        return
    cols = [r["name"] for r in info]
    collist = ",".join(f'"{c}"' for c in cols)
    con.execute(f'ALTER TABLE "{table}" RENAME TO "{table}_old"')
    con.execute(_BOT_DDL[table])
    con.execute(f'INSERT OR IGNORE INTO "{table}" ({collist}) SELECT {collist} FROM "{table}_old"')
    con.execute(f'DROP TABLE "{table}_old"')


def init_schema(con: sqlite3.Connection) -> None:
    """Канон (как в build, но IF NOT EXISTS — БД персистентная) + таблицы бота."""
    for ddl in _DDL.values():
        con.execute(ddl.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS", 1))
    for ddl in _BOT_DDL.values():
        con.execute(ddl)
    for tbl in ("daily", "activities"):
        try:
            con.execute(f'ALTER TABLE {tbl} ADD COLUMN "extra" TEXT')
        except sqlite3.OperationalError:
            pass
    try:
        con.execute('ALTER TABLE users ADD COLUMN "lang" TEXT DEFAULT \'ru\'')
    except sqlite3.OperationalError:
        pass
    try:
        con.execute('ALTER TABLE users ADD COLUMN "astro" INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass
    try:
        con.execute('ALTER TABLE users ADD COLUMN "goal" TEXT DEFAULT \'maintain\'')
    except sqlite3.OperationalError:
        pass
    try:
        con.execute('ALTER TABLE users ADD COLUMN "city" TEXT DEFAULT \'Москва\'')
    except sqlite3.OperationalError:
        pass
    for col, typ in (("quality", "INTEGER"), ("quality_note", "TEXT")):
        try:
            con.execute(f'ALTER TABLE meals ADD COLUMN "{col}" {typ}')
        except sqlite3.OperationalError:
            pass
    try:
        con.execute('ALTER TABLE llm_cache ADD COLUMN "lang" TEXT DEFAULT \'ru\'')
    except sqlite3.OperationalError:
        pass
    try:
        con.execute('ALTER TABLE disciplines ADD COLUMN "name_en" TEXT')
    except sqlite3.OperationalError:
        pass
    try:
        con.execute('ALTER TABLE wod_programs ADD COLUMN "blocks" TEXT')
    except sqlite3.OperationalError:
        pass
    for tbl in ("claude_review", "next_advice", "wk_narrative"):
        try:
            con.execute(f'ALTER TABLE {tbl} ADD COLUMN "lang" TEXT DEFAULT \'ru\'')
        except sqlite3.OperationalError:
            pass
    for tbl in ("claude_review", "next_advice", "wk_narrative"):
        _migrate_pk_add_lang(con, tbl)
    try:
        seed_standards(con)
    except Exception:
        pass
    con.commit()


def garmin_tokenstore(tg_id) -> Path:
    return default_db_path().parent / "garmin_tokens" / str(int(tg_id))


def garmin_account_get(con: sqlite3.Connection, tg_id: int) -> dict | None:
    r = con.execute('SELECT "tg_id","email","connected_at","status" FROM garmin_accounts WHERE "tg_id"=?',
                    (int(tg_id),)).fetchone()
    return dict(r) if r else None


def garmin_account_set(con: sqlite3.Connection, tg_id: int, email: str, status: str = "ok") -> None:
    con.execute(
        'INSERT INTO garmin_accounts ("tg_id","email","connected_at","status") VALUES (?,?,?,?) '
        'ON CONFLICT("tg_id") DO UPDATE SET "email"=excluded."email", '
        '"connected_at"=excluded."connected_at", "status"=excluded."status"',
        (int(tg_id), email, datetime.now(timezone.utc).isoformat(timespec="seconds"), status))
    con.commit()


def garmin_account_set_status(con: sqlite3.Connection, tg_id: int, status: str) -> None:
    con.execute('UPDATE garmin_accounts SET "status"=? WHERE "tg_id"=?', (status, int(tg_id)))
    con.commit()


def garmin_account_delete(con: sqlite3.Connection, tg_id: int) -> None:
    con.execute('DELETE FROM garmin_accounts WHERE "tg_id"=?', (int(tg_id),))
    con.commit()


def _activity_row(a: Activity, note: str | None = None) -> tuple:
    """Объект Activity -> строка в порядке _COLS['activities']."""
    e = a.endurance
    presc = a.strength.prescription if a.strength else None
    perf = a.strength.performed if a.strength else None
    return (
        note, a.start.date().isoformat(), a.sport.value, a.activity_id, a.source,
        a.duration_min, a.avg_hr, a.max_hr, a.calories,
        e.distance_km if e else None, e.avg_pace_s_per_km if e else None,
        e.avg_power_w if e else None, e.elevation_gain_m if e else None,
        e.series_ref if e else None,
        presc.name if presc else None,
        presc.format.value if presc and presc.format else None,
        perf.scaling.value if perf and perf.scaling else None,
        perf.load_kg if perf else None,
        perf.score if perf else None,
        perf.rpe if perf else None,
        json.dumps(getattr(a, "extra", None) or {}, ensure_ascii=False),
    )


def _daily_row(m: DailyMetrics) -> tuple:
    return (m.day.isoformat(), m.sleep_h, m.resting_hr, m.hrv,
            m.body_battery, m.readiness, m.stress_avg, m.weight_kg,
            json.dumps(getattr(m, "extra", None) or {}, ensure_ascii=False))


def mark_data_changed(con: sqlite3.Connection) -> None:
    """Отметить, что тренировочные данные изменились (для флага «совет устарел»)."""
    con.execute('INSERT OR REPLACE INTO meta ("key","value") VALUES (?,?)',
                ("data_version", datetime.now(timezone.utc).isoformat(timespec="seconds")))
    con.commit()


def data_version(con: sqlite3.Connection) -> str | None:
    row = con.execute('SELECT "value" FROM meta WHERE "key"=?', ("data_version",)).fetchone()
    return row["value"] if row else None


def insert_activity(con: sqlite3.Connection, a: Activity, tg_id: int, note: str | None = None) -> None:
    """Апсерт тренировки по (tg_id, activity_id) (повторный ввод не плодит дубли)."""
    if a.activity_id:
        con.execute('DELETE FROM activities WHERE "tg_id"=? AND "activity_id"=?', (tg_id, a.activity_id))
    ph = ", ".join("?" * len(_COLS["activities"]))
    con.execute(f"INSERT INTO activities VALUES ({ph})", _activity_row(a, note) + (tg_id,))
    con.commit()
    mark_data_changed(con)


def insert_daily(con: sqlite3.Connection, m: DailyMetrics, tg_id: int) -> None:
    ph = ", ".join("?" * len(_COLS["daily"]))
    con.execute(f"INSERT OR REPLACE INTO daily VALUES ({ph})", _daily_row(m) + (tg_id,))
    con.commit()
    mark_data_changed(con)


def set_bodyweight(con: sqlite3.Connection, day: str, kg: float, tg_id: int) -> None:
    row = con.execute('SELECT day FROM daily WHERE "tg_id"=? AND "day"=?', (tg_id, day)).fetchone()
    if row:
        con.execute('UPDATE daily SET "weight_kg"=? WHERE "tg_id"=? AND "day"=?', (kg, tg_id, day))
    else:
        vals = [day] + [None] * (len(_COLS["daily"]) - 1)
        vals[_COLS["daily"].index("weight_kg")] = kg
        vals[_COLS["daily"].index("tg_id")] = tg_id
        ph = ", ".join("?" * len(_COLS["daily"]))
        con.execute(f"INSERT INTO daily VALUES ({ph})", vals)
    con.commit()
    mark_data_changed(con)


def add_meal(con: sqlite3.Connection, tg_id: int, day: str, ts: str,
             foods: list, totals: dict, note: str | None = None,
             photo_id: str | None = None, engine: str | None = None,
             quality: int | None = None, quality_note: str | None = None) -> int:
    cur = con.execute(
        'INSERT INTO meals ("tg_id","day","ts","foods","kcal","protein_g",'
        '"fat_g","carb_g","note","photo_id","engine","quality","quality_note") '
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (tg_id, day, ts, json.dumps(foods, ensure_ascii=False),
         totals.get("kcal"), totals.get("protein_g"), totals.get("fat_g"),
         totals.get("carb_g"), note, photo_id, engine, quality, quality_note))
    con.commit()
    mark_data_changed(con)
    return cur.lastrowid


def meals_for_day(con: sqlite3.Connection, tg_id: int, day: str) -> list[dict]:
    out = []
    for r in con.execute('SELECT * FROM meals WHERE "tg_id"=? AND "day"=? ORDER BY "ts"',
                         (tg_id, day)):
        m = dict(r)
        try:
            m["foods"] = json.loads(m["foods"]) if m["foods"] else []
        except ValueError:
            m["foods"] = []
        out.append(m)
    return out


def delete_meal(con: sqlite3.Connection, tg_id: int, meal_id: int) -> bool:
    cur = con.execute('DELETE FROM meals WHERE "id"=? AND "tg_id"=?', (meal_id, tg_id))
    con.commit()
    return cur.rowcount > 0


def nutrition_days(con: sqlite3.Connection, tg_id: int, days: int = 7,
                   upto_day: str | None = None) -> list[dict]:
    """Тоталы КБЖУ+микро по дням (последние `days` дней с записями, по убыванию даты)."""
    q = ('SELECT "day", COUNT(*) meals, SUM("kcal") kcal, SUM("protein_g") protein_g, '
         'SUM("fat_g") fat_g, SUM("carb_g") carb_g FROM meals WHERE "tg_id"=?')
    args: list = [tg_id]
    if upto_day:
        q += ' AND "day"<=?'
        args.append(upto_day)
    q += ' GROUP BY "day" ORDER BY "day" DESC LIMIT ?'
    args.append(days)
    rows = [dict(r) for r in con.execute(q, args)]
    if not rows:
        return rows
    day_names = [r["day"] for r in rows]
    micro = {d: {k: 0.0 for k in _MICRO} for d in day_names}
    ph = ",".join("?" * len(day_names))
    for r in con.execute(
            f'SELECT "day","foods" FROM meals WHERE "tg_id"=? AND "day" IN ({ph})',
            [tg_id, *day_names]):
        foods = json.loads(r["foods"]) if r["foods"] else []
        totals = micro[r["day"]]
        for f in foods:
            for k in _MICRO:
                totals[k] += f.get(k) or 0
    for r in rows:
        for k, v in micro[r["day"]].items():
            r[k] = round(v, 1)
    return rows


def meal_qualities_by_day(con: sqlite3.Connection, tg_id: int) -> dict[str, list[dict]]:
    """{day: [{"kcal":..,"quality":..}, ...]} по всем оценённым приёмам."""
    out: dict[str, list[dict]] = {}
    for r in con.execute(
            'SELECT "day","kcal","quality" FROM meals WHERE "tg_id"=? AND "quality" IS NOT NULL',
            (tg_id,)):
        out.setdefault(r["day"], []).append({"kcal": r["kcal"], "quality": r["quality"]})
    return out


def add_water(con: sqlite3.Connection, tg_id: int, day: str, liters: float) -> float:
    """+liters к дню (может быть отрицательным для отката). Возвращает итог дня."""
    con.execute(
        'INSERT INTO water_log ("tg_id","day","liters") VALUES (?,?,MAX(0,?)) '
        'ON CONFLICT("tg_id","day") DO UPDATE SET "liters"=MAX(0, "liters"+?)',
        (tg_id, day, liters, liters))
    con.commit()
    return water_for_day(con, tg_id, day)


def water_days(con: sqlite3.Connection, tg_id: int, limit: int = 30) -> dict:
    """{day: liters} за последние дни с записями воды."""
    return {r["day"]: round(r["liters"], 2) for r in con.execute(
        'SELECT "day","liters" FROM water_log WHERE "tg_id"=? '
        'ORDER BY "day" DESC LIMIT ?', (tg_id, limit)) if r["liters"]}


def water_for_day(con: sqlite3.Connection, tg_id: int, day: str) -> float:
    row = con.execute('SELECT "liters" FROM water_log WHERE "tg_id"=? AND "day"=?',
                      (tg_id, day)).fetchone()
    return round(row["liters"], 2) if row and row["liters"] else 0.0


def add_coach_qa(con: sqlite3.Connection, tg_id: int, ts: str, question: str,
                 answer: str, lang: str = "ru", engine: str | None = None) -> int:
    cur = con.execute(
        'INSERT INTO coach_qa ("tg_id","ts","lang","question","answer","engine") '
        "VALUES (?,?,?,?,?,?)",
        (int(tg_id), ts, lang, question, answer, engine))
    con.commit()
    return cur.lastrowid


def coach_recent(con: sqlite3.Connection, tg_id: int, limit: int = 5) -> list[dict]:
    return [dict(r) for r in con.execute(
        'SELECT "ts","lang","question","answer","engine" FROM coach_qa '
        'WHERE "tg_id"=? ORDER BY "id" DESC LIMIT ?', (int(tg_id), limit))]


def coach_count_today(con: sqlite3.Connection, tg_id: int, day: str) -> int:
    row = con.execute('SELECT COUNT(*) FROM coach_qa WHERE "tg_id"=? AND "ts" LIKE ?',
                      (int(tg_id), day + "%")).fetchone()
    return row[0] if row else 0


def save_devices(con: sqlite3.Connection, tg_id: int, devices: list) -> None:
    """Снапшот устройств Garmin (модель + capable-флаги + настройки) для
    «Тюнинга часов». Апсерт по (tg_id, device_id)."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for d in devices or []:
        did = d.get("deviceId")
        if did is None:
            continue
        con.execute(
            'INSERT INTO garmin_devices ("tg_id","device_id","name","raw","updated_at") '
            "VALUES (?,?,?,?,?) "
            'ON CONFLICT("tg_id","device_id") DO UPDATE SET "name"=excluded."name", '
            '"raw"=excluded."raw", "updated_at"=excluded."updated_at"',
            (tg_id, did, d.get("productDisplayName"),
             json.dumps(d, ensure_ascii=False), now))
    con.commit()


def load_devices(con: sqlite3.Connection, tg_id: int) -> list[dict]:
    out = []
    for r in con.execute('SELECT "raw" FROM garmin_devices WHERE "tg_id"=?', (tg_id,)):
        try:
            out.append(json.loads(r["raw"]))
        except ValueError:
            pass
    return out


def latest_weight(con: sqlite3.Connection, tg_id: int, upto_day: str | None = None):
    """Последний известный вес атлета (кг) не позже upto_day (или вообще последний)."""
    q = 'SELECT "weight_kg" FROM daily WHERE "tg_id"=? AND "weight_kg" IS NOT NULL'
    args: list = [tg_id]
    if upto_day:
        q += ' AND "day"<=?'
        args.append(upto_day)
    row = con.execute(q + ' ORDER BY "day" DESC LIMIT 1', args).fetchone()
    return row["weight_kg"] if row else None


def set_self_feel(con: sqlite3.Connection, day: str, score: int, tg_id: int) -> None:
    row = con.execute('SELECT "extra" FROM daily WHERE "tg_id"=? AND "day"=?', (tg_id, day)).fetchone()
    if row is not None:
        try:
            extra = json.loads(row["extra"]) if row["extra"] else {}
        except (ValueError, TypeError):
            extra = {}
        extra["self_feel"] = int(score)
        con.execute('UPDATE daily SET "extra"=? WHERE "tg_id"=? AND "day"=?',
                    (json.dumps(extra, ensure_ascii=False), tg_id, day))
    else:
        vals = [day] + [None] * (len(_COLS["daily"]) - 1)
        vals[_COLS["daily"].index("extra")] = json.dumps({"self_feel": int(score)}, ensure_ascii=False)
        vals[_COLS["daily"].index("tg_id")] = tg_id
        ph = ", ".join("?" * len(_COLS["daily"]))
        con.execute(f"INSERT INTO daily VALUES ({ph})", vals)
    con.commit()
    mark_data_changed(con)


def _board_source(extra_json) -> str:
    try:
        return (json.loads(extra_json) if extra_json else {}).get("board_source") or "own"
    except (ValueError, AttributeError):
        return "own"


def recent_manual_workouts(con: sqlite3.Connection, tg_id: int, limit: int = 10) -> list:
    rows = con.execute(
        'SELECT "activity_id","day","sport","wod_format","perf_score","perf_scaling",'
        '"perf_rpe","extra" FROM activities WHERE "source"=? AND "tg_id"=? ORDER BY "day" DESC LIMIT ?',
        ("manual", tg_id, limit)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["board_source"] = _board_source(r["extra"])
        out.append(d)
    return out


def get_activity(con: sqlite3.Connection, activity_id: str, tg_id: int) -> dict | None:
    r = con.execute('SELECT * FROM activities WHERE "tg_id"=? AND "activity_id"=?',
                    (tg_id, activity_id)).fetchone()
    if not r:
        return None
    d = dict(r)
    extra = json.loads(r["extra"]) if r["extra"] else {}
    d["board_source"] = extra.get("board_source") or "own"
    d["board_text"] = extra.get("board_text")
    return d


_UNSET = object()


def update_activity(con: sqlite3.Connection, activity_id: str, tg_id: int, *,
                    score=_UNSET, rpe=_UNSET, scaling=_UNSET) -> None:
    sets, vals = [], []
    if score is not _UNSET:
        sets.append('"perf_score"=?'); vals.append(score)
    if rpe is not _UNSET:
        sets.append('"perf_rpe"=?'); vals.append(rpe)
    if scaling is not _UNSET:
        sets.append('"perf_scaling"=?'); vals.append(scaling)
    if not sets:
        return
    vals.append(tg_id)
    vals.append(activity_id)
    con.execute(f'UPDATE activities SET {", ".join(sets)} WHERE "tg_id"=? AND "activity_id"=?', vals)
    con.commit()


def set_activity_board(con: sqlite3.Connection, activity_id: str, tg_id: int, raw_text: str,
                       fmt: str | None = None) -> None:
    r = con.execute('SELECT "extra" FROM activities WHERE "tg_id"=? AND "activity_id"=?',
                    (tg_id, activity_id)).fetchone()
    extra = json.loads(r["extra"]) if r and r["extra"] else {}
    extra["board_text"] = raw_text
    if fmt:
        con.execute('UPDATE activities SET "wod_format"=?, "extra"=? WHERE "tg_id"=? AND "activity_id"=?',
                    (fmt, json.dumps(extra, ensure_ascii=False), tg_id, activity_id))
    else:
        con.execute('UPDATE activities SET "extra"=? WHERE "tg_id"=? AND "activity_id"=?',
                    (json.dumps(extra, ensure_ascii=False), tg_id, activity_id))
    con.commit()


def set_activity_metcon(con: sqlite3.Connection, activity_id: str, tg_id: int, mdata) -> None:
    r = con.execute('SELECT "extra" FROM activities WHERE "tg_id"=? AND "activity_id"=?',
                    (tg_id, activity_id)).fetchone()
    extra = json.loads(r["extra"]) if r and r["extra"] else {}
    extra["metcon"] = mdata
    con.execute('UPDATE activities SET "extra"=? WHERE "tg_id"=? AND "activity_id"=?',
                (json.dumps(extra, ensure_ascii=False), tg_id, activity_id))
    con.commit()


def get_user(con: sqlite3.Connection, tg_id: int):
    return con.execute('SELECT * FROM users WHERE "tg_id" = ?', (int(tg_id),)).fetchone()


def user_lang(con: sqlite3.Connection, tg_id: int) -> str:
    row = con.execute('SELECT "lang" FROM users WHERE "tg_id"=?', (int(tg_id),)).fetchone()
    lang = (row["lang"] if row else None) or "ru"
    return lang if lang in ("ru", "en") else "ru"


def set_lang(con: sqlite3.Connection, tg_id: int, lang: str) -> None:
    if lang not in ("ru", "en"):
        raise ValueError(f"bad lang: {lang!r}")
    con.execute('UPDATE users SET "lang"=? WHERE "tg_id"=?', (lang, int(tg_id)))
    con.commit()


def user_astro(con: sqlite3.Connection, tg_id: int) -> bool:
    row = con.execute('SELECT "astro" FROM users WHERE "tg_id"=?', (int(tg_id),)).fetchone()
    return bool(row["astro"]) if row and row["astro"] is not None else False


def set_astro(con: sqlite3.Connection, tg_id: int, on: bool) -> None:
    con.execute('UPDATE users SET "astro"=? WHERE "tg_id"=?', (1 if on else 0, int(tg_id)))
    con.commit()


GOALS = ("cut", "maintain", "bulk", "recomp")


def user_goal(con: sqlite3.Connection, tg_id: int) -> str:
    row = con.execute('SELECT "goal" FROM users WHERE "tg_id"=?', (int(tg_id),)).fetchone()
    g = (row["goal"] if row else None) or "maintain"
    return g if g in GOALS else "maintain"


def set_goal(con: sqlite3.Connection, tg_id: int, goal: str) -> None:
    if goal not in GOALS:
        raise ValueError(f"bad goal: {goal!r}")
    con.execute('UPDATE users SET "goal"=? WHERE "tg_id"=?', (goal, int(tg_id)))
    con.commit()


def user_city(con: sqlite3.Connection, tg_id: int) -> str:
    row = con.execute('SELECT "city" FROM users WHERE "tg_id"=?', (int(tg_id),)).fetchone()
    return (row["city"] if row else None) or "Москва"


def set_city(con: sqlite3.Connection, tg_id: int, city: str) -> None:
    con.execute('UPDATE users SET "city"=? WHERE "tg_id"=?', (city.strip()[:60], int(tg_id)))
    con.commit()


def all_users(con: sqlite3.Connection) -> list[dict]:
    rows = con.execute('SELECT "tg_id","nick" FROM users ORDER BY "nick"').fetchall()
    return [{"tg_id": r["tg_id"], "nick": r["nick"]} for r in rows]


def gym_members(con: sqlite3.Connection, gym: str) -> list[dict]:
    rows = con.execute(
        'SELECT "tg_id","nick","sex","weight_kg" FROM users WHERE "gym"=? ORDER BY "nick"',
        (gym,)).fetchall()
    return [dict(r) for r in rows]


def save_user(con: sqlite3.Connection, tg_id: int, *, nick, height_cm, weight_kg,
              sex, gym, age=None, level=None) -> None:
    con.execute(
        'INSERT OR REPLACE INTO users '
        '("tg_id","nick","height_cm","weight_kg","sex","age","gym","level","created_at") '
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (int(tg_id), nick, height_cm, weight_kg, sex, age, gym, level,
         datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )
    con.commit()


def profile_hr_sex(con: sqlite3.Connection, tg_id: int) -> tuple[int, str]:
    """(hr_max, sex) из профиля пользователя. hr_max = 220 - age.
    Фолбэк — дефолт атлета (184, 'm'), если профиля/возраста нет."""
    u = get_user(con, tg_id)
    age = (dict(u).get("age") if u else None)
    sex = (dict(u).get("sex") if u else None) or "m"
    hr_max = (220 - int(age)) if age else 184
    return hr_max, sex


# --- программа зала (Universe) — wod_programs --------------------------------

def add_program(con: sqlite3.Connection, day, gym, raw_text, fmt="other",
                movements=None, source="photo", confirmed=0, blocks=None) -> int:
    """blocks — выверенные Клодом блоки шаблона результатов (JSON); NULL, если
    проверка не прошла — потребители тогда перепарсивают raw_text."""
    cur = con.execute(
        'INSERT INTO wod_programs '
        '("day","gym","raw_text","format","movements","source","confirmed","blocks") '
        "VALUES (?,?,?,?,?,?,?,?)",
        (day, gym, raw_text, fmt, json.dumps(movements or [], ensure_ascii=False),
         source, confirmed,
         json.dumps(blocks, ensure_ascii=False) if blocks else None),
    )
    con.commit()
    return cur.lastrowid


def get_program(con: sqlite3.Connection, day, gym=None, confirmed_only=True):
    q, args = 'SELECT * FROM wod_programs WHERE "day" = ?', [day]
    if gym:
        q += ' AND "gym" = ?'
        args.append(gym)
    if confirmed_only:
        q += ' AND "confirmed" = 1'
    q += ' ORDER BY "id" DESC LIMIT 1'
    return con.execute(q, args).fetchone()


def get_program_by_id(con: sqlite3.Connection, prog_id):
    return con.execute('SELECT * FROM wod_programs WHERE "id" = ?', (prog_id,)).fetchone()


def confirm_program(con: sqlite3.Connection, prog_id, raw_text=None) -> None:
    if raw_text is not None:
        con.execute('UPDATE wod_programs SET "confirmed" = 1, "raw_text" = ? WHERE "id" = ?',
                    (raw_text, prog_id))
    else:
        con.execute('UPDATE wod_programs SET "confirmed" = 1 WHERE "id" = ?', (prog_id,))
    con.commit()


def add_alias(con: sqlite3.Connection, alias: str, canon: str, source: str = "manual") -> None:
    con.execute(
        'INSERT OR REPLACE INTO movement_aliases ("alias","canon","source","created_at") '
        "VALUES (?,?,?,?)",
        (alias.strip().lower(), canon.strip().lower(), source,
         datetime.now(timezone.utc).isoformat(timespec="seconds")))
    con.commit()


def load_aliases(con: sqlite3.Connection) -> dict:
    return {r["alias"]: r["canon"]
            for r in con.execute('SELECT "alias","canon" FROM movement_aliases').fetchall()}


def last_program(con: sqlite3.Connection, gym: str = "Universe"):
    return con.execute(
        'SELECT * FROM wod_programs WHERE "gym"=? AND "confirmed"=1 '
        'ORDER BY "day" DESC LIMIT 1', (gym,)).fetchone()


def create_event(con, *, name, city, date_start, date_end, sport, fmt, created_by) -> int:
    cur = con.execute(
        'INSERT INTO comp_events ("name","city","date_start","date_end","sport","format","created_by","created_at")'
        ' VALUES (?,?,?,?,?,?,?,?)',
        (name, city, date_start, date_end, sport, fmt, int(created_by),
         datetime.now(timezone.utc).isoformat(timespec="seconds")))
    con.commit(); return cur.lastrowid

def add_division(con, event_id, *, name, field_size=None) -> int:
    cur = con.execute('INSERT INTO comp_divisions ("event_id","name","field_size") VALUES (?,?,?)',
                      (event_id, name, field_size))
    con.commit(); return cur.lastrowid

def add_participant(con, division_id, *, tg_id, athlete=None) -> int:
    cur = con.execute('INSERT INTO comp_participants ("division_id","tg_id","athlete") VALUES (?,?,?)',
                      (division_id, int(tg_id), athlete))
    con.commit(); return cur.lastrowid

def get_event(con, event_id) -> dict | None:
    ev = con.execute('SELECT * FROM comp_events WHERE "id"=?', (event_id,)).fetchone()
    if not ev:
        return None
    out = dict(ev)
    out["divisions"] = [dict(d) for d in
        con.execute('SELECT * FROM comp_divisions WHERE "event_id"=?', (event_id,)).fetchall()]
    return out

def list_competitions(con, tg_id) -> list[dict]:
    rows = con.execute(
        'SELECT e."id", e."name", e."city", e."date_start", e."date_end",'
        ' MIN(d."id") AS "division_id"'
        ' FROM comp_events e'
        ' JOIN comp_divisions d ON d."event_id"=e."id"'
        ' JOIN comp_participants p ON p."division_id"=d."id" AND p."tg_id"=?'
        ' GROUP BY e."id"'
        ' ORDER BY e."date_start" DESC, e."id" DESC', (int(tg_id),)).fetchall()
    return [dict(r) for r in rows]


def list_other_competitions(con, tg_id) -> list[dict]:
    rows = con.execute(
        'SELECT e."id", e."name", e."city", e."date_start", e."date_end",'
        ' MIN(d."id") AS "division_id"'
        ' FROM comp_events e'
        ' JOIN comp_divisions d ON d."event_id"=e."id"'
        ' WHERE NOT EXISTS ('
        '   SELECT 1 FROM comp_participants p'
        '   JOIN comp_divisions d2 ON d2."id"=p."division_id"'
        '   WHERE d2."event_id"=e."id" AND p."tg_id"=?)'
        ' GROUP BY e."id"'
        ' ORDER BY e."date_start" DESC, e."id" DESC', (int(tg_id),)).fetchall()
    return [dict(r) for r in rows]


def find_events_by_city_date(con, *, city, date) -> list[dict]:
    rows = con.execute(
        'SELECT * FROM comp_events WHERE ? BETWEEN "date_start" AND COALESCE("date_end","date_start")',
        (date,)).fetchall()
    needle = city.strip().lower()
    return [dict(r) for r in rows if r["city"].lower() == needle]

def add_stage(con, division_id, *, idx, name, prescription, movements=None,
              fmt="text", source_ref=None, stage_date=None) -> int:
    cur = con.execute(
        'INSERT INTO comp_stages ("division_id","idx","name","prescription","movements","fmt","source_ref","stage_date")'
        ' VALUES (?,?,?,?,?,?,?,?)',
        (division_id, idx, name, prescription,
         json.dumps(movements or [], ensure_ascii=False), fmt, source_ref, stage_date))
    con.commit(); return cur.lastrowid

def add_comp_result(con, stage_id, *, athlete, value, place=None, points=None) -> int:
    cur = con.execute('INSERT INTO comp_results ("stage_id","athlete","value","place","points") VALUES (?,?,?,?,?)',
                      (stage_id, athlete, value, place, points if points is not None else place))
    con.commit(); return cur.lastrowid

def get_stages(con, division_id) -> list[dict]:
    out = []
    for s in con.execute('SELECT * FROM comp_stages WHERE "division_id"=? ORDER BY "idx"', (division_id,)).fetchall():
        d = dict(s); d["movements"] = json.loads(s["movements"] or "[]")
        d["results"] = [dict(r) for r in
            con.execute('SELECT * FROM comp_results WHERE "stage_id"=? ORDER BY "place"', (s["id"],)).fetchall()]
        out.append(d)
    return out

def set_total(con, participant_id, *, final_place, total_points, confirmed=1) -> None:
    con.execute('UPDATE comp_participants SET "final_place"=?, "total_points"=?, "confirmed_total"=? WHERE "id"=?',
                (final_place, total_points, confirmed, participant_id))
    con.commit()

def suggest_total(con, division_id, athlete) -> dict:
    sums = {}
    for s in con.execute('SELECT id FROM comp_stages WHERE "division_id"=?', (division_id,)).fetchall():
        for r in con.execute('SELECT athlete, points FROM comp_results WHERE "stage_id"=?', (s["id"],)).fetchall():
            if r["points"] is not None:
                sums[r["athlete"]] = sums.get(r["athlete"], 0) + r["points"]
    if athlete not in sums:
        return {"total_points": None, "final_place": None}
    ordered = sorted(sums.items(), key=lambda kv: kv[1])
    place = [a for a, _ in ordered].index(athlete) + 1
    return {"total_points": sums[athlete], "final_place": place}


def seed_standards(con: sqlite3.Connection) -> None:
    discs = _standards.disciplines()
    for d in discs.values():
        con.execute(
            'INSERT OR REPLACE INTO disciplines VALUES (?,?,?,?,?,?,?,?,?)',
            (d["id"], d["name_ru"], d.get("name_en"), d["kind"], d["unit"], d["better"],
             d["basis"], d.get("ontology"), d["order"]))
    tiers = _standards.tiers()
    con.execute("DELETE FROM perf_standards")
    for d in discs.values():
        for sex in ("m", "f"):
            for i, lvl in enumerate(tiers):
                con.execute(
                    'INSERT INTO perf_standards ("benchmark","level","sex","target_value","metric") '
                    'VALUES (?,?,?,?,?)',
                    (d["id"], lvl, sex, d["thresholds"][sex][i], d["basis"]))
    keep = list(discs.keys())
    ph = ",".join("?" * len(keep))
    con.execute(f'DELETE FROM disciplines WHERE id NOT IN ({ph})', keep)
    con.commit()


def add_result(con, tg_id, discipline, value, source, day, reps=None,
               est_1rm=None, scaling=None, activity_id=None, created_at=None):
    con.execute(
        'INSERT INTO discipline_results '
        '("tg_id","discipline","value","reps","est_1rm","scaling","source","day","activity_id","created_at") '
        'VALUES (?,?,?,?,?,?,?,?,?,?)',
        (tg_id, discipline, value, reps, est_1rm, scaling, source, day, activity_id, created_at))
    con.commit()


def add_goal(con, tg_id, kind, discipline, target_value, metric, title, created_at=None):
    cur = con.execute(
        'INSERT INTO goals ("tg_id","kind","title","exercise","benchmark","target_value","metric","status","created_at") '
        'VALUES (?,?,?,?,?,?,?,?,?)',
        (tg_id, kind, title, discipline, discipline, str(target_value), metric, "active", created_at))
    con.commit()
    return cur.lastrowid


def active_goals(con, tg_id) -> list:
    rows = con.execute(
        "SELECT * FROM goals WHERE tg_id=? AND status='active' ORDER BY id", (tg_id,)).fetchall()
    return [dict(r) for r in rows]


def archive_goal(con, goal_id) -> None:
    con.execute("UPDATE goals SET status='archived' WHERE id=?", (goal_id,))
    con.commit()


def complete_goal(con, goal_id) -> None:
    con.execute("UPDATE goals SET status='done' WHERE id=?", (goal_id,))
    con.commit()


def _resolve_lift_disciplines(wod_name: str) -> set[str]:
    discs = _standards.disciplines()
    onto_to_disc = {d["ontology"]: d["id"] for d in discs.values()
                    if d["kind"] == "lift" and d.get("ontology")}
    norm = " ".join(w.strip(" .,:;()") for w in
                    wod_name.lower().replace("+", " ").replace("-", " ").split())
    text = f" {norm} "
    pairs = []
    for mid in onto_to_disc:
        for alias in _ontology.MOVEMENTS.get(mid, []):
            pairs.append((alias, mid))
    pairs.sort(key=lambda p: len(p[0].split()), reverse=True)
    found = set()
    for alias, mid in pairs:
        needle = f" {alias} "
        if needle in text:
            found.add(onto_to_disc[mid])
            text = text.replace(needle, " ")
    return found


def autopick_from_activity(con, tg_id, wod_name, load_kg, day, activity_id) -> int:
    if not wod_name or not load_kg:
        return 0
    disc_ids = _resolve_lift_disciplines(wod_name)
    if len(disc_ids) != 1:
        return 0
    did = next(iter(disc_ids))
    est = _epley(float(load_kg), 1)
    if activity_id:
        con.execute('DELETE FROM discipline_results WHERE activity_id=? AND "tg_id"=? AND source=\'auto\'',
                    (activity_id, tg_id))
    add_result(con, tg_id=tg_id, discipline=did, value=load_kg, reps=1,
               est_1rm=est, source="auto", day=day, activity_id=activity_id)
    return 1


def lifts_to_results(con, parsed) -> list:
    """[{movement, weight_kg, reps}] -> [{discipline, name, weight, reps, est_1rm}].
    Движение -> канон (онтология+алиасы) -> лифт-дисциплина; мусор/0/не-лифт отсеиваются."""
    aliases = load_aliases(con)
    discs = _standards.disciplines()
    onto_to_disc = {d["ontology"]: d["id"] for d in discs.values()
                    if d["kind"] == "lift" and d.get("ontology")}
    out = []
    for item in parsed or []:
        if not isinstance(item, dict):
            continue
        try:
            weight = float(item.get("weight_kg"))
            reps = int(item.get("reps") if item.get("reps") is not None else 1)
        except (TypeError, ValueError):
            continue
        if weight <= 0 or reps <= 0:
            continue
        movement = str(item.get("movement") or "")
        # точный алиас, иначе — скан канонов внутри описательной фразы (последний лифт;
        # для комплекса «взятие+толчок» это clean_and_jerk, а не просто clean)
        canon = _ontology.resolve(movement, aliases)
        did = onto_to_disc.get(canon)
        if not did:
            lift_canons = [c for c in _ontology.find(movement, aliases) if c in onto_to_disc]
            # комплекс «взятие + толчок» = clean_and_jerk (толчок задаёт движение)
            if "clean_and_jerk" in lift_canons:
                did = onto_to_disc["clean_and_jerk"]
            elif lift_canons:
                did = onto_to_disc.get(lift_canons[-1])
        if not did:
            continue
        out.append({"discipline": did, "name": discs[did]["name_ru"],
                    "weight": weight, "reps": reps, "est_1rm": _epley(weight, reps)})
    return out


def split_lifts(con, parsed):
    """[{movement,weight_kg,reps}] -> (resolved, ambiguous).
    resolved: [{discipline,name,weight,reps,est_1rm}] — конкретный лифт.
    ambiguous: [{family,weight,reps,movement}] — общий рывок/взятие, нужен вопрос."""
    aliases = load_aliases(con)
    discs = _standards.disciplines()
    onto_to_disc = {d["ontology"]: d["id"] for d in discs.values()
                    if d["kind"] == "lift" and d.get("ontology")}
    resolved, ambiguous = [], []
    for item in parsed or []:
        if not isinstance(item, dict):
            continue
        try:
            weight = float(item.get("weight_kg"))
            reps = int(item.get("reps") if item.get("reps") is not None else 1)
        except (TypeError, ValueError):
            continue
        if weight <= 0 or reps <= 0:
            continue
        movement = str(item.get("movement") or "")
        canon = _ontology.resolve(movement, aliases)
        if canon is None:
            found = _ontology.find(movement, aliases)
            lift_canons = [c for c in found if c in onto_to_disc]
            fam_canons = [c for c in found if _ontology.variant_family(c)]
            canon = lift_canons[-1] if lift_canons else (fam_canons[-1] if fam_canons else None)
        did = onto_to_disc.get(canon)
        fam = _ontology.variant_family(canon)
        if did:
            resolved.append({"discipline": did, "name": discs[did]["name_ru"],
                             "weight": weight, "reps": reps, "est_1rm": _epley(weight, reps)})
        elif fam:
            ambiguous.append({"family": fam, "weight": weight, "reps": reps, "movement": movement})
    return resolved, ambiguous


def record_lift_results(con, tg_id, results, day, activity_id) -> int:
    """Запись лифтов из тренировки в discipline_results (source=auto), дедуп по activity_id."""
    if activity_id:
        con.execute('DELETE FROM discipline_results WHERE activity_id=? AND "tg_id"=? AND source=\'auto\'',
                    (activity_id, tg_id))
    for r in results:
        add_result(con, tg_id=tg_id, discipline=r["discipline"], value=r["weight"],
                   reps=r["reps"], est_1rm=r["est_1rm"], source="auto", day=day,
                   activity_id=activity_id)
    con.commit()
    return len(results)


def llm_cache_get(con, tg_id, kind, ref_key, data_hash, lang="ru") -> dict | None:
    """-> {"text", "engine"} | None. engine — кто писал разбор (claude/gemini)."""
    row = con.execute(
        'SELECT content, model FROM llm_cache WHERE tg_id=? AND kind=? AND ref_key=? AND data_hash=? AND lang=?',
        (tg_id, kind, ref_key, data_hash, lang)).fetchone()
    return {"text": row["content"], "engine": row["model"]} if row else None


def llm_cache_get_latest(con, tg_id, kind, ref_key, lang="ru") -> dict | None:
    """Разбор позиции игнорируя data_hash (строка одна на kind+ref+lang).
    -> {"text","engine","data_hash"} | None. Для персистентного показа."""
    row = con.execute(
        'SELECT content, model, data_hash FROM llm_cache WHERE tg_id=? AND kind=? AND ref_key=? AND lang=?',
        (tg_id, kind, ref_key, lang)).fetchone()
    return {"text": row["content"], "engine": row["model"], "data_hash": row["data_hash"]} if row else None


def llm_cache_delete(con, tg_id, kind, ref_key) -> None:
    """Стереть Gemini-кэш разбора (все языки) — Claude-разбор перекрывает Gemini."""
    con.execute('DELETE FROM llm_cache WHERE tg_id=? AND kind=? AND ref_key=?',
                (int(tg_id), kind, ref_key))
    con.commit()


def llm_cache_put(con, tg_id, kind, ref_key, data_hash, content, model, created_at=None, lang="ru") -> None:
    con.execute('DELETE FROM llm_cache WHERE tg_id=? AND kind=? AND ref_key=? AND lang=?',
                (tg_id, kind, ref_key, lang))
    con.execute(
        'INSERT INTO llm_cache ("tg_id","kind","ref_key","data_hash","content","model","created_at","lang") '
        'VALUES (?,?,?,?,?,?,?,?)',
        (tg_id, kind, ref_key, data_hash, content, model, created_at, lang))
    con.commit()


def llm_quota_used(con, tg_id, day) -> int:
    """Сколько обращений к ИИ сделал пользователь за конкретный день (0, если нет)."""
    row = con.execute(
        'SELECT count FROM llm_quota WHERE tg_id=? AND day=?', (int(tg_id), day)).fetchone()
    return int(row["count"]) if row else 0


def llm_quota_bump(con, tg_id, day, n=1) -> int:
    """Инкремент суточного счётчика (UPSERT). Возвращает новое значение."""
    con.execute(
        'INSERT INTO llm_quota ("tg_id","day","count") VALUES (?,?,?) '
        'ON CONFLICT("tg_id","day") DO UPDATE SET count = count + ?',
        (int(tg_id), day, n, n))
    con.commit()
    return llm_quota_used(con, tg_id, day)


def claude_review_get(con, tg_id, day, lang="ru") -> str | None:
    row = con.execute(
        'SELECT text FROM claude_review WHERE tg_id=? AND day=? AND lang=?',
        (int(tg_id), day, lang)).fetchone()
    return row["text"] if row else None


def claude_review_put(con, tg_id, day, text, created_at=None, lang="ru") -> None:
    con.execute('DELETE FROM claude_review WHERE "tg_id"=? AND "day"=? AND "lang"=?',
                (int(tg_id), day, lang))
    con.execute(
        'INSERT INTO claude_review ("tg_id","day","text","created_at","lang") VALUES (?,?,?,?,?)',
        (int(tg_id), day, text, created_at, lang))
    con.commit()


def claude_review_put_many(con, tg_ids, day, text, created_at=None, lang="ru") -> None:
    for tid in tg_ids:
        claude_review_put(con, tid, day, text, created_at, lang=lang)


def claude_reviews_pending(con, tg_id, lang="ru") -> list[dict]:
    rows = con.execute(
        'SELECT DISTINCT a."day", a."sport" FROM activities a '
        'WHERE a."tg_id"=? AND a."day" NOT IN '
        '(SELECT "day" FROM claude_review WHERE "tg_id"=? AND "lang"=?) '
        'ORDER BY a."day" DESC', (int(tg_id), int(tg_id), lang)).fetchall()
    return [{"day": r["day"], "sport": r["sport"]} for r in rows]


def next_advice_put(con, tg_id, source, text, created_at=None, lang="ru") -> None:
    created_at = created_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    con.execute('DELETE FROM next_advice WHERE "tg_id"=? AND "source"=? AND "lang"=?',
                (int(tg_id), source, lang))
    con.execute(
        'INSERT INTO next_advice ("tg_id","source","text","created_at","lang") VALUES (?,?,?,?,?)',
        (int(tg_id), source, text, created_at, lang))
    con.commit()


def next_advice_put_many(con, tg_ids, source, text, created_at=None, lang="ru") -> None:
    for tid in tg_ids:
        next_advice_put(con, tid, source, text, created_at, lang=lang)


def next_advice_get(con, tg_id, lang="ru") -> dict | None:
    """Совет с приоритетом claude > gemini. None, если ничего не записано."""
    row = con.execute(
        'SELECT "source","text","created_at" FROM next_advice WHERE tg_id=? AND lang=? '
        "ORDER BY CASE \"source\" WHEN 'claude' THEN 0 ELSE 1 END LIMIT 1",
        (int(tg_id), lang)).fetchone()
    return {"source": row["source"], "text": row["text"],
            "created_at": row["created_at"]} if row else None


def wk_narrative_put(con, tg_id, day, source, blocks, created_at=None, lang="ru") -> None:
    con.execute('DELETE FROM wk_narrative WHERE "tg_id"=? AND "day"=? AND "source"=? AND "lang"=?',
                (int(tg_id), day, source, lang))
    con.execute(
        'INSERT INTO wk_narrative ("tg_id","day","source","blocks","created_at","lang") VALUES (?,?,?,?,?,?)',
        (int(tg_id), day, source, json.dumps(blocks, ensure_ascii=False), created_at, lang))
    con.commit()


def wk_narrative_put_many(con, tg_ids, day, source, blocks, created_at=None, lang="ru") -> None:
    for tid in tg_ids:
        wk_narrative_put(con, tid, day, source, blocks, created_at, lang=lang)


def wk_narrative_get(con, tg_id, day, lang="ru") -> dict | None:
    """Блоки разбора тренировки с приоритетом claude > gemini. None, если нет."""
    row = con.execute(
        'SELECT "source","blocks" FROM wk_narrative WHERE tg_id=? AND day=? AND lang=? '
        "ORDER BY CASE \"source\" WHEN 'claude' THEN 0 ELSE 1 END LIMIT 1",
        (int(tg_id), day, lang)).fetchone()
    if not row:
        return None
    try:
        blocks = json.loads(row["blocks"])
    except Exception:
        return None
    return {"source": row["source"], "blocks": blocks}


def best_results(con, tg_id) -> dict:
    discs = _standards.disciplines()
    out: dict[str, dict] = {}
    rows = con.execute(
        'SELECT * FROM discipline_results WHERE tg_id=?', (tg_id,)).fetchall()
    for r in rows:
        did = r["discipline"]
        meta = discs.get(did)
        if not meta:
            continue
        key = "value"
        cur = r[key]
        if cur is None:
            continue
        prev = out.get(did)
        better_higher = meta["better"] == "higher"
        if prev is None or (cur > prev[key] if better_higher else cur < prev[key]) \
           or (cur == prev[key] and r["source"] == "manual"):
            out[did] = {"est_1rm": r["est_1rm"], "value": r["value"],
                        "reps": r["reps"], "source": r["source"], "day": r["day"]}
    return out


def log_action(con: sqlite3.Connection, tg_id: int, action: str, ts: str | None = None) -> None:
    con.execute(
        'INSERT INTO action_log ("tg_id","action","ts") VALUES (?,?,?)',
        (int(tg_id), action, ts or datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )
    con.commit()


def action_counts(con: sqlite3.Connection, since: str | None = None) -> list[dict]:
    sql = 'SELECT "tg_id","action", COUNT(*) AS n FROM action_log'
    args: tuple = ()
    if since:
        sql += ' WHERE "ts" >= ?'
        args = (since,)
    sql += ' GROUP BY "tg_id","action"'
    rows = con.execute(sql, args).fetchall()
    return [{"tg_id": r["tg_id"], "action": r["action"], "n": r["n"]} for r in rows]
