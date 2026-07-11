"""Синхронизация свежих дней Garmin -> training.db.

Тянет только НОВЫЕ дни (после последней даты в daily) и НОВЫЕ активности
(по activity_id) — не перетирает инжект богатых полей и ручные записи.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def _owner_legacy_tokenstores() -> list[Path]:
    return [Path.home() / ".garminconnect", Path("/root/.garminconnect")]


def ensure_owner_token(tg_id, tokenstore) -> None:
    from . import db as botdb
    if int(tg_id) != int(botdb.OWNER_ID):
        return
    dest = Path(tokenstore)
    if dest.exists() and any(dest.iterdir()):
        return
    for src in _owner_legacy_tokenstores():
        if src.exists() and any(src.iterdir()):
            dest.mkdir(parents=True, exist_ok=True)
            for f in src.iterdir():
                if f.is_file():
                    dest.joinpath(f.name).write_bytes(f.read_bytes())
            return


def _adapter_for(tg_id, tokenstore):
    ensure_owner_token(tg_id, tokenstore)
    from tj import config as cfgmod
    from tj.adapters.garmin import GarminAdapter
    cfg = cfgmod.load_config(_root() / "config.toml")
    tz = cfgmod.timezone(cfg)
    return GarminAdapter("", "", str(tokenstore), tz,
                         raw_dir=str(_root() / "raw"), data_dir=str(_root() / "data"))


def _extract_hr_series(details: dict, cap: int = 1600) -> list[list[int]]:
    """get_activity_details -> [[elapsed_sec, hr], ...] (посекундная линия для графика)."""
    descs = details.get("metricDescriptors") or []
    idx = {d.get("key"): d.get("metricsIndex") for d in descs if isinstance(d, dict)}
    hr_i = idx.get("directHeartRate")
    t_i = idx.get("sumElapsedDuration")
    ts_i = idx.get("directTimestamp")
    if hr_i is None:
        return []
    rows = details.get("activityDetailMetrics") or []
    ser, t0 = [], None
    for r in rows:
        m = r.get("metrics") if isinstance(r, dict) else None
        if not isinstance(m, list) or hr_i >= len(m) or m[hr_i] is None:
            continue
        if t_i is not None and t_i < len(m) and m[t_i] is not None:
            t = m[t_i]
        elif ts_i is not None and ts_i < len(m) and m[ts_i] is not None:
            if t0 is None:
                t0 = m[ts_i]
            t = (m[ts_i] - t0) / 1000
        else:
            t = len(ser)
        ser.append([int(round(t)), int(round(m[hr_i]))])
    if len(ser) > cap:
        step = (len(ser) + cap - 1) // cap
        ser = ser[::step]
    return ser


def dump_hr_series(client, activity_id, root: Path | None = None, tg_id=None) -> str | None:
    """Дотянуть посекундный HR активности -> data/hr_<id>.json, вернуть относительный ref."""
    root = root or _root()
    try:
        details = client.get_activity_details(str(activity_id), maxchart=2000)
    except Exception:
        return None
    ser = _extract_hr_series(details or {})
    if len(ser) < 2:
        return None
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    name = f"hr_{tg_id}_{activity_id}.json" if tg_id is not None else f"hr_{activity_id}.json"
    (data_dir / name).write_text(json.dumps(ser, ensure_ascii=False), encoding="utf-8")
    return f"data/{name}"


def last_watch_date(con, tg_id) -> str | None:
    r = con.execute('SELECT max("day") AS d FROM daily WHERE "tg_id"=?', (tg_id,)).fetchone()
    return r["d"] if r and r["d"] else None


def _heal_missing_daily(con, botdb, ad, tg_id, since: date, until: date) -> int:
    # Дни с пропущенными метриками СНА (сон/HRV/готовность приходят из Garmin позже
    # непрерывных). Ловим и ЧАСТИЧНЫЕ дни (напр. есть resting_hr, но нет сна) — иначе
    # утренний синк до финализации сна оставляет день навсегда без готовности.
    rows = con.execute(
        'SELECT "day" FROM daily WHERE "tg_id"=? AND "day" BETWEEN ? AND ? '
        'AND ("readiness" IS NULL OR "hrv" IS NULL OR "sleep_h" IS NULL) ORDER BY "day"',
        (tg_id, since.isoformat(), until.isoformat())).fetchall()
    healed = 0
    for r in rows:
        m = ad.fetch_daily(date.fromisoformat(r["day"]))
        if not m or not any(v is not None for v in (m.readiness, m.hrv, m.sleep_h)):
            continue                       # сон ещё не готов у Garmin — не трогаем
        con.execute(
            'UPDATE daily SET "sleep_h"=?, "resting_hr"=?, "hrv"=?, "body_battery"=?, '
            '"readiness"=?, "stress_avg"=?, "extra"=? WHERE "tg_id"=? AND "day"=?',
            (m.sleep_h, m.resting_hr, m.hrv, m.body_battery, m.readiness,
             m.stress_avg, json.dumps(m.extra or {}, ensure_ascii=False), tg_id, r["day"]))
        healed += 1
    if healed:
        con.commit()
        botdb.mark_data_changed(con)
    return healed


def sync_recent(db_path, tg_id, tokenstore, upto: date | None = None,
                start: date | None = None, heal_lookback: int = 10) -> dict:
    from . import db as botdb
    con = botdb.connect(db_path)
    try:
        last = last_watch_date(con, tg_id)
        upto = upto or date.today()
        if start is None:
            start = (date.fromisoformat(last) + timedelta(days=1)) if last else upto - timedelta(days=7)
        ad = _adapter_for(tg_id, tokenstore)
        n_daily = 0
        d = start
        while d <= upto:
            m = ad.fetch_daily(d)
            if m:
                botdb.insert_daily(con, m, tg_id=tg_id)
                n_daily += 1
            d += timedelta(days=1)
        existing = {r["activity_id"] for r in
                    con.execute('SELECT "activity_id" FROM activities WHERE "tg_id"=?', (tg_id,)).fetchall()}
        root = _root()
        client = None
        n_act = 0
        for a in ad.fetch_activities(start - timedelta(days=3), upto):
            if a.activity_id and a.activity_id not in existing:
                if client is None:
                    client = ad._login()
                ref = dump_hr_series(client, a.activity_id, root, tg_id=tg_id)
                if ref:
                    a.extra = {**(a.extra or {}), "hr_series_ref": ref}
                botdb.insert_activity(con, a, tg_id=tg_id)
                n_act += 1
        n_healed = 0
        if heal_lookback:
            n_healed = _heal_missing_daily(con, botdb, ad, tg_id,
                                           upto - timedelta(days=heal_lookback), upto)
        try:                    # снапшот устройств для «Тюнинга часов» — не критичен
            botdb.save_devices(con, tg_id, ad.fetch_devices())
        except Exception:
            pass
        return {"days": n_daily, "activities": n_act, "healed": n_healed,
                "last": last_watch_date(con, tg_id),
                "from": start.isoformat(), "to": upto.isoformat()}
    finally:
        con.close()


def sync_history(db_path, tg_id, tokenstore, days: int = 60,
                 upto: date | None = None) -> dict:
    """Принудительный бэкфилл: тянет последние `days` дней, игнорируя last-дату.
    Идемпотентно — insert_daily = INSERT OR REPLACE, активности по activity_id."""
    upto = upto or date.today()
    return sync_recent(db_path, tg_id, tokenstore, upto=upto,
                       start=upto - timedelta(days=days))


def backfill_hr_series(db_path, tg_id, tokenstore, root: Path | None = None) -> dict:
    """Разовый проход: дотянуть посекундный HR для garmin-активностей без серии."""
    from . import db as botdb
    root = root or _root()
    con = botdb.connect(db_path)
    try:
        rows = con.execute(
            'SELECT "activity_id","extra" FROM activities WHERE "source"=? AND "tg_id"=? '
            'AND "activity_id" IS NOT NULL', ("garmin", tg_id)).fetchall()
        client = None
        done, skipped = [], []
        for r in rows:
            extra = json.loads(r["extra"]) if r["extra"] else {}
            ref = extra.get("hr_series_ref")
            if ref and (root / ref).exists():
                continue
            if client is None:
                client = _adapter_for(tg_id, tokenstore)._login()
            new_ref = dump_hr_series(client, r["activity_id"], root, tg_id=tg_id)
            if not new_ref:
                skipped.append(r["activity_id"])
                continue
            extra["hr_series_ref"] = new_ref
            con.execute('UPDATE activities SET "extra"=? WHERE "tg_id"=? AND "activity_id"=?',
                        (json.dumps(extra, ensure_ascii=False), tg_id, r["activity_id"]))
            con.commit()
            done.append(r["activity_id"])
        return {"filled": done, "skipped": skipped}
    finally:
        con.close()


if __name__ == "__main__":
    import sys
    from . import db as botdb
    if len(sys.argv) > 1 and sys.argv[1] == "backfill":
        print(backfill_hr_series(botdb.default_db_path(), botdb.OWNER_ID, botdb.garmin_tokenstore(botdb.OWNER_ID)))
    else:
        print(sync_recent(botdb.default_db_path(), botdb.OWNER_ID, botdb.garmin_tokenstore(botdb.OWNER_ID)))
