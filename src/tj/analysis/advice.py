"""Детерминированный совет на следующую тренировку по состоянию (ACWR, готовность,
риск, серия тяжёлых, монотонность). База под блок "Совет на следующую тренировку";
ИИ (Клод/Gemini) может перекрыть его сверху."""
from __future__ import annotations

from tj import i18n


def next_session_advice(acwr=None, readiness=None, risk_level=None,
                        hard_streak=None, monotony=None, lang="ru") -> dict:
    def out(level, title_key, text_key, **kwargs):
        return {"level": level, "title": i18n.t(title_key, lang),
                "text": i18n.t(text_key, lang, **kwargs), "source": "rules"}

    if readiness is not None and readiness < 40:
        return out("red", "advice.low_readiness.title", "advice.low_readiness.text")
    if acwr is not None and acwr > 1.5:
        return out("red", "advice.acwr_high.title", "advice.acwr_high.text")
    if acwr is not None and acwr > 1.3:
        return out("amber", "advice.acwr_mid.title", "advice.acwr_mid.text")
    if hard_streak is not None and hard_streak >= 3:
        return out("amber", "advice.hard_streak.title", "advice.hard_streak.text")
    if monotony is not None and monotony >= 2:
        return out("amber", "advice.monotony.title", "advice.monotony.text")
    if risk_level in ("amber", "red"):
        return out("amber" if risk_level == "amber" else "red",
                   "advice.risk.title", "advice.risk.text")
    if acwr is not None and acwr < 0.8:
        return out("green", "advice.low_acwr.title", "advice.low_acwr.text")
    return out("green", "advice.normal.title", "advice.normal.text")
