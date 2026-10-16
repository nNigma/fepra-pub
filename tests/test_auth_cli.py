import pytest

from tj.services import auth, auth_cli
from tjbot import db as botdb


def test_cli_invite_prints_link_and_redeems(tmp_path, monkeypatch, capsys):
    p = tmp_path / "t.db"
    monkeypatch.setenv("FEPRA_DB_PATH", str(p))
    monkeypatch.setenv("FEPRA_PUBLIC_URL", "https://x.test")
    assert auth_cli.main(["invite", "--admin"]) == 0
    url = capsys.readouterr().out.strip()
    prefix = "https://x.test/app/#/invite/"
    assert url.startswith(prefix)
    con = botdb.connect(p)
    uid, _ = auth.redeem_invite(con, url[len(prefix):], "Owner")
    assert auth.roles_of(con, uid)["admin"]


def test_cli_existing_id_unknown(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FEPRA_DB_PATH", str(tmp_path / "t.db"))
    assert auth_cli.main(["invite", "--existing-id", "5"]) == 2
    assert "ошибка" in capsys.readouterr().err


def test_cli_existing_id_ok(tmp_path, monkeypatch, capsys):
    p = tmp_path / "t.db"
    monkeypatch.setenv("FEPRA_DB_PATH", str(p))
    con = botdb.connect(p); botdb.init_schema(con)
    botdb.save_user(con, 7, nick="a", height_cm=None, weight_kg=None, sex=None, gym=None)
    con.close()
    assert auth_cli.main(["invite", "--existing-id", "7"]) == 0
