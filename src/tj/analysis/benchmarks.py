"""Каталог эталонных (benchmark) WOD: имя/алиас -> формат + вес + правило скора."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "data" / "benchmarks.json"


@lru_cache(maxsize=1)
def catalog() -> dict:
    return json.loads(_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _alias_index() -> dict:
    idx = {}
    for key, rec in catalog().items():
        idx[key] = key
        for a in rec.get("aliases", []):
            idx[a.strip().lower()] = key
    return idx


def lookup(name: str) -> dict | None:
    key = _alias_index().get((name or "").strip().lower())
    return catalog()[key] if key else None


def key_of(name: str) -> str | None:
    return _alias_index().get((name or "").strip().lower())


NAMES = {
    "thruster": "трастер", "pull_up": "подтягивание", "clean_and_jerk": "взятие и толчок",
    "snatch": "рывок", "deadlift": "становая тяга", "hspu": "отжимания в стойке",
    "clean": "взятие на грудь", "ring_dip": "отжимания на кольцах",
    "air_squat": "воздушные приседания", "push_up": "отжимания",
    "double_under": "двойные прыжки", "sit_up": "скручивания", "run": "бег",
    "kb_swing": "махи гирей", "overhead_squat": "присед над головой",
    "shoulder_press": "жим стоя", "toes_to_bar": "носки к перекладине",
    "burpee": "бёрпи", "box_step_up": "зашагивания на тумбу",
}


def expand(name: str, sex: str = "m") -> list[dict] | None:
    key = key_of(name)
    if not key:
        return None
    rec = catalog()[key]
    weights = rec.get("weighted") or {}
    scheme = None
    rs = rec.get("rep_scheme")
    if rs and "-" in rs:
        scheme = [int(x) for x in rs.split("-")]
    movements = []
    for canon in rec.get("movements", []):
        w = (weights.get(canon) or {}).get(sex)
        label = NAMES.get(canon, canon.replace("_", " "))
        if w:
            label = f"{label} {w:g} кг"
        movements.append({"name": label, "canon": canon, "weighted": bool(w)})
    rounds = rec.get("rounds") or (len(scheme) if scheme else None)
    header = key.replace("_", " ").title()
    if rounds and not scheme:
        header = f"{header} ({rounds}×)"
    return [{"header": header, "format": "ladder" if scheme else rec.get("format"),
             "rounds": rounds, "reps": None, "work_min": rec.get("work_min"),
             "rest_min": None, "has_cap": False, "movements": movements,
             "benchmark": key, "scheme": scheme}]
