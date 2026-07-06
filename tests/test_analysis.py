"""Юнит-тесты аналитики нагрузки/прогрессии (чистые функции, без БД)."""
from __future__ import annotations

from tj.analysis.load import acwr, monotony, strain, trimp
from tj.analysis.progression import benchmark_trend, epley_1rm
from tj.analysis.verdict import verdict


def test_trimp_known_value():
    assert 105 < trimp(60, 150, 50, 190, "m") < 112


def test_trimp_guards():
    assert trimp(None, 150, 50, 190) == 0.0
    assert trimp(60, 150, 50, 50) == 0.0


def test_acwr():
    assert acwr([10] * 28) == 1.0
    assert acwr([10] * 21 + [20] * 7) == 1.6
    assert acwr([10] * 10) is None


def test_monotony_strain():
    assert monotony([10, 10, 10, 10, 10, 10, 10]) is None
    assert monotony([10, 0, 10, 0, 10, 0, 12]) > 0
    assert strain([10, 0, 10, 0, 10, 0, 12]) is not None


def test_epley():
    assert epley_1rm(100, 5) == 116.7
    assert epley_1rm(0, 5) is None


def test_benchmark_trend():
    rows = [("2026-03-01", "4:30", "rx"), ("2026-06-01", "4:12", "rx"), ("x", "AMRAP?", "rx")]
    out = benchmark_trend(rows)
    assert out == [("2026-03-01", 270, "rx"), ("2026-06-01", 252, "rx")]


def test_verdict_tiers():
    assert verdict(85, 0.2, 0.9)["level"] == "green"
    assert verdict(20, -3.5, 0.82)["level"] == "red"
    assert verdict(60, -0.5, 1.0)["level"] == "amber"
    assert verdict(80, -2.6, 0.9)["level"] == "red"
    assert verdict(85, 0.0, 1.6)["level"] == "amber"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} тестов прошло")
