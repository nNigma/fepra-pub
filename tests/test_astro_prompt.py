from __future__ import annotations

from tj.analysis import llm_coach as lc


def test_payload_hash_varies_by_astro():
    p = {"a": 1}
    assert lc.payload_hash(p, "ru", False) != lc.payload_hash(p, "ru", True)
    assert lc.payload_hash(p, "ru", True) == lc.payload_hash(p, "ru", True)


def test_sys_prompt_includes_astro_only_when_on():
    assert "Астро-разбор от Месье Клода" in lc._sys_workout("ru", astro=True)
    assert "Астро-разбор от Месье Клода" not in lc._sys_workout("ru", astro=False)
    assert "Astro reading by Monsieur Claude" in lc._sys_workout("en", astro=True)
    assert "Астро-разбор от Месье Клода" in lc._sys_summary("ru", astro=True)
    assert "Астро-разбор от Месье Клода" not in lc._sys_summary("ru", astro=False)
