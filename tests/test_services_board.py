from __future__ import annotations

import pytest

from svc_common import BOARD, fill_by, make_con
from tj.analysis.wod_program import render_template
from tj.analysis.wod_results import extract_maxes, summarize_filled
from tj.services import board as B
from tj.services import uploads
from tj.services.errors import BadRequest, Invalid
from tjbot import access, vision
from tjbot import db as botdb

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def _ladder():
    return [{"header": "WOD", "format": "ladder", "scheme": [21, 15, 9], "rounds": 3,
             "reps": None, "work_min": None, "rest_min": None, "has_cap": False,
             "benchmark": None,
             "movements": [{"name": "становая тяга", "canon": "deadlift", "weighted": True},
                           {"name": "гребля", "canon": "row", "weighted": False},
                           {"name": "бёрпи", "canon": "burpee", "weighted": False}]}]


def _gym_skill():
    return [{"header": "Скилл", "format": "other", "rounds": None, "reps": None,
             "work_min": None, "rest_min": None, "has_cap": False, "scheme": None,
             "benchmark": None,
             "movements": [{"name": "Bar Muscle-Up ×5", "canon": "bar_muscle_up", "weighted": False}]}]


def _cap():
    return [{"header": "WOD", "format": "for_time", "rounds": 1, "reps": None, "work_min": None,
             "rest_min": None, "has_cap": True, "movements": [], "benchmark": None},
            {"header": "Death by", "format": "death_by", "rounds": None, "reps": None,
             "work_min": None, "rest_min": None, "has_cap": False, "benchmark": None,
             "movements": [{"name": "бёрпи", "canon": "burpee", "weighted": False}]},
            {"header": "AMRAP", "format": "amrap", "rounds": 1, "reps": None, "work_min": 20.0,
             "rest_min": None, "has_cap": False, "benchmark": None,
             "movements": [{"name": "подтягивания", "canon": "pull_up", "weighted": False}]}]


# --- форма = данные, а не текст -------------------------------------------------------------

def test_form_from_existing_board_example(tmp_path):
    con = make_con(tmp_path)
    b = B.build(con, 1, BOARD, verify=False, use_llm=False)
    form = b["form"]
    assert form["version"] == 1 and len(form["blocks"]) == len(b["blocks"]) == 4
    kinds = [x["kind"] for x in form["blocks"]]
    assert kinds == ["strength", "strength", "metcon", "metcon"]
    sq = form["blocks"][0]
    assert sq["title"] == "приседание со штангой на спине" and len(sq["fields"]) == 5
    assert {f["type"] for f in sq["fields"]} == {"weight_reps"}
    assert sq["fields"][0]["movement"] == "приседание со штангой на спине"
    wod = form["blocks"][2]
    assert [f["type"] for f in wod["fields"]] == ["weight_reps", "time"]   # вес × повторы (повторы по желанию)
    amrap = form["blocks"][3]
    assert amrap["format"] == "amrap_interval"
    assert [f["type"] for f in amrap["fields"]].count("rounds_reps") == 5
    keys = [f["key"] for x in form["blocks"] for f in x["fields"]]
    assert len(keys) == len(set(keys))                       # ключи уникальны
    assert all(not str(f["label"]).endswith("_") for x in form["blocks"] for f in x["fields"])
    assert b["template_text"] and "___" not in b["template_text"]


@pytest.mark.parametrize("blocks", [_ladder(), _gym_skill(), _cap()])
def test_empty_form_reproduces_bot_template_line_by_line(blocks):
    """Форма, превращённая обратно в текст без значений, = шаблон бота (те же строки)."""
    form = B.result_form(blocks)
    text = B.fill_template(form, {})
    assert [ln.rstrip() for ln in text.splitlines()] == render_template(blocks).splitlines()


def test_ladder_gym_and_cap_field_types():
    lad = B.result_form(_ladder())["blocks"][0]
    types = [f["type"] for f in lad["fields"]]
    # вес в лесенке — «вес×повторы» с повторами по схеме (атрибут reps_default), но их можно менять
    assert types == ["weight_reps"] * 3 + ["cardio"] * 3 + ["int"] * 3 + ["time"]
    assert [f.get("reps_default") for f in lad["fields"][:3]] == [10, 8, 6][:3] or all(
        f.get("reps_default") for f in lad["fields"][:3])
    assert {f["group"] for f in lad["fields"]} >= {"становая тяга", "гребля", "бёрпи"}
    assert B.result_form(_gym_skill())["blocks"][0]["fields"][0]["type"] == "int"
    cap = B.result_form(_cap())["blocks"]
    assert [f["type"] for f in cap[0]["fields"]] == ["time", "int"]
    assert [f["type"] for f in cap[1]["fields"]] == ["int", "int"]
    assert [f["type"] for f in cap[2]["fields"]] == ["int", "int"]


def test_filled_form_goes_through_existing_parsers():
    blocks = B.check_blocks(_cap() + [
        {"header": "ТА", "format": "emom_strength", "rounds": 2, "reps": 3, "has_cap": False,
         "movements": [{"name": "становая тяга", "canon": "deadlift", "weighted": True}],
         "benchmark": None}])
    form = B.result_form(blocks)
    text = B.fill_template(form, fill_by(form, {
        "время": "12:30", "не уложился": 7, "дошёл до минуты": "9", "повторов в незавершённой": 4,
        "кругов": 6, "повторов (неполный круг)": 2, "раунд 1": "140x3", "раунд 2": {"weight": 150, "reps": 2}}))
    data, lines = summarize_filled(blocks, text)
    assert data["times_sec"] == [750]
    assert data["amrap"]["rounds"] == [(6, 2)]
    assert any("до минуты 9" in ln for ln in lines) and any("не в кэпе: 7" in ln for ln in lines)
    assert extract_maxes(blocks, text) == [{"movement": "становая тяга", "weight_kg": 150.0, "reps": 2}]


def test_value_normalization_and_errors():
    form = B.result_form(_cap() + _ladder())
    f = {x["label"]: x for b in form["blocks"] for x in b["fields"]}
    t = f["время (мм:сс)"]
    assert B.normalize_value(t, 252) == "4:12" and B.normalize_value(t, "4:12") == "4:12"
    assert B.normalize_value(t, None) == "" and B.normalize_value(t, "") == ""
    for bad in ("4:75", "abc", -5, "1:2:3"):
        with pytest.raises(Invalid):
            B.normalize_value(t, bad)
    wr = B.result_form([{"format": "strength", "rounds": 1, "movements": [
        {"name": "жим", "canon": "bench_press", "weighted": True}]}])["blocks"][0]["fields"][0]
    assert B.normalize_value(wr, "100 x 5") == "100x5" and B.normalize_value(wr, 80) == "80x1"
    assert B.normalize_value(wr, [90, 3]) == "90x3"
    for bad in ("много", 0, {"weight": 100}, "-5x1"):
        with pytest.raises(Invalid):
            B.normalize_value(wr, bad)
    rr = next(x for x in B.result_form(_ladder() + [
        {"header": "AMRAP", "format": "amrap_interval", "rounds": 2, "work_min": 3.0, "has_cap": False,
         "movements": [], "benchmark": None}])["blocks"][1]["fields"] if x["type"] == "rounds_reps")
    assert B.normalize_value(rr, "5 + 3") == "5+3" and B.normalize_value(rr, 4) == "4"
    assert B.normalize_value(rr, {"rounds": 5, "reps": 3}) == "5+3"
    with pytest.raises(Invalid):
        B.normalize_value(rr, "пять")


def test_check_blocks_rejects_garbage():
    for bad in (None, [], "x", [1], [{"movements": []}], [{"format": "amrap", "movements": "x"}]):
        with pytest.raises(Invalid):
            B.check_blocks(bad)


# --- parse: текст / фото / квота ---------------------------------------------------------------

def _mock_llm(monkeypatch, *, has=True):
    calls = {"text": [], "board": []}
    monkeypatch.setattr(vision, "has_vision", lambda: has)
    monkeypatch.setattr(vision, "has_claude", lambda: False)
    monkeypatch.setattr(vision, "enrich_aliases",
                        lambda con, text, use_llm=True: botdb.load_aliases(con))

    def parse_text(text, use_llm=True):
        calls["text"].append(use_llm)
        return {"raw_text": text.strip(), "format": "amrap", "movements": []}

    def parse_board(data, media_type="image/jpeg", engine="gemini"):
        calls["board"].append((len(data), media_type, engine))
        return {"raw_text": BOARD, "format": "other", "engine_used": engine}

    monkeypatch.setattr(vision, "parse_text", parse_text)
    monkeypatch.setattr(vision, "parse_board", parse_board)
    return calls


def test_parse_text_returns_blocks_and_form(tmp_path, monkeypatch):
    calls = _mock_llm(monkeypatch)
    con = make_con(tmp_path)
    r = B.parse(con, 5, text=BOARD)
    assert r["recognized"] and r["board_text"].startswith("Актив") and r["format"] == "amrap"
    assert len(r["blocks"]) == 4 and len(r["form"]["blocks"]) == 4
    assert "приседание" in r["template_text"] and "(5 раунд" in r["annotated"] or "раунд" in r["annotated"]
    assert calls["text"] == [True]


def test_parse_verbatim_edit_uses_no_llm_and_no_quota(tmp_path, monkeypatch):
    calls = _mock_llm(monkeypatch)
    con = make_con(tmp_path)
    r = B.parse(con, 5, text=BOARD, verbatim=True)
    assert r["recognized"] and calls["text"] == []
    assert botdb.llm_quota_used(con, 5, __import__("datetime").date.today().isoformat()) == 0


def test_parse_photo_via_upload(tmp_path, monkeypatch):
    calls = _mock_llm(monkeypatch)
    monkeypatch.setenv("FEPRA_UPLOADS_DIR", str(tmp_path / "up"))
    con = make_con(tmp_path)
    up = uploads.save(con, 5, JPEG, kind="board")
    r = B.parse(con, 5, upload_id=up["id"], engine="slow")
    assert r["recognized"] and r["engine_used"] == "claude" and len(r["form"]["blocks"]) == 4
    assert calls["board"] == [(len(JPEG), "image/jpeg", "claude")]
    B.parse(con, 5, upload_id=up["id"], engine="fast")
    assert calls["board"][-1][2] == "gemini"
    with pytest.raises(BadRequest):
        B.parse(con, 5, upload_id=up["id"], engine="warp")


def test_parse_photo_of_other_user_is_not_found(tmp_path, monkeypatch):
    _mock_llm(monkeypatch)
    monkeypatch.setenv("FEPRA_UPLOADS_DIR", str(tmp_path / "up"))
    con = make_con(tmp_path)
    up = uploads.save(con, 5, JPEG)
    from tj.services.errors import NotFound
    with pytest.raises(NotFound):
        B.parse(con, 6, upload_id=up["id"])


def test_parse_needs_exactly_one_source(tmp_path, monkeypatch):
    _mock_llm(monkeypatch)
    con = make_con(tmp_path)
    for kw in ({}, {"text": "  "}, {"text": "x", "upload_id": "y"}):
        with pytest.raises(BadRequest):
            B.parse(con, 5, **kw)


def test_llm_quota_photo_and_text(tmp_path, monkeypatch):
    calls = _mock_llm(monkeypatch)
    monkeypatch.setenv("FEPRA_UPLOADS_DIR", str(tmp_path / "up"))
    con = make_con(tmp_path)
    up = uploads.save(con, 5, JPEG)
    for _ in range(access.LLM_DAILY_LIMIT - 1):
        assert B.parse(con, 5, upload_id=up["id"])["recognized"]
    assert B.parse(con, 5, text=BOARD)["recognized"]            # последняя единица квоты — текстом
    assert calls["text"] == [True]
    n_board = len(calls["board"])
    r = B.parse(con, 5, upload_id=up["id"])                     # квота кончилась: фото не разбираем
    assert r["recognized"] is False and r["reason"] == "quota" and r["blocks"] == []
    assert len(calls["board"]) == n_board
    r = B.parse(con, 5, text=BOARD)                             # текст — без ИИ, но блоки строятся
    assert r["recognized"] and calls["text"][-1] is False and len(r["blocks"]) == 4


def test_parse_photo_not_recognized_and_no_vision(tmp_path, monkeypatch):
    _mock_llm(monkeypatch)
    monkeypatch.setenv("FEPRA_UPLOADS_DIR", str(tmp_path / "up"))
    con = make_con(tmp_path)
    up = uploads.save(con, 5, JPEG)
    monkeypatch.setattr(vision, "parse_board", lambda *a, **k: None)
    r = B.parse(con, 5, upload_id=up["id"])
    assert r == {**r, "recognized": False, "reason": "not_recognized"}
    monkeypatch.setattr(vision, "has_vision", lambda: False)
    assert B.parse(con, 5, upload_id=up["id"])["reason"] == "no_vision"
    assert B.parse(con, 5, text=BOARD)["recognized"]            # текст без ИИ всё равно разбирается


def test_claude_verification_is_used_when_available(tmp_path, monkeypatch):
    _mock_llm(monkeypatch)
    monkeypatch.setattr(vision, "has_claude", lambda: True)
    monkeypatch.setattr(vision, "engine_for", lambda uid: "claude")
    seen = {}

    def verify(text, blocks, aliases=None):
        seen["n"] = len(blocks)
        return blocks[:1], True

    monkeypatch.setattr(vision, "verify_result_blocks", verify)
    con = make_con(tmp_path)
    r = B.parse(con, 5, text=BOARD)
    assert seen["n"] == 4 and r["blocks_verified"] is True and len(r["form"]["blocks"]) == 1


# --- программа зала на день ------------------------------------------------------------------

def test_gym_program_uses_stored_verified_blocks(tmp_path, monkeypatch):
    import json
    _mock_llm(monkeypatch)
    con = make_con(tmp_path)
    assert B.gym_program(con, 5, "2026-09-01") is None
    stored = _ladder()
    botdb.add_program(con, "2026-09-01", "Universe", "WOD ladder", confirmed=1, blocks=stored)
    botdb.add_program(con, "2026-09-02", "Universe", BOARD, confirmed=1)
    botdb.add_program(con, "2026-09-03", "Universe", BOARD, confirmed=0)   # не подтверждена
    p = B.gym_program(con, 5, "2026-09-01")
    assert p["blocks_verified"] and p["gym"] == "Universe" and p["form"]["blocks"][0]["kind"] == "metcon"
    p2 = B.gym_program(con, 5, "2026-09-02")
    assert not p2["blocks_verified"] and len(p2["form"]["blocks"]) == 4
    assert B.gym_program(con, 5, "2026-09-03") is None
