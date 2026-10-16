from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from tj.services import auth
from tjbot import db as botdb

T0 = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("FEPRA_PUBLIC_URL", "https://fepra.example")
    c = botdb.connect(tmp_path / "t.db")
    botdb.init_schema(c)
    yield c
    c.close()


def _verified_reg(cred=b"cred-1", key=b"PUBKEY", count=0):
    return lambda **kw: SimpleNamespace(credential_id=cred, credential_public_key=key, sign_count=count)


def _register(con, monkeypatch, uid, cred=b"cred-1"):
    monkeypatch.setattr(auth, "verify_registration_response", _verified_reg(cred))
    o = auth.passkey_register_options(con, uid, now=T0)
    return auth.passkey_register_verify(con, uid, o["challenge_id"], {"id": "x", "response": {"transports": ["internal"]}},
                                        name="iPhone", now=T0)


def test_rp_from_public_url(con):
    assert auth.rp_id() == "fepra.example" and auth.rp_origin() == "https://fepra.example"


def test_register_options_shape(con):
    uid = auth.create_web_user(con, "p")
    o = auth.passkey_register_options(con, uid, now=T0)
    assert o["options"]["rp"]["id"] == "fepra.example"
    assert o["options"]["authenticatorSelection"]["residentKey"] == "required"
    assert con.execute("SELECT purpose,user_id FROM webauthn_challenges").fetchone()[:] == ("register", uid)


def test_register_verify_saves_passkey(con, monkeypatch):
    uid = auth.create_web_user(con, "p")
    cid = _register(con, monkeypatch, uid)
    row = con.execute("SELECT * FROM passkeys").fetchone()
    assert row["credential_id"] == cid and row["user_id"] == uid and row["name"] == "iPhone"
    assert bytes(row["public_key"]) == b"PUBKEY"
    assert auth.get_me(con, uid)["has_passkey"] is True
    assert con.execute("SELECT provider FROM auth_identities WHERE user_id=? AND provider='passkey'", (uid,)).fetchone()


def test_register_challenge_expired(con, monkeypatch):
    uid = auth.create_web_user(con, "p")
    monkeypatch.setattr(auth, "verify_registration_response", _verified_reg())
    o = auth.passkey_register_options(con, uid, now=T0)
    with pytest.raises(auth.AuthFailure, match="просрочен"):
        auth.passkey_register_verify(con, uid, o["challenge_id"], {"id": "x"},
                                     now=T0 + timedelta(seconds=auth.CHALLENGE_TTL_S + 1))


def test_register_foreign_challenge(con, monkeypatch):
    a, b = auth.create_web_user(con, "a"), auth.create_web_user(con, "b")
    monkeypatch.setattr(auth, "verify_registration_response", _verified_reg())
    o = auth.passkey_register_options(con, a, now=T0)
    with pytest.raises(auth.AuthFailure) as e:
        auth.passkey_register_verify(con, b, o["challenge_id"], {"id": "x"}, now=T0)
    assert e.value.status == 403


def test_challenge_single_use(con, monkeypatch):
    uid = auth.create_web_user(con, "p")
    monkeypatch.setattr(auth, "verify_registration_response", _verified_reg())
    o = auth.passkey_register_options(con, uid, now=T0)
    auth.passkey_register_verify(con, uid, o["challenge_id"], {"id": "x"}, now=T0)
    with pytest.raises(auth.AuthFailure, match="не найден"):
        auth.passkey_register_verify(con, uid, o["challenge_id"], {"id": "x"}, now=T0)


def test_register_wrong_purpose_and_lib_error(con, monkeypatch):
    uid = auth.create_web_user(con, "p")
    lo = auth.passkey_login_options(con, now=T0)
    with pytest.raises(auth.AuthFailure, match="другой операции"):
        auth.passkey_register_verify(con, uid, lo["challenge_id"], {"id": "x"}, now=T0)

    def boom(**kw):
        raise ValueError("bad attestation")
    monkeypatch.setattr(auth, "verify_registration_response", boom)
    o = auth.passkey_register_options(con, uid, now=T0)
    with pytest.raises(auth.AuthFailure) as e:
        auth.passkey_register_verify(con, uid, o["challenge_id"], {"id": "x"}, now=T0)
    assert e.value.status == 400
    assert con.execute("SELECT COUNT(*) FROM passkeys").fetchone()[0] == 0


def _login(con, monkeypatch, cred_b64, new_count, now=T0):
    monkeypatch.setattr(auth, "verify_authentication_response",
                        lambda **kw: SimpleNamespace(new_sign_count=new_count))
    o = auth.passkey_login_options(con, now=now)
    return auth.passkey_login_verify(con, o["challenge_id"], {"id": cred_b64}, "UA", now=now)


def test_login_discoverable_success_and_sign_count(con, monkeypatch):
    uid = auth.create_web_user(con, "p")
    cred = _register(con, monkeypatch, uid)
    assert auth.passkey_login_options(con, now=T0)["options"]["rpId"] == "fepra.example"
    got, sess = _login(con, monkeypatch, cred, 5)
    assert got == uid and auth.validate_session(con, sess, now=T0) == uid
    assert con.execute("SELECT sign_count FROM passkeys").fetchone()[0] == 5
    # тот же или меньший счётчик — клон
    with pytest.raises(auth.AuthFailure, match="sign_count"):
        _login(con, monkeypatch, cred, 5)
    with pytest.raises(auth.AuthFailure, match="sign_count"):
        _login(con, monkeypatch, cred, 3)
    assert _login(con, monkeypatch, cred, 6)[0] == uid


def test_login_zero_counter_allowed(con, monkeypatch):
    uid = auth.create_web_user(con, "p")
    cred = _register(con, monkeypatch, uid)
    assert _login(con, monkeypatch, cred, 0)[0] == uid
    assert _login(con, monkeypatch, cred, 0)[0] == uid


def test_login_unknown_credential_and_reuse_and_expiry(con, monkeypatch):
    uid = auth.create_web_user(con, "p")
    cred = _register(con, monkeypatch, uid)
    with pytest.raises(auth.AuthFailure) as e:
        _login(con, monkeypatch, "AAAA", 1)
    assert e.value.status == 401
    monkeypatch.setattr(auth, "verify_authentication_response", lambda **kw: SimpleNamespace(new_sign_count=1))
    o = auth.passkey_login_options(con, now=T0)
    auth.passkey_login_verify(con, o["challenge_id"], {"id": cred}, now=T0)
    with pytest.raises(auth.AuthFailure, match="не найден"):
        auth.passkey_login_verify(con, o["challenge_id"], {"id": cred}, now=T0)
    o = auth.passkey_login_options(con, now=T0)
    with pytest.raises(auth.AuthFailure, match="просрочен"):
        auth.passkey_login_verify(con, o["challenge_id"], {"id": cred}, now=T0 + timedelta(hours=1))


def test_login_signature_failure(con, monkeypatch):
    uid = auth.create_web_user(con, "p")
    cred = _register(con, monkeypatch, uid)

    def bad(**kw):
        raise ValueError("bad sig")
    monkeypatch.setattr(auth, "verify_authentication_response", bad)
    o = auth.passkey_login_options(con, now=T0)
    with pytest.raises(auth.AuthFailure) as e:
        auth.passkey_login_verify(con, o["challenge_id"], {"id": cred}, now=T0)
    assert e.value.status == 401


def test_login_denied_when_allowlist_removed(con, monkeypatch):
    uid = auth.create_web_user(con, "p")
    cred = _register(con, monkeypatch, uid)
    con.execute("DELETE FROM user_roles WHERE user_id=?", (uid,))
    con.commit()
    with pytest.raises(auth.AuthFailure) as e:
        _login(con, monkeypatch, cred, 1)
    assert e.value.status == 403


def test_duplicate_credential_conflict(con, monkeypatch):
    a, b = auth.create_web_user(con, "a"), auth.create_web_user(con, "b")
    _register(con, monkeypatch, a, cred=b"same")
    with pytest.raises(auth.AuthFailure) as e:
        _register(con, monkeypatch, b, cred=b"same")
    assert e.value.status == 409
