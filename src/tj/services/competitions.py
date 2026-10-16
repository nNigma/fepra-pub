"""Соревнования: старты, участие, этапы, результаты, итог, размер поля.

Поток бота (handlers/competition.py) без Telegram и без `user_data["fill"]`: контекст
«заполнения» — явные параметры (event_id, division_id, athlete). Атлет в comp_results —
строка: «Я» по умолчанию или имя (как в боте). Весь прямой SQL по comp_participants /
comp_divisions живёт здесь. Распознавание таблиц — tjbot.vision.parse_stages/parse_results
(синхронно, для jobs); в БД ничего не пишется, пока клиент не подтвердит
(confirm_stages / confirm_results).

Права: смотреть чужие старты может любой вошедший (list_events, get_event); менять
этапы, результаты и размер поля — участник дивизиона или админ; итог (total) — только
своя запись участия.
"""
from __future__ import annotations

from datetime import date, datetime

from tj import i18n

from .errors import Forbidden, Invalid, NotFound

ME = "Я"
MAX_STAGES = 30
MAX_ROWS = 60

CATEGORY_CODES = ("newbie", "pro", "int", "rx", "custom")
_FIXED_LABELS = {"pro": "PRO", "int": "INT", "rx": "RX"}


# --- чистые функции (перенесены из хендлера) ------------------------------------------

def category_label(code: str, lang: str = "ru") -> str:
    if code in _FIXED_LABELS:
        return _FIXED_LABELS[code]
    if code == "newbie":
        return i18n.t("comp.cat_newbie", lang)
    raise Invalid("category: newbie, pro, int, rx или custom (с division)", code="bad_category")


def parse_date(txt: str, today: date) -> date | None:
    """«ДД.ММ.ГГГГ», «ДД.ММ» (год текущий) или ISO «ГГГГ-ММ-ДД» -> date | None."""
    txt = (txt or "").strip()
    for fmt in ("%d.%m.%Y", "%d.%m", "%Y-%m-%d"):
        src = f"{txt}.{today.year}" if fmt == "%d.%m" else txt
        try:
            return datetime.strptime(src, "%d.%m.%Y" if fmt == "%d.%m" else fmt).date()
        except ValueError:
            continue
    return None


def parse_result_text(text: str) -> dict:
    """«значение, место[, размер поля]» -> {value, place, field_size|None}.
    Меньше двух частей или место не число -> Invalid; размер поля не число -> игнорируется."""
    parts = [p.strip() for p in (text or "").split(",")]
    if len(parts) < 2:
        raise Invalid("формат: «значение, место[, размер поля]», например «5:30, 12, 40»",
                      code="result_text_hint")
    try:
        place = int(parts[1])
    except ValueError:
        raise Invalid("место должно быть числом", code="place_invalid")
    field_size = None
    if len(parts) >= 3:
        try:
            field_size = int(parts[2])
        except ValueError:
            pass
    return {"value": parts[0], "place": place, "field_size": field_size}


def pick_stage_for_text_result(stages: list[dict], athlete: str) -> int | None:
    """Этап для текстового результата: последний, где у атлета ещё нет результата;
    если везде есть — последний этап; нет этапов — None."""
    for s in reversed(stages):
        if not [r for r in s.get("results", []) if r["athlete"] == athlete]:
            return s["id"]
    return stages[-1]["id"] if stages else None


def map_result_rows(rows: list[dict], stages: list[dict]) -> list[int | None]:
    """Строки таблицы результатов -> id этапов (в порядке строк; None = не сопоставлено).
    Порядок правил как в confirm_result_save бота: номер этапа == idx (int или цифры в строке),
    затем точное имя этапа, затем позиция строки по порядку этапов."""
    by_idx = {s["idx"]: s["id"] for s in stages}
    ordered = [s["id"] for s in sorted(stages, key=lambda s: s["idx"])]
    out: list[int | None] = []
    for i, r in enumerate(rows):
        st = r.get("stage")
        sid = None
        if isinstance(st, int) and not isinstance(st, bool) and st in by_idx:
            sid = by_idx[st]
        elif str(st).isdigit() and int(st) in by_idx:
            sid = by_idx[int(st)]
        else:
            sid = next((s["id"] for s in stages
                        if (s["name"] or "").strip() == str(st).strip()), None)
        if sid is None and i < len(ordered):
            sid = ordered[i]
        out.append(sid)
    return out


def _place(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# --- доступ ---------------------------------------------------------------------------

def _is_admin(uid: int) -> bool:
    from tjbot import access
    return access.is_admin(uid)


def _event(con, event_id: int) -> dict:
    from tjbot import db as botdb
    ev = botdb.get_event(con, int(event_id))
    if not ev:
        raise NotFound("старт не найден")
    return ev


def _participant(con, uid: int, division_id: int):
    return con.execute('SELECT * FROM comp_participants WHERE "division_id"=? AND "tg_id"=? '
                       'ORDER BY "id" LIMIT 1', (int(division_id), int(uid))).fetchone()


def context(con, uid: int, event_id: int, division_id: int | None = None) -> dict:
    """Контекст «заполнения» из явных параметров -> {event, division, participant_id|None}.
    division_id не задан: берём единственный дивизион, где вы участвуете (админ без участия —
    единственный дивизион старта). Несколько подходящих -> Invalid need_division.
    Не участник и не админ -> Forbidden."""
    ev = _event(con, event_id)
    divs = ev["divisions"]
    admin = _is_admin(uid)
    if division_id is not None:
        div = next((d for d in divs if d["id"] == int(division_id)), None)
        if div is None:
            raise NotFound("дивизион не найден в этом старте")
        part = _participant(con, uid, div["id"])
        if part is None and not admin:
            raise Forbidden("вы не участник этого дивизиона")
        return {"event": ev, "division": div, "participant_id": part["id"] if part else None}
    mine = [(d, _participant(con, uid, d["id"])) for d in divs]
    mine = [(d, p) for d, p in mine if p is not None]
    if len(mine) == 1:
        d, p = mine[0]
        return {"event": ev, "division": d, "participant_id": p["id"]}
    if len(mine) > 1:
        raise Invalid("вы участвуете в нескольких дивизионах — укажите division_id",
                      code="need_division")
    if admin and len(divs) == 1:
        return {"event": ev, "division": divs[0], "participant_id": None}
    if admin and len(divs) > 1:
        raise Invalid("укажите division_id", code="need_division")
    raise Forbidden("вы не участник этого старта")


# --- старты ---------------------------------------------------------------------------

def _event_brief(con, ev: dict, uid: int) -> dict:
    divs = []
    for d in ev.get("divisions", []):
        p = _participant(con, uid, d["id"])
        divs.append({"id": d["id"], "name": d["name"], "field_size": d["field_size"],
                     "participant_id": p["id"] if p else None})
    return {"id": ev["id"], "name": ev["name"], "city": ev["city"],
            "date_start": ev["date_start"], "date_end": ev["date_end"],
            "divisions": divs}


def list_events(con, uid: int) -> dict:
    """{mine: [...], others: [...]} — мои старты (я участник) и чужие (можно смотреть/вступить)."""
    from tjbot import db as botdb
    def _full(rows):
        out = []
        for r in rows:
            ev = botdb.get_event(con, r["id"])
            if ev:
                b = _event_brief(con, ev, uid)
                b["division_id"] = r.get("division_id")
                out.append(b)
        return out
    return {"mine": _full(botdb.list_competitions(con, uid)),
            "others": _full(botdb.list_other_competitions(con, uid))}


def get_event(con, uid: int, event_id: int) -> dict:
    """Старт с дивизионами и этапами. Результаты — только в дивизионах, где вы участник."""
    from tjbot import db as botdb
    ev = _event(con, event_id)
    out = _event_brief(con, ev, uid)
    for d in out["divisions"]:
        stages = botdb.get_stages(con, d["id"])
        mine = d["participant_id"] is not None
        d["stages"] = [{"id": s["id"], "idx": s["idx"], "name": s["name"],
                        "prescription": s["prescription"], "movements": s["movements"],
                        "format": s["fmt"],
                        **({"results": s["results"]} if mine else {})} for s in stages]
    return out


def create_event(con, uid: int, *, name: str, date: str, city: str,
                 category: str | None = None, division: str | None = None,
                 force_new: bool = False, lang: str = "ru", today=None) -> dict:
    """Создать старт + дивизион + участие создателя.
    Дубль (тот же город без учёта регистра, дата внутри существующего старта) и не force_new
    -> {created: false, duplicate: true, candidates: [...]} — клиент вступает в найденный старт
    (join) или повторяет запрос с force_new=true.
    Ответ: {created, event_id, division_id, participant_id}."""
    from tjbot import db as botdb
    name, city = (name or "").strip(), (city or "").strip()
    if not name or not city:
        raise Invalid("нужны name и city", code="bad_event")
    d = parse_date(date, today or _today())
    if d is None:
        raise Invalid("date: ожидается ГГГГ-ММ-ДД или ДД.ММ.ГГГГ", code="bad_date")
    iso = d.isoformat()
    div_name = (division or "").strip()
    if not div_name:
        if not category or category == "custom":
            raise Invalid("нужна category (newbie/pro/int/rx) или division", code="bad_category")
        div_name = category_label(category, lang)
    if not force_new:
        matches = botdb.find_events_by_city_date(con, city=city, date=iso)
        if matches:
            return {"created": False, "duplicate": True,
                    "candidates": [_event_brief(con, botdb.get_event(con, m["id"]), uid)
                                   for m in matches]}
    eid = botdb.create_event(con, name=name, city=city, date_start=iso, date_end=iso,
                             sport="crossfit", fmt="", created_by=uid)
    did = botdb.add_division(con, eid, name=div_name[:80])
    pid = botdb.add_participant(con, did, tg_id=uid, athlete=None)
    return {"created": True, "duplicate": False, "event_id": eid, "division_id": did,
            "participant_id": pid}


def _today() -> date:
    return date.today()


def join(con, uid: int, event_id: int, division_id: int | None = None) -> dict:
    """Вступить в старт (идемпотентно: повтор возвращает ту же запись участия).
    Несколько дивизионов и division_id не задан -> Invalid need_division; нет дивизионов ->
    Invalid no_divisions. Ответ: {event_id, division_id, participant_id, created}."""
    from tjbot import db as botdb
    ev = _event(con, event_id)
    divs = ev["divisions"]
    if not divs:
        raise Invalid("в старте нет дивизионов", code="no_divisions")
    if division_id is None:
        if len(divs) > 1:
            raise Invalid("в старте несколько дивизионов — укажите division_id",
                          code="need_division")
        div = divs[0]
    else:
        div = next((d for d in divs if d["id"] == int(division_id)), None)
        if div is None:
            raise NotFound("дивизион не найден в этом старте")
    row = _participant(con, uid, div["id"])
    if row:
        return {"event_id": ev["id"], "division_id": div["id"], "participant_id": row["id"],
                "created": False}
    pid = botdb.add_participant(con, div["id"], tg_id=uid, athlete=None)
    return {"event_id": ev["id"], "division_id": div["id"], "participant_id": pid,
            "created": True}


# --- этапы ----------------------------------------------------------------------------

def add_stage_text(con, uid: int, event_id: int, text: str,
                   division_id: int | None = None) -> dict:
    """Этап текстом: имя — первая строка (до 80 знаков), описание — весь текст."""
    from tjbot import db as botdb
    text = (text or "").strip()
    if not text:
        raise Invalid("text: пустое описание этапа", code="empty")
    ctx = context(con, uid, event_id, division_id)
    did = ctx["division"]["id"]
    stages = botdb.get_stages(con, did)
    idx = max((s["idx"] for s in stages), default=0) + 1
    sid = botdb.add_stage(con, did, idx=idx, name=text.splitlines()[0][:80],
                          prescription=text, movements=[], fmt="text")
    return {"stage_id": sid, "idx": idx, "division_id": did}


def parse_stages(con, uid: int, event_id: int, upload_id: str,
                 division_id: int | None = None, uploads_root=None, note: str | None = None) -> dict:
    """Фото этапов -> превью (ничего не сохраняет). Синхронная, для jobs.
    {recognized, reason (null|quota|no_vision|not_recognized), division_id, stages, preview}.
    stages[i] = {idx, name, prescription, format, movements, source_ref}; source_ref делает
    подтверждение идемпотентным."""
    from tjbot import access, vision
    from . import uploads
    ctx = context(con, uid, event_id, division_id)
    did = ctx["division"]["id"]
    res = {"recognized": False, "reason": None, "division_id": did, "stages": [], "preview": []}
    data, mime = uploads.read_bytes(con, uid, upload_id, root=uploads_root)
    if not vision.has_vision():
        res["reason"] = "no_vision"
        return res
    if not access.llm_quota_consume(uid, con):
        res["reason"] = "quota"
        return res
    try:
        extra = {"hint": note.strip()[:600]} if note and note.strip() else {}
        found = vision.parse_stages(data, media_type=mime, engine=vision.engine_for(uid), **extra)
    except Exception:
        found = None
    if not found:
        res["reason"] = "not_recognized"
        return res
    uid_ref = uploads.get(con, uid, upload_id)["id"]
    stages = []
    for i, s in enumerate(found[:MAX_STAGES], 1):
        stages.append({"idx": i, "name": s.get("name") or "", "prescription": s.get("prescription") or "",
                       "format": s.get("format"), "movements": s.get("movements") or [],
                       "source_ref": f"upload:{uid_ref}#{i}"})
    res.update({"recognized": True, "stages": stages,
                "preview": [f"{s['idx']}. {s['name'] or '—'}: {s['prescription'][:120]}"
                            for s in stages]})
    return res


def _clean_stage(st) -> dict:
    if not isinstance(st, dict):
        raise Invalid("stages: ожидается список объектов", code="bad_stages")
    movs = st.get("movements")
    movs = [str(m).strip() for m in movs if str(m).strip()] if isinstance(movs, list) else []
    ref = st.get("source_ref")
    return {"name": str(st.get("name") or "").strip(), "prescription": str(st.get("prescription") or ""),
            "movements": movs, "format": str(st.get("format") or "") or "text",
            "source_ref": str(ref)[:120] if ref else None}


def confirm_stages(con, uid: int, event_id: int, stages: list,
                   division_id: int | None = None) -> dict:
    """Сохранить подтверждённые этапы (после parse_stages), нумерация продолжает существующую.
    Этап с уже сохранённым source_ref пропускается — повторное подтверждение безопасно.
    -> {saved, skipped, division_id}."""
    from tjbot import db as botdb
    if not isinstance(stages, list) or not stages or len(stages) > MAX_STAGES:
        raise Invalid(f"stages: непустой список до {MAX_STAGES}", code="bad_stages")
    drafts = [_clean_stage(s) for s in stages]
    ctx = context(con, uid, event_id, division_id)
    did = ctx["division"]["id"]
    existing = botdb.get_stages(con, did)
    idx = max((s["idx"] for s in existing), default=0)
    refs = {r["source_ref"] for r in con.execute(
        'SELECT "source_ref" FROM comp_stages WHERE "division_id"=? AND "source_ref" IS NOT NULL',
        (did,))}
    saved = skipped = 0
    for st in drafts:
        if st["source_ref"] and st["source_ref"] in refs:
            skipped += 1
            continue
        idx += 1
        botdb.add_stage(con, did, idx=idx, name=(st["name"] or f"Этап {idx}")[:80],
                        prescription=st["prescription"], movements=st["movements"],
                        fmt=st["format"], source_ref=st["source_ref"])
        if st["source_ref"]:
            refs.add(st["source_ref"])
        saved += 1
    return {"saved": saved, "skipped": skipped, "division_id": did}


# --- результаты -----------------------------------------------------------------------

def _stage_in_division(con, division_id: int, stage_id) -> int:
    r = con.execute('SELECT "id" FROM comp_stages WHERE "id"=? AND "division_id"=?',
                    (stage_id, division_id)).fetchone() if stage_id is not None else None
    if not r:
        raise NotFound("этап не найден в этом дивизионе")
    return r["id"]


def _put_result(con, stage_id: int, athlete: str, value: str, place, *, replace: bool) -> int:
    """Записать результат; replace=True — заменить существующую строку атлета на этапе."""
    from tjbot import db as botdb
    if replace:
        old = con.execute('SELECT "id" FROM comp_results WHERE "stage_id"=? AND "athlete"=? '
                          'ORDER BY "id" LIMIT 1', (stage_id, athlete)).fetchone()
        if old:
            con.execute('UPDATE comp_results SET "value"=?,"place"=?,"points"=? WHERE "id"=?',
                        (value, place, place, old["id"]))
            con.commit()
            return old["id"]
    return botdb.add_comp_result(con, stage_id, athlete=athlete, value=value, place=place,
                                 points=place)


def _set_field_size_if_empty(con, division_id: int, field_size: int | None) -> None:
    if field_size:
        con.execute('UPDATE comp_divisions SET "field_size"=? WHERE "id"=? AND "field_size" IS NULL',
                    (field_size, division_id))
        con.commit()


def add_result_text(con, uid: int, event_id: int, text: str, *, athlete: str = ME,
                    division_id: int | None = None, stage_idx: int | None = None) -> dict:
    """Результат текстом «значение, место[, размер поля]». Этап подбирается эвристикой бота
    (pick_stage_for_text_result) либо задан stage_idx (тогда результат атлета на этапе
    заменяется — повтор идемпотентен). Размер поля пишется, только если он ещё не задан.
    -> {result_id, stage_id, stage_idx, value, place, field_size}."""
    from tjbot import db as botdb
    parsed = parse_result_text(text)
    athlete = (athlete or ME).strip()[:80] or ME
    ctx = context(con, uid, event_id, division_id)
    did = ctx["division"]["id"]
    stages = botdb.get_stages(con, did)
    if not stages:
        raise Invalid("сначала добавьте этап", code="no_stages")
    if stage_idx is not None:
        st = next((s for s in stages if s["idx"] == int(stage_idx)), None)
        if st is None:
            raise NotFound("этап с таким idx не найден")
        stage_id, replace = st["id"], True
    else:
        stage_id, replace = pick_stage_for_text_result(stages, athlete), False
    rid = _put_result(con, stage_id, athlete, parsed["value"], parsed["place"], replace=replace)
    _set_field_size_if_empty(con, did, parsed["field_size"])
    st = next(s for s in stages if s["id"] == stage_id)
    return {"result_id": rid, "stage_id": stage_id, "stage_idx": st["idx"],
            "value": parsed["value"], "place": parsed["place"],
            "field_size": parsed["field_size"]}


def parse_results(con, uid: int, event_id: int, upload_id: str, *, athlete: str = ME,
                  division_id: int | None = None, uploads_root=None, note: str | None = None) -> dict:
    """Фото таблицы результатов -> строки атлета с сопоставлением этапам (не сохраняет).
    {recognized, reason, athlete, division_id, rows: [{stage, value, place, stage_id, stage_idx,
    stage_name}]}. Синхронная, для jobs."""
    from tjbot import access, vision
    from . import uploads
    from tjbot import db as botdb
    athlete = (athlete or ME).strip()[:80] or ME
    ctx = context(con, uid, event_id, division_id)
    did = ctx["division"]["id"]
    res = {"recognized": False, "reason": None, "athlete": athlete, "division_id": did,
           "rows": []}
    data, mime = uploads.read_bytes(con, uid, upload_id, root=uploads_root)
    if not vision.has_vision():
        res["reason"] = "no_vision"
        return res
    if not access.llm_quota_consume(uid, con):
        res["reason"] = "quota"
        return res
    try:
        extra = {"hint": note.strip()[:600]} if note and note.strip() else {}
        parsed = vision.parse_results(data, athlete, media_type=mime,
                                      engine=vision.engine_for(uid), **extra)
    except Exception:
        parsed = None
    rows = (parsed or {}).get("rows") or []
    if not rows:
        res["reason"] = "not_recognized"
        return res
    stages = botdb.get_stages(con, did)
    by_id = {s["id"]: s for s in stages}
    out = []
    for r, sid in zip(rows, map_result_rows(rows, stages)):
        st = by_id.get(sid)
        out.append({"stage": r.get("stage"), "value": r.get("value"), "place": r.get("place"),
                    "stage_id": sid, "stage_idx": st["idx"] if st else None,
                    "stage_name": st["name"] if st else None})
    res.update({"recognized": True, "rows": out})
    return res


def confirm_results(con, uid: int, event_id: int, rows: list, *, athlete: str = ME,
                    division_id: int | None = None) -> dict:
    """Сохранить подтверждённые строки (после parse_results). Этап: явный stage_id строки
    (должен быть в дивизионе) либо map_result_rows. Несопоставленные пропускаются.
    Результат атлета на этапе заменяется, поэтому повторное подтверждение не плодит дубли.
    -> {saved, skipped, division_id}."""
    from tjbot import db as botdb
    if not isinstance(rows, list) or not rows or len(rows) > MAX_ROWS:
        raise Invalid(f"rows: непустой список до {MAX_ROWS}", code="bad_rows")
    for r in rows:
        if not isinstance(r, dict):
            raise Invalid("rows: ожидается список объектов", code="bad_rows")
    athlete = (athlete or ME).strip()[:80] or ME
    ctx = context(con, uid, event_id, division_id)
    did = ctx["division"]["id"]
    stages = botdb.get_stages(con, did)
    mapped = map_result_rows(rows, stages)
    saved = skipped = 0
    for r, sid in zip(rows, mapped):
        if r.get("stage_id") is not None:
            sid = _stage_in_division(con, did, r["stage_id"])
        if sid is None:
            skipped += 1
            continue
        _put_result(con, sid, athlete, str(r.get("value") or ""), _place(r.get("place")),
                    replace=True)
        saved += 1
    return {"saved": saved, "skipped": skipped, "division_id": did}


# --- итог, размер поля ----------------------------------------------------------------

def _own_participation(con, uid: int, event_id: int, division_id: int | None,
                       athlete: str) -> dict:
    ctx = context(con, uid, event_id, division_id)
    if ctx["participant_id"] is None:
        raise Forbidden("итог ставится только по своему участию — сначала вступите в старт")
    return ctx


def total_suggestion(con, uid: int, event_id: int, *, athlete: str = ME,
                     division_id: int | None = None) -> dict:
    """Предложение итога по сумме мест этапов: {total_points, final_place, field_size,
    place_str, division_id, participant_id}; нет результатов -> total_points=None."""
    from tjbot import db as botdb
    ctx = _own_participation(con, uid, event_id, division_id, athlete)
    did = ctx["division"]["id"]
    sug = botdb.suggest_total(con, did, (athlete or ME).strip() or ME)
    field = con.execute('SELECT "field_size" FROM comp_divisions WHERE "id"=?',
                        (did,)).fetchone()["field_size"]
    place_str = (f"{sug['final_place']}/{field}" if field and sug["final_place"] else
                 (str(sug["final_place"]) if sug["final_place"] else None))
    return {**sug, "field_size": field, "place_str": place_str, "division_id": did,
            "participant_id": ctx["participant_id"]}


def set_total(con, uid: int, event_id: int, *, total_points=None, final_place=None,
              athlete: str = ME, division_id: int | None = None) -> dict:
    """Подтвердить итог. Без значений — принять предложение (suggest_total); оба значения —
    вручную (как «Исправить» в боте); одно из двух -> Invalid. -> {participant_id,
    total_points, final_place, source: "suggested"|"manual"}."""
    from tjbot import db as botdb
    if (total_points is None) != (final_place is None):
        raise Invalid("нужны оба поля: total_points и final_place", code="bad_total")
    if total_points is None:
        sug = total_suggestion(con, uid, event_id, athlete=athlete, division_id=division_id)
        if sug["total_points"] is None:
            raise Invalid("нет результатов для подсчёта итога", code="no_results")
        pts, place, src, pid = sug["total_points"], sug["final_place"], "suggested", \
            sug["participant_id"]
    else:
        try:
            pts, place = float(total_points), int(final_place)
        except (TypeError, ValueError):
            raise Invalid("total_points — число, final_place — целое", code="bad_total")
        if place < 1 or pts < 0:
            raise Invalid("final_place ≥ 1, total_points ≥ 0", code="bad_total")
        ctx = _own_participation(con, uid, event_id, division_id, athlete)
        src, pid = "manual", ctx["participant_id"]
    botdb.set_total(con, pid, final_place=place, total_points=pts, confirmed=1)
    return {"participant_id": pid, "total_points": pts, "final_place": place, "source": src}


def set_field_size(con, uid: int, division_id: int, field_size) -> dict:
    """Размер поля дивизиона (число участников): участник дивизиона или админ."""
    div = con.execute('SELECT * FROM comp_divisions WHERE "id"=?', (int(division_id),)).fetchone()
    if not div:
        raise NotFound("дивизион не найден")
    if isinstance(field_size, bool) or not isinstance(field_size, int) or not 1 <= field_size <= 10000:
        raise Invalid("field_size: целое от 1 до 10000", code="bad_field_size")
    if _participant(con, uid, div["id"]) is None and not _is_admin(uid):
        raise Forbidden("вы не участник этого дивизиона")
    con.execute('UPDATE comp_divisions SET "field_size"=? WHERE "id"=?', (field_size, div["id"]))
    con.commit()
    return {"division_id": div["id"], "field_size": field_size}
