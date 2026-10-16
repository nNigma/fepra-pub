from __future__ import annotations
from tj.analysis import llm_coach


_REPORT = {
    "day": "2026-06-26", "hr_max": 184,
    "sessions": [{
        "sport": "crossfit", "duration_min": 89.4, "avg_hr": 132, "max_hr": 171,
        "calories": 700, "wod_name": "Становая-волна", "scaling": "scaled",
        "load_kg": 130, "score": "13:25", "rpe": 7,
        "hr_series": [[0, 80], [1, 90]],
        "zones": [600, 1200, 1500, 1080, 960],
        "extra": {"te_aerobic": 2.8, "te_anaerobic": 2.3, "primary_benefit": "ANAEROBIC_CAPACITY",
                  "intensity_min": [35, 28], "time_in_zones": [600, 1200, 1500, 1080, 960],
                  "hr_series_ref": "data/hr_x.json"},
    }],
    "condition": {"readiness": 58, "acwr": 1.2, "hrv": 51, "sleep_h": 7.9, "resting_hr": 44},
}


def test_workout_payload_is_compact():
    p = llm_coach.workout_payload(_REPORT)
    flat = str(p)
    assert "hr_series" not in flat and "hr_series_ref" not in flat
    assert p["max_hr"] == 171
    assert p["zones_min"] == {"z1": 10.0, "z2": 20.0, "z3": 25.0, "z4": 18.0, "z5": 16.0}
    assert p["te_aerobic"] == 2.8 and p["primary_benefit"] == "ANAEROBIC_CAPACITY"
    assert p["readiness"] == 58 and p["wod_name"] == "Становая-волна"
    assert p["resting_hr"] == 44 and p["sleep_h"] == 7.9 and p["acwr"] == 1.2


def test_payload_hash_stable_and_differs():
    p = llm_coach.workout_payload(_REPORT)
    h1 = llm_coach.payload_hash(p)
    h2 = llm_coach.payload_hash(llm_coach.workout_payload(_REPORT))
    assert h1 == h2
    p2 = dict(p, max_hr=180)
    assert llm_coach.payload_hash(p2) != h1


def test_coach_workout_falls_back_without_llm(monkeypatch):
    monkeypatch.setattr(llm_coach.llm, "complete", lambda *a, **k: None)
    assert llm_coach.coach_workout(llm_coach.workout_payload(_REPORT)) is None


def test_coach_workout_returns_text(monkeypatch):
    monkeypatch.setattr(llm_coach.llm, "complete", lambda system, user, **k: "ТЕКСТ")
    assert llm_coach.coach_workout(llm_coach.workout_payload(_REPORT)) == "ТЕКСТ"


def test_coach_claude_first(monkeypatch):
    from tj import llm
    monkeypatch.setattr(llm, "has_agent", lambda: False)
    monkeypatch.setattr(llm, "has_claude_text", lambda: True)
    monkeypatch.setattr(llm, "claude_complete", lambda p, **k: "от клода")
    text, engine = llm_coach.coach("summary", {"x": 1})
    assert text == "от клода" and engine == "claude"


def test_coach_agent_first_when_engine_agent(monkeypatch):
    """FEPRA_LLM_ENGINE=agent -> сначала агент; подпись — agent, не claude."""
    from tj import llm
    monkeypatch.setenv("FEPRA_LLM_ENGINE", "agent")
    monkeypatch.setattr(llm, "has_agent", lambda: True)
    monkeypatch.setattr(llm, "agent_run", lambda p, **k: "от агента")
    monkeypatch.setattr(llm, "claude_complete", lambda p, **k: "клод не должен был вызваться")
    text, engine = llm_coach.coach("summary", {"x": 1})
    assert text == "от агента" and engine == "agent"


def test_coach_falls_back_to_gemini(monkeypatch):
    """Ни агента, ни claude — разбор пишет Gemini, и это видно по подписи."""
    from tj import llm
    monkeypatch.setattr(llm, "has_agent", lambda: False)
    monkeypatch.setattr(llm, "has_claude_vision", lambda: False)
    monkeypatch.setattr(llm, "has_llm", lambda: True)
    monkeypatch.setattr(llm, "complete", lambda s, u, **k: "от жени")
    for kind in ("workout", "summary", "competitions"):
        text, engine = llm_coach.coach(kind, {"x": 1})
        assert text == "от жени" and engine == "gemini"
