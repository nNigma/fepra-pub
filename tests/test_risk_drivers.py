from tj.analysis.dashboard import _risk_driver_names


def test_risk_drivers_humanized_ru():
    assert _risk_driver_names(["rhr", "bb_charge", "respiration_rest"], "ru") == \
        ["Пульс покоя", "Ночной заряд", "Дыхание"]


def test_risk_drivers_humanized_en():
    assert _risk_driver_names(["rhr", "hrv"], "en") == ["Resting HR", "HRV"]


def test_risk_drivers_empty():
    assert _risk_driver_names([], "ru") == []


def test_spo2_low_flags_risk_and_output(tmp_path):
    import datetime as dt
    from tjbot import db as botdb
    from tj.models import DailyMetrics
    from tj.analysis.dashboard import summary_data
    p = tmp_path / "s.db"
    con = botdb.connect(str(p)); botdb.init_schema(con)
    botdb.insert_daily(con, DailyMetrics(day=dt.date(2026, 7, 10), readiness=70,
                       extra={"spo2_avg": 90, "spo2_lowest": 82}), tg_id=1)
    con.close()
    data = summary_data(str(p), "sqlite", 184, "m", dt.date(2026, 7, 10), tg_id=1)
    assert "Сатурация (SpO₂)" in data["state"]["risk"]["drivers"]
    assert data["spo2"] == {"avg": 90, "lowest": 82}


def test_spo2_normal_dip_not_flagged(tmp_path):
    # реальный кейс: средняя в норме (95), минимум кратко просел (86) — НЕ флаг
    import datetime as dt
    from tjbot import db as botdb
    from tj.models import DailyMetrics
    from tj.analysis.dashboard import summary_data
    p = tmp_path / "s2.db"
    con = botdb.connect(str(p)); botdb.init_schema(con)
    botdb.insert_daily(con, DailyMetrics(day=dt.date(2026, 7, 10), readiness=70,
                       extra={"spo2_avg": 95, "spo2_lowest": 86}), tg_id=1)
    con.close()
    data = summary_data(str(p), "sqlite", 184, "m", dt.date(2026, 7, 10), tg_id=1)
    assert "Сатурация (SpO₂)" not in data["state"]["risk"]["drivers"]
    assert data["spo2"] == {"avg": 95, "lowest": 86}


def test_summary_payload_carries_spo2():
    from tj.analysis.llm_coach import summary_payload
    p = summary_payload({"spo2": {"avg": 95, "lowest": 86}, "state": {}, "m": {}})
    assert p["spo2"] == {"avg": 95, "lowest": 86}


def test_summary_carries_hrv_status_and_sleep_struct(tmp_path):
    import datetime as dt
    from tjbot import db as botdb
    from tj.models import DailyMetrics
    from tj.analysis.dashboard import summary_data
    from tj.analysis.llm_coach import summary_payload
    p = tmp_path / "hs.db"
    con = botdb.connect(str(p)); botdb.init_schema(con)
    botdb.insert_daily(con, DailyMetrics(day=dt.date(2026, 7, 10), readiness=70,
                       extra={"hrv_status": "UNBALANCED", "sleep_deep_h": 1.2, "sleep_rem_h": 1.8}), tg_id=1)
    con.close()
    data = summary_data(str(p), "sqlite", 184, "m", dt.date(2026, 7, 10), tg_id=1)
    assert data["hrv_status"] == "UNBALANCED"
    assert data["sleep_deep_h"] == 1.2 and data["sleep_rem_h"] == 1.8
    pl = summary_payload(data)
    assert pl["hrv_status"] == "UNBALANCED"
    assert pl["sleep_deep_h"] == 1.2 and pl["sleep_rem_h"] == 1.8


def test_metrics_payload_has_new_series(tmp_path):
    import datetime as dt
    from tjbot import db as botdb
    from tj.models import DailyMetrics
    from tj.analysis.dashboard import summary_data
    p = tmp_path / "ms.db"
    con = botdb.connect(str(p)); botdb.init_schema(con)
    botdb.insert_daily(con, DailyMetrics(day=dt.date(2026, 7, 10), readiness=70,
                       extra={"spo2_avg": 95, "respiration_rest": 13,
                              "sleep_deep_h": 1.2, "sleep_rem_h": 1.1}), tg_id=1)
    con.close()
    mt = summary_data(str(p), "sqlite", 184, "m", dt.date(2026, 7, 10), tg_id=1)["metrics"]
    for k in ("spo2", "respiration", "sleep_deep", "sleep_rem"):
        assert k in mt, k
        assert mt[k]["series"][-1][1] is not None
