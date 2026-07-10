"""«Тюнинг часов»: дифф возможностей часов и реально приходящих данных."""
from __future__ import annotations

from tj.analysis import watch_advice as wa
from tjbot import db as botdb


def _watch(**over):
    d = {"deviceId": 1, "productDisplayName": "Instinct 2 Solar Tactical",
         "activeInd": 1, "pulseOxSleepCapable": True, "pulseOxAllDayCapable": True,
         "bodyBatteryCapable": True, "allDayStressCapable": True,
         "gpsRouteCapable": True, "ftpCapable": True}
    d.update(over)
    return d


def _strap():
    return {"deviceId": 2, "productDisplayName": "HRM 200", "activeInd": 1,
            "bodyBatteryCapable": False, "allDayStressCapable": False}


def _day(**over):
    d = {"readiness": 70, "hrv": 55, "stress_avg": 30, "sleep_h": 7.5,
         "extra": {"bb_charge": 80, "sleep_score": 80, "respiration_rest": 14,
                   "vo2max": 53.3, "training_status": "MAINTAINING_1"}}
    d.update(over)
    return d


def test_pick_watch_prefers_richer_device():
    assert wa.pick_watch([_strap(), _watch()])["productDisplayName"].startswith("Instinct")
    assert wa.pick_watch([]) is None


def test_pulse_ox_off_when_capable_but_silent():
    out = wa.evaluate([_watch(), _strap()], [_day()])
    st = {i["id"]: i["state"] for i in out["items"]}
    assert st["pulse_ox"] == "off"          # умеет, но данных нет — совет
    assert st["hrv"] == "ok" and st["body_battery"] == "ok"
    assert out["watch"].startswith("Instinct")
    assert out["others"] == ["HRM 200"]
    assert out["n_off"] == 1


def test_pulse_ox_ok_when_data_flows():
    day = _day()
    day["extra"]["spo2_avg"] = 95
    out = wa.evaluate([_watch()], [day])
    st = {i["id"]: i["state"] for i in out["items"]}
    assert st["pulse_ox"] == "ok"


def test_unsupported_when_caps_false():
    w = _watch(pulseOxSleepCapable=False, pulseOxAllDayCapable=False)
    out = wa.evaluate([w], [_day()])
    st = {i["id"]: i["state"] for i in out["items"]}
    assert st["pulse_ox"] == "unsupported"  # часы не умеют — совета нет


def test_devices_roundtrip(tmp_path):
    con = botdb.connect(tmp_path / "t.db")
    botdb.init_schema(con)
    botdb.save_devices(con, 111, [_watch(), _strap()])
    devs = botdb.load_devices(con, 111)
    assert len(devs) == 2
    botdb.save_devices(con, 111, [_watch(productDisplayName="Instinct 3")])
    names = {d["productDisplayName"] for d in botdb.load_devices(con, 111)}
    assert "Instinct 3" in names            # апсерт по device_id
    assert botdb.load_devices(con, 222) == []
    con.close()
