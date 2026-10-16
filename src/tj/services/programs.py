"""Сервис программ: каталог, запись на программу, сессии, подходы, финиш.

Чистые функции над sqlite-соединением: без HTTP и Telegram, время — параметром (`today`, `now`).
Под роуты (следующий шаг):
  GET  /api/programs/tree                      -> tree
  GET  /api/programs/{slug}                    -> get_program
  POST /api/programs/{slug}/enroll             -> enroll
  GET  /api/enrollments                        -> list_enrollments
  GET  /api/enrollments/{id}/today             -> today_session
  GET  /api/sessions/{id}                      -> get_session
  PUT  /api/sessions/{id}/sets/{set_id}        -> log_set
  POST /api/sessions/{id}/checkin              -> submit_checkin
  POST /api/sessions/{id}/finish               -> finish_session
  POST /api/enrollments/{id}/refresh-base      -> refresh_base
Ошибки — подклассы ProgramError с полем `code` (not_found/conflict/unavailable/closed/needs_input/invalid).
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from tj import ontology
from tj.analysis import standards
from tj.services import program_engine as eng
from tj.services.program_engine import (Conflict, NeedsInput, NotFound, ProgramError, SessionClosed,
                                        Unavailable)

CATALOG_PATH = eng.PROGRAMS_DIR / "catalog.json"
REFRESH_STEP_KG = 2.5     # предложение «обновить опорные?» — от +2.5 кг к базе
_NS = uuid.UUID("0b8f4d3e-7a21-4c9b-8e55-3a6d1f2c9b70")


def _iso(now=None) -> str:
    n = now or datetime.now(timezone.utc)
    if n.tzinfo is not None:
        n = n.astimezone(timezone.utc)
    return n.replace(tzinfo=None).isoformat(timespec="seconds") + "Z"


def _j(s, default):
    try:
        return json.loads(s) if s else default
    except ValueError:
        return default


def _fmt(kg) -> str:
    return eng._fmt(kg)


# --------------------------------------------------------------------------- каталог

def seed_catalog(con: sqlite3.Connection, path: Path | None = None) -> int:
    """Идемпотентный сид дерева из catalog.json: upsert по slug (название, родитель, статус, порядок,
    шаблон обновляются из файла). Возвращает число узлов."""
    data = json.loads((path or CATALOG_PATH).read_text(encoding="utf-8"))
    nodes = data["nodes"]
    for n in nodes:
        con.execute(
            "INSERT INTO program_nodes (id,parent_id,kind,slug,title_ru,title_en,status,sort,template_slug) "
            "VALUES (?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(slug) DO UPDATE SET parent_id=excluded.parent_id, kind=excluded.kind, "
            "title_ru=excluded.title_ru, title_en=excluded.title_en, status=excluded.status, "
            "sort=excluded.sort, template_slug=excluded.template_slug",
            (n["slug"], n.get("parent"), n["kind"], n["slug"], n["title_ru"], n["title_en"],
             n.get("status", "planned"), int(n.get("sort", 0)), n.get("template_slug")))
    con.commit()
    return len(nodes)


def _node_dict(r) -> dict:
    return {"slug": r["slug"], "parent": r["parent_id"], "kind": r["kind"], "title_ru": r["title_ru"],
            "title_en": r["title_en"], "status": r["status"], "soon": r["status"] == "planned",
            "sort": r["sort"], "template_slug": r["template_slug"]}


def tree(con: sqlite3.Connection, *, include_hidden: bool = False) -> list[dict]:
    """Дерево каталога [{…, children:[…]}]. planned = «скоро» (soon=True). hidden по умолчанию скрыты."""
    rows = con.execute("SELECT * FROM program_nodes ORDER BY sort, slug").fetchall()
    nodes = {r["slug"]: {**_node_dict(r), "children": []} for r in rows
             if include_hidden or r["status"] != "hidden"}
    roots = []
    for n in nodes.values():
        p = n["parent"]
        if p and p in nodes:
            nodes[p]["children"].append(n)
        elif not p:
            roots.append(n)
    return roots


def lift_name(lift: str) -> dict:
    d = standards.disciplines().get(lift) or {}
    return {"ru": d.get("name_ru") or ontology.base_ru(lift) or lift,
            "en": d.get("name_en") or lift.replace("_", " ").capitalize()}


def requirements(con: sqlite3.Connection, uid: int, tpl: dict, today=None) -> dict:
    """Что нужно для записи: по каждому лифту разрешённый опорный вес (resolve_reference), а если ввод нужен —
    ещё и три варианта стартового уровня (`reference.options`). needs_test: обязательные лифты без свежего
    реального макса (первая сессия будет тестом)."""
    today_d = eng._day(today)
    bests = eng._best_map(con, uid, today_d)
    out, need_input, need_test = [], [], []
    for req, lifts in ((True, tpl["required_lifts"]), (False, tpl.get("optional_lifts", []))):
        for lift in lifts:
            ref = eng.resolve_reference(con, uid, lift, today_d, _bests=bests)
            if ref["source"] == "needs_input":
                need_input.append(lift)
            elif req and (ref["source"] != "best" or ref["stale"]):
                need_test.append(lift)
            out.append({"lift": lift, "name": lift_name(lift), "required": req, "reference": ref})
    return {"lifts": out, "needs_input": need_input, "needs_test": need_test + [l for l in need_input if l in tpl["required_lifts"]]}


def get_program(con: sqlite3.Connection, slug: str, uid: int | None = None, today=None) -> dict:
    """Узел каталога; для программы с шаблоном — сводка шаблона (недели, лифты, правила) и, если известен uid,
    `requirements` (опорные веса атлета)."""
    r = con.execute("SELECT * FROM program_nodes WHERE slug=?", (slug,)).fetchone()
    if not r or r["status"] == "hidden":
        raise NotFound(f"program {slug!r}")
    out = _node_dict(r)
    out["children"] = [_node_dict(c) for c in con.execute(
        "SELECT * FROM program_nodes WHERE parent_id=? AND status!='hidden' ORDER BY sort, slug", (slug,))]
    if r["template_slug"] and r["status"] == "active":
        tpl = eng.load_template(r["template_slug"])
        out["template"] = {
            "slug": tpl["slug"], "version": tpl["version"], "title": tpl["title"], "summary": tpl["summary"],
            "params": tpl["params"], "required_lifts": tpl["required_lifts"],
            "optional_lifts": tpl.get("optional_lifts", []), "rules": tpl["rules"],
            "about": tpl.get("about", []), "week_types": tpl.get("week_types", {}),
            "weeks": [{"week": w["week"], "type": w["type"], "title": w["title"], "note": w.get("note"),
                       "sessions": len(w["sessions"]),
                       "days": [{"idx": s["idx"], "dow": s["dow"], "title": s["title"], "minutes": s["minutes"],
                                 "kind": s.get("kind", "normal"), "purpose": s.get("purpose"),
                                 "focus": s.get("focus"), "intensity": s.get("intensity")}
                                for s in w["sessions"]]} for w in tpl["weeks"]]}
        if uid is not None:
            out["requirements"] = requirements(con, uid, tpl, today)
            en = con.execute("SELECT id FROM program_enrollments WHERE uid=? AND program_slug=? AND deleted_at IS NULL "
                             "AND status IN ('active','paused')", (int(uid), slug)).fetchone()
            out["enrollment_id"] = en["id"] if en else None
    return out


# --------------------------------------------------------------------------- запись на программу

def _enrollment_row(con, uid: int, enrollment_id: str):
    r = con.execute("SELECT * FROM program_enrollments WHERE id=? AND deleted_at IS NULL", (enrollment_id,)).fetchone()
    if not r or r["uid"] != int(uid):
        raise NotFound(f"enrollment {enrollment_id!r}")
    return r


def _writable(e) -> None:
    if e["status"] in ("paused", "cancelled"):
        raise SessionClosed(f"запись {e['status']}: сначала возобнови" if e["status"] == "paused" else "запись отменена")


def _session_row(con, uid: int, session_id: str):
    s = con.execute("SELECT * FROM program_sessions WHERE id=?", (session_id,)).fetchone()
    if not s:
        raise NotFound(f"session {session_id!r}")
    e = _enrollment_row(con, uid, s["enrollment_id"])
    return s, e


def enrollment_view(con: sqlite3.Connection, r, with_refresh: bool = False) -> dict:
    cnt = {row["status"]: row["c"] for row in con.execute(
        "SELECT status, COUNT(*) c FROM program_sessions WHERE enrollment_id=? GROUP BY status", (r["id"],))}
    nxt = con.execute(
        "SELECT id, planned_day, week, idx, kind FROM program_sessions WHERE enrollment_id=? "
        "AND status IN ('planned','in_progress') ORDER BY planned_day, week, idx LIMIT 1", (r["id"],)).fetchone()
    node = con.execute("SELECT title_ru, title_en FROM program_nodes WHERE slug=?", (r["program_slug"],)).fetchone()
    out = {"id": r["id"], "uid": r["uid"], "program_slug": r["program_slug"],
            "title_ru": node["title_ru"] if node else None, "title_en": node["title_en"] if node else None,
            "template_version": r["template_version"], "start_day": r["start_day"], "status": r["status"],
            "level": r["level"], "base_maxes": _j(r["base_maxes"], {}), "created_at": r["created_at"],
            "updated_at": r["updated_at"], "sessions": {"total": sum(cnt.values()), **cnt},
            "next_session": dict(nxt) if nxt else None}
    if with_refresh:
        out["refresh"] = _refresh_for(con, r)
    return out


def get_enrollment(con: sqlite3.Connection, uid: int, enrollment_id: str) -> dict:
    """Запись; `refresh` — предложения «обновить опорные?» (лифты с макс >= базы + 2.5 кг), не зависят от finish."""
    return enrollment_view(con, _enrollment_row(con, uid, enrollment_id), with_refresh=True)


def list_sessions(con: sqlite3.Connection, uid: int, enrollment_id: str) -> list[dict]:
    """Сессии записи для календаря: id, planned_day, week, idx, kind, status, activity_id, sets_done, sets_total, title.
    sets_done — плановые подходы с внесённым весом и без промаха."""
    e = _enrollment_row(con, uid, enrollment_id)
    bases = _j(e["base_maxes"], {})
    done_by: dict[str, set] = {}
    for r in con.execute("SELECT l.id, l.session_id FROM set_log l JOIN program_sessions s ON s.id=l.session_id "
                         "WHERE s.enrollment_id=? AND l.deleted_at IS NULL AND l.done_kg IS NOT NULL "
                         "AND (l.ok IS NULL OR l.ok=1)", (enrollment_id,)):
        done_by.setdefault(r["session_id"], set()).add(r["id"])
    out = []
    for r in con.execute("SELECT * FROM program_sessions WHERE enrollment_id=? ORDER BY planned_day, week, idx",
                         (enrollment_id,)):
        plan = _j(r["plan"], {})
        ids = {x["id"] for x in eng.expand_session(plan, bases, r["id"])}
        out.append({"id": r["id"], "planned_day": r["planned_day"], "week": r["week"], "idx": r["idx"],
                    "kind": r["kind"], "status": r["status"], "activity_id": r["activity_id"],
                    "title": plan.get("title"), "week_type": plan.get("week_type"),
                    "sets_done": len(ids & done_by.get(r["id"], set())), "sets_total": len(ids)})
    return out


def list_enrollments(con: sqlite3.Connection, uid: int, status: str | None = None) -> list[dict]:
    q = "SELECT * FROM program_enrollments WHERE uid=? AND deleted_at IS NULL"
    args: list = [int(uid)]
    if status:
        q += " AND status=?"
        args.append(status)
    return [enrollment_view(con, r) for r in con.execute(q + " ORDER BY created_at, id", args)]


def _base_entry(kg: float, source: str, note: str, note_en: str) -> dict:
    return {"kg": kg, "source": source, "stale": False, "note": note, "note_en": note_en}


def _num(v):
    if isinstance(v, dict):
        v = v.get("kg")
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not (0 < v <= 500):
        raise ProgramError("base_maxes: вес в кг, число 0..500")
    return float(v)


def _resolve_bases(con, uid: int, lifts: list[str], today: date, base_maxes: dict | None,
                   level: str | None) -> dict[str, dict]:
    """Снимок опорных максов на момент записи. Заданные атлетом (base_maxes) — источник user и
    служат исходными для производных оценок остальных лифтов."""
    bests = eng._best_map(con, uid, today)
    out: dict[str, dict] = {}
    for lift, v in (base_maxes or {}).items():
        if lift not in ontology.MOVEMENTS or not ontology.is_weighted(lift):
            raise ProgramError(f"base_maxes: {lift!r} не весовое движение")
        kg = _num(v)
        out[lift] = _base_entry(kg, "user", "Вес указан атлетом.", "Weight entered by the athlete.")
        bests = {**bests, lift: {"kg": kg, "day": today.isoformat(), "stale": False}}
    need: dict[str, dict] = {}
    for lift in lifts:
        if lift in out:
            continue
        ref = eng.resolve_reference(con, uid, lift, today, level=level, _bests=bests)
        if ref["source"] == "needs_input":
            need[lift] = ref
            continue
        out[lift] = {k: ref[k] for k in ref if k not in ("lift", "options", "question")}
    if need:
        raise NeedsInput(need)
    return out


def _mondays(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _spec_of(tpl: dict, week: dict, s: dict) -> dict:
    kind = s.get("kind", "normal")
    if kind == "normal" and week["type"] == "deload":
        kind = "deload"
    return {"kind": kind, "week_type": week["type"], "week_title": week["title"], "week_note": week.get("note"),
            "title": s["title"], "minutes": s["minutes"], "blocks": s["blocks"], "rules": tpl["rules"],
            "template": tpl["slug"], "template_version": tpl["version"]}


def enroll(con: sqlite3.Connection, uid: int, slug: str, *, start_day, today=None, base_maxes: dict | None = None,
           level: str | None = None, weekdays: list[int] | None = None, enrollment_id: str | None = None,
           now: datetime | None = None) -> dict:
    """Запись на программу: снимок опорных максов и расписание сессий.
    Опорный вес каждого лифта: заданный атлетом -> лучший результат -> производная -> (level) стартовый;
    иначе NeedsInput с вопросами. Если у обязательного лифта нет свежего реального макса (нет данных,
    старше 60 дней, оценка) — в start_day ставится тест-сессия (kind=test, week=0), а недели шаблона
    начинаются со следующего дня. Идемпотентно по enrollment_id.
    weekdays — свои дни недели (0=пн) вместо дней шаблона, если их хватает на все сессии недели."""
    node = con.execute("SELECT * FROM program_nodes WHERE slug=?", (slug,)).fetchone()
    if not node or node["status"] == "hidden":
        raise NotFound(f"program {slug!r}")
    if node["status"] != "active" or not node["template_slug"]:
        raise Unavailable(f"program {slug!r} пока недоступна (скоро)")
    if enrollment_id:
        ex = con.execute("SELECT * FROM program_enrollments WHERE id=?", (enrollment_id,)).fetchone()
        if ex:
            if ex["uid"] != int(uid) or ex["program_slug"] != slug or ex["deleted_at"]:
                raise Conflict("enrollment id занят")
            return {**enrollment_view(con, ex), "existing": True}
    else:
        enrollment_id = str(uuid.uuid4())
    dup = con.execute("SELECT id FROM program_enrollments WHERE uid=? AND program_slug=? AND deleted_at IS NULL "
                      "AND status IN ('active','paused')", (int(uid), slug)).fetchone()
    if dup:
        raise Conflict(f"уже есть активная запись на {slug!r}: {dup['id']}")
    if weekdays is not None:
        if not (isinstance(weekdays, list) and weekdays and len(set(weekdays)) == len(weekdays)
                and all(isinstance(x, int) and 0 <= x <= 6 for x in weekdays)):
            raise ProgramError("weekdays: уникальные числа 0..6")
        weekdays = sorted(weekdays)
    tpl = eng.load_template(node["template_slug"])
    today_d = eng._day(today)
    start_d = eng._day(start_day)
    lifts = list(dict.fromkeys(tpl["required_lifts"] + tpl.get("optional_lifts", [])))
    bases = _resolve_bases(con, uid, lifts, today_d, base_maxes, level)
    test_lifts = [l for l in tpl["required_lifts"]
                  if bases[l]["source"] not in ("best", "user") or bases[l].get("stale")]
    program_start = start_d + timedelta(days=1) if test_lifts else start_d
    ts = _iso(now)
    con.execute(
        "INSERT INTO program_enrollments (id,uid,program_slug,template_version,start_day,status,base_maxes,level,"
        "created_at,updated_at,deleted_at) VALUES (?,?,?,?,?,?,?,?,?,?,NULL)",
        (enrollment_id, int(uid), slug, tpl["version"], start_d.isoformat(), "active",
         json.dumps(bases, ensure_ascii=False), level, ts, ts))

    def put(week, idx, day, spec):
        sid = str(uuid.uuid5(_NS, f"{enrollment_id}:{week}:{idx}"))
        con.execute(
            "INSERT INTO program_sessions (id,enrollment_id,planned_day,week,idx,kind,status,plan,checkin,activity_id,"
            "updated_at) VALUES (?,?,?,?,?,?,?,?,NULL,NULL,?)",
            (sid, enrollment_id, day.isoformat(), week, idx, spec["kind"], "planned",
             json.dumps(spec, ensure_ascii=False), ts))

    if test_lifts:
        spec = eng.build_test_spec(test_lifts)
        spec.update(week_type="test", week_title={"ru": "День 0: тест", "en": "Day 0: test"}, week_note=None,
                    rules=tpl["rules"], template=tpl["slug"], template_version=tpl["version"])
        put(0, 0, start_d, spec)
    prev = program_start - timedelta(days=1)
    first_monday = _mondays(program_start)
    for w in tpl["weeks"]:
        n = len(w["sessions"])
        for s in w["sessions"]:
            dow = weekdays[s["idx"] - 1] if weekdays and len(weekdays) >= n else s["dow"]
            day = first_monday + timedelta(days=7 * (w["week"] - 1) + dow)
            day = max(day, prev + timedelta(days=1), program_start)
            prev = day
            put(w["week"], s["idx"], day, _spec_of(tpl, w, s))
    con.commit()
    return {**enrollment_view(con, _enrollment_row(con, uid, enrollment_id)), "test_lifts": test_lifts,
            "existing": False}


_TRANSITIONS = {"pause": ({"active"}, "paused"), "resume": ({"paused"}, "active"),
                "cancel": ({"active", "paused"}, "cancelled")}


def set_enrollment_status(con: sqlite3.Connection, uid: int, enrollment_id: str, action: str, *, now=None) -> dict:
    """pause: active -> paused; resume: paused -> active; cancel: active|paused -> cancelled. Иначе Conflict.
    Сессии и подходы не удаляются (история остаётся)."""
    if action not in _TRANSITIONS:
        raise ProgramError(f"action: одно из {sorted(_TRANSITIONS)}")
    e = _enrollment_row(con, uid, enrollment_id)
    allowed, new = _TRANSITIONS[action]
    if e["status"] not in allowed:
        raise Conflict(f"из статуса {e['status']!r} нельзя: {action}")
    if action == "resume":
        dup = con.execute("SELECT id FROM program_enrollments WHERE uid=? AND program_slug=? AND deleted_at IS NULL "
                          "AND status IN ('active','paused') AND id!=?", (int(uid), e["program_slug"], enrollment_id)).fetchone()
        if dup:
            raise Conflict("уже есть другая активная запись на эту программу")
    con.execute("UPDATE program_enrollments SET status=?, updated_at=? WHERE id=?", (new, _iso(now), enrollment_id))
    con.commit()
    return get_enrollment(con, uid, enrollment_id)


# --------------------------------------------------------------------------- сессия: разворачивание и вид

def _bar(con, uid) -> float:
    return eng.BAR_KG.get(eng.athlete_profile(con, uid)["sex"] or "m", 20.0)


def _logs(con, session_id: str) -> dict[str, sqlite3.Row]:
    return {r["id"]: r for r in con.execute(
        "SELECT * FROM set_log WHERE session_id=? AND deleted_at IS NULL", (session_id,))}


def _is_logged(row) -> bool:
    return row is not None and (row["done_kg"] is not None or row["ok"] is not None)


def _compute(con, uid: int, srow, erow, *, persist: bool, now=None, plan_override: dict | None = None) -> dict:
    """Единая точка расчёта: формулы -> кг с учётом чек-ина, промахов и уже отмеченных подходов.
    persist=True записывает plan.resolved и planned_kg в set_log (только для не отмеченных подходов)."""
    plan = plan_override if plan_override is not None else _j(srow["plan"], {})
    checkin = _j(srow["checkin"], None)
    bases = _j(erow["base_maxes"], {})
    adjust = eng.checkin_adjust(checkin, plan.get("rules"), srow["kind"])
    resolved = eng.expand_session(plan, bases, srow["id"], adjust=adjust, misses=plan.get("misses", []),
                                  bar_kg=_bar(con, uid))
    logs = _logs(con, srow["id"])
    for s in resolved:
        row = logs.get(s["id"])
        if _is_logged(row) and row["planned_kg"] is not None:
            s["planned_kg"] = row["planned_kg"]     # факт уже зафиксирован: план не двигаем
    if persist:
        ts = _iso(now)
        for s in resolved:
            row = logs.get(s["id"])
            if row is None:
                con.execute("INSERT INTO set_log (id,session_id,exercise,planned_kg,done_kg,reps,ok,note,ts,updated_at,"
                            "deleted_at) VALUES (?,?,?,?,NULL,?,NULL,NULL,NULL,?,NULL)",
                            (s["id"], srow["id"], s["lift"], s["planned_kg"], s["reps"], ts))
            elif not _is_logged(row) and row["planned_kg"] != s["planned_kg"]:
                con.execute("UPDATE set_log SET planned_kg=?, updated_at=? WHERE id=?", (s["planned_kg"], ts, s["id"]))
        plan["resolved"] = resolved
        plan["adjust"] = adjust
        con.execute("UPDATE program_sessions SET plan=?, updated_at=? WHERE id=?",
                    (json.dumps(plan, ensure_ascii=False), ts, srow["id"]))
        logs = _logs(con, srow["id"])
    return _view(srow, plan, checkin, adjust, resolved, logs)


def _set_out(s: dict, row) -> dict:
    return {"id": s["id"], "n": s["n"], "kind": s["kind"], "pct": s["pct"], "planned_kg": s["planned_kg"],
            "rest_sec": s.get("rest_sec"),
            "reps": (row["reps"] if row is not None and row["reps"] is not None else s["reps"]),
            "done_kg": row["done_kg"] if row is not None else None,
            "ok": (None if row is None or row["ok"] is None else bool(row["ok"])),
            "note": row["note"] if row is not None else None, "ts": row["ts"] if row is not None else None}


def _view(srow, plan: dict, checkin, adjust: dict, resolved: list[dict], logs: dict) -> dict:
    by_ex: dict[str, list[dict]] = {}
    for s in resolved:
        by_ex.setdefault(s["exercise"], []).append(_set_out(s, logs.get(s["id"])))
    blocks = []
    for b in plan.get("blocks", []):
        blocks.append({"title": b["title"], "exercises": [
            {"id": ex["id"], "lift": ex["lift"], "name": ex["name"], "sets": by_ex.get(ex["id"], [])}
            for ex in b["exercises"]]})
    known = {s["id"] for s in resolved}
    extra = [{"id": r["id"], "exercise": r["exercise"], "planned_kg": r["planned_kg"], "done_kg": r["done_kg"],
              "reps": r["reps"], "ok": None if r["ok"] is None else bool(r["ok"]), "note": r["note"], "ts": r["ts"]}
             for r in logs.values() if r["id"] not in known]
    info = _session_info(plan, srow)
    return {"id": srow["id"], "enrollment_id": srow["enrollment_id"], "planned_day": srow["planned_day"],
            "week": srow["week"], "idx": srow["idx"], "kind": srow["kind"], "status": srow["status"],
            "week_type": plan.get("week_type"), "week_title": plan.get("week_title"),
            "week_note": plan.get("week_note"), "title": plan.get("title"), "minutes": plan.get("minutes"),
            "purpose": info.get("purpose"), "focus": info.get("focus"), "intensity": info.get("intensity"),
            "week_type_info": info.get("week_type_info"),
            "checkin": checkin, "adjust": adjust, "why": adjust.get("why"), "why_en": adjust.get("why_en"),
            "activity_id": srow["activity_id"], "blocks": blocks, "extra_sets": extra,
            "misses": plan.get("misses", [])}


def _session_info(plan: dict, srow) -> dict:
    """Описание дня из шаблона (зачем он нужен, над чем работаем): берётся при чтении по неделе и номеру дня,
    поэтому есть и у записей, сделанных до появления описаний."""
    try:
        tpl = eng.load_template(plan.get("template"))
    except Exception:  # noqa: BLE001 — нет шаблона: просто без описания
        return {}
    for w in tpl.get("weeks", []):
        if w["week"] != srow["week"]:
            continue
        for s in w["sessions"]:
            if s["idx"] == srow["idx"]:
                return {"purpose": s.get("purpose"), "focus": s.get("focus"), "intensity": s.get("intensity"),
                        "week_type_info": (tpl.get("week_types") or {}).get(w["type"])}
    return {}


def get_session(con: sqlite3.Connection, uid: int, session_id: str, today=None) -> dict:
    """Сессия с раскрытыми весами (без записи в БД)."""
    s, e = _session_row(con, uid, session_id)
    return _compute(con, uid, s, e, persist=False)


def plan_session(con: sqlite3.Connection, uid: int, session_id: str, today=None, *, checkin: dict | None = None,
                 now=None) -> dict:
    """Разворачивает формулы шаблона в кг (округление 2.5, не ниже грифа), учитывает чек-ин и on_miss,
    сохраняет план подходов в set_log. Повторный вызов пересчитывает только ещё не отмеченные подходы
    (например, после обновления опорных)."""
    s, e = _session_row(con, uid, session_id)
    if s["status"] == "done":
        return _compute(con, uid, s, e, persist=False)
    if checkin is not None:
        return submit_checkin(con, uid, session_id, checkin, today, now=now)
    v = _compute(con, uid, s, e, persist=True, now=now)
    con.commit()
    return v


_CHECKIN_KEYS = ("energy", "tired", "sleepy", "joint", "ill")


def submit_checkin(con: sqlite3.Connection, uid: int, session_id: str, checkin: dict, today=None, *, now=None) -> dict:
    """Чек-ин готовности: energy 1..5, tired, sleepy, joint, ill. Веса пересчитываются детерминированно,
    причина в `why`. Отмеченные подходы не меняются."""
    s, e = _session_row(con, uid, session_id)
    _writable(e)
    if s["status"] == "done":
        raise SessionClosed("сессия завершена")
    if not isinstance(checkin, dict):
        raise ProgramError("checkin: объект")
    clean: dict = {}
    for k in _CHECKIN_KEYS:
        v = checkin.get(k)
        if v is None:
            continue
        if k == "energy":
            if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 5:
                raise ProgramError("energy: целое 1..5")
        else:
            v = bool(v)
        clean[k] = v
    ts = _iso(now)
    con.execute("UPDATE program_sessions SET checkin=?, updated_at=? WHERE id=?",
                (json.dumps(clean, ensure_ascii=False), ts, session_id))
    s = con.execute("SELECT * FROM program_sessions WHERE id=?", (session_id,)).fetchone()
    v = _compute(con, uid, s, e, persist=True, now=now)
    con.commit()
    return v


def today_session(con: sqlite3.Connection, uid: int, enrollment_id: str, today) -> dict:
    """Сессия «на сегодня»: сегодняшняя -> начатая -> ближайшая -> последняя пропущенная. state: today|in_progress|
    upcoming|overdue|none."""
    e = _enrollment_row(con, uid, enrollment_id)
    t = eng._day(today).isoformat()
    if e["status"] != "active":
        return {"state": e["status"], "enrollment_id": enrollment_id, "date": t, "session": None}
    q = ("SELECT * FROM program_sessions WHERE enrollment_id=? AND status IN ('planned','in_progress') ")
    rows = con.execute(q + "ORDER BY planned_day, week, idx", (enrollment_id,)).fetchall()
    pick, state = None, "none"
    for r in rows:
        if r["planned_day"] == t:
            pick, state = r, "today"
            break
    if not pick:
        pick = next((r for r in rows if r["status"] == "in_progress" and r["planned_day"] < t), None)
        state = "in_progress" if pick else "none"
    if not pick:
        pick = next((r for r in rows if r["planned_day"] > t), None)
        state = "upcoming" if pick else "none"
    if not pick and rows:
        pick, state = rows[-1], "overdue"
    return {"state": state, "enrollment_id": enrollment_id, "date": t,
            "session": _compute(con, uid, pick, e, persist=False) if pick else None}


# --------------------------------------------------------------------------- подходы

def log_set(con: sqlite3.Connection, uid: int, session_id: str, set_id: str, *, done_kg=None, reps=None, ok=None,
            note: str | None = None, exercise: str | None = None, ts: str | None = None, now=None,
            fields: set[str] | None = None) -> dict:
    """PUT подхода (идемпотентно, повтор ничего не ломает). `fields` — какие поля клиент реально передал
    (роут отдаёт `model_fields_set`): непереданные остаются как были, а переданный `ok=None` без веса —
    СБРОС отметки: подход снова неотмеченный, done_kg очищен, промах снят, вес остатка пересчитывается от базы.
    Без `fields` (прямой вызов) поля заменяются целиком. set_id — id из плана или клиентский UUID
    внеплановой записи (тогда укажи exercise). ok=False на плановом подходе: правило on_miss
    `drop_5kg_continue` — оставшиеся подходы этого лифта в сессии легче на 5 кг (кроме тест-сессии).
    -> {set, changed: [id пересчитанных подходов], why}."""
    s, e = _session_row(con, uid, session_id)
    _writable(e)
    if s["status"] == "done":
        raise SessionClosed("сессия завершена")
    if done_kg is not None:
        if isinstance(done_kg, bool) or not isinstance(done_kg, (int, float)) or not 0 <= done_kg <= 500:
            raise ProgramError("done_kg: 0..500")
        done_kg = float(done_kg)
    if reps is not None and (isinstance(reps, bool) or not isinstance(reps, int) or not 0 <= reps <= 200):
        raise ProgramError("reps: целое 0..200")
    if ok is not None:
        ok = bool(ok)
    plan = _j(s["plan"], {})
    before = _compute(con, uid, s, e, persist=False, plan_override=json.loads(json.dumps(plan)))
    prev_planned = {x["id"]: x["planned_kg"] for b in before["blocks"] for ex in b["exercises"] for x in ex["sets"]}
    cur = eng.expand_session(plan, _j(e["base_maxes"], {}), session_id, adjust=before["adjust"],
                             misses=plan.get("misses", []), bar_kg=_bar(con, uid))
    planned = next((x for x in cur if x["id"] == set_id), None)
    row = con.execute("SELECT * FROM set_log WHERE id=?", (set_id,)).fetchone()
    exercise = exercise or (row["exercise"] if row else None)
    if not planned and not exercise:
        raise ProgramError("внеплановый подход: укажи exercise")
    ts_now = _iso(now)
    if row and row["session_id"] != session_id:
        raise Conflict("set id занят другой сессией")
    if fields is not None:
        def _keep(name, new, col=None):
            return new if name in fields else (row[col or name] if row else None)
        done_kg = _keep("done_kg", done_kg)
        reps = _keep("reps", reps)
        note = _keep("note", note)
        ts = _keep("ts", ts)
        if "ok" not in fields:
            ok = None if not row or row["ok"] is None else bool(row["ok"])
        elif ok is None and "done_kg" not in fields:
            done_kg = None          # явный ok: null без веса — сброс отметки
    reset = done_kg is None and ok is None
    if reset:
        reps, ts = (reps if fields is not None and "reps" in fields else None), None
    plan_kg = (prev_planned.get(set_id) if planned else None)
    if row and row["planned_kg"] is not None and _is_logged(row) and not reset:
        plan_kg = row["planned_kg"]
    lift = planned["lift"] if planned else exercise
    if row is None:
        con.execute("INSERT INTO set_log (id,session_id,exercise,planned_kg,done_kg,reps,ok,note,ts,updated_at,deleted_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,NULL)",
                    (set_id, session_id, lift, plan_kg, done_kg, reps, None if ok is None else int(ok), note,
                     ts or (None if reset else ts_now), ts_now))
    else:
        con.execute("UPDATE set_log SET done_kg=?, reps=?, ok=?, note=?, ts=?, updated_at=?, deleted_at=NULL, "
                    "planned_kg=" + ("NULL" if reset else "COALESCE(planned_kg, ?)") + " WHERE id=?",
                    (done_kg, reps, None if ok is None else int(ok), note,
                     None if reset else (ts or row["ts"] or ts_now), ts_now)
                    + (() if reset else (plan_kg,)) + (set_id,))
    if reset and not planned:
        con.execute("UPDATE set_log SET deleted_at=? WHERE id=?", (ts_now, set_id))
    # on_miss
    misses = [m for m in plan.get("misses", []) if m["set_id"] != set_id]
    rule = (plan.get("rules") or {}).get("on_miss")
    if planned and ok is False and rule == "drop_5kg_continue" and s["kind"] != "test" and planned["kind"] != "attempt":
        misses.append({"set_id": set_id, "lift": planned["lift"], "after_seq": planned["seq"],
                       "drop_kg": eng.MISS_DROP_KG})
    plan["misses"] = misses
    con.execute("UPDATE program_sessions SET plan=?, status=?, updated_at=? WHERE id=?",
                (json.dumps(plan, ensure_ascii=False), "in_progress", ts_now, session_id))
    s = con.execute("SELECT * FROM program_sessions WHERE id=?", (session_id,)).fetchone()
    after = _compute(con, uid, s, e, persist=True, now=now)
    con.commit()
    now_planned = {x["id"]: x["planned_kg"] for b in after["blocks"] for ex in b["exercises"] for x in ex["sets"]}
    changed = [i for i, v in now_planned.items() if i != set_id and prev_planned.get(i) != v]
    r = con.execute("SELECT * FROM set_log WHERE id=?", (set_id,)).fetchone()
    why = None
    if changed:
        why = {"ru": f"Не вышло: остальные подходы по «{_lift_ru(lift)}» на {_fmt(eng.MISS_DROP_KG)} кг легче.",
               "en": f"Missed: the remaining {lift.replace('_', ' ')} sets are {_fmt(eng.MISS_DROP_KG)} kg lighter."}
    return {"set": {"id": r["id"], "exercise": r["exercise"], "planned_kg": r["planned_kg"], "done_kg": r["done_kg"],
                    "reps": r["reps"], "ok": None if r["ok"] is None else bool(r["ok"]), "note": r["note"],
                    "ts": r["ts"]},
            "changed": changed, "why": why, "session_status": "in_progress"}


def _lift_ru(lift: str) -> str:
    return (standards.disciplines().get(lift) or {}).get("name_ru") or ontology.base_ru(lift) or lift


# --------------------------------------------------------------------------- финиш

def _board_text(con, plan: dict, session_id: str) -> str:
    """Текст доски = план сессии: «Название: 60x1, 70x1, …» по упражнениям."""
    lines = []
    by_ex: dict[str, list] = {}
    for s in plan.get("resolved", []):
        by_ex.setdefault(s["exercise"], []).append(s)
    title = (plan.get("title") or {}).get("ru", "")
    for b in plan.get("blocks", []):
        for ex in b["exercises"]:
            sets = by_ex.get(ex["id"], [])
            lines.append(f"{ex['name']['ru']}: " + ", ".join(
                f"{_fmt(x['planned_kg'])}x{x['reps']}" if x["planned_kg"] is not None else f"{x['pct']}%x{x['reps']}"
                for x in sets))
    return (f"{title}\n" + "\n".join(lines)).strip()


def _workout_payload(con, plan: dict, session_id: str, day: date, rpe) -> dict:
    """Сессия -> payload для tj.services.workouts.save_result: по упражнению блок `emom_strength`
    (раундов столько, сколько подходов), значения формы — «кгxповторы» только удавшихся подходов
    (промах ok=False в результат и максы не идёт)."""
    logs = _logs(con, session_id)
    resolved = plan.get("resolved", [])
    planned_ids = {s["id"] for s in resolved}
    extras: dict[str, list] = {}
    for r in logs.values():
        if r["id"] not in planned_ids and r["done_kg"] is not None:
            extras.setdefault(r["exercise"], []).append(r)
    entries: list[tuple[dict, list[tuple[float | None, int | None]]]] = []   # (exercise, [(kg, reps)])

    def val(r, default_reps):
        if r is None or r["done_kg"] is None or not r["done_kg"] > 0 or r["ok"] == 0:
            return (None, None)
        return (r["done_kg"], r["reps"] or default_reps)

    used_extra: set[str] = set()
    for b in plan.get("blocks", []):
        for ex in b["exercises"]:
            vals = [val(logs.get(s["id"]), s["reps"]) for s in resolved if s["exercise"] == ex["id"]]
            if ex["lift"] in extras and ex["lift"] not in used_extra:
                vals += [val(r, 1) for r in extras[ex["lift"]]]
                used_extra.add(ex["lift"])
            entries.append((ex, vals))
    for lift, rows in extras.items():
        if lift not in used_extra:
            entries.append(({"name": {"ru": _lift_ru(lift)}, "lift": lift}, [val(r, 1) for r in rows]))
    blocks, form_result = [], {}
    for bi, (ex, vals) in enumerate(entries):
        if not vals:
            continue
        idx = len(blocks)
        blocks.append({"header": "ТА", "format": "emom_strength", "rounds": len(vals), "reps": None,
                       "work_min": None, "rest_min": None, "has_cap": False, "benchmark": None,
                       "movements": [{"name": ex["name"]["ru"], "canon": ex["lift"], "weighted": True}]})
        for j, (kg, reps) in enumerate(vals):
            if kg is not None:
                form_result[f"{idx}.{j}"] = f"{_fmt(kg)}x{reps}"
    payload: dict = {"day": day.isoformat(), "sport": "weightlifting", "rpe": rpe,
                     "board": {"text": _board_text(con, plan, session_id), "source": "own"}}
    if blocks:
        payload["board"]["blocks"] = blocks
        payload["form_result"] = form_result
    return payload


def finish_session(con: sqlite3.Connection, uid: int, session_id: str, *, rpe: int | None = None,
                   feel: int | str | None = None, activity_id: str | None = None, today=None, now=None,
                   tz: str = "UTC") -> dict:
    """Завершение сессии. Запись тренировки и максов делает `tj.services.workouts.save_result` (та же цепочка,
    что у ручной записи: Sport.WEIGHTLIFTING, максы -> discipline_results source='auto'); здесь только сборка
    payload из подходов и связь с программой в `extra.program`. activity_id — клиентский UUID (иначе
    детерминированный uuid5). Тест-сессия обновляет опорные и пересчитывает остальные веса. Опорные без твоего
    согласия НЕ меняются: сервис лишь предлагает `refresh` (suggest_base_refresh).
    Идемпотентно: повтор по завершённой сессии ничего не пишет и возвращает `already=True`."""
    from tj.services import workouts
    s, e = _session_row(con, uid, session_id)
    day = eng._day(today)
    if rpe is not None and (isinstance(rpe, bool) or not isinstance(rpe, int) or not 1 <= rpe <= 10):
        raise ProgramError("rpe: целое 1..10")
    plan = _j(s["plan"], {})
    if s["status"] != "done":
        _writable(e)
    if s["status"] == "done":
        fin = plan.get("finish", {})
        return {"session_id": session_id, "status": "done", "already": True, "activity_id": s["activity_id"],
                "maxes": fin.get("maxes", []), "refresh": suggest_base_refresh(con, uid, e["id"]),
                "base_updated": fin.get("base_updated", [])}
    _compute(con, uid, s, e, persist=True, now=now)          # заморозить план
    plan = _j(con.execute("SELECT plan FROM program_sessions WHERE id=?", (session_id,)).fetchone()["plan"], {})
    act_id = workouts.normalize_activity_id(uid, activity_id or str(uuid.uuid5(_NS, f"activity:{session_id}")))
    saved = workouts.save_result(con, uid, act_id, _workout_payload(con, plan, session_id, day, rpe), tz=tz)
    node = con.execute("SELECT title_ru FROM program_nodes WHERE slug=?", (e["program_slug"],)).fetchone()
    row = con.execute('SELECT "extra" FROM activities WHERE "tg_id"=? AND "activity_id"=?', (uid, act_id)).fetchone()
    extra = _j(row["extra"], {}) if row else {}
    extra["program"] = {"enrollment_id": e["id"], "session_id": session_id, "slug": e["program_slug"],
                        "title": node["title_ru"] if node else None, "week": s["week"], "idx": s["idx"],
                        "kind": s["kind"]}
    if feel is not None:
        extra["feel"] = feel
    con.execute('UPDATE activities SET "extra"=? WHERE "tg_id"=? AND "activity_id"=?',
                (json.dumps(extra, ensure_ascii=False), uid, act_id))
    tested: dict[str, float] = {}
    for r in saved["credited"]:
        tested[r["discipline"]] = max(tested.get(r["discipline"], 0), r["weight"])
    maxes = [{"lift": r["discipline"], "kg": r["weight"], "reps": r["reps"]} for r in saved["credited"]]
    base_updated: list[str] = []
    if s["kind"] == "test" and tested:
        base_updated = _apply_test_result(con, uid, e, tested, day)
    ts = _iso(now)
    plan["finish"] = {"rpe": rpe, "feel": feel, "day": day.isoformat(), "maxes": maxes, "base_updated": base_updated}
    con.execute("UPDATE program_sessions SET status='done', activity_id=?, plan=?, updated_at=? WHERE id=?",
                (act_id, json.dumps(plan, ensure_ascii=False), ts, session_id))
    left = con.execute("SELECT COUNT(*) c FROM program_sessions WHERE enrollment_id=? AND status IN "
                       "('planned','in_progress')", (e["id"],)).fetchone()["c"]
    if left == 0:
        con.execute("UPDATE program_enrollments SET status='done', updated_at=? WHERE id=?", (ts, e["id"]))
    con.commit()
    return {"session_id": session_id, "status": "done", "already": False, "activity_id": act_id, "maxes": maxes,
            "refresh": suggest_base_refresh(con, uid, e["id"]), "base_updated": base_updated,
            "enrollment_done": left == 0}


def _apply_test_result(con, uid: int, e, tested: dict[str, float], day: date) -> list[str]:
    """Тест-сессия: результат становится опорным по проверенным лифтам; оценённые (derived/starter) лифты
    пересчитываются от новых максов (результаты уже записаны в discipline_results)."""
    bases = _j(e["base_maxes"], {})
    for lift, kg in tested.items():
        bases[lift] = {"kg": kg, "source": "test", "stale": False, "day": day.isoformat(),
                       "note": "Максимум дня из тест-сессии.", "note_en": "Day max from the test session."}
    best_now = eng._best_map(con, uid, day)
    for lift, b in list(bases.items()):
        if lift in tested or b.get("source") not in ("derived", "starter"):
            continue
        ref = eng.resolve_reference(con, uid, lift, day, level=e["level"], _bests=best_now)
        if ref["source"] in ("best", "derived", "starter"):
            bases[lift] = {k: ref[k] for k in ref if k not in ("lift", "options", "question")}
    con.execute("UPDATE program_enrollments SET base_maxes=?, updated_at=? WHERE id=?",
                (json.dumps(bases, ensure_ascii=False), _iso(), e["id"]))
    return sorted(tested)


# --------------------------------------------------------------------------- опорные: предложение и обновление

def suggest_base_refresh(con: sqlite3.Connection, uid: int, enrollment_id: str) -> list[dict]:
    """Если после старта записи появился макс >= базы + 2.5 кг — предложение «обновить опорные?».
    Базу молча не меняем: применяет refresh_base по явному действию атлета."""
    return _refresh_for(con, _enrollment_row(con, uid, enrollment_id))


def _refresh_for(con, e) -> list[dict]:
    uid = e["uid"]
    out = []
    for lift, b in _j(e["base_maxes"], {}).items():
        base = b.get("kg")
        if not base:
            continue
        r = con.execute('SELECT MAX("value") m FROM discipline_results WHERE "tg_id"=? AND "discipline"=? '
                        'AND "value" IS NOT NULL AND "day">=?', (int(uid), lift, e["start_day"])).fetchone()
        new = r["m"] if r else None
        if new is not None and new >= base + REFRESH_STEP_KG:
            out.append({"lift": lift, "base_kg": base, "new_kg": new, "delta_kg": round(new - base, 2),
                        "ru": f"Новый максимум по «{_lift_ru(lift)}»: {_fmt(new)} кг (база {_fmt(base)}). Обновить опорные?",
                        "en": f"New max for {lift.replace('_', ' ')}: {_fmt(new)} kg (base {_fmt(base)}). Update base maxes?"})
    return out


def refresh_base(con: sqlite3.Connection, uid: int, enrollment_id: str, lifts: list[str] | None = None, *,
                 now=None) -> dict:
    """Применяет предложения suggest_base_refresh (все или по списку лифтов). Веса не начатых подходов пересчитаются
    при следующем разворачивании сессии."""
    e = _enrollment_row(con, uid, enrollment_id)
    sug = suggest_base_refresh(con, uid, enrollment_id)
    if lifts is not None:
        sug = [x for x in sug if x["lift"] in lifts]
    bases = _j(e["base_maxes"], {})
    for x in sug:
        bases[x["lift"]] = {"kg": x["new_kg"], "source": "best", "stale": False,
                            "note": "Обновлено атлетом по новому максимуму.",
                            "note_en": "Updated by the athlete after a new max."}
    con.execute("UPDATE program_enrollments SET base_maxes=?, updated_at=? WHERE id=?",
                (json.dumps(bases, ensure_ascii=False), _iso(now), enrollment_id))
    con.commit()
    return {**get_enrollment(con, uid, enrollment_id), "refreshed": [x["lift"] for x in sug]}


# --------------------------------------------------------------------------- тренд «максимум дня»

def day_max_trend(con: sqlite3.Connection, uid: int, lift: str, window: int = 7) -> dict:
    """Максимум дня по лифту в последних `window` тренировочных днях с данными (по журналу подходов программ,
    удавшиеся подходы). -> {lift, points:[{day, kg, session_id}] по возрастанию, delta_kg, trend: up|flat|down|none, best}."""
    rows = con.execute(
        "SELECT s.planned_day AS day, s.id AS sid, MAX(l.done_kg) AS mx FROM set_log l "
        "JOIN program_sessions s ON s.id=l.session_id JOIN program_enrollments e ON e.id=s.enrollment_id "
        "WHERE e.uid=? AND e.deleted_at IS NULL AND l.exercise=? AND l.deleted_at IS NULL AND l.done_kg IS NOT NULL "
        "AND (l.ok IS NULL OR l.ok=1) GROUP BY s.id ORDER BY s.planned_day DESC, s.week DESC, s.idx DESC LIMIT ?",
        (int(uid), lift, max(1, int(window)))).fetchall()
    pts = [{"day": r["day"], "kg": r["mx"], "session_id": r["sid"]} for r in reversed(rows)]
    if len(pts) < 2:
        return {"lift": lift, "points": pts, "delta_kg": 0, "trend": "none", "best": pts[0]["kg"] if pts else None}
    delta = pts[-1]["kg"] - pts[0]["kg"]
    trend = "up" if delta >= eng.ROUNDING else "down" if delta <= -eng.ROUNDING else "flat"
    return {"lift": lift, "points": pts, "delta_kg": round(delta, 2), "trend": trend,
            "best": max(p["kg"] for p in pts)}
