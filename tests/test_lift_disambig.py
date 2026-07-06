from __future__ import annotations

import asyncio

from tjbot.handlers import lift_disambig as ld


class Msg:
    def __init__(self):
        self.texts = []

    async def reply_text(self, t, **kw):
        self.texts.append(t)


class Q:
    def __init__(self, data, uid=1):
        self.data = data
        self.from_user = type("U", (), {"id": uid})()
        self.edited = []

    async def answer(self, *a, **k):
        pass

    async def edit_message_text(self, t, **kw):
        self.edited.append(t)


class Upd:
    def __init__(self, q=None, uid=1):
        self.callback_query = q
        self.effective_user = type("U", (), {"id": uid})()
        self.effective_message = Msg()


class Ctx:
    def __init__(self, db_path):
        self.user_data = {}
        self.bot_data = {"db_path": db_path}


def test_family_variants_shape():
    assert ld.FAMILY_VARIANTS["snatch"][0][0] == "squat_snatch"
    assert ld.FAMILY_VARIANTS["clean"][1][0] == "hang_clean"


def test_no_ambiguous_is_noop(tmp_path):
    from tjbot import db
    p = str(tmp_path / "t.db"); con = db.connect(p); db.init_schema(con); con.close()
    ctx = Ctx(p); upd = Upd()
    asked = asyncio.run(ld.ask_ambiguous(upd, ctx, [], day="2026-07-06",
                                         activity_id="a1", tg_id=1))
    assert asked is False and not ctx.user_data.get("ld_amb") and not upd.effective_message.texts


def test_ambiguous_asks_then_appends_on_pick(tmp_path):
    from tjbot import db
    p = str(tmp_path / "t.db"); con = db.connect(p); db.init_schema(con); con.close()
    ctx = Ctx(p); upd = Upd()
    amb = [{"family": "snatch", "weight": 55, "reps": 1, "movement": "рывок"}]
    asked = asyncio.run(ld.ask_ambiguous(upd, ctx, amb, day="2026-07-06",
                                         activity_id="manual-2026-07-06-crossfit", tg_id=1))
    assert asked is True and ctx.user_data["ld_amb"]["queue"] and upd.effective_message.texts
    q = Q("ldis:squat_snatch"); upd2 = Upd(q=q)
    asyncio.run(ld.on_pick(upd2, ctx))
    con = db.connect(p)
    row = con.execute("SELECT discipline, value FROM discipline_results").fetchone()
    assert row["discipline"] == "squat_snatch" and row["value"] == 55
    assert not ctx.user_data.get("ld_amb")
