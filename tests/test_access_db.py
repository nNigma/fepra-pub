import json

import pytest

from tjbot import access, db as botdb


@pytest.fixture
def dbenv(tmp_path, monkeypatch):
    p = tmp_path / "t.db"
    monkeypatch.setenv("FEPRA_DB_PATH", str(p))
    con = botdb.connect(p)
    botdb.init_schema(con)
    con.close()
    return p


def test_no_db_means_no_roles_and_no_file_created(tmp_path, monkeypatch):
    p = tmp_path / "absent.db"
    monkeypatch.setenv("FEPRA_DB_PATH", str(p))
    assert access.is_allowed(1) is False and access.load_admins() == set()
    assert not p.exists()


def test_allow_roundtrip_in_db(dbenv):
    assert access.is_allowed(5) is False
    access.add_user(5)
    access.add_user(6)
    assert access.is_allowed(5) and access.load_allow() == {5, 6}
    access.remove_user(5)
    assert not access.is_allowed(5) and access.load_allow() == {6}


def test_admin_pro_in_db(dbenv):
    access.add_admin(1)
    access.add_pro(2)
    assert access.is_admin(1) and not access.is_admin(2)
    assert access.is_pro(2) and access.load_pro() == {2}
    access.remove_pro(2)
    assert not access.is_pro(2)


def test_coach_in_db(dbenv):
    access.add_coach(7, "Universe")
    access.add_coach(7, "Атлант")  # тренер может вести несколько залов: зал добавляется
    assert access.is_coach(7)
    assert access.coach_gyms(7) == ["Universe", "Атлант"]
    assert access.coach_gym(7) == "Universe"            # основной зал — первый
    assert access.load_coaches() == {7: "Universe"}
    access.remove_coach(7, gym="Universe")             # снять из одного зала: остальные остаются
    assert access.coach_gyms(7) == ["Атлант"] and access.coach_gym(7) == "Атлант"
    access.remove_coach(7)
    assert not access.is_coach(7) and access.coach_gym(7) is None and access.coach_gyms(7) == []


def test_set_coach_gyms_replaces_the_whole_set(dbenv):
    access.add_coach(8, "A")
    access.set_coach_gyms(8, ["B", "C"])
    assert access.coach_gyms(8) == ["B", "C"] and access.coach_gym(8) == "B"
    access.set_coach_gyms(8, [])
    assert not access.is_coach(8)


def test_explicit_path_keeps_json_behavior(dbenv, tmp_path):
    p = tmp_path / "users_allow.json"
    access.add_user(1, path=p)
    assert json.loads(p.read_text())["allowed_users"] == [1]
    assert access.is_allowed(1, path=p) is True
    assert access.is_allowed(1) is False  # в БД его нет: источники независимы


def test_add_works_when_db_lacks_table(tmp_path, monkeypatch):
    p = tmp_path / "old.db"
    monkeypatch.setenv("FEPRA_DB_PATH", str(p))
    botdb.connect(p).close()  # пустая БД без миграций
    assert access.is_allowed(1) is False
    access.add_user(1)
    assert access.is_allowed(1)
