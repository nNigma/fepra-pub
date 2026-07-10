from __future__ import annotations

from tj import ontology as o


def test_specific_variants_resolve():
    assert o.resolve("рывок в сед") == "squat_snatch"
    assert o.resolve("рывок в стойку") == "power_snatch"
    assert o.resolve("взятие с виса") == "hang_clean"
    assert o.resolve("взятие с пола") == "clean_floor"
    assert o.resolve("взятие на грудь") == "clean_floor"
    assert o.resolve("overhead squat") == "overhead_squat"
    assert o.resolve("Оверхед") == "overhead_squat"
    assert o.resolve("оверхед присед") == "overhead_squat"


def test_generic_stays_generic():
    assert o.resolve("рывок") == "snatch"
    assert o.resolve("взятие") == "clean"


def test_expanded_goal_lift_aliases():
    assert o.resolve("дэдлифт") == "deadlift"
    assert o.resolve("псшнс") == "back_squat"
    assert o.resolve("фр. пр") == "front_squat"
    assert o.resolve("бенч") == "bench_press"
    assert o.resolve("военный жим") == "shoulder_press"
    assert o.resolve("силовой рывок") == "power_snatch"
    assert o.resolve("рывок в глубокий сед") == "squat_snatch"
    assert o.resolve("толчок в ножницы") == "clean_and_jerk"
    assert o.resolve("взятие+толчок") == "clean_and_jerk"


def test_vzyatie_v_sed_is_squat_clean_not_hang():
    # «в сед» — про глубину (squat clean с пола), а не про вис
    assert o.resolve("взятие в сед") == "clean_floor"
    assert o.resolve("взятие с виса в сед") == "hang_clean"


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
