"""Программа зала («клуб») без Telegram: просмотр, черновики, статистика, атлеты, правка текстом.

Портировано из handlers/club.py и handlers/program.py (userbot ingest_universe уходит вместе
с ботом: черновики теперь создаёт add_from_board). Хендлеры бота не менялись, поэтому
несколько мелких чистых функций (slug, срез заголовков-обёрток, SQL атлетов) здесь продублированы.

Права: смотреть программу и статистику своего зала — любой пользователь с доступом;
управлять (добавить/править/подтвердить, список атлетов) — админ или тренер этого зала.
Фото доски здесь не обрабатывается: vision приходит из ветки тренировок, сюда попадает
уже распознанный raw_text (add_from_board).
"""
from __future__ import annotations

from urllib.parse import quote

import json
import re
import uuid
from datetime import date, timedelta

from tj import ontology
from tj.analysis import gym as gym_analysis
from tj.analysis.wod_program import annotate, movements_of, parse_program
from tjbot import access
from tjbot import db as botdb

from ._schema import ensure
from .clock import now_iso

_MIG = "0060_program_meta"
MIN_TEXT = 4
MAX_TEXT = 20000
MAX_ATHLETE_DAYS = 365


class ClubError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


# --------------------------------------------------------------------------- права и зал

def _canon_gym(con, name: str) -> str | None:
    """Название зала как в БД (без учёта регистра) или None."""
    for g in botdb.list_gyms(con):
        if g["name"].casefold() == (name or "").casefold():
            return g["name"]
    return None


def managed_gyms(con, uid: int) -> list[str]:
    """Залы, которыми пользователь управляет: админ — все, тренер — свои (несколько), иначе пусто."""
    if access.is_admin(uid):
        return [g["name"] for g in botdb.list_gyms(con)]
    out = []
    for g in access.coach_gyms(uid):
        c = _canon_gym(con, g)
        if c and c not in out:
            out.append(c)
    return out


def target_gym(con, uid: int) -> str:
    """Зал по умолчанию: зал из профиля (если он есть и, для тренера, среди его залов),
    иначе первый зал тренера, иначе основной зал системы."""
    u = botdb.get_user(con, uid)
    mine = u["gym"] if u and u["gym"] and botdb.gym_exists(con, u["gym"]) else None
    managed = managed_gyms(con, uid) if not access.is_admin(uid) else []
    if mine and (not managed or mine in managed):
        return mine
    if managed:
        return managed[0]
    return mine or botdb.default_gym(con)


def can_manage(uid: int, gym: str) -> bool:
    if access.is_admin(uid):
        return True
    return (gym or "").casefold() in {g.casefold() for g in access.coach_gyms(uid)}


def resolve_gym(con, uid: int, requested: str | None = None) -> str:
    """Зал запроса. Другой зал по параметру: админу — любой, тренеру — из его залов."""
    own = target_gym(con, uid)
    if not requested or requested.casefold() == own.casefold():
        return own
    canon = _canon_gym(con, requested)
    if canon is None:
        raise ClubError(404, "такого зала нет")
    if not (access.is_admin(uid) or canon in managed_gyms(con, uid) or canon in botdb.extra_gyms(con, uid)):
        raise ClubError(403, "чужой зал недоступен")
    return canon


def gyms_for(con, uid: int) -> dict:
    """Залы для выбора в интерфейсе: админу все, тренеру свои и зал из профиля, атлету свои (основной и дополнительные)."""
    cur = target_gym(con, uid)
    managed = managed_gyms(con, uid)
    names = list(managed)
    u = botdb.get_user(con, uid)
    mine = u["gym"] if u and u["gym"] and botdb.gym_exists(con, u["gym"]) else None
    if mine and mine not in names:
        names.append(mine)
    for g in botdb.extra_gyms(con, uid):            # дополнительные залы атлета (просмотр программы)
        c = _canon_gym(con, g)
        if c and c not in names:
            names.append(c)
    if not names:
        names = [cur]
    default = next((g["name"] for g in botdb.list_gyms(con) if g["is_default"]), None)
    return {"current": cur, "can_add": access.is_admin(uid), "gyms": [
        {"name": n, "is_default": n == default, "is_mine": n == mine, "can_manage": can_manage(uid, n)}
        for n in names]}


def require_manage(con, uid: int, requested: str | None = None) -> str:
    gym = resolve_gym(con, uid, requested)
    if not can_manage(uid, gym):
        raise ClubError(403, "управлять программой зала может администратор или тренер зала")
    return gym


def parse_day(value: str | None, today: date) -> date:
    if not value:
        return today
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ClubError(422, "day: дата в формате YYYY-MM-DD")


# --------------------------------------------------------------------------- представление

def program_dict(con, row) -> dict | None:
    """Строка wod_programs -> JSON. uuid дозаполняется лениво (бот и userbot его не пишут)."""
    if row is None:
        return None
    ensure(con, _MIG)
    d = dict(row)
    if not d.get("uuid"):
        d["uuid"] = str(uuid.uuid4())
        d["updated_at"] = d.get("updated_at") or now_iso()
        con.execute('UPDATE wod_programs SET "uuid"=?,"updated_at"=? WHERE "id"=? AND "uuid" IS NULL',
                    (d["uuid"], d["updated_at"], d["id"]))
        con.commit()
    return {"id": d["id"], "uuid": d["uuid"], "day": d["day"], "gym": d["gym"],
            "raw_text": d["raw_text"], "format": d["format"],
            "movements": json.loads(d["movements"] or "[]"),
            "blocks": json.loads(d["blocks"]) if d.get("blocks") else None,
            "blocks_verified": bool(d.get("blocks")),
            "source": d["source"], "confirmed": bool(d["confirmed"]),
            "updated_at": d.get("updated_at"), "created_by": d.get("created_by")}


# --------------------------------------------------------------------------- просмотр

def program_for_day(con, uid: int, day: date, gym: str | None = None) -> dict:
    """Подтверждённая программа зала на день; если нет — day последней программы (last)."""
    ensure(con, _MIG)
    g = resolve_gym(con, uid, gym)
    row = botdb.get_program(con, day.isoformat(), g)
    last = None if row else botdb.last_program(con, g)
    return {"gym": g, "day": day.isoformat(), "program": program_dict(con, row),
            "last_day": last["day"] if last else None, "can_manage": can_manage(uid, g)}


def movement_stats(con, uid: int, gym: str | None = None, lang: str = "ru") -> dict:
    g = resolve_gym(con, uid, gym)
    rows = gym_analysis.movement_frequency(con, g, lang=lang)
    return {"gym": g, "movements": [{"canon": c, "count": n, "name": name} for c, n, name in rows]}


def athletes_activity(con, gym: str, since_day: str) -> list[dict]:
    """Атлеты зала и число их тренировок с since_day (одна тренировка = день+вид спорта,
    дубли из разных источников не считаются; SQL из handlers/club._athletes_text)."""
    members = botdb.gym_members(con, gym)
    if not members:
        return []
    ph = ",".join("?" * len(members))
    rows = con.execute(
        f'SELECT "tg_id", SUM(m) AS n FROM ('
        f'  SELECT "tg_id", MAX(c) AS m FROM ('
        f'    SELECT "tg_id","day","sport","source", COUNT(*) AS c FROM activities'
        f'    WHERE "day">=? AND "sport" IS NOT NULL AND "tg_id" IN ({ph})'
        f'    GROUP BY "tg_id","day","sport","source")'
        f'  GROUP BY "tg_id","day","sport")'
        f'GROUP BY "tg_id"',
        (since_day, *[m["tg_id"] for m in members])).fetchall()
    counts = {r["tg_id"]: r["n"] for r in rows}
    return [{"id": m["tg_id"], "nick": m["nick"], "workouts": int(counts.get(m["tg_id"], 0))}
            for m in members]


def athletes(con, uid: int, today: date, days: int = 30, gym: str | None = None) -> dict:
    g = require_manage(con, uid, gym)
    if not 1 <= days <= MAX_ATHLETE_DAYS:
        raise ClubError(422, f"days: от 1 до {MAX_ATHLETE_DAYS}")
    since = (today - timedelta(days=days)).isoformat()
    return {"gym": g, "days": days, "since": since, "athletes": athletes_activity(con, g, since)}


# --------------------------------------------------------------------------- черновики

def pending(con, uid: int, gym: str | None = None) -> list[dict]:
    """Ожидающие подтверждения программы (confirmed=0). Админ — все залы (или gym=), тренер — свой."""
    ensure(con, _MIG)
    if access.is_admin(uid):
        gyms = [resolve_gym(con, uid, gym)] if gym else None
    else:
        gyms = [require_manage(con, uid, gym)]
    sql, args = 'SELECT * FROM wod_programs WHERE "confirmed"=0', []
    if gyms is not None:
        sql += ' AND "gym"=?'
        args.append(gyms[0])
    sql += ' ORDER BY "day" DESC, "id" DESC'
    return [program_dict(con, r) for r in con.execute(sql, args).fetchall()]


def _draft_row(con, uid: int, prog_id: int):
    ensure(con, _MIG)
    row = botdb.get_program_by_id(con, prog_id)
    if row is None:
        raise ClubError(404, "программа не найдена")
    if not can_manage(uid, row["gym"]):
        raise ClubError(403, "нет прав на программу этого зала")
    return row


def confirm(con, uid: int, prog_id: int, raw_text: str | None = None) -> dict:
    """Подтвердить черновик (с правкой текста — как «Поправить» в боте; движения и формат пересчитываются).
    Повторное подтверждение безопасно."""
    row = _draft_row(con, uid, prog_id)
    text = None
    if raw_text is not None:
        text = strip_wrappers(raw_text)
        _check_text(text)
    botdb.confirm_program(con, prog_id, raw_text=text)
    if text is not None:
        d = parse_draft(con, text)
        con.execute('UPDATE wod_programs SET "format"=?,"movements"=?,"blocks"=NULL WHERE "id"=?',
                    (d["format"], json.dumps(d["canon"], ensure_ascii=False), prog_id))
    con.execute('UPDATE wod_programs SET "updated_at"=? WHERE "id"=?', (now_iso(), prog_id))
    con.commit()
    return program_dict(con, botdb.get_program_by_id(con, prog_id))


def reject(con, uid: int, prog_id: int) -> None:
    """Отклонить (удалить) неподтверждённый черновик. Подтверждённые программы так не удаляются."""
    row = _draft_row(con, uid, prog_id)
    if row["confirmed"]:
        raise ClubError(409, "программа уже подтверждена")
    con.execute('DELETE FROM wod_programs WHERE "id"=?', (prog_id,))
    con.commit()


# --------------------------------------------------------------------------- текст программы

_PROG_WRAPPER = re.compile(
    r"^\s*(?:программа\b[^\n:]*:"
    r"|текущая\s+программа:"
    r"|program\b[^\n:]*:"
    r"|current\s+program:"
    r"|gym\s+program[^\n:]*:)\s*\n+", re.IGNORECASE)


def strip_wrappers(text: str) -> str:
    """Срезать заголовки-обёртки («Программа:» и т.п.), чтобы вставленная обратно программа их не копила."""
    t = text or ""
    prev = None
    while t != prev:
        prev = t
        t = _PROG_WRAPPER.sub("", t, count=1)
    return t.strip()


def _check_text(text: str) -> None:
    if len(text) < MIN_TEXT:
        raise ClubError(422, f"raw_text: не короче {MIN_TEXT} символов")
    if len(text) > MAX_TEXT:
        raise ClubError(422, f"raw_text: не длиннее {MAX_TEXT} символов")


def parse_draft(con, raw_text: str) -> dict:
    """Текст -> черновик: формат, распознанные движения (canon) и нераспознанные фразы (unknown)."""
    aliases = botdb.load_aliases(con)
    blocks = parse_program(raw_text, aliases)
    canon, unknown = movements_of(blocks)
    fmt = "+".join(dict.fromkeys(b["format"] for b in blocks)) or "other"
    return {"raw_text": raw_text, "format": fmt, "canon": canon, "unknown": unknown,
            "annotated": annotate(raw_text, aliases)}


def preview(con, uid: int, raw_text: str, gym: str | None = None) -> dict:
    require_manage(con, uid, gym)
    text = strip_wrappers(raw_text)
    _check_text(text)
    return parse_draft(con, text)


# --------------------------------------------------------------------------- словарь движений

_SLUG_RE = re.compile(r"[^0-9a-zа-яё]+")


def slug(name: str) -> str:
    """Имя движения -> канон-id: нижний регистр, не-буквы/цифры -> «_»."""
    return _SLUG_RE.sub("_", (name or "").lower()).strip("_")


def register_canon(con, slug_: str) -> None:
    """Лёгкий канон (self-alias), чтобы он резолвился и попадал в словарь."""
    botdb.add_alias(con, slug_, slug_, source="manual")


def dictionary(con) -> list[dict]:
    """Словарь [{canon, aliases}]: статическая онтология + рантайм-алиасы."""
    groups: dict[str, list[str]] = {}
    for canon, aliases in ontology.MOVEMENTS.items():
        groups.setdefault(canon, []).extend(aliases)
    for alias, canon in botdb.load_aliases(con).items():
        groups.setdefault(canon, [])
        if alias != canon:
            groups[canon].append(alias)
    return [{"canon": c, "aliases": list(dict.fromkeys(groups[c]))} for c in sorted(groups)]


def add_aliases(con, pairs: list[tuple[str, str]]) -> int:
    """Пары (алиас, канон) в словарь. Пустые пропускаются; возвращает число записанных."""
    n = 0
    for alias, canon in pairs:
        alias, canon = (alias or "").strip().lower(), (canon or "").strip()
        if alias and canon:
            botdb.add_alias(con, alias, canon, source="manual")
            n += 1
    return n


def resolve_movement(con, phrase: str, name: str | None = None) -> dict:
    """Сопоставить нераспознанную фразу: name пусто — новое движение «как есть»; name — существующее
    движение/алиас (иначе заводится новый канон по имени). Логика mv_new/mv_text бота."""
    phrase = (phrase or "").strip()
    if not phrase:
        raise ClubError(422, "phrase: пусто")
    if not name or not name.strip():
        s = slug(phrase)
        if not s:
            raise ClubError(422, "phrase: из этого не получится идентификатор движения")
        register_canon(con, s)
        botdb.add_alias(con, phrase, s, source="manual")
        return {"phrase": phrase, "canon": s, "created": True}
    name = name.strip()
    aliases = botdb.load_aliases(con)
    canon = ontology.resolve(name, aliases)
    name_is_alias = canon is not None
    if not canon:
        found = ontology.find(name, aliases)
        canon = found[-1] if found else None
    if canon:
        botdb.add_alias(con, phrase, canon, source="manual")
        if not name_is_alias:
            botdb.add_alias(con, name, canon, source="manual")
        return {"phrase": phrase, "canon": canon, "created": False}
    s = slug(name)
    if not s:
        raise ClubError(422, "name: из этого не получится идентификатор движения")
    register_canon(con, s)
    botdb.add_alias(con, name, s, source="manual")
    botdb.add_alias(con, phrase, s, source="manual")
    return {"phrase": phrase, "canon": s, "created": True}


# --------------------------------------------------------------------------- сохранение программы

def _write_program(con, uid: int, gym: str, day: date, raw_text: str, source: str,
                   confirmed: int, replace: bool) -> dict:
    ensure(con, _MIG)
    d = parse_draft(con, raw_text)
    keep_uuid = None
    if replace:
        old = botdb.get_program(con, day.isoformat(), gym)      # подтверждённая: её uuid сохраняем
        if old is not None and dict(old).get("uuid"):
            keep_uuid = dict(old)["uuid"]
        con.execute('DELETE FROM wod_programs WHERE "day"=? AND "gym"=?', (day.isoformat(), gym))
    pid = botdb.add_program(con, day.isoformat(), gym, raw_text, fmt=d["format"],
                            movements=d["canon"], source=source, confirmed=confirmed, blocks=None)
    con.execute('UPDATE wod_programs SET "uuid"=?,"updated_at"=?,"created_by"=? WHERE "id"=?',
                (keep_uuid or str(uuid.uuid4()), now_iso(), int(uid), pid))
    con.commit()
    out = program_dict(con, botdb.get_program_by_id(con, pid))
    out["unknown"] = d["unknown"]
    return out


def save_program(con, uid: int, day: date, raw_text: str, gym: str | None = None,
                 source: str = "text") -> dict:
    """Добавить/заменить подтверждённую программу зала на день (PUT: повтор с тем же текстом
    даёт то же состояние и тот же uuid). Блоки шаблона результатов выверяются отдельной задачей
    (verify_blocks). Возвращает программу + unknown — нераспознанные движения для словаря."""
    g = require_manage(con, uid, gym)
    text = strip_wrappers(raw_text)
    _check_text(text)
    return _write_program(con, uid, g, day, text, source, confirmed=1, replace=True)


def add_from_board(con, uid: int, gym: str | None, day: date, raw_text: str, *,
                   confirm: bool = False, source: str = "photo") -> dict:
    """Точка входа для доски, уже распознанной vision (загрузки приходят из ветки тренировок).
    confirm=False — черновик в очередь «ожидающих» (как раньше делал userbot);
    confirm=True — сразу подтверждённая программа с заменой на день (как «Подтвердить» в боте)."""
    g = require_manage(con, uid, gym)
    text = strip_wrappers(raw_text)
    _check_text(text)
    return _write_program(con, uid, g, day, text, source,
                          confirmed=1 if confirm else 0, replace=confirm)


def should_verify(uid: int, con, raw_text: str) -> bool:
    """Есть ли смысл выверять блоки Claude: блоки распознаны и движок по подписке готов."""
    from tjbot import vision
    if not parse_program(raw_text, botdb.load_aliases(con)):
        return False
    return vision.subscription_ready(vision.engine_for(uid))


def verify_blocks(db_path, prog_id: int) -> dict:
    """Тело задачи: Claude один раз выверяет блоки шаблона, участники получают исправленную форму
    без собственных обращений к ИИ. Сбой/сомнение — blocks остаётся NULL (потребители перепарсят
    raw_text). Если программу за это время заменили, ничего не пишем."""
    from tjbot import vision
    con = botdb.connect(db_path)
    try:
        row = botdb.get_program_by_id(con, prog_id)
        if row is None:
            return {"verified": False, "reason": "programme gone"}
        text = row["raw_text"]
        aliases = botdb.load_aliases(con)
        blocks = parse_program(text, aliases)
        if not blocks:
            return {"verified": False, "reason": "no blocks"}
        checked, verified = vision.verify_result_blocks(text, blocks, aliases)
        if not verified:
            return {"verified": False, "reason": "not verified"}
        cur = con.execute('UPDATE wod_programs SET "blocks"=?,"updated_at"=? '
                          'WHERE "id"=? AND "raw_text"=?',
                          (json.dumps(checked, ensure_ascii=False), now_iso(), prog_id, text))
        con.commit()
        return {"verified": cur.rowcount > 0}
    finally:
        con.close()


def parse_board_photo(db_path, uid: int, upload_id: str, engine: str = "fast") -> dict:
    """Тело задачи: фото доски -> текст доски для редактора программы зала.
    Квоту ИИ не списываем: программу зала грузит админ/тренер один раз на весь зал."""
    from . import board
    con = botdb.connect(db_path)
    try:
        res = board.parse(con, uid, upload_id=upload_id, engine=engine, sport="crossfit", charge=False)
    finally:
        con.close()
    return {"recognized": bool(res.get("recognized")), "reason": res.get("reason"),
            "board_text": res.get("board_text"), "engine_used": res.get("engine_used"),
            "annotated": res.get("annotated")}


def notify_members(con, uid: int, gym: str, day: date, today: date) -> int:
    """Сообщить атлетам зала, что программа на день появилась: запись в уведомления + push.
    Только на сегодня и вперёд; автору не шлём. Возвращает число адресатов."""
    if day < today:
        return 0
    from . import push
    text = (f"Программа зала на {day.strftime('%d.%m')} готова. Открой, чтобы записать результат."
            if day != today else "Программа зала на сегодня готова. Открой, чтобы записать результат.")
    n = 0
    for m in botdb.gym_members(con, gym):
        mid = int(m["tg_id"])
        if mid == int(uid):
            continue
        try:
            push.notify_user(con, mid, "gym_program", text, title=f"Зал · {gym}",
                             url=f"/app/#/record?gym={quote(gym)}&day={day.isoformat()}", tag=f"gym-{day.isoformat()}")
            n += 1
        except Exception as e:  # noqa: BLE001 — уведомление не должно ронять сохранение
            print(f"[club] notify failed: {type(e).__name__}", flush=True)
    return n
