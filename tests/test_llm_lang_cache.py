from tj.analysis import llm_coach


def test_hash_depends_on_lang():
    p = {"a": 1}
    assert llm_coach.payload_hash(p, "ru") != llm_coach.payload_hash(p, "en")


def test_workout_markers_differ_by_lang():
    ru = llm_coach._wk_labels("ru"); en = llm_coach._wk_labels("en")
    assert [k for _, k in ru] == [k for _, k in en]
    assert [lb for lb, _ in ru] != [lb for lb, _ in en]


def test_parse_workout_blocks_en():
    txt = "What it builds: engine.\nZones: z1.\nRisk: low.\nAdvice: rest."
    blocks = llm_coach.parse_workout_blocks(txt, "en")
    assert blocks and any(b.get("kind") == "verdict" for b in blocks)
