from __future__ import annotations
from tj.analysis import standards
from tj import ontology


def test_load_has_tiers_and_disciplines():
    data = standards.load()
    assert data["tiers"][0] == "Новичок" and data["tiers"][-1] == "Элита"
    assert "deadlift" in standards.disciplines()
    assert "fran" in standards.disciplines()


def test_discipline_meta():
    dl = standards.disciplines()["deadlift"]
    assert dl["kind"] == "lift" and dl["unit"] == "kg" and dl["better"] == "higher"
    assert dl["basis"] == "bw_ratio" and len(dl["thresholds"]["m"]) == 5
    fr = standards.disciplines()["fran"]
    assert fr["kind"] == "benchmark" and fr["better"] == "lower" and fr["unit"] == "time"


def test_new_ontology_lifts_resolve():
    assert ontology.resolve("присед") == "back_squat"
    assert ontology.resolve("жим стоя") == "shoulder_press"
    assert ontology.resolve("clean and jerk") == "clean_and_jerk"
