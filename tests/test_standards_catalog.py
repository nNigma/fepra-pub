from __future__ import annotations

from tj.analysis import standards


def test_catalog_has_new_lifts_and_drops_generic():
    d = standards.disciplines()
    for did in ("squat_snatch", "power_snatch", "clean_floor", "hang_clean", "overhead_squat"):
        assert did in d and d[did]["kind"] == "lift", did
    assert "snatch" not in d and "clean" not in d
    assert d["clean_and_jerk"]["kind"] == "lift"


def test_thresholds_match_strength_level():
    d = standards.disciplines()
    assert d["deadlift"]["thresholds"]["m"] == [1.10, 1.46, 1.87, 2.34, 2.84]
    assert d["squat_snatch"]["thresholds"]["m"] == [0.47, 0.67, 0.92, 1.21, 1.53]
    assert d["power_snatch"]["thresholds"]["f"] == [0.27, 0.41, 0.56, 0.76, 0.97]
    assert d["overhead_squat"]["thresholds"]["m"] == [0.40, 0.66, 1.01, 1.43, 1.90]
