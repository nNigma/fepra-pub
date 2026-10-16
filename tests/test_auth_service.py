from datetime import datetime, timedelta, timezone

import pytest

from tj.services import auth
from tjbot import db as botdb

T0 = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def con(tmp_path):
    c = botdb.connect(tmp_path / "t.db")
    botdb.init_schema(c)
    yield c
    c.close()


def test_web_user_ids_start_at_base_and_increment(con):
    a = auth.create_web_user(con, "Аня")
    b = auth.create_web_user(con, "Боря")
    assert a == auth.WEB_ID_BASE and b == a + 1
    assert auth.roles_of(con, a)["allowed"]
    row = con.execute('SELECT nick,lang FROM users WHERE tg_id=?', (a,)).fetchone()
    assert row["nick"] == "Аня" and row["lang"] == "ru"


def test_web_id_ignores_telegram_ids(con):
    botdb.save_user(con, 11111111, nick="tg", height_cm=None, weight_kg=None, sex=None, gym=None)
    assert auth.create_web_user(con, "x") == auth.WEB_ID_BASE


def test_web_id_js_safe():
    assert auth.WEB_ID_BASE + 10**9 < 2**53


@pytest.mark.parametrize("nick", ["", "   ", "x" * 41])
def test_bad_nick(con, nick):
    with pytest.raises(ValueError):
        auth.create_web_user(con, nick)


def test_invite_stores_only_hash(con):
    tok = auth.create_invite(con, None, "user", now=T0)
    stored = con.execute("SELECT token_hash FROM invites").fetchone()[0]
    assert stored == auth.hash_token(tok) and tok not in stored


def test_redeem_creates_user_role_session_once(con):
    tok = auth.create_invite(con, None, "pro", now=T0)
    uid, sess = auth.redeem_invite(con, tok, "Вася", now=T0)
    assert uid >= auth.WEB_ID_BASE
    r = auth.roles_of(con, uid)
    assert r["allowed"] and r["pro"] and not r["admin"]
    assert auth.validate_session(con, sess, now=T0) == uid
    inv = con.execute("SELECT used_by,used_at FROM invites").fetchone()
    assert inv["used_by"] == uid and inv["used_at"]
    assert con.execute("SELECT provider FROM auth_identities WHERE user_id=?", (uid,)).fetchone()[0] == "invite"
    with pytest.raises(auth.AuthFailure) as e:
        auth.redeem_invite(con, tok, "Другой", now=T0)
    assert e.value.status == 400


def test_redeem_roles_admin_and_coach(con):
    a, _ = auth.redeem_invite(con, auth.create_invite(con, None, "admin", now=T0), "Adm", now=T0)
    assert auth.roles_of(con, a)["admin"]
    c, _ = auth.redeem_invite(con, auth.create_invite(con, None, "coach", gym="Universe", now=T0), "Co", now=T0)
    assert auth.roles_of(con, c)["coach_gym"] == "Universe"
    with pytest.raises(ValueError):
        auth.create_invite(con, None, "coach")  # без зала


def test_redeem_expired_and_unknown(con):
    tok = auth.create_invite(con, None, "user", ttl_hours=1, now=T0)
    with pytest.raises(auth.AuthFailure):
        auth.redeem_invite(con, tok, "x", now=T0 + timedelta(hours=2))
    with pytest.raises(auth.AuthFailure):
        auth.redeem_invite(con, "nonsense", "x", now=T0)
    # просроченный не погашен и не создал пользователей
    assert con.execute("SELECT used_at FROM invites").fetchone()[0] is None
    assert con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


def test_redeem_needs_nick_for_new_user(con):
    tok = auth.create_invite(con, None, "user", now=T0)
    with pytest.raises(auth.AuthFailure) as e:
        auth.redeem_invite(con, tok, "  ", now=T0)
    assert e.value.status == 422
    # ошибка валидации не сжигает приглашение
    assert auth.redeem_invite(con, tok, "ok", now=T0)


def test_invite_for_existing_telegram_user_keeps_id(con):
    botdb.save_user(con, 111, nick="Аня", height_cm=None, weight_kg=None, sex=None, gym=None)
    tok = auth.create_invite(con, None, "user", existing_user_id=111, now=T0)
    uid, sess = auth.redeem_invite(con, tok, None, now=T0)
    assert uid == 111 and auth.validate_session(con, sess, now=T0) == 111
    assert con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1


def test_invite_info_does_not_consume_and_names_existing_account(con):
    botdb.save_user(con, 111, nick="Аня", height_cm=None, weight_kg=None, sex=None, gym=None)
    tok = auth.create_invite(con, None, "user", existing_user_id=111, now=T0)
    plain = auth.create_invite(con, None, "athlete", now=T0)       # «athlete» из интерфейса = user
    assert auth.invite_info(con, tok, now=T0) == {"valid": True, "existing": True, "nick": "Аня"}
    assert auth.invite_info(con, plain, now=T0) == {"valid": True, "existing": False, "nick": None}
    assert auth.invite_info(con, tok, now=T0)["valid"] is True      # просмотр не гасит приглашение
    auth.redeem_invite(con, tok, None, now=T0)
    assert auth.invite_info(con, tok, now=T0)["valid"] is False
    assert auth.invite_info(con, "мусор", now=T0)["valid"] is False


def test_invite_for_missing_existing_user_rejected(con):
    with pytest.raises(ValueError):
        auth.create_invite(con, None, "user", existing_user_id=424242)


def test_list_invites_statuses(con):
    a = auth.create_invite(con, 1, "user", ttl_hours=1, note="n", now=T0)
    auth.create_invite(con, 1, "user", ttl_hours=100, now=T0)
    auth.redeem_invite(con, a, "x", now=T0)
    st = {i["status"] for i in auth.list_invites(con, now=T0 + timedelta(hours=10))}
    assert st == {"used", "active"}
    assert "token" not in auth.list_invites(con)[0]


def test_session_sliding_expiry_and_revoke(con):
    uid = auth.create_web_user(con, "s")
    sess = auth.create_session(con, uid, "UA", now=T0)
    # через 59 дней жива и продлевается ещё на 60
    t1 = T0 + timedelta(days=59)
    assert auth.validate_session(con, sess, now=t1) == uid
    assert auth.validate_session(con, sess, now=t1 + timedelta(days=59)) == uid
    # без обращений 61 день — умерла
    assert auth.validate_session(con, sess, now=t1 + timedelta(days=59 + 61)) is None
    assert con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0


def test_session_revoke(con):
    uid = auth.create_web_user(con, "s")
    s1, s2 = auth.create_session(con, uid, now=T0), auth.create_session(con, uid, now=T0)
    assert auth.revoke_session(con, s1) and auth.validate_session(con, s1, now=T0) is None
    assert auth.validate_session(con, s2, now=T0) == uid
    assert auth.revoke_user_sessions(con, uid) == 1
    assert auth.validate_session(con, None) is None and auth.validate_session(con, "zzz") is None


def test_get_me(con, monkeypatch):
    monkeypatch.setenv("FEPRA_PUBLIC_URL", "https://x.test")
    uid = auth.create_web_user(con, "Me")
    auth.add_role(con, uid, "coach", "Universe")
    me = auth.get_me(con, uid)
    assert me["id"] == uid and me["nick"] == "Me" and me["gym"] == "Universe"
    assert me["roles"] == {"admin": False, "pro": False, "coach": True}
    assert me["has_passkey"] is False and me["garmin"] is None and me["public_url"] == "https://x.test"
    botdb.garmin_account_set(con, uid, "a@b.c", "ok")
    assert auth.get_me(con, uid)["garmin"] == {"connected": True, "status": "ok"}
