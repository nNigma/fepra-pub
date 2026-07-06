from __future__ import annotations

from tj.analysis.benchmarks import lookup, catalog


def test_catalog_has_core():
    c = catalog()
    for k in ("fran", "grace", "cindy", "murph", "dt"):
        assert k in c


def test_lookup_by_alias():
    assert lookup("Fran")["format"] == "for_time"
    assert lookup("фрэн")["format"] == "for_time"
    assert lookup("Cindy")["format"] == "amrap"
    assert lookup("не бенчмарк") is None


def test_fran_fields():
    fr = lookup("fran")
    assert fr["rep_scheme"] == "21-15-9"
    assert "thruster" in fr["movements"]
    assert fr["score"] == "time"
