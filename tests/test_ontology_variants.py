from __future__ import annotations

from tj import ontology as o


def test_specific_variants_resolve():
    assert o.resolve("рывок в сед") == "squat_snatch"
    assert o.resolve("рывок в стойку") == "power_snatch"
    assert o.resolve("взятие с виса") == "hang_clean"
    assert o.resolve("взятие с пола") == "clean_floor"
    assert o.resolve("взятие на грудь") == "clean_floor"
    assert o.resolve("overhead squat") == "overhead_squat"


def test_generic_stays_generic():
    assert o.resolve("рывок") == "snatch"
    assert o.resolve("взятие") == "clean"


def test_bench_declensions_and_order():
    for p in ("жим лёжа", "жимов лёжа штанги", "жим лёжа штанги", "10 жимов лёжа"):
        assert "bench_press" in o.find(p), p


def test_new_canons_are_weighted():
    for c in ("power_snatch", "squat_snatch", "clean_floor", "hang_clean"):
        assert o.is_weighted(c), c


def test_variant_family():
    assert o.variant_family("snatch") == "snatch"
    assert o.variant_family("clean") == "clean"
    assert o.variant_family("squat_snatch") is None
    assert o.variant_family("deadlift") is None
