from __future__ import annotations
from tjbot.handlers.record_result import parse_lift, parse_benchmark


def test_parse_lift():
    assert parse_lift("130x1") == (130.0, 1)
    assert parse_lift("100 5") == (100.0, 5)
    assert parse_lift("142.5") == (142.5, 1)
    assert parse_lift("чушь") is None


def test_parse_lift_cyrillic_x():
    assert parse_lift("75 х 5") == (75.0, 5)
    assert parse_lift("75x5") == (75.0, 5)


def test_parse_benchmark_time():
    assert parse_benchmark("4:12", "time") == 252.0
    assert parse_benchmark("75", "time") == 75.0
    assert parse_benchmark("abc", "time") is None


def test_parse_benchmark_rounds():
    assert parse_benchmark("18", "rounds") == 18.0
    assert parse_benchmark("18+5", "rounds") == 18.0


def test_parse_lift_rejects_zero_and_bad_reps():
    assert parse_lift("0x1") is None
    assert parse_lift("0") is None
    assert parse_lift("100x0") is None


def test_parse_lift_unit_suffix():
    assert parse_lift("130 кг") == (130.0, 1)


def test_parse_benchmark_rejects_bad_time():
    assert parse_benchmark("4:60", "time") is None
    assert parse_benchmark("-1:00", "time") is None
