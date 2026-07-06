from __future__ import annotations

from dataclasses import dataclass

from tj import i18n


@dataclass
class Block:
    kind: str
    title: str
    body: str


class Narrative:
    def render(self, blocks: list[Block]) -> list[Block]:
        raise NotImplementedError


class TemplatedNarrative(Narrative):
    def render(self, blocks: list[Block]) -> list[Block]:
        return [b for b in blocks if b.body]


def to_json(blocks: list[Block]) -> list[dict]:
    return [{"kind": b.kind, "title": b.title, "body": b.body} for b in blocks]


_AXIS_KEY = {
    "Движок": "axis.engine", "Сила": "axis.strength", "Гимнастика": "axis.gymnastics",
    "Над головой": "axis.overhead", "Спринт": "axis.sprint", "Хват/тяга": "axis.grip_pull",
}


def _axis(name, lang):
    key = _AXIS_KEY.get(name)
    return i18n.t(key, lang) if key else name


def comp_blocks(analysis: dict, lang="ru") -> list[Block]:
    caps = analysis.get("caps") or {}
    strong = [_axis(k, lang) for k, v in caps.items() if v >= 7]
    weak = [_axis(k, lang) for k, v in caps.items() if v <= 3]
    dash = i18n.t("narrative.comp.dash", lang)
    blocks = [Block("verdict", i18n.t("narrative.comp.verdict.title", lang),
        i18n.t("narrative.comp.verdict.text", lang,
               strong=", ".join(strong) or dash, weak=", ".join(weak) or dash))]
    sc = analysis.get("scenario") or {}
    if sc.get("gain"):
        blocks.append(Block("section", i18n.t("narrative.comp.scenario.title", lang),
            i18n.t("narrative.comp.scenario.text", lang,
                   target_place=sc["target_place"], gain=sc["gain"])))
    bw = analysis.get("best_worst") or {}
    if bw.get("worst"):
        blocks.append(Block("advice", i18n.t("narrative.comp.advice.title", lang),
            i18n.t("narrative.comp.advice.text", lang,
                   worst=", ".join(w["name"] for w in bw["worst"]))))
    return blocks


_BENEFIT_KEYS = {
    "ANAEROBIC_CAPACITY": "narrative.benefit.anaerobic_capacity",
    "AEROBIC_BASE": "narrative.benefit.aerobic_base",
    "VO2MAX": "narrative.benefit.vo2max",
    "LACTATE_THRESHOLD": "narrative.benefit.lactate_threshold",
    "TEMPO": "narrative.benefit.tempo",
    "RECOVERY": "narrative.benefit.recovery",
}


def _fmt_min(secs, lang):
    return i18n.t("narrative.min_suffix", lang, n=round((secs or 0) / 60))


def workout_blocks(extra: dict, max_hr=None, lang="ru") -> list:
    blocks = []
    benefit_key = _BENEFIT_KEYS.get(extra.get("primary_benefit"), "narrative.benefit.default")
    benefit = i18n.t(benefit_key, lang)
    tea, tan = extra.get("te_aerobic"), extra.get("te_anaerobic")
    tea_txt = round(tea, 1) if isinstance(tea, (int, float)) else "—"
    tan_txt = round(tan, 1) if isinstance(tan, (int, float)) else "—"
    blocks.append(Block(
        "verdict", i18n.t("narrative.workout.what_develops.title", lang),
        i18n.t("narrative.workout.what_develops.text", lang, benefit=benefit, tea=tea_txt, tan=tan_txt)))

    z = extra.get("time_in_zones") or []
    if len(z) == 5 and sum(z):
        hard = z[3] + z[4]
        easy = z[0] + z[1]
        tail_key = "narrative.workout.zones.tail_intense" if hard > easy else "narrative.workout.zones.tail_easy"
        blocks.append(Block(
            "section", i18n.t("narrative.workout.zones.title", lang),
            i18n.t("narrative.workout.zones.text", lang,
                   hard=_fmt_min(hard, lang), easy=_fmt_min(easy, lang),
                   tail=i18n.t(tail_key, lang))))

    im = extra.get("intensity_min") or []
    if len(im) == 2 and (im[0] or im[1]):
        total = (im[0] or 0) + (im[1] or 0) * 2
        blocks.append(Block(
            "section", i18n.t("narrative.workout.intensity_min.title", lang),
            i18n.t("narrative.workout.intensity_min.text", lang, total=total)))

    if max_hr and max_hr >= 170:
        blocks.append(Block(
            "risk", i18n.t("narrative.workout.risk.title", lang),
            i18n.t("narrative.workout.risk.text", lang, max_hr=max_hr)))

    rec = extra.get("recovery_h")
    advice = i18n.t("narrative.workout.advice.default", lang)
    if rec is not None:
        advice = i18n.t("narrative.workout.advice.recovery_prefix", lang, rec=rec) + advice
    blocks.append(Block("advice", i18n.t("narrative.workout.advice.title", lang), advice))
    return blocks


def _pl_train(n: int, lang: str) -> str:
    m = abs(n) % 100
    if 11 <= m <= 14:
        return i18n.t("narrative.period.train_word.many", lang)
    d = m % 10
    if d == 1:
        return i18n.t("narrative.period.train_word.one", lang)
    if 2 <= d <= 4:
        return i18n.t("narrative.period.train_word.few", lang)
    return i18n.t("narrative.period.train_word.many", lang)


def period_blocks(agg: dict, lang="ru") -> list:
    blocks = []
    vd = agg.get("vo2max_delta")
    wd = agg.get("weight_delta")
    vo2_txt = f"{'+' if (vd or 0) >= 0 else ''}{vd}" if vd is not None else "—"
    n = agg.get("workouts", 0)
    trend_key = "narrative.period.headline.trend_up" if (vd or 0) > 0 else "narrative.period.headline.trend_flat"
    body = i18n.t("narrative.period.headline.text", lang,
                  n=n, train_word=_pl_train(n, lang), trend=i18n.t(trend_key, lang), vo2=vo2_txt)
    if wd is not None:
        body += i18n.t("narrative.period.headline.weight_suffix", lang,
                       sign="+" if wd >= 0 else "", wd=wd)
    blocks.append(Block("verdict", i18n.t("narrative.period.headline.title", lang), body))

    if agg.get("low_aerobic_share", 1) < 0.3:
        blocks.append(Block(
            "section", i18n.t("narrative.period.skew.title", lang),
            i18n.t("narrative.period.skew.text", lang)))

    risks = []
    if agg.get("rhr_trend") == "above":
        risks.append(i18n.t("narrative.period.risk.rhr_above", lang))
    if (agg.get("hard_streak") or 0) >= 3:
        risks.append(i18n.t("narrative.period.risk.hard_streak", lang, n=agg["hard_streak"]))
    if risks:
        tail = ""
        if agg.get("next_start_days") is not None:
            tail = i18n.t("narrative.period.risk.tail", lang, days=agg["next_start_days"])
        blocks.append(Block(
            "risk", i18n.t("narrative.period.risk.title", lang),
            i18n.t("narrative.period.risk.text", lang, risks=", ".join(risks), tail=tail)))

    blocks.append(Block(
        "advice", i18n.t("narrative.period.advice.title", lang),
        i18n.t("narrative.period.advice.text", lang)))
    return blocks
