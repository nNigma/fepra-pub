"""Общие помощники тестов API питания и соревнований."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from tj.services import uploads
from tjapp.api import app
from tjapp.deps import require_user
from tjbot import access, db as botdb

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64

DRAFT = {"foods": [{"name": "овощной суп", "grams": 300, "kcal": 150,
                    "protein_g": 5, "fat_g": 5, "carb_g": 20}],
         "totals": {"kcal": 150, "protein_g": 5, "fat_g": 5, "carb_g": 20},
         "question": None, "confidence": "medium",
         "quality": 2, "quality_note": "лёгкий суп"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    p = tmp_path / "t.db"
    monkeypatch.setenv("FEPRA_DB_PATH", str(p))
    monkeypatch.setenv("FEPRA_UPLOADS_DIR", str(tmp_path / "up"))
    con = botdb.connect(p)
    botdb.init_schema(con)
    yield con
    con.close()
    app.dependency_overrides.clear()


def login(uid: int, *, pro: bool = False, admin: bool = False) -> TestClient:
    if pro:
        access.add_pro(uid)
    if admin:
        access.add_admin(uid)
    app.dependency_overrides[require_user] = lambda: {"id": uid, "via": "test"}
    return TestClient(app)


def make_upload(con, uid: int, kind: str = "meal") -> str:
    return uploads.save(con, uid, JPEG, kind=kind)["id"]


def wait_job(c: TestClient, job_id: str, timeout: float = 5.0) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        j = c.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("done", "error"):
            return j
        time.sleep(0.02)
    raise AssertionError("job не завершился")
