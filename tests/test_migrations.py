import json

from tj import migrations
from tjbot import db as botdb


def _con(tmp_path):
    con = botdb.connect(tmp_path / "t.db")
    return con


def test_init_schema_runs_migrations_and_sets_version(tmp_path):
    con = _con(tmp_path)
    botdb.init_schema(con)
    top = migrations._registry()[-1][0]
    assert migrations.current_version(con) == top
    for t in ("user_roles", "auth_identities", "invites", "sessions", "passkeys",
              "webauthn_challenges", "jobs"):
        assert con.execute("SELECT name FROM sqlite_master WHERE name=?", (t,)).fetchone(), t


def test_run_migrations_idempotent(tmp_path):
    con = _con(tmp_path)
    botdb.init_schema(con)
    v = migrations.run_migrations(con)
    v2 = migrations.run_migrations(con)
    botdb.init_schema(con)
    assert v == v2 == migrations.current_version(con)


def test_registry_sorted_and_unique():
    nums = [n for n, _ in migrations._registry()]
    assert nums == sorted(set(nums)) and nums[0] == 1


def test_json_roles_imported_from_next_to_db(tmp_path):
    (tmp_path / "users_allow.json").write_text(json.dumps({"allowed_users": [1, 2, 3]}))
    (tmp_path / "admins.json").write_text(json.dumps({"admins": [1]}))
    (tmp_path / "pro_users.json").write_text(json.dumps({"pro_users": [2]}))
    (tmp_path / "coaches.json").write_text(json.dumps({"coaches": {"3": "Universe"}}))
    con = _con(tmp_path)
    botdb.init_schema(con)
    rows = {(r[0], r[1], r[2]) for r in con.execute("SELECT user_id,role,gym FROM user_roles")}
    assert rows == {(1, "allowlist", None), (2, "allowlist", None), (3, "allowlist", None),
                    (1, "admin", None), (2, "pro", None), (3, "coach", "Universe")}


def test_json_import_is_one_time(tmp_path):
    f = tmp_path / "users_allow.json"
    f.write_text(json.dumps({"allowed_users": [1]}))
    con = _con(tmp_path)
    botdb.init_schema(con)
    con.execute("DELETE FROM user_roles")
    con.commit()
    botdb.init_schema(con)  # версия уже применена — повторного импорта нет
    assert con.execute("SELECT COUNT(*) FROM user_roles").fetchone()[0] == 0


def test_broken_json_ignored(tmp_path):
    (tmp_path / "admins.json").write_text("{oops")
    con = _con(tmp_path)
    botdb.init_schema(con)
    assert con.execute("SELECT COUNT(*) FROM user_roles").fetchone()[0] == 0


def test_late_lower_number_migration_is_not_skipped(tmp_path, monkeypatch):
    """Миграция с номером ниже уже применённых (параллельные ветки) всё равно применяется."""
    import sqlite3
    from tj import migrations

    con = sqlite3.connect(":memory:")
    real = migrations._registry()
    applied_first = [(n, m) for n, m in real if n != 20]
    monkeypatch.setattr(migrations, "_registry", lambda: applied_first)
    migrations.run_migrations(con)
    assert migrations.current_version(con) >= 40
    monkeypatch.setattr(migrations, "_registry", lambda: real)
    migrations.run_migrations(con)
    tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    assert "jobs" in tables


def test_two_migrations_same_number_both_apply():
    import sqlite3
    from tj import migrations
    nums = [n for n, _ in migrations._registry()]
    assert len(nums) == len(set(nums)), "дубли номеров миграций"
    con = sqlite3.connect(":memory:")
    migrations.run_migrations(con)
    tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    assert {"jobs", "uploads", "user_notices"} <= tables
