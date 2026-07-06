from __future__ import annotations

from tj.analysis.advice import next_session_advice


def test_low_readiness_overrides_everything():
    a = next_session_advice(acwr=0.7, readiness=32, risk_level="green",
                            hard_streak=0, monotony=0.5)
    assert a["level"] == "red"
    assert "не грузись" in a["title"].lower()
    assert a["source"] == "rules"


def test_fresh_acwr_push():
    a = next_session_advice(acwr=0.75, readiness=75, risk_level="green",
                            hard_streak=1, monotony=0.6)
    assert a["level"] == "green"
    assert "рвать" in a["title"].lower()
    assert "объ" in a["text"].lower() or "вес" in a["text"].lower()


def test_high_acwr_brake():
    a = next_session_advice(acwr=1.6, readiness=70, risk_level="amber",
                            hard_streak=1, monotony=1.0)
    assert a["level"] == "red"
    assert "тормоз" in a["title"].lower()


def test_mid_high_acwr_caution():
    a = next_session_advice(acwr=1.35, readiness=70, risk_level="green",
                            hard_streak=1, monotony=1.0)
    assert a["level"] == "amber"


def test_hard_streak_before_push():
    a = next_session_advice(acwr=0.7, readiness=70, risk_level="green",
                            hard_streak=3, monotony=0.6)
    assert a["level"] == "amber"
    assert "рвать" not in a["title"].lower()


def test_normal_zone():
    a = next_session_advice(acwr=1.0, readiness=72, risk_level="green",
                            hard_streak=1, monotony=1.0)
    assert a["level"] == "green"
    assert "рабоч" in a["title"].lower()


def test_missing_data_safe():
    a = next_session_advice(acwr=None, readiness=None, risk_level=None,
                            hard_streak=None, monotony=None)
    assert a["level"] in ("green", "amber", "red")
    assert a["title"] and a["text"]
