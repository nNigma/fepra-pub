"""Сборка компактного payload и тренерский LLM-разбор (Gemini). Сырьё не уходит."""
from __future__ import annotations

import hashlib
import json

from tj import llm
from tj.analysis import wod_results

_SYS_WORKOUT_RU = (
    "Ты опытный тренер по кроссфиту и физиологии. Разбери ОДНУ тренировку по-русски, "
    "живым человеческим языком, опираясь на цифры. Ответ строго тремя разделами, "
    "каждый со своим заголовком:\n"
    "1) «Как ты подошёл» — был ли восстановлен перед тренировкой: сон, пульс покоя, "
    "готовность, HRV, ACWR. Зашёл свежим или с долгом восстановления и как это влияет "
    "на оценку.\n"
    "2) «Как прошла» — внутренняя нагрузка: пульс, распределение по зонам, Training "
    "Effect, что развивала (энергосистемы, сердце), цена и восстановление; почему так "
    "с точки зрения физиологии.\n"
    "3) «Разбор работы» — сама тренировка по факту из поля work и board: силовые "
    "(движения, рабочие веса, повторы, тоннаж, прогресс от подхода к подходу), метконы "
    "(время, круги, счёт). Насколько веса серьёзные, где прибавка или просадка, попал "
    "ли в замысел доски (board). Заверши коротким практичным советом на следующий раз.\n"
    "Без воды и общих фраз. Чего нет в данных — не выдумывай. 6-9 абзацев.\n"
    "Технические аббревиатуры расшифровывай при первом упоминании: RHR — пульс "
    "покоя, HRV — вариабельность пульса, ACWR — отношение свежей нагрузки к "
    "хронической; дальше можно короткой формой.\n"
    "Если has_biometrics=false — не выдумывай HRV/сон/Body Battery; опирайся на "
    "самооценку (self_feel/10) и внешнюю работу/RPE.\n"
    "В САМОМ КОНЦЕ отдельной строкой напиши 'РАЗБОР:' и под ней ровно пять строк "
    "формата 'Метка: одна-две фразы' с метками именно такими: Что развивает, Зоны, "
    "Интенсивные минуты, Риск, Совет. Каждая опирается на цифры этой тренировки."
)

_SYS_WORKOUT_EN = (
    "You are an experienced CrossFit coach and physiologist. Break down ONE workout "
    "in English, in a natural human voice, grounded in the numbers. Respond in "
    "English. Reply in exactly three sections, each with its own heading:\n"
    "1) \"How you showed up\" — were you recovered before the session: sleep, resting "
    "heart rate, readiness, HRV, ACWR. Did you arrive fresh or with a recovery debt, "
    "and how that shapes the assessment.\n"
    "2) \"How it went\" — internal load: heart rate, zone distribution, Training "
    "Effect, what it built (energy systems, heart), cost and recovery; why, "
    "physiologically.\n"
    "3) \"Work breakdown\" — the session itself from the work and board fields: "
    "strength work (movements, working weights, reps, tonnage, set-to-set progress), "
    "metcons (time, rounds, score). How serious the weights were, where there was a "
    "gain or a dip, whether it matched the board's intent. Close with one short, "
    "practical tip for next time.\n"
    "No filler, no generic phrases. Never invent what isn't in the data. 6-9 "
    "paragraphs.\n"
    "If has_biometrics=false — do not invent HRV/sleep/Body Battery; rely on the "
    "self-rating (self_feel/10) and external work/RPE.\n"
    "AT THE VERY END, on its own line, write 'BREAKDOWN:' and under it exactly five "
    "lines in the format 'Label: one or two sentences' with labels exactly as follows: "
    "What it builds, Zones, Intense minutes, Risk, Advice. Each grounded in this "
    "workout's numbers."
)


def _astro_addendum(lang: str) -> str:
    if lang == "en":
        return ("Fortune is ON: as the VERY LAST paragraph of the prose (before the "
                "'BREAKDOWN:' line for a workout / 'ADVICE:' line for a summary / "
                "'TAKEAWAY:' line for nutrition) add a "
                "playful block starting with '🔮 Astro reading by Monsieur Claude:' — 1-2 "
                "sentences of a lordly horoscope, riffing on THIS session's/period's numbers "
                "in astrological language (planets, signs, retrogrades). Humor, not advice; "
                "do not touch the physiology.")
    return ("Гадание включено: САМЫМ ПОСЛЕДНИМ абзацем основного текста (перед строкой "
            "'РАЗБОР:' для тренировки / 'СОВЕТ:' для сводки / 'ИТОГ:' для питания) "
            "добавь шуточный блок, начав его "
            "с '🔮 Астро-разбор от Месье Клода:' — 1-2 фразы барского гороскопа, обыгрывая "
            "ЦИФРЫ этой тренировки/периода астро-языком (планеты, знаки, ретрограды). Это "
            "юмор, не советы, физиологию не трогай.")


def _sys_workout(lang: str, astro: bool = False) -> str:
    base = _SYS_WORKOUT_EN if lang == "en" else _SYS_WORKOUT_RU
    return base + "\n" + _astro_addendum(lang) if astro else base


_WK_LABELS_RU = [("Что развивает", "verdict"), ("Зоны", "section"),
                 ("Интенсивные минуты", "section"), ("Риск", "risk"), ("Совет", "advice")]

_WK_LABELS_EN = [("What it builds", "verdict"), ("Zones", "section"),
                 ("Intense minutes", "section"), ("Risk", "risk"), ("Advice", "advice")]


def _wk_labels(lang: str) -> list[tuple[str, str]]:
    return _WK_LABELS_EN if lang == "en" else _WK_LABELS_RU


def parse_workout_blocks(text: str, lang: str = "ru") -> list[dict]:
    blocks = []
    labels = _wk_labels(lang)
    for line in (text or "").splitlines():
        s = line.strip().lstrip("-*•").strip().lstrip("*").strip()
        for label, kind in labels:
            if s.lower().startswith(label.lower() + ":"):
                body = s.split(":", 1)[1].strip().strip("*").strip()
                if body:
                    blocks.append({"kind": kind, "title": label, "body": body})
                break
    return blocks


def strip_workout_blocks(text: str, lang: str = "ru") -> str:
    lines = (text or "").splitlines()
    labels = [lb.lower() for lb, _ in _wk_labels(lang)]
    recap = "разбор:" if lang != "en" else "breakdown:"
    cut = None
    for i, line in enumerate(lines):
        s = line.strip().lstrip("-*•").strip().lstrip("*").strip().lower()
        if s.startswith(recap) or any(s.startswith(lb + ":") for lb in labels):
            cut = i
            break
    return "\n".join(lines[:cut]).rstrip() if cut is not None else text


_SYS_SUMMARY_RU = (
    "Ты опытный тренер. По агрегату за период (15-30 дней) дай разбор по-русски в "
    "markdown, РОВНО такими разделами (заголовок каждого — отдельной строкой через '## '):\n"
    "## Куда идёт форма — динамика (ACWR, тренды, VO2max, вес), куда движется.\n"
    "## Оценка месяца — характер блока: баланс модальностей, перекосы, тяжёлые серии, "
    "нагрузка против восстановления.\n"
    "## Риски и куда дальше — риск перетрена и что делать в ближайшие недели.\n"
    "Если в данных есть nutrition7 (не null) — добавь ещё раздел:\n"
    "## Питание — разбери период по nutrition7: средние КБЖУ против норм, вода, качество "
    "дней; назови 1-2 перекоса С РАСЧЁТОМ (например «недостача 40 г белка в день»), "
    "не общими словами. Если nutrition7 = null — раздел Питание не пиши.\n"
    "Опирайся на цифры, 1-2 абзаца на раздел. Аббревиатуры расшифровывай при первом "
    "упоминании (RHR — пульс покоя, HRV — вариабельность пульса, ACWR — отношение свежей "
    "нагрузки к хронической, КБЖУ — калории/белки/жиры/углеводы). Если has_biometrics=false "
    "— не выдумывай HRV/сон/Body Battery, опирайся на самооценку (self_feel/10) и внешнюю "
    "работу/RPE. Если есть spo2 (ночная сатурация) и она устойчиво низкая (средняя ниже 93 "
    "или минимум ниже 85) — упомяни в разделе про восстановление как возможную причину "
    "слабого сна; норму (средняя 95+) не комментируй. Если есть hrv_status (BALANCED/"
    "UNBALANCED/LOW) или структура сна (sleep_deep_h — глубокий, sleep_rem_h — REM) — учти "
    "их в оценке восстановления (мало глубокого/REM или UNBALANCED = хуже восстановился). "
    "В САМОМ КОНЦЕ отдельной строкой: СОВЕТ: <одна фраза на ближайшую сессию>."
)

_SYS_SUMMARY_EN = (
    "You are an experienced coach. From the aggregate over the period (15-30 days), "
    "give a breakdown in English in markdown, with EXACTLY these sections (each header "
    "on its own line via '## '):\n"
    "## Where fitness is heading — trajectory (ACWR, trends, VO2max, weight).\n"
    "## Month assessment — character of the block: modality balance, imbalances, hard "
    "series, load vs recovery.\n"
    "## Risks and next — overtraining risk and what to do in the coming weeks.\n"
    "If the data has nutrition7 (not null) — add one more section:\n"
    "## Nutrition — break down the period from nutrition7: average macros vs targets, "
    "water, day quality; name 1-2 imbalances WITH numbers (e.g. \"40 g protein short "
    "per day\"), not platitudes. If nutrition7 = null — skip the Nutrition section.\n"
    "Ground it in the numbers, 1-2 paragraphs per section. If has_biometrics=false — do "
    "not invent HRV/sleep/Body Battery; rely on the self-rating (self_feel/10) and "
    "external work/RPE. AT THE VERY END, on its own line, in the format: "
    "ADVICE: <one sentence on what to do in the next session>."
)


def _sys_summary(lang: str, astro: bool = False) -> str:
    base = _SYS_SUMMARY_EN if lang == "en" else _SYS_SUMMARY_RU
    return base + "\n" + _astro_addendum(lang) if astro else base


def parse_advice_line(text: str, lang: str = "ru") -> str | None:
    marker = "advice:" if lang == "en" else "совет:"
    for line in reversed((text or "").splitlines()):
        s = line.strip().lstrip("*").strip()
        if s.lower().startswith(marker):
            return s.split(":", 1)[1].strip().strip("*").strip() or None
    return None


def _zones_min(zones):
    if not zones:
        return None
    mins = [round((z or 0) / 60, 1) for z in zones]
    return {f"z{i + 1}": m for i, m in enumerate(mins)}


def _work(extra: dict, score) -> dict | None:
    blocks = extra.get("result_blocks")
    strength = wod_results.strength_work(blocks, score) if (blocks and score) else []
    metcon = extra.get("metcon")
    if strength or metcon:
        return {"strength": strength, "metcon": metcon}
    return {"raw_score": score} if score else None


def workout_payload(report: dict) -> dict:
    s = (report.get("sessions") or [{}])[0]
    extra = s.get("extra") or {}
    cond = report.get("condition") or {}
    board = extra.get("board_text")
    has_biometrics = any(cond.get(k) is not None for k in ("readiness", "hrv", "resting_hr", "sleep_h"))
    return {
        "sport": s.get("sport"),
        "duration_min": s.get("duration_min"),
        "avg_hr": s.get("avg_hr"),
        "max_hr": s.get("max_hr"),
        "hr_max_user": report.get("hr_max"),
        "calories": s.get("calories"),
        "zones_min": _zones_min(s.get("zones") or extra.get("time_in_zones")),
        "te_aerobic": extra.get("te_aerobic"),
        "te_anaerobic": extra.get("te_anaerobic"),
        "primary_benefit": extra.get("primary_benefit"),
        "intensity_min": extra.get("intensity_min"),
        "wod_name": s.get("wod_name"),
        "distance_km": s.get("distance_km"),
        "avg_pace_s_per_km": s.get("avg_pace_s_per_km"),
        "avg_power_w": s.get("avg_power_w"),
        "elevation_gain_m": s.get("elevation_gain_m"),
        "board": board[:1000] if board else None,
        "performed": {"scaling": s.get("scaling"), "load_kg": s.get("load_kg"),
                      "rpe": s.get("rpe")},
        "work": _work(extra, s.get("score")),
        "readiness": cond.get("readiness"),
        "sleep_h": cond.get("sleep_h"),
        "resting_hr": cond.get("resting_hr"),
        "hrv": cond.get("hrv"),
        "acwr": cond.get("acwr"),
        "has_biometrics": has_biometrics,
    }


def summary_payload(summary: dict) -> dict:
    agg = summary.get("agg") or {}
    state = summary.get("state") or {}
    m = summary.get("m") or {}
    verdict_source = (summary.get("verdict") or {}).get("source")
    has_biometrics = verdict_source == "watch" or any(
        m.get(k) is not None for k in ("readiness", "hrv", "rhr", "sleep"))
    return {
        "range": summary.get("range"),
        "workouts": agg.get("workouts"),
        "acwr": m.get("acwr"),
        "vo2max_delta": agg.get("vo2max_delta"),
        "weight_delta": agg.get("weight_delta"),
        "rhr_trend": agg.get("rhr_trend"),
        "hard_streak": agg.get("hard_streak"),
        "readiness_now": (state.get("readiness") or {}).get("value"),
        "form": state.get("form"),
        "risk": state.get("risk"),
        "spo2": summary.get("spo2"),
        "hrv_status": summary.get("hrv_status"),
        "sleep_deep_h": summary.get("sleep_deep_h"),
        "sleep_rem_h": summary.get("sleep_rem_h"),
        "has_biometrics": has_biometrics,
        "self_feel": summary.get("self_feel"),
    }


def payload_hash(payload: dict, lang: str = "ru", astro: bool = False) -> str:
    raw = json.dumps({"lang": lang, "astro": astro, **payload}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def coach_workout(payload: dict, lang: str = "ru", astro: bool = False) -> str | None:
    return llm.complete(_sys_workout(lang, astro), json.dumps(payload, ensure_ascii=False),
                        max_output_tokens=2200)


def coach_summary(payload: dict, lang: str = "ru", astro: bool = False) -> str | None:
    return llm.complete(_sys_summary(lang, astro), json.dumps(payload, ensure_ascii=False),
                        max_output_tokens=1600)


_SYS_COMP_RU = (
    "Ты опытный тренер по функциональному многоборью. По данным соревнований "
    "атлета (старты, места, перцентили по этапам, лучшие/худшие задания) дай "
    "разбор по-русски: где атлет силён и где проседает по способностям, как "
    "меняется уровень от старта к старту, что конкретно тренировать к следующему "
    "старту. Опирайся только на цифры из данных, не выдумывай. 3-5 абзацев."
)

_SYS_COMP_EN = (
    "You are an experienced functional fitness coach. From the athlete's "
    "competition data (starts, placements, per-stage percentiles, best/worst "
    "events) give a breakdown in English: strengths and weaknesses by ability, "
    "how the level changes start to start, and what exactly to train for the "
    "next competition. Ground it in the numbers only. 3-5 paragraphs."
)


def _sys_comp(lang: str, astro: bool = False) -> str:
    return _SYS_COMP_EN if lang == "en" else _SYS_COMP_RU


_SYS_NUTR_RU = (
    "Ты тренер по питанию атлета-кроссфитера. Тебе дан JSON: тоталы КБЖУ и микро "
    "по дням, нормы и процент попадания, вердикты качества дней (1 лучший — 4 "
    "худший), вода против цели, тренировки периода, цель (cut/maintain/bulk/"
    "recomp), тренд веса, город, число записанных дней. Разбери питание: назови "
    "2-3 главных перекоса С РАСЧЁТОМ (например «недостача 40 г белка в день»), "
    "а не общими словами; честно скажи, где данных мало; порекомендуй конкретные "
    "продукты и блюда, доступные в городе атлета, под его цель; плохие дни стебай "
    "по-доброму. Аббревиатуры расшифровывай (КБЖУ — калории/белки/жиры/углеводы). "
    "Для period=day — 2-3 абзаца с фокусом «чем закрыть сегодняшний день»; для "
    "period=week — 3-5 абзацев. В САМОМ КОНЦЕ отдельной строкой: «ИТОГ: …» — одна "
    "фраза с вердиктом."
)

_SYS_NUTR_EN = (
    "You are a nutrition coach for a CrossFit athlete. You get JSON: daily "
    "macro/micro totals, targets and hit rates, day quality verdicts (1 best - 4 "
    "worst), water vs target, workouts, goal (cut/maintain/bulk/recomp), weight "
    "trend, city, number of logged days. Break down the nutrition: name 2-3 main "
    "imbalances WITH numbers (e.g. \"40 g protein short per day\"), not "
    "platitudes; be honest where data is thin; recommend specific foods and "
    "dishes available in the athlete's city for their goal; roast bad days "
    "kindly. For period=day - 2-3 paragraphs focused on how to close out today; "
    "for period=week - 3-5 paragraphs. AT THE VERY END, on its own line: "
    "\"TAKEAWAY: ...\" - one sentence verdict."
)


def _sys_nutrition(lang: str, astro: bool = False) -> str:
    base = _SYS_NUTR_RU if lang == "ru" else _SYS_NUTR_EN
    return base + ("\n" + _astro_addendum(lang) if astro else "")


_SYS_BY_KIND = {"workout": _sys_workout, "summary": _sys_summary,
                "competitions": _sys_comp,
                "nutr_day": _sys_nutrition, "nutr_week": _sys_nutrition}


def coach(kind: str, payload: dict, lang: str = "ru",
          astro: bool = False) -> tuple[str | None, str]:
    """Единый текстовый разбор по кнопке: Claude первым (подписка, «Месье Клод»),
    Gemini flash — запасным («Женя»). -> (text | None, engine)."""
    system = _SYS_BY_KIND[kind](lang, astro)
    body = json.dumps(payload, ensure_ascii=False)
    limit = 3800 if kind == "summary" else 2500
    cap = (f"Write densely; keep the whole answer under ~{limit} characters."
           if lang == "en" else
           f"Пиши плотно; весь ответ — не длиннее ~{limit} знаков.")
    text = llm.claude_complete(f"{system}\n{cap}\n\nДАННЫЕ:\n{body}")
    if text:
        return text, "claude"
    max_tok = 2600 if kind == "summary" else (2200 if kind == "workout" else 1600)
    return llm.complete(system, body, max_output_tokens=max_tok), "gemini"
