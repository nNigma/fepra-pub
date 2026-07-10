"""«Тюнинг часов»: дифф между возможностями часов (capable-флаги Garmin) и
реально приходящими данными -> советы включить датчики.

Движок чистый: на вход снапшот устройств (tjbot.db.load_devices) и последние
дни daily, на выход — состояние по курируемому списку метрик:
  ok          — часы умеют, данные идут;
  off         — часы умеют, данных нет (похоже, датчик выключен / не носится);
  unsupported — часы этого не умеют (честно, без ложных советов).
Тексты (имя/польза/как включить) живут на фронте (strings.js) по id метрики.

Список курируемый сознательно: 234 capable-флага Garmin не 1:1 с метриками
(например hrvStressCapable=false при исправно идущем ночном HRV) — слепой дифф
дал бы ложные советы. Советуем только ночные/дневные датчики: на тренировке
часов может не быть (пульс с нагрудника), это не повод для «совета».
"""
from __future__ import annotations

# caps: any-of *Capable-флаги (пусто = считаем, что умеют);
# cols: колонки daily; extras: ключи daily.extra. Данные есть хотя бы в одном
# дне окна -> ok.
METRICS = [
    {"id": "pulse_ox", "caps": ("pulseOxSleepCapable", "pulseOxAllDayCapable"),
     "cols": (), "extras": ("spo2_avg", "spo2_lowest")},
    {"id": "hrv", "caps": (), "cols": ("hrv",), "extras": ()},
    {"id": "sleep", "caps": (), "cols": ("sleep_h",), "extras": ("sleep_score",)},
    {"id": "body_battery", "caps": ("bodyBatteryCapable",),
     "cols": (), "extras": ("bb_charge",)},
    {"id": "stress", "caps": ("allDayStressCapable",),
     "cols": ("stress_avg",), "extras": ()},
    {"id": "respiration", "caps": (), "cols": (), "extras": ("respiration_rest",)},
    {"id": "readiness", "caps": (), "cols": ("readiness",), "extras": ()},
    {"id": "vo2max", "caps": (), "cols": (), "extras": ("vo2max",)},
    {"id": "training_status", "caps": (), "cols": (), "extras": ("training_status",)},
]


def _true_caps(device: dict) -> int:
    return sum(1 for k, v in device.items() if k.endswith("Capable") and v)


def pick_watch(devices: list[dict]) -> dict | None:
    """Часы = активное устройство с максимумом умений (нагрудник/датчики
    отсеиваются сами — у них capable-флагов на порядок меньше)."""
    cand = [d for d in devices or [] if isinstance(d, dict) and d.get("activeInd") != 0]
    if not cand:
        return None
    return max(cand, key=_true_caps)


def _supported(watch: dict, caps: tuple) -> bool:
    present = [c for c in caps if c in watch]
    if not present:
        return True                      # флагов нет в записи — не судим
    return any(watch.get(c) for c in present)


def _has_data(days: list[dict], cols: tuple, extras: tuple) -> bool:
    for day in days or []:
        if any(day.get(c) is not None for c in cols):
            return True
        ex = day.get("extra") or {}
        if any(ex.get(e) is not None for e in extras):
            return True
    return False


def evaluate(devices: list[dict], days: list[dict]) -> dict | None:
    """-> {"watch", "others", "items": [{id, state}], "n_off"} | None (нет снапшота)."""
    watch = pick_watch(devices)
    if not watch:
        return None
    items = []
    for m in METRICS:
        if not _supported(watch, m["caps"]):
            state = "unsupported"
        else:
            state = "ok" if _has_data(days, m["cols"], m["extras"]) else "off"
        items.append({"id": m["id"], "state": state})
    return {
        "watch": watch.get("productDisplayName"),
        "others": [d.get("productDisplayName") for d in devices
                   if d is not watch and isinstance(d, dict)
                   and d.get("productDisplayName")],
        "items": items,
        "n_off": sum(1 for i in items if i["state"] == "off"),
    }
