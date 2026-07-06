"""Каталог дисциплин и нормативы по уровням (источник — data/standards.json)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "data" / "standards.json"


@lru_cache(maxsize=1)
def load() -> dict:
    return json.loads(_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def disciplines() -> dict:
    data = load()
    out: dict[str, dict] = {}
    order = 0
    for did, m in data["lifts"].items():
        out[did] = {
            "id": did, "name_ru": m["name_ru"], "name_en": m.get("name_en", m["name_ru"]),
            "kind": "lift", "unit": "kg",
            "better": "higher", "basis": "bw_ratio", "ontology": m.get("ontology"),
            "thresholds": {"m": m["m"], "f": m["f"]}, "order": order,
        }
        order += 1
    for did, m in data["benchmarks"].items():
        unit = "rounds" if m["basis"] == "abs_rounds" else "time"
        out[did] = {
            "id": did, "name_ru": m["name_ru"], "name_en": m.get("name_en", m["name_ru"]),
            "kind": "benchmark", "unit": unit,
            "better": m["better"], "basis": m["basis"], "ontology": None,
            "spec": m.get("spec"), "rx_m": m.get("rx_m"), "rx_f": m.get("rx_f"),
            "cap_min": m.get("cap_min"),
            "thresholds": {"m": m["m"], "f": m["f"]}, "order": order,
        }
        order += 1
    return out


def tiers(lang: str = "ru") -> list[str]:
    data = load()
    return data["tiers_en"] if lang == "en" else data["tiers"]


def tier_name(index_or_ru, lang: str = "ru") -> str:
    ru = tiers("ru")
    en = tiers("en")
    if isinstance(index_or_ru, int):
        idx = index_or_ru
    else:
        idx = ru.index(index_or_ru) if index_or_ru in ru else None
    if idx is None or not (0 <= idx < len(ru)):
        return index_or_ru if isinstance(index_or_ru, str) else ""
    return en[idx] if lang == "en" else ru[idx]


def discipline_name(meta: dict, lang: str = "ru") -> str:
    return meta.get("name_en", meta["name_ru"]) if lang == "en" else meta["name_ru"]
