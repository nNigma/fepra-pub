"""Программа зала: тренер грузит ФОТО доски, атлеты получают её на выбранный день.
Раньше это делал userbot и кнопки бота; в PWA без фото тренеру приходилось набирать текст."""
from __future__ import annotations

from datetime import date

from p5a_env import p5a, wait_job  # noqa: F401
from tj.services import club as club_svc
from tj.services import uploads
from tjbot import access, vision
from tjbot import db as botdb

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64
BOARD = "Фронтальный присед 5×5\nWod#1\n21-15-9\nТрастеры с гантелями\nБерпи с подтягиванием"


def _mock(monkeypatch, calls):
    monkeypatch.setattr(vision, "has_vision", lambda: True)
    monkeypatch.setattr(vision, "has_claude", lambda: False)
    monkeypatch.setattr(vision, "enrich_aliases", lambda con, text, use_llm=True: botdb.load_aliases(con))

    def parse_board(data, media_type="image/jpeg", engine="gemini"):
        calls.append(engine)
        return {"raw_text": BOARD, "format": "other", "engine_used": engine}

    monkeypatch.setattr(vision, "parse_board", parse_board)


def _upload(p5a, uid, monkeypatch, tmp_path):
    monkeypatch.setenv("FEPRA_UPLOADS_DIR", str(tmp_path / "up"))
    return uploads.save(p5a.con, uid, JPEG, kind="board")["id"]


def test_coach_uploads_photo_then_athlete_sees_program(p5a, monkeypatch, tmp_path):
    calls = []
    _mock(monkeypatch, calls)
    coach = p5a.user(10, coach="Universe", gym="Universe")
    athlete = p5a.user(20, gym="Universe")
    up = _upload(p5a, coach, monkeypatch, tmp_path)
    cc = p5a.client(coach)

    r = cc.post("/api/club/program/parse", json={"upload_id": up, "engine": "fast"})
    assert r.status_code == 200, r.text
    j = wait_job(cc, r.json()["job_id"])
    assert j["status"] == "done" and j["result"]["recognized"]
    assert "Фронтальный присед" in j["result"]["board_text"]

    day = date.today().isoformat()
    s = cc.put("/api/club/program", json={"day": day, "raw_text": j["result"]["board_text"]})
    assert s.status_code == 200, s.text

    # атлет выбирает день и сразу получает форму по программе зала
    g = p5a.client(athlete).get(f"/api/gym-program?day={day}").json()
    assert g["found"] and g["gym"] == "Universe"
    assert [b["kind"] for b in g["form"]["blocks"]][:1] == ["strength"]
    assert calls == ["gemini"]                           # ИИ вызван один раз, на тренера


def test_photo_parse_does_not_spend_trainer_quota(p5a, monkeypatch, tmp_path):
    _mock(monkeypatch, [])
    coach = p5a.user(10, coach="Universe", gym="Universe")
    up = _upload(p5a, coach, monkeypatch, tmp_path)
    cc = p5a.client(coach)
    jid = cc.post("/api/club/program/parse", json={"upload_id": up}).json()["job_id"]
    assert wait_job(cc, jid)["status"] == "done"
    assert botdb.llm_quota_used(p5a.con, coach, date.today().isoformat()) == 0


def test_plain_user_cannot_parse_program_photo(p5a, monkeypatch, tmp_path):
    _mock(monkeypatch, [])
    athlete = p5a.user(20, gym="Universe")
    up = _upload(p5a, athlete, monkeypatch, tmp_path)
    r = p5a.client(athlete).post("/api/club/program/parse", json={"upload_id": up})
    assert r.status_code == 403


def test_foreign_upload_is_not_found(p5a, monkeypatch, tmp_path):
    _mock(monkeypatch, [])
    coach = p5a.user(10, coach="Universe", gym="Universe")
    other = p5a.user(30, gym="Universe")
    up = _upload(p5a, other, monkeypatch, tmp_path)
    r = p5a.client(coach).post("/api/club/program/parse", json={"upload_id": up})
    assert r.status_code == 404


def test_saving_program_notifies_gym_members_not_author(p5a):
    coach = p5a.user(10, coach="Universe", gym="Universe")
    a1 = p5a.user(20, gym="Universe")
    p5a.user(21, gym="Other")
    cc = p5a.client(coach)
    day = date.today().isoformat()
    assert cc.put("/api/club/program", json={"day": day, "raw_text": BOARD}).status_code == 200
    rows = p5a.con.execute('SELECT "uid","kind","text" FROM user_notices').fetchall()
    assert [(r["uid"], r["kind"]) for r in rows] == [(a1, "gym_program")]
    assert "сегодня" in rows[0]["text"]


def test_past_day_program_does_not_notify(p5a):
    coach = p5a.user(10, coach="Universe", gym="Universe")
    p5a.user(20, gym="Universe")
    day = "2020-01-01"
    p5a.client(coach).put("/api/club/program", json={"day": day, "raw_text": BOARD})
    assert p5a.con.execute("SELECT COUNT(*) FROM user_notices").fetchone()[0] == 0


def test_notify_members_counts_recipients(p5a):
    p5a.user(10, gym="Universe")
    p5a.user(20, gym="Universe")
    p5a.user(21, gym="Universe")
    assert club_svc.notify_members(p5a.con, 10, "Universe", date.today(), date.today()) == 2
