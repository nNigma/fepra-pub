from __future__ import annotations
from tj.analysis import llm_coach
from tj.analysis.llm_coach import summary_payload, workout_payload


def test_summary_payload_flags_no_biometrics():
    data = {"m": {"readiness": None, "hrv": None, "rhr": None, "sleep": None, "acwr": 1.0,
                  "monotony": 1.0, "strain": 0, "range": ("2026-06-01", "2026-07-05"),
                  "acute7": 0, "chronic28": 0},
            "state": {"readiness": {"value": 70, "source": "self"}}, "agg": {},
            "verdict": {"source": "self"}, "self_feel": 7}
    p = summary_payload(data)
    assert p.get("has_biometrics") is False and p.get("self_feel") == 7


def test_summary_payload_flags_has_biometrics_via_watch_source():
    data = {"m": {"readiness": None, "hrv": None, "rhr": None, "sleep": None},
            "state": {"readiness": {"value": 62, "source": "watch"}}, "agg": {},
            "verdict": {"source": "watch"}, "self_feel": None}
    p = summary_payload(data)
    assert p.get("has_biometrics") is True


def test_summary_payload_flags_has_biometrics_via_biomarker():
    data = {"m": {"readiness": {"latest": 60, "base": 55, "delta": 5},
                  "hrv": None, "rhr": None, "sleep": None},
            "state": {"readiness": {"value": 60, "source": None}}, "agg": {},
            "verdict": {"source": None}, "self_feel": None}
    p = summary_payload(data)
    assert p.get("has_biometrics") is True


def test_workout_payload_flags_no_biometrics():
    report = {"day": "d", "hr_max": 184,
              "sessions": [{"sport": "crossfit", "score": "13:25", "extra": {}}],
              "condition": {}}
    p = workout_payload(report)
    assert p.get("has_biometrics") is False


def test_workout_payload_flags_has_biometrics():
    report = {"day": "2026-06-26", "hr_max": 184,
              "sessions": [{"sport": "crossfit", "duration_min": 89.4, "avg_hr": 132,
                            "max_hr": 171, "extra": {}}],
              "condition": {"readiness": 58, "acwr": 1.2, "hrv": 51, "sleep_h": 7.9,
                            "resting_hr": 44}}
    p = workout_payload(report)
    assert p.get("has_biometrics") is True


def test_sys_prompts_mention_self_feel_fallback():
    assert "self_feel" in llm_coach._SYS_SUMMARY_RU
    assert "self_feel" in llm_coach._SYS_WORKOUT_RU
    assert "self_feel" in llm_coach._SYS_SUMMARY_EN
    assert "self_feel" in llm_coach._SYS_WORKOUT_EN
