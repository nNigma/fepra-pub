from __future__ import annotations

from tj.analysis import wod_results, llm_coach


_BLOCKS = [
    {"format": "emom_strength", "header": "ТА",
     "movements": [{"name": "приседание со штангой на спине", "canon": "back_squat"}]},
    {"format": "amrap_interval", "header": "AMRAP", "movements": []},
]
_SCORE = (
    "приседание со штангой на спине:\n"
    "  раунд 1 (вес×повторы): 75 х 5\n"
    "  раунд 2 (вес×повторы): 80 х 5\n"
    "  раунд 3 (вес×повторы): 85 х 3\n"
    "AMRAP:\n"
    "  круги, амрап 1: 2\n"
)


def test_strength_work_sets_top_reps_tonnage():
    w = wod_results.strength_work(_BLOCKS, _SCORE)
    assert len(w) == 1
    sq = w[0]
    assert sq["movement"] == "приседание со штангой на спине"
    assert sq["sets"] == [[75.0, 5], [80.0, 5], [85.0, 3]]
    assert sq["top_kg"] == 85.0
    assert sq["reps_total"] == 13
    assert sq["tonnage_kg"] == 75 * 5 + 80 * 5 + 85 * 3


def test_workout_payload_carries_work_and_board():
    report = {
        "day": "2026-06-29", "hr_max": 184,
        "sessions": [{
            "sport": "crossfit", "duration_min": 84, "avg_hr": 130, "max_hr": 174,
            "calories": 828, "score": _SCORE,
            "extra": {"time_in_zones": [1000, 1100, 900, 1300, 140],
                      "primary_benefit": "ANAEROBIC_CAPACITY",
                      "board_text": "3 WOD\n- 20 прыжки через бокс",
                      "result_blocks": _BLOCKS,
                      "metcon": {"amrap": {"total_rounds": 10}, "times_sec": [516]}},
        }],
        "condition": {"readiness": 68, "acwr": 0.98, "hrv": 60, "sleep_h": 6.9, "resting_hr": 42},
    }
    p = llm_coach.workout_payload(report)
    assert p["board"] == "3 WOD\n- 20 прыжки через бокс"
    assert p["work"]["strength"][0]["top_kg"] == 85.0
    assert p["work"]["metcon"]["times_sec"] == [516]
    assert "score" not in p["performed"]
    assert "raw_score" not in str(p["work"])


def test_workout_payload_raw_score_fallback_without_blocks():
    report = {"day": "d", "hr_max": 184,
              "sessions": [{"sport": "crossfit", "score": "13:25", "extra": {}}],
              "condition": {}}
    p = llm_coach.workout_payload(report)
    assert p["work"] == {"raw_score": "13:25"}
    assert p["board"] is None
