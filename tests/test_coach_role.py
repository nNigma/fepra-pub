from __future__ import annotations

import asyncio
import sqlite3
from datetime import date

from tj import i18n
from tjbot import access
from tjbot import db as botdb
from tjbot.handlers import add_result, admin, club


def _con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    botdb.init_schema(con)
    return con


def _user(con, tg_id, gym, nick=None):
    botdb.save_user(con, tg_id, nick=nick or f"u{tg_id}", height_cm=180,
                    weight_kg=80, sex="m", age=30, gym=gym)


class Msg:
    def __init__(self):
        self.texts = []
        self.markups = []

    async def reply_text(self, t, **kw):
        self.texts.append(t)
        self.markups.append(kw.get("reply_markup"))


class Upd:
    def __init__(self, uid=1):
        self.effective_user = type("U", (), {"id": uid})()
        self.effective_message = Msg()


class CbQ:
    def __init__(self, uid, data):
        self.from_user = type("U", (), {"id": uid})()
        self.data = data
        self.message = Msg()
        self.answers = []
        self.edited = []

    async def answer(self, *a, **kw):
        self.answers.append((a, kw))

    async def edit_message_text(self, t, **kw):
        self.edited.append(t)


class CbUpd:
    def __init__(self, uid, data):
        self.callback_query = CbQ(uid, data)
        self.effective_user = self.callback_query.from_user
        self.effective_message = self.callback_query.message


class Ctx:
    def __init__(self, db_path):
        self.user_data = {}
        self.bot_data = {"db_path": db_path}


def _file_con(tmp_path):
    p = str(tmp_path / "t.db")
    con = botdb.connect(p)
    botdb.init_schema(con)
    return p, con


def test_coaches_file_roundtrip(tmp_path):
    p = tmp_path / "coaches.json"
    assert access.load_coaches(p) == {}
    access.add_coach(7, "Universe", p)
    access.add_coach(9, "Атлант", p)
    assert access.coach_gym(7, p) == "Universe"
    assert access.coach_gym(8, p) is None
    assert access.is_coach(9, p)
    assert not access.is_coach(8, p)
    access.add_coach(9, "Universe", p)
    assert access.coach_gym(9, p) == "Universe"
    access.remove_coach(7, p)
    assert not access.is_coach(7, p)
    assert access.is_coach(9, p)


def test_coaches_broken_or_missing_file(tmp_path):
    p = tmp_path / "coaches.json"
    assert access.load_coaches(p) == {}
    p.write_text("не json", encoding="utf-8")
    assert access.load_coaches(p) == {}
    assert access.coach_gym(1, p) is None


def test_default_gym():
    con = _con()
    assert botdb.default_gym(con) == "Universe"


def test_target_gym_resolution(monkeypatch):
    con = _con()
    botdb.add_gym(con, "Атлант")
    _user(con, 1, "Атлант")
    _user(con, 2, "solo")
    _user(con, 4, "Снесенный")
    monkeypatch.setattr(access, "coach_gym",
                        lambda uid, path=None: "Атлант" if uid == 3 else None)
    assert club.target_gym(con, 1) == "Атлант"
    assert club.target_gym(con, 2) == "Universe"
    assert club.target_gym(con, 3) == "Атлант"
    assert club.target_gym(con, 4) == "Universe"
    assert club.target_gym(con, 99) == "Universe"


def test_target_gym_coach_stale_gym_falls_back(monkeypatch):
    con = _con()
    monkeypatch.setattr(access, "coach_gym", lambda uid, path=None: "Снесенный")
    _user(con, 5, "solo")
    assert club.target_gym(con, 5) == "Universe"


def test_can_manage(monkeypatch):
    monkeypatch.setattr(club, "is_admin", lambda uid: uid == 1)
    monkeypatch.setattr(access, "coach_gym",
                        lambda uid, path=None: "Атлант" if uid == 2 else None)
    assert club.can_manage(1, "Universe")
    assert club.can_manage(1, "Атлант")
    assert club.can_manage(2, "Атлант")
    assert not club.can_manage(2, "Universe")
    assert not club.can_manage(3, "Universe")


def test_club_kb_manage_has_athletes():
    m = [b.text for row in club.club_kb(True).keyboard for b in row]
    r = [b.text for row in club.club_kb(False).keyboard for b in row]
    assert club.BTN_CLUB_ATHLETES in m
    assert club.BTN_CLUB_ATHLETES not in r
    assert club.BTN_CLUB_ADD in m and club.BTN_CLUB_ADD not in r


def test_fmt_program_names_gym():
    s = club._fmt_program({"day": "2026-07-01", "raw_text": "Фран 21-15-9", "gym": "Атлант"})
    assert "Атлант" in s and "2026-07-01" in s
    en = club._fmt_program({"day": "2026-07-01", "raw_text": "Fran", "gym": "Атлант"}, "en")
    assert "Атлант" in en


def _act(con, aid, tg_id, day, source, sport="crossfit"):
    con.execute(
        'INSERT INTO activities ("activity_id","tg_id","day","source","sport") VALUES (?,?,?,?,?)',
        (aid, tg_id, day, source, sport))


def test_athletes_text_counts_recent_workouts():
    con = _con()
    botdb.add_gym(con, "Атлант")
    _user(con, 1, "Атлант", nick="Ник")
    _user(con, 2, "Атлант", nick="Боб")
    _user(con, 3, "Universe")
    today = date.today().isoformat()
    _act(con, "a1", 1, today, "manual")
    _act(con, "a2", 1, today, "garmin")
    _act(con, "a3", 1, "2026-02-01", "manual")
    _act(con, "a4", 1, "2026-02-01", "manual")
    _act(con, "a5", 1, "2020-01-01", "manual")
    _act(con, "a6", 3, today, "manual")
    text = club._athletes_text(con, "Атлант", "2026-01-01", "ru")
    assert "Атлант" in text
    assert "Ник" in text and "Боб" in text
    assert "u3" not in text
    assert i18n.t("club.athletes_line", "ru", name="Ник", n=3) in text
    assert i18n.t("club.athletes_line", "ru", name="Боб", n=0) in text


def test_athletes_text_empty_gym():
    con = _con()
    botdb.add_gym(con, "Атлант")
    assert club._athletes_text(con, "Атлант", "2026-01-01", "ru") == i18n.t("club.athletes_empty", "ru")


def test_athletes_handler_gate(tmp_path, monkeypatch):
    monkeypatch.setattr(access, "is_allowed", lambda uid, path=None: True)
    p, con = _file_con(tmp_path)
    botdb.add_gym(con, "Атлант")
    _user(con, 1, "Атлант")
    con.close()
    monkeypatch.setattr(club, "is_admin", lambda uid: False)
    monkeypatch.setattr(access, "coach_gym", lambda uid, path=None: None)
    upd, ctx = Upd(uid=1), Ctx(p)
    asyncio.run(club.athletes(upd, ctx))
    assert upd.effective_message.texts == [i18n.t("club.manage_only", "ru")]
    monkeypatch.setattr(access, "coach_gym", lambda uid, path=None: "Атлант")
    upd2 = Upd(uid=1)
    asyncio.run(club.athletes(upd2, ctx))
    assert "Атлант" in upd2.effective_message.texts[0]


def test_add_entry_gate_coach_vs_stranger(tmp_path, monkeypatch):
    p, con = _file_con(tmp_path)
    botdb.add_gym(con, "Атлант")
    _user(con, 1, "Атлант")
    con.close()
    monkeypatch.setattr(club, "is_admin", lambda uid: False)
    monkeypatch.setattr(access, "coach_gym", lambda uid, path=None: None)
    upd, ctx = Upd(uid=1), Ctx(p)
    asyncio.run(club.add_entry(upd, ctx))
    assert upd.effective_message.texts == [i18n.t("club.manage_only", "ru")]
    monkeypatch.setattr(access, "coach_gym", lambda uid, path=None: "Атлант")
    upd2, ctx2 = Upd(uid=1), Ctx(p)
    asyncio.run(club.add_entry(upd2, ctx2))
    assert upd2.effective_message.texts == [i18n.t("club.ask_add_date", "ru")]
    assert ctx2.user_data["cgym"] == "Атлант"


def test_stats_uses_target_gym(tmp_path, monkeypatch):
    monkeypatch.setattr(access, "is_allowed", lambda uid, path=None: True)
    p, con = _file_con(tmp_path)
    botdb.add_gym(con, "Атлант")
    _user(con, 1, "Атлант")
    botdb.add_program(con, "2026-07-01", "Universe", "5x5", movements=["deadlift"], confirmed=1)
    botdb.add_program(con, "2026-07-01", "Атлант", "21-15-9", movements=["thruster"], confirmed=1)
    con.close()
    monkeypatch.setattr(club, "is_admin", lambda uid: False)
    monkeypatch.setattr(access, "coach_gym", lambda uid, path=None: None)
    upd, ctx = Upd(uid=1), Ctx(p)
    asyncio.run(club.stats(upd, ctx))
    text = upd.effective_message.texts[0]
    assert "Трастер" in text or "thruster" in text.lower()
    assert "Становая" not in text


def test_open_club_shows_own_gym_program(tmp_path, monkeypatch):
    monkeypatch.setattr(access, "is_allowed", lambda uid, path=None: True)
    p, con = _file_con(tmp_path)
    botdb.add_gym(con, "Атлант")
    _user(con, 1, "Атлант")
    botdb.add_program(con, date.today().isoformat(), "Атлант", "Фран 21-15-9", confirmed=1)
    con.close()
    monkeypatch.setattr(club, "is_admin", lambda uid: False)
    monkeypatch.setattr(access, "coach_gym", lambda uid, path=None: None)
    upd, ctx = Upd(uid=1), Ctx(p)
    asyncio.run(club.open_club(upd, ctx))
    assert "Фран" in upd.effective_message.texts[0]
    assert "Атлант" in upd.effective_message.texts[0]


def test_add_ok_saves_to_conversation_gym(tmp_path, monkeypatch):
    p, con = _file_con(tmp_path)
    botdb.add_gym(con, "Атлант")
    _user(con, 1, "Атлант")
    con.close()
    from tjbot import vision
    monkeypatch.setattr(vision, "engine_for", lambda uid: "gemini")

    async def _noop(*a, **kw):
        return None

    monkeypatch.setattr(club, "show_menu", _noop)
    upd, ctx = CbUpd(1, "cok"), Ctx(p)
    ctx.user_data.update({
        "lang": "ru", "cgym": "Атлант", "cday": date(2026, 7, 10),
        "draft": {"raw_text": "Фран 21-15-9", "format": "other",
                  "canon": ["thruster"], "unknown": [], "source": "text"}})
    asyncio.run(club.add_ok(upd, ctx))
    con = botdb.connect(p)
    try:
        row = botdb.get_program(con, "2026-07-10", "Атлант")
    finally:
        con.close()
    assert row is not None and row["raw_text"] == "Фран 21-15-9"


def test_add_ok_without_cgym_uses_default_gym(tmp_path, monkeypatch):
    p, con = _file_con(tmp_path)
    con.execute('UPDATE gyms SET "is_default"=0')
    botdb.add_gym(con, "Кузня")
    con.execute('UPDATE gyms SET "is_default"=1 WHERE "name"=?', ("Кузня",))
    con.commit()
    _user(con, 1, "Кузня")
    con.close()
    from tjbot import vision
    monkeypatch.setattr(vision, "engine_for", lambda uid: "gemini")

    async def _noop(*a, **kw):
        return None

    monkeypatch.setattr(club, "show_menu", _noop)
    upd, ctx = CbUpd(1, "cok"), Ctx(p)
    ctx.user_data.update({
        "lang": "ru", "cday": date(2026, 7, 11),
        "draft": {"raw_text": "Фран 21-15-9", "format": "other",
                  "canon": ["thruster"], "unknown": [], "source": "text"}})
    asyncio.run(club.add_ok(upd, ctx))
    con = botdb.connect(p)
    try:
        row = botdb.get_program(con, "2026-07-11", "Кузня")
    finally:
        con.close()
    assert row is not None


def test_club_register_includes_athletes():
    captured = []

    class App:
        def add_handler(self, h):
            captured.append(h)

    club.register(App())
    assert len(captured) == 5


def test_after_date_uses_target_gym(tmp_path, monkeypatch):
    p, con = _file_con(tmp_path)
    botdb.add_gym(con, "Атлант")
    _user(con, 1, "Атлант")
    botdb.add_program(con, "2026-07-10", "Атлант", "Фран 21-15-9", confirmed=1)
    botdb.add_program(con, "2026-07-10", "Universe", "Синди 20 мин", confirmed=1)
    con.close()
    monkeypatch.setattr(access, "coach_gym", lambda uid, path=None: None)
    msg, ctx = Msg(), Ctx(p)
    asyncio.run(add_result._after_date(ctx, msg, date(2026, 7, 10), "ru", 1))
    assert ctx.user_data["ar_prog"] == "Фран 21-15-9"


def test_gyms_open_has_coaches_button(tmp_path, monkeypatch):
    p, con = _file_con(tmp_path)
    con.close()
    monkeypatch.setattr(admin, "is_admin", lambda uid: True)
    upd, ctx = Upd(uid=1), Ctx(p)
    asyncio.run(admin.gyms_open(upd, ctx))
    btns = [b for row in upd.effective_message.markups[0].inline_keyboard for b in row]
    assert any(b.callback_data == "coaches" for b in btns)
    assert any(b.callback_data == "gymadd" for b in btns)


def test_coaches_text_lists_and_empty(monkeypatch):
    con = _con()
    _user(con, 7, "Universe", nick="Ник")
    monkeypatch.setattr(access, "load_coaches", lambda path=None: {7: "Universe", 8: "Атлант"})
    text = admin._coaches_text(con, "ru")
    assert "Ник" in text and "Universe" in text
    assert "8" in text and "Атлант" in text
    monkeypatch.setattr(access, "load_coaches", lambda path=None: {})
    assert admin._coaches_text(con, "ru") == i18n.t("admin.coaches_empty", "ru")


def test_coaches_open_buttons(tmp_path, monkeypatch):
    p, con = _file_con(tmp_path)
    con.close()
    monkeypatch.setattr(admin, "is_admin", lambda uid: True)
    monkeypatch.setattr(access, "load_coaches", lambda path=None: {7: "Universe"})
    upd, ctx = CbUpd(1, "coaches"), Ctx(p)
    asyncio.run(admin.coaches_open(upd, ctx))
    btns = [b for row in upd.callback_query.message.markups[0].inline_keyboard for b in row]
    assert any(b.callback_data == "coach:add" for b in btns)
    assert any(b.callback_data == "coachrm:7" for b in btns)


def test_coach_grant_flow(tmp_path, monkeypatch):
    p, con = _file_con(tmp_path)
    botdb.add_gym(con, "Атлант")
    con.close()
    monkeypatch.setattr(admin, "is_admin", lambda uid: True)
    granted = []
    monkeypatch.setattr(access, "add_coach", lambda tg_id, gym, path=None: granted.append((tg_id, gym)))
    ctx = Ctx(p)
    upd = CbUpd(1, "coach:add")
    st = asyncio.run(admin.coach_add_entry(upd, ctx))
    assert st == admin.COACH_ID

    upd2 = Upd(uid=1)
    upd2.effective_message.text = "не цифры"
    st = asyncio.run(admin.coach_add_take(upd2, ctx))
    assert st == admin.COACH_ID
    assert upd2.effective_message.texts == [i18n.t("admin.need_number", "ru")]

    upd3 = Upd(uid=1)
    upd3.effective_message.text = "555"
    st = asyncio.run(admin.coach_add_take(upd3, ctx))
    assert st == admin.COACH_GYM
    btns = [b for row in upd3.effective_message.markups[0].inline_keyboard for b in row]
    assert [b.callback_data for b in btns] == ["cg:Universe", "cg:Атлант"]

    upd4 = CbUpd(1, "cg:Атлант")
    from telegram.ext import ConversationHandler
    st = asyncio.run(admin.coach_pick_gym(upd4, ctx))
    assert st == ConversationHandler.END
    assert granted == [(555, "Атлант")]


def test_coach_rm(tmp_path, monkeypatch):
    p, con = _file_con(tmp_path)
    con.close()
    monkeypatch.setattr(admin, "is_admin", lambda uid: True)
    removed = []
    monkeypatch.setattr(access, "remove_coach", lambda tg_id, path=None: removed.append(tg_id))
    upd, ctx = CbUpd(1, "coachrm:7"), Ctx(p)
    asyncio.run(admin.coach_rm(upd, ctx))
    assert removed == [7]


def test_coach_admin_gates(tmp_path, monkeypatch):
    p, con = _file_con(tmp_path)
    con.close()
    monkeypatch.setattr(admin, "is_admin", lambda uid: False)
    ctx = Ctx(p)
    upd = CbUpd(2, "coaches")
    asyncio.run(admin.coaches_open(upd, ctx))
    assert upd.callback_query.message.texts == []
    upd2 = CbUpd(2, "coachrm:7")
    called = []
    monkeypatch.setattr(access, "remove_coach", lambda tg_id, path=None: called.append(tg_id))
    asyncio.run(admin.coach_rm(upd2, ctx))
    assert called == []


def test_i18n_coach_keys_both_langs():
    keys = ["btn.club_athletes", "club.manage_only", "club.athletes_empty",
            "admin.gym_coaches_btn", "admin.coaches_empty", "admin.coach_grant_btn",
            "admin.coach_ask_id", "admin.coach_pick_gym", "admin.coach_revoked"]
    for k in keys:
        for lang in ("ru", "en"):
            assert i18n.t(k, lang) != k
    assert "Атлант" in i18n.t("club.athletes_header", "ru", gym="Атлант", lines="x")
    assert "555" in i18n.t("admin.coach_granted", "ru", tg_id=555, gym="Атлант")
    assert "Ник" in i18n.t("admin.coach_revoke_btn", "ru", label="Ник")
    assert "Атлант" in i18n.t("club.program_saved", "ru", gym="Атлант", day="2026-07-10")
    assert "Атлант" in i18n.t("club.program_header", "en", gym="Атлант", day="d", text="t")


def test_club_views_closed_to_strangers(tmp_path, monkeypatch):
    """Просмотр зала, статистика и список атлетов закрыты для чужих."""
    monkeypatch.setattr(access, "is_allowed", lambda uid, path=None: False)
    p, con = _file_con(tmp_path)
    con.close()
    for handler in (club.open_club, club.stats, club.athletes):
        upd = Upd(uid=999)
        asyncio.run(handler(upd, Ctx(p)))
        assert len(upd.effective_message.texts) == 1
        assert "Доступ закрыт" in upd.effective_message.texts[0]
