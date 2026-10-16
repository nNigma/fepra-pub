"""Несколько залов: админ выбирает любой зал, тренер — из своих; программа пишется в выбранный зал."""
from __future__ import annotations

from datetime import date

from p5a_env import p5a  # noqa: F401
from tj.services import club as club_svc
from tjbot import access
from tjbot import db as botdb

BOARD = "Фронтальный присед 5×5\nWod#1\n21-15-9\nТрастеры с гантелями\nБерпи"
TODAY = date.today().isoformat()


def _gyms(p5a):
    for g in ("Атлант", "Сигма"):
        botdb.add_gym(p5a.con, g)


def test_admin_lists_all_gyms_and_saves_to_the_chosen_one(p5a):
    _gyms(p5a)
    admin = p5a.user(1, admin=True, gym="Universe")
    c = p5a.client(admin)
    j = c.get("/api/club/gyms").json()
    assert {g["name"] for g in j["gyms"]} == {"Universe", "Атлант", "Сигма"}
    assert all(g["can_manage"] for g in j["gyms"])
    assert j["current"] == "Universe" and j["can_add"] is True
    r = c.put("/api/club/program", json={"day": TODAY, "raw_text": BOARD, "gym": "Сигма"})
    assert r.status_code == 200, r.text
    assert r.json()["program"]["gym"] == "Сигма"
    # программа лежит только в выбранном зале
    assert c.get(f"/api/club/program?day={TODAY}&gym=Сигма").json()["program"]["raw_text"] == BOARD
    assert c.get(f"/api/club/program?day={TODAY}&gym=Универсал").status_code == 404
    assert c.get(f"/api/club/program?day={TODAY}&gym=Атлант").json()["program"] is None
    assert c.get(f"/api/club/program?day={TODAY}").json()["program"] is None       # свой зал Universe


def test_coach_with_two_gyms_chooses_between_them_but_not_others(p5a):
    _gyms(p5a)
    coach = p5a.user(2, gym="Universe")
    access.add_coach(coach, "Несуществующий")   # такой зал в списке тренера не показывается
    access.set_coach_gyms(coach, ["Universe", "Атлант"])
    c = p5a.client(coach)
    j = c.get("/api/club/gyms").json()
    assert [g["name"] for g in j["gyms"]] == ["Universe", "Атлант"]
    assert {g["name"]: g["can_manage"] for g in j["gyms"]} == {"Universe": True, "Атлант": True}
    assert c.put("/api/club/program", json={"day": TODAY, "raw_text": BOARD, "gym": "Атлант"}).status_code == 200
    assert c.put("/api/club/program", json={"day": TODAY, "raw_text": BOARD, "gym": "Universe"}).status_code == 200
    # чужой зал недоступен ни для просмотра, ни для записи
    assert c.put("/api/club/program", json={"day": TODAY, "raw_text": BOARD, "gym": "Сигма"}).status_code == 403
    assert c.get(f"/api/club/program?day={TODAY}&gym=Сигма").status_code == 403


def test_plain_athlete_sees_only_own_gym_and_cannot_pick_another(p5a):
    _gyms(p5a)
    ath = p5a.user(3, gym="Universe")
    c = p5a.client(ath)
    j = c.get("/api/club/gyms").json()
    assert [g["name"] for g in j["gyms"]] == ["Universe"] and not j["gyms"][0]["can_manage"]
    assert j["can_add"] is False
    assert c.get(f"/api/club/program?day={TODAY}&gym=Атлант").status_code == 403
    assert c.put("/api/club/program", json={"day": TODAY, "raw_text": BOARD, "gym": "Universe"}).status_code == 403


def test_gym_program_for_athlete_uses_profile_gym_and_gym_param_is_guarded(p5a):
    _gyms(p5a)
    coach = p5a.user(2, gym="Universe")
    access.set_coach_gyms(coach, ["Universe", "Атлант"])
    p5a.client(coach).put("/api/club/program", json={"day": TODAY, "raw_text": BOARD, "gym": "Атлант"})
    ath_a = p5a.user(4, gym="Атлант")
    ath_u = p5a.user(5, gym="Universe")
    assert p5a.client(ath_a).get(f"/api/gym-program?day={TODAY}").json()["found"] is True
    assert p5a.client(ath_u).get(f"/api/gym-program?day={TODAY}").json()["found"] is False
    assert p5a.client(ath_u).get(f"/api/gym-program?day={TODAY}&gym=Атлант").status_code == 403
    # тренер обоих залов может открыть программу Атланта, будучи прописан в Universe
    assert p5a.client(coach).get(f"/api/gym-program?day={TODAY}&gym=Атлант").json()["found"] is True


def test_notification_goes_to_members_of_the_chosen_gym_only(p5a):
    _gyms(p5a)
    admin = p5a.user(1, admin=True, gym="Universe")
    in_atlant = p5a.user(6, gym="Атлант")
    p5a.user(7, gym="Universe")
    p5a.client(admin).put("/api/club/program", json={"day": TODAY, "raw_text": BOARD, "gym": "Атлант"})
    rows = p5a.con.execute('SELECT "uid" FROM user_notices WHERE "kind"=\'gym_program\'').fetchall()
    assert [r["uid"] for r in rows] == [in_atlant]


def test_photo_parse_respects_the_chosen_gym(p5a, monkeypatch, tmp_path):
    from tj.services import uploads
    from tjbot import vision
    from p5a_env import wait_job
    monkeypatch.setattr(vision, "has_vision", lambda: True)
    monkeypatch.setattr(vision, "has_claude", lambda: False)
    monkeypatch.setattr(vision, "enrich_aliases", lambda con, text, use_llm=True: botdb.load_aliases(con))
    monkeypatch.setattr(vision, "parse_board", lambda d, media_type="image/jpeg", engine="gemini":
                        {"raw_text": BOARD, "format": "other", "engine_used": engine})
    monkeypatch.setenv("FEPRA_UPLOADS_DIR", str(tmp_path / "up"))
    _gyms(p5a)
    coach = p5a.user(2, gym="Universe")
    access.set_coach_gyms(coach, ["Universe"])
    up = uploads.save(p5a.con, coach, b"\xff\xd8\xff\xe0" + b"0" * 64, kind="board")["id"]
    c = p5a.client(coach)
    assert c.post("/api/club/program/parse", json={"upload_id": up, "gym": "Атлант"}).status_code == 403
    r = c.post("/api/club/program/parse", json={"upload_id": up, "gym": "Universe"})
    assert wait_job(c, r.json()["job_id"])["status"] == "done"


# --- администрирование тренеров ---

def test_admin_assigns_several_gyms_to_a_coach_and_revokes_one(p5a):
    _gyms(p5a)
    admin = p5a.user(1, admin=True)
    coach = p5a.user(2, gym="Universe")
    c = p5a.client(admin)
    assert c.post("/api/admin/coaches", json={"user_id": coach, "gym": "Universe"}).json()["gyms"] == ["Universe"]
    r = c.post("/api/admin/coaches", json={"user_id": coach, "gym": "Атлант"}).json()
    assert r["gyms"] == ["Universe", "Атлант"] and r["gym"] == "Universe"
    listed = c.get("/api/admin/coaches").json()
    assert listed == [{"id": coach, "nick": f"u{coach}", "gym": "Universe", "gyms": ["Universe", "Атлант"]}]
    # тренеры видны в списке залов админки по каждому залу
    by_gym = {g["name"]: [x["id"] for x in g["coaches"]] for g in c.get("/api/admin/gyms").json()}
    assert by_gym["Universe"] == [coach] and by_gym["Атлант"] == [coach] and by_gym["Сигма"] == []
    assert c.delete(f"/api/admin/coaches/{coach}?gym=Universe").status_code == 200
    assert c.get("/api/admin/coaches").json()[0]["gyms"] == ["Атлант"]
    assert c.delete(f"/api/admin/coaches/{coach}?gym=Сигма").status_code == 404
    assert c.delete(f"/api/admin/coaches/{coach}").status_code == 200
    assert c.get("/api/admin/coaches").json() == []


def test_admin_roles_endpoint_accepts_a_list_of_gyms(p5a):
    _gyms(p5a)
    admin = p5a.user(1, admin=True)
    coach = p5a.user(2, gym="Universe")
    c = p5a.client(admin)
    r = c.put(f"/api/admin/users/{coach}/roles", json={"coach": ["Атлант", "Сигма"]})
    assert r.status_code == 200 and r.json()["roles"]["coach_gyms"] == ["Атлант", "Сигма"]
    assert c.put(f"/api/admin/users/{coach}/roles", json={"coach": ["Нет такого"]}).status_code == 422
    assert c.put(f"/api/admin/users/{coach}/roles", json={"coach": []}).status_code == 422
    assert c.put(f"/api/admin/users/{coach}/roles", json={"coach": "Сигма"}).json()["roles"]["coach_gyms"] == ["Сигма"]
    assert c.put(f"/api/admin/users/{coach}/roles", json={"coach": None}).json()["roles"]["coach"] is False


def test_migration_imports_existing_single_gym_coaches(tmp_path):
    import sqlite3
    from tj.migrations import _registry
    import importlib
    con = sqlite3.connect(":memory:")
    con.execute('CREATE TABLE user_roles ("user_id" INTEGER,"role" TEXT,"gym" TEXT,PRIMARY KEY("user_id","role"))')
    con.execute("INSERT INTO user_roles VALUES (9,'coach','Universe'),(9,'pro',NULL)")
    importlib.import_module("tj.migrations.0062_coach_gyms").upgrade(con)
    importlib.import_module("tj.migrations.0062_coach_gyms").upgrade(con)       # идемпотентна
    assert con.execute("SELECT user_id, gym FROM coach_gyms").fetchall() == [(9, "Universe")]


def test_managed_gyms_and_can_manage_are_case_insensitive(p5a):
    _gyms(p5a)
    coach = p5a.user(2, gym="Universe")
    access.set_coach_gyms(coach, ["атлант"])
    assert club_svc.can_manage(coach, "Атлант") and not club_svc.can_manage(coach, "Сигма")
    assert club_svc.managed_gyms(p5a.con, coach) == ["Атлант"]


def test_athlete_can_join_extra_gym_and_see_its_program(p5a):
    _gyms(p5a)
    coach = p5a.user(2, gym="Universe")
    access.set_coach_gyms(coach, ["Universe", "Атлант"])
    p5a.client(coach).put("/api/club/program", json={"day": TODAY, "raw_text": BOARD, "gym": "Атлант"})
    ath = p5a.user(3, gym="Universe")
    c = p5a.client(ath)
    # до вступления чужой зал недоступен
    assert c.get(f"/api/gym-program?day={TODAY}&gym=Атлант").status_code == 403
    r = c.patch("/api/profile", json={"extra_gyms": ["атлант", "Universe", "Атлант"]})
    assert r.status_code == 200, r.text
    assert r.json()["extra_gyms"] == ["Атлант"]           # без дублей, основной зал не входит, регистр канонический
    j = c.get("/api/club/gyms").json()
    assert [g["name"] for g in j["gyms"]] == ["Universe", "Атлант"] and not any(g["can_manage"] for g in j["gyms"])
    assert c.get(f"/api/gym-program?day={TODAY}&gym=Атлант").json()["found"] is True
    # писать в чужой зал по-прежнему нельзя
    assert c.put("/api/club/program", json={"day": TODAY, "raw_text": BOARD, "gym": "Атлант"}).status_code == 403
    # неизвестный зал и «solo/other» в доп. залы не годятся
    assert c.patch("/api/profile", json={"extra_gyms": ["Нет такого"]}).status_code == 422
    assert c.patch("/api/profile", json={"extra_gyms": ["solo"]}).status_code == 422
    # смена основного зала на доп. убирает его из доп.
    c.patch("/api/profile", json={"gym": "Атлант"})
    assert c.get("/api/profile").json()["extra_gyms"] == []


def test_extra_gym_members_are_notified(p5a):
    from tj.services import club
    _gyms(p5a)
    ath = p5a.user(3, gym="Universe")
    p5a.client(ath).patch("/api/profile", json={"extra_gyms": ["Сигма"]})
    assert 3 in [m["tg_id"] for m in botdb.gym_members(p5a.con, "Сигма")]
