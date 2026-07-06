from __future__ import annotations

from statistics import mean, pstdev

from tj import i18n


def baseline(values, window=30) -> dict | None:
    vals = [v for v in values[-window:] if v is not None]
    if len(vals) < 3:
        return None
    mu = mean(vals)
    sd = pstdev(vals) or (abs(mu) * 0.05 or 1.0)
    return {"mean": round(mu, 1), "lo": round(mu - sd, 1), "hi": round(mu + sd, 1), "n": len(vals)}


def classify(current, b, higher_better) -> str:
    if current is None or b is None:
        return "unknown"
    if current > b["hi"]:
        return "above"
    if current < b["lo"]:
        return "below"
    return "in"


def _bad(sig) -> bool:
    cls, higher_better = sig
    return (cls == "above" and not higher_better) or (cls == "below" and higher_better)


def risk_flag(signals: dict, lang: str = "ru") -> dict:
    bad = [name for name, sig in signals.items() if _bad(sig)]
    n = len(bad)
    if n == 0:
        return {"level": "green", "title": i18n.t("state.risk.green", lang), "drivers": []}
    if n == 1:
        return {"level": "amber", "title": i18n.t("state.risk.amber", lang), "drivers": bad}
    return {"level": "red", "title": i18n.t("state.risk.red", lang), "drivers": bad}


def decompose_readiness(readiness, base, contribs: dict) -> dict:
    items = sorted(contribs.items(), key=lambda kv: -abs(kv[1]))
    return {"value": readiness, "base": base,
            "delta": round(readiness - base, 1) if (readiness is not None and base is not None) else None,
            "items": items}


def microcycle(days, hard_threshold=70) -> dict:
    out = []
    hard_count = max_streak = cur = 0
    for d, load, rd in days:
        hard = (load or 0) >= hard_threshold
        if hard:
            hard_count += 1
            cur += 1
            max_streak = max(max_streak, cur)
        else:
            cur = 0
        out.append({"day": d, "load": round(load or 0), "readiness": rd, "hard": hard})
    return {"days": out, "hard_count": hard_count, "max_streak": max_streak}
