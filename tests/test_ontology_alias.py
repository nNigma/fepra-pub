from __future__ import annotations
from tj.ontology import resolve


def test_resolve_static_unchanged():
    assert resolve("становая") == "deadlift"
    assert resolve("СТАНОВАЯ") == "deadlift"
    assert resolve("неведомое") is None


def test_resolve_with_runtime_aliases():
    al = {"присед на ящик": "back_squat"}
    assert resolve("присед на ящик", al) == "back_squat"
    assert resolve("становая", al) == "deadlift"   # статика всё ещё работает


def test_resolve_alias_takes_priority():
    assert resolve("становая", {"становая": "deadlift_special"}) == "deadlift_special"
