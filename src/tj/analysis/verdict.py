"""
Вердикт готовности (SPEC §7): свести readiness + сон + ACWR + HRV/RHR в одну
рекомендацию человеческим языком. Чистая функция, тестируемая.
"""
from __future__ import annotations

from tj import i18n

_LEVELS = {
    "green": ("success", "verdict.title.green"),
    "amber": ("warning", "verdict.title.amber"),
    "red":   ("danger",  "verdict.title.red"),
}


def verdict(readiness, sleep_delta=None, acwr=None, hrv_delta=None, rhr_delta=None, lang="ru") -> dict:
    """
    -> {level, callout, title, reason, flags}.
    level: green | amber | red. callout: тип Obsidian-callout (success/warning/danger).
    """
    flags = []
    if sleep_delta is not None and sleep_delta <= -2:
        flags.append(i18n.t("verdict.flag.sleep_debt", lang, sleep_delta=sleep_delta))
    if acwr is not None and acwr >= 1.5:
        flags.append(i18n.t("verdict.flag.acwr_spike", lang, acwr=acwr))
    if hrv_delta is not None and hrv_delta <= -6:
        flags.append(i18n.t("verdict.flag.hrv_low", lang))
    if rhr_delta is not None and rhr_delta >= 4:
        flags.append(i18n.t("verdict.flag.rhr_high", lang))

    r = readiness if readiness is not None else 60
    if r < 45 or (sleep_delta is not None and sleep_delta <= -2.5):
        level = "red"
    elif r < 65 or flags:
        level = "amber"
    else:
        level = "green"

    callout, title_key = _LEVELS[level]
    title = i18n.t(title_key, lang)
    head = i18n.t("verdict.head.value", lang, r=int(r)) if readiness is not None else i18n.t("verdict.head.unknown", lang)
    if level == "green":
        reason = i18n.t("verdict.reason.green", lang, head=head)
    elif level == "red":
        tail = "; ".join(flags) if flags else i18n.t("verdict.tail.deep_fatigue", lang)
        reason = i18n.t("verdict.reason.red", lang, head=head, tail=tail)
    else:
        tail = "; ".join(flags) if flags else i18n.t("verdict.tail.incomplete_recovery", lang)
        reason = i18n.t("verdict.reason.amber", lang, head=head, tail=tail)
    return {"level": level, "callout": callout, "title": title, "reason": reason, "flags": flags}
