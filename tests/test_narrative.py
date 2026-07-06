from __future__ import annotations
from tj.analysis.narrative import TemplatedNarrative, Block, to_json

def test_templated_passthrough_and_json():
    g = TemplatedNarrative()
    out = g.render([Block(kind="verdict", title="V", body="ok"),
                    Block(kind="risk", title="R", body="")])
    assert [b.title for b in out] == ["V"]
    assert to_json(out) == [{"kind": "verdict", "title": "V", "body": "ok"}]


def test_workout_blocks_from_extra():
    from tj.analysis.narrative import workout_blocks
    extra = {"primary_benefit": "ANAEROBIC_CAPACITY", "te_aerobic": 2.8, "te_anaerobic": 2.3,
             "time_in_zones": [1720, 925, 539, 929, 118], "intensity_min": [35, 28],
             "active_cal": 496, "recovery_h": 36}
    blocks = workout_blocks(extra, max_hr=171)
    kinds = [b.kind for b in blocks]
    assert "verdict" in kinds and "risk" in kinds and "advice" in kinds
    assert "анаэроб" in blocks[0].body.lower()


def test_period_blocks():
    from tj.analysis.narrative import period_blocks
    agg = {"workouts": 18, "vo2max_delta": +1, "weight_delta": -0.9,
           "low_aerobic_share": 0.22, "rhr_trend": "above", "hard_streak": 3,
           "next_start_days": 14}
    blocks = period_blocks(agg)
    kinds = [b.kind for b in blocks]
    assert "verdict" in kinds and "risk" in kinds and "advice" in kinds
    assert "18" in blocks[0].body


def test_workout_blocks_no_none_when_te_absent():
    from tj.analysis.narrative import workout_blocks
    blocks = workout_blocks({"primary_benefit": "AEROBIC_BASE"})
    assert "None" not in blocks[0].body


def test_period_blocks_no_none_when_fields_absent():
    from tj.analysis.narrative import period_blocks
    blocks = period_blocks({"workouts": 5})
    assert "None" not in blocks[0].body
