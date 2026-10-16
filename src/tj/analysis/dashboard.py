"""
Интерактивный HTML-дашборд (подход A): standalone-страница в vault.
Открывается в браузере; Chart.js c CDN, данные вшиты. Регенерится `tj report`.
Вердикт + карточки метрик + цветной календарь готовности + график readiness/нагрузки.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

from tj import i18n

from ..store.build import _connect
from .advice import next_session_advice
from .engine import analyze, daily_loads
from .muscles import week_muscles
from . import nutrition
from .narrative import period_blocks, to_json
from .report import _read_full
from .state import baseline, classify, decompose_readiness, microcycle, risk_flag
from .verdict import verdict


_RISK_METRIC = {"rhr": "rhr", "hrv": "hrv", "bb_charge": "bb",
                "respiration_rest": "respiration", "spo2": "spo2"}


def _risk_driver_names(drivers, lang):
    """Сырые ключи сигналов риска -> человеческие названия метрик."""
    return [i18n.t(f"metric.{_RISK_METRIC.get(d, d)}.name", lang) for d in drivers]


def _first(seq, key, default=None):
    for x in seq:
        v = x.get(key) if isinstance(x, dict) else None
        if v is not None:
            return v
    return default


def readiness_source(bio_readiness, self_feel):
    if bio_readiness is not None:
        return bio_readiness, "watch"
    if self_feel is not None:
        return int(self_feel) * 10, "self"
    return None, None


def _metrics_payload(full_rows, extra_list, rdy_base, rhr_base, hrv_base, sleep_base,
                     days=30) -> dict:
    all_days = [r[0] for r in full_rows]
    col = {"readiness": 1, "rhr": 2, "hrv": 3, "sleep": 4}
    raw = {k: [r[i] for r in full_rows] for k, i in col.items()}
    raw["bb"] = [ex.get("bb_charge") for ex in extra_list]
    raw["sleep_score"] = [ex.get("sleep_score") for ex in extra_list]
    raw["vo2max"] = [ex.get("vo2max") for ex in extra_list]
    raw["spo2"] = [ex.get("spo2_avg") for ex in extra_list]
    raw["respiration"] = [ex.get("respiration_rest") for ex in extra_list]
    raw["sleep_deep"] = [ex.get("sleep_deep_h") for ex in extra_list]
    raw["sleep_rem"] = [ex.get("sleep_rem_h") for ex in extra_list]
    raw["weight"] = [r[6] for r in full_rows]

    def _ser(vals, keep=days):
        pts = [[d, v] for d, v in zip(all_days, vals) if v is not None]
        if keep:
            pts = pts[-keep:]
        if len(pts) > 60:                     # медленные метрики: вся история, даунсемпл
            step = (len(pts) - 1) / 59
            pts = [pts[round(i * step)] for i in range(60)]
        return pts

    def _base(vals, precomputed=None):
        if precomputed:
            return round(precomputed["mean"], 1)
        b = baseline(vals)
        return round(b["mean"], 1) if b else None

    # окно None = вся история (VO₂max и вес меняются месяцами, 30 точек — флэт)
    spec = {
        "readiness": ("Готовность", "low_bad", rdy_base, days),
        "rhr": ("Пульс покоя", "high_bad", rhr_base, days),
        "hrv": ("HRV", "low_bad", hrv_base, days),
        "sleep": ("Сон, ч", "low_bad", sleep_base, days),
        "bb": ("Ночной заряд", "low_bad", None, days),
        "sleep_score": ("Sleep score", "low_bad", None, days),
        "vo2max": ("VO₂max", "low_bad", None, None),
        "spo2": ("Сатурация (SpO₂)", "low_bad", None, days),
        "respiration": ("Дыхание", "high_bad", None, days),
        "sleep_deep": ("Глубокий сон", "low_bad", None, days),
        "sleep_rem": ("REM-сон", "low_bad", None, days),
        "weight": ("Вес, кг", "low_bad", None, None),
    }
    out = {}
    for k, (label, direction, pre, keep) in spec.items():
        out[k] = {"label": label, "dir": direction,
                  "series": _ser(raw[k], keep), "base": _base(raw[k], pre)}
    return out


_TS_LABEL = {
    "PEAKING": {"ru": "Пик формы", "en": "Peaking"},
    "PRODUCTIVE": {"ru": "Продуктивно", "en": "Productive"},
    "MAINTAINING": {"ru": "Поддержание", "en": "Maintaining"},
    "RECOVERY": {"ru": "Восстановление", "en": "Recovery"},
    "OVERREACHING": {"ru": "Перегрузка", "en": "Overreaching"},
    "STRAINED": {"ru": "Перенапряжение", "en": "Strained"},
    "UNPRODUCTIVE": {"ru": "Непродуктивно", "en": "Unproductive"},
    "DETRAINING": {"ru": "Растренированность", "en": "Detraining"},
}


def _ts_human(phrase, lang="ru"):
    """Garmin trainingStatusFeedbackPhrase (MAINTAINING_1) -> человеческий лейбл."""
    if not phrase:
        return None
    up = str(phrase).upper()
    for pref, names in _TS_LABEL.items():
        if up.startswith(pref):
            return names.get(lang) or names["ru"]
    return str(phrase).replace("_", " ").title()


def _nutrition_contrib(db_path, backend, tg_id, readiness_day):
    """Вклад питания в готовность за день до замера.

    Утренняя готовность отражает еду накануне, поэтому берём readiness_day - 1.
    Любой сбой (нет профиля, нет норм, чужой бэкенд) — None: строка просто не
    появится, как и у HRV со сном без данных.
    """
    if backend != "sqlite" or not readiness_day:
        return None
    try:
        from tjbot import db as botdb
        from tjbot import llm_gen

        day = (datetime.date.fromisoformat(readiness_day)
               - datetime.timedelta(days=1)).isoformat()
        con = botdb.connect(str(db_path))
        try:
            meals = botdb.meals_for_day(con, tg_id, day)
            _, _, targets = llm_gen.user_targets(con, tg_id, day)
        finally:
            con.close()
        return nutrition.readiness_contrib(meals, targets)
    except Exception:
        return None


def summary_data(db_path, backend, hr_max, sex, today, tg_id, lang="ru") -> dict:
    rep = analyze(db_path, backend, hr_max, sex, tg_id=tg_id)
    daily, acts = _read_full(db_path, backend, tg_id)
    days, loads = daily_loads(db_path, backend, hr_max, sex, tg_id=tg_id)
    li = {d: loads[i] for i, d in enumerate(days)}
    aset = {a[0] for a in acts}
    series = [[r[0], r[3], r[4], round(li.get(r[0], 0)), 1 if r[0] in aset else 0, r[2], r[1]]
              for r in daily[-56:]]

    con_s, _ = _connect(Path(db_path), backend)
    try:
        sports = con_s.execute('select sport, count(*) from activities where "tg_id"=? '
                               'group by sport order by 2 desc', (tg_id,)).fetchall()
    finally:
        con_s.close()

    con2, _ = _connect(Path(db_path), backend)
    try:
        full_rows = con2.execute(
            'select "day","readiness","resting_hr","hrv","sleep_h","stress_avg","weight_kg","extra" '
            'from daily where "tg_id"=? order by "day"', (tg_id,)).fetchall()
    finally:
        con2.close()

    readiness_s, rhr_s, hrv_s, sleep_s, weight_s = [], [], [], [], []
    extra_list = []
    for row in full_rows:
        readiness_s.append(row[1])
        rhr_s.append(row[2])
        hrv_s.append(row[3])
        sleep_s.append(row[4])
        weight_s.append(row[6])
        try:
            ex = json.loads(row[7]) if row[7] else {}
        except Exception:
            ex = {}
        extra_list.append(ex)

    cur = full_rows[-1] if full_rows else None
    rdy_cur = cur[1] if cur else None
    rhr_cur = cur[2] if cur else None
    hrv_cur = cur[3] if cur else None
    sleep_cur = cur[4] if cur else None
    weight_cur = cur[6] if cur else None
    cur_extra = extra_list[-1] if extra_list else {}
    eff_readiness, rdy_source = readiness_source(rdy_cur, cur_extra.get("self_feel"))

    rdy_base = baseline(readiness_s)
    rhr_base = baseline(rhr_s)
    hrv_base = baseline(hrv_s)
    sleep_base = baseline(sleep_s)

    acwr_val = rep.get("acwr") or 1.0
    load_debt = round(-(acwr_val - 1) * 20)
    load_debt = max(-30, min(30, load_debt))

    contribs = {}
    if sleep_cur is not None and sleep_base:
        contribs["Сон-качество"] = round(sleep_cur - sleep_base["mean"])
    if hrv_cur is not None and hrv_base:
        contribs["HRV vs база"] = round(hrv_cur - hrv_base["mean"])
    if rhr_cur is not None and rhr_base:
        contribs["Пульс покоя"] = round(rhr_base["mean"] - rhr_cur)
    contribs["Долг нагрузки"] = load_debt
    nutr = _nutrition_contrib(db_path, backend, tg_id, cur[0] if cur else None)
    if nutr is not None:
        contribs["Питание"] = nutr

    rdy_decomp = decompose_readiness(
        rdy_cur,
        rdy_base["mean"] if rdy_base else None,
        contribs,
    )
    rdy_items = [{"name": name, "weight": w} for name, w in rdy_decomp["items"]]

    def _sig(metric_id, value, base):
        return {"label": i18n.t(f"metric.{metric_id}.name", lang), "value": value,
                "base": i18n.t("metric.base_prefix", lang, v=base["mean"]),
                "cls": classify(value, base, metric_id in ("hrv", "sleep", "bb", "sleep_score", "spo2"))}

    signals = {}
    if hrv_cur is not None and hrv_base:
        signals["hrv"] = _sig("hrv", hrv_cur, hrv_base)
    if rhr_cur is not None and rhr_base:
        signals["rhr"] = _sig("rhr", rhr_cur, rhr_base)
    if sleep_cur is not None and sleep_base:
        signals["sleep"] = _sig("sleep", sleep_cur, sleep_base)

    bb_vals = [ex.get("bb_charge") for ex in extra_list if ex.get("bb_charge") is not None]
    resp_vals = [ex.get("respiration_rest") for ex in extra_list if ex.get("respiration_rest") is not None]
    ss_vals = [ex.get("sleep_score") for ex in extra_list if ex.get("sleep_score") is not None]
    spo2_vals = [ex.get("spo2_avg") for ex in extra_list if ex.get("spo2_avg") is not None]

    bb_base = baseline(bb_vals) if len(bb_vals) >= 3 else None
    resp_base = baseline(resp_vals) if len(resp_vals) >= 3 else None
    ss_base = baseline(ss_vals) if len(ss_vals) >= 3 else None
    spo2_base = baseline(spo2_vals) if len(spo2_vals) >= 3 else None

    bb_cur = cur_extra.get("bb_charge")
    resp_cur = cur_extra.get("respiration_rest")
    ss_cur = cur_extra.get("sleep_score")
    spo2_cur = cur_extra.get("spo2_avg")
    spo2_low_cur = cur_extra.get("spo2_lowest")

    if bb_cur is not None and bb_base:
        signals["bb"] = _sig("bb", bb_cur, bb_base)
    if ss_cur is not None and ss_base:
        signals["sleep_score"] = _sig("sleep_score", ss_cur, ss_base)
    if resp_cur is not None and resp_base:
        signals["respiration"] = {"label": i18n.t("metric.respiration.name", lang), "value": resp_cur,
                                   "base": i18n.t("metric.base_prefix", lang, v=resp_base["mean"]),
                                   "cls": classify(resp_cur, resp_base, False)}
    if spo2_cur is not None and spo2_base:
        signals["spo2"] = _sig("spo2", spo2_cur, spo2_base)

    risk_sigs = {}
    if rhr_cur is not None and rhr_base:
        risk_sigs["rhr"] = (classify(rhr_cur, rhr_base, False), False)
    if hrv_cur is not None and hrv_base:
        risk_sigs["hrv"] = (classify(hrv_cur, hrv_base, True), True)
    if bb_cur is not None and bb_base:
        risk_sigs["bb_charge"] = (classify(bb_cur, bb_base, True), True)
    if resp_cur is not None and resp_base:
        risk_sigs["respiration_rest"] = (classify(resp_cur, resp_base, False), False)
    # SpO₂ — устойчиво низкая сатурация = сигнал недовосстановления. Средняя ниже 93%
    # или ночной минимум ниже 85%; редкий провал минимума при норм. средней — не флаг.
    if spo2_cur is not None or spo2_low_cur is not None:
        spo2_bad = ((spo2_cur is not None and spo2_cur < 93)
                    or (spo2_low_cur is not None and spo2_low_cur < 85))
        risk_sigs["spo2"] = ("below" if spo2_bad else "in", True)
    risk = (risk_flag(risk_sigs, lang=lang) if risk_sigs
            else {"level": "green", "title": i18n.t("summary.data_collecting", lang), "drivers": []})
    risk["drivers"] = _risk_driver_names(risk.get("drivers", []), lang)

    def _last_nonnull(xs):
        for x in reversed(xs):
            if x is not None:
                return x
        return None
    vo2max_cur = _last_nonnull([e.get("vo2max") for e in extra_list])
    training_status = _last_nonnull([e.get("training_status") for e in extra_list])
    weight_last = _last_nonnull(weight_s)
    form = {}
    if vo2max_cur is not None:
        form["vo2max"] = round(vo2max_cur, 1)
    if weight_last is not None:
        form["weight"] = round(weight_last, 1)
    if training_status is not None:
        form["status"] = _ts_human(training_status, lang)

    week_cut = (today - datetime.timedelta(days=6)).isoformat()
    week_sessions = [{"sport": a[1], "score": a[10],
                      "extra": json.loads(a[12]) if a[12] else {}}
                     for a in acts if a[0] and week_cut <= a[0] <= today.isoformat()]

    today_str = rep["range"][1] or today.isoformat()
    mc_days_input = []
    for row in full_rows[-7:]:
        mc_days_input.append((row[0], round(li.get(row[0], 0)), row[1]))
    mc = microcycle(mc_days_input)

    vo2max_series = [ex.get("vo2max") for ex in extra_list if ex.get("vo2max") is not None]
    month_cut = (datetime.date.fromisoformat(today_str) - datetime.timedelta(days=30)).isoformat()
    agg = {"workouts": len({a[0] for a in acts if a[0] and a[0] >= month_cut})}
    wt_30ago = next((r[6] for r in reversed(full_rows[:-30]) if r[6] is not None), None) if len(full_rows) > 30 else None
    if weight_cur is not None and wt_30ago is not None:
        agg["weight_delta"] = round(weight_cur - wt_30ago, 1)
    if rhr_cur is not None and rhr_base:
        agg["rhr_trend"] = classify(rhr_cur, rhr_base, False)
    agg["hard_streak"] = mc["max_streak"]
    agg["next_start_days"] = None
    if len(vo2max_series) >= 2:
        agg["vo2max_delta"] = round(vo2max_series[-1] - vo2max_series[0], 1)

    # плитка VO₂max в сетке метрик (та же форма {latest, delta}, что sleep/hrv/rhr)
    rep["vo2max"] = ({"latest": round(vo2max_cur, 1),
                      "delta": agg.get("vo2max_delta")}
                     if vo2max_cur is not None else None)
    # последний день с данными часов (для шапки «на {день}»)
    last_data_day = next((r[0] for r in reversed(full_rows)
                          if any(r[i] is not None for i in (1, 2, 3, 4))), None)

    def _d(b):
        return b["delta"] if b else None

    if rdy_source == "self":
        v = verdict(eff_readiness, None, rep["acwr"], None, None, lang=lang)
    else:
        v = verdict(rep["readiness"]["latest"] if rep["readiness"] else None,
                    _d(rep["sleep"]), rep["acwr"], _d(rep["hrv"]), _d(rep["rhr"]), lang=lang)
    v["source"] = rdy_source
    if rdy_source == "self":
        readiness_state = {"value": eff_readiness, "base": None, "delta": None,
                            "items": [], "source": "self"}
    else:
        readiness_state = {
            "value": rdy_decomp["value"],
            "base": rdy_decomp["base"],
            "delta": rdy_decomp["delta"],
            "items": rdy_items,
            "source": rdy_source,
        }
    return {
        "today": today_str,
        "generated": today.isoformat(),
        "range": rep["range"],
        "last_data_day": last_data_day,
        "hr_max": hr_max,
        "verdict": v,
        "m": rep,
        "series": series,
        "sports": sports,
        "muscles_week": week_muscles(week_sessions),
        "spo2": ({"avg": spo2_cur, "lowest": spo2_low_cur}
                 if spo2_cur is not None or spo2_low_cur is not None else None),
        "hrv_status": cur_extra.get("hrv_status"),
        "sleep_deep_h": cur_extra.get("sleep_deep_h"),
        "sleep_rem_h": cur_extra.get("sleep_rem_h"),
        "self_feel": cur_extra.get("self_feel"),
        "state": {
            "risk": risk,
            "signals": signals,
            "form": form,
            "readiness": readiness_state,
        },
        "microcycle": mc,
        "narrative30": to_json(period_blocks(agg, lang=lang)),
        "agg": agg,
        "metrics": _metrics_payload(full_rows, extra_list,
                                    rdy_base, rhr_base, hrv_base, sleep_base),
        "advice": next_session_advice(
            acwr=rep["acwr"], readiness=readiness_state["value"],
            risk_level=(risk or {}).get("level"), hard_streak=agg.get("hard_streak"),
            monotony=rep["monotony"], lang=lang),
    }


def build_html(db_path, backend, hr_max, sex, today, tg_id) -> str:
    data = summary_data(db_path, backend, hr_max, sex, today, tg_id)
    return _HTML.replace("/*DATA*/", json.dumps(data, ensure_ascii=False))


_HTML = r"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Тренировочная сводка</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
:root{--bg:#f6f5f1;--card:#fff;--bd:#e6e3da;--tx:#1d1d1b;--mut:#7a786f;
--green:#0f6e56;--greenb:#e1f5ee;--amber:#854f0b;--amberb:#faeeda;--red:#a32d2d;--redb:#fcebeb;}
@media(prefers-color-scheme:dark){:root{--bg:#141413;--card:#1d1d1b;--bd:#33322e;--tx:#ecebe6;--mut:#9a988e;
--greenb:#103b30;--amberb:#3a2c10;--redb:#3a1717;--green:#5dcaa5;--amber:#ef9f27;--red:#f09595;}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;line-height:1.5}
.wrap{max-width:840px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:22px;font-weight:600;margin:0 0 2px}
.sub{color:var(--mut);font-size:13px;margin-bottom:20px}
.hero{border-radius:16px;padding:20px 22px;margin-bottom:22px}
.hero .t{font-size:13px;opacity:.8;margin-bottom:3px}
.hero .h{font-size:23px;font-weight:600;margin-bottom:7px}
.hero .r{font-size:15px;line-height:1.55}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(135px,1fr));gap:12px;margin-bottom:26px}
.mc{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:14px 15px}
.mc .l{font-size:12px;color:var(--mut)}
.mc .v{font-size:25px;font-weight:600;margin:2px 0}
.mc .d{font-size:13px;font-weight:500}
.mc .n{font-size:11.5px;color:var(--mut);margin-top:3px;line-height:1.45}
h2{font-size:16px;font-weight:600;margin:30px 0 12px}
.cal{display:grid;grid-template-columns:repeat(7,1fr);gap:6px}
.cal .hd{font-size:11px;color:var(--mut);text-align:center}
.cell{border-radius:9px;min-height:48px;padding:6px 7px;display:flex;flex-direction:column;justify-content:space-between}
.cell .dd{font-size:11px;opacity:.85}
.cell .bb{font-size:14px;align-self:flex-end}
.leg{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--mut);margin-bottom:11px}
.sw{width:12px;height:12px;border-radius:3px;display:inline-block;vertical-align:-1px;margin-right:5px}
.card{background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:16px;margin-bottom:8px}
.sp{display:inline-block;background:var(--bg);border:1px solid var(--bd);border-radius:20px;padding:4px 12px;font-size:13px;margin:0 6px 6px 0}
.foot{color:var(--mut);font-size:12px;margin-top:30px;border-top:1px solid var(--bd);padding-top:14px}
</style></head><body><div class="wrap" id="app"></div>
<script>
const DATA=/*DATA*/;
const V={green:['var(--greenb)','var(--green)'],amber:['var(--amberb)','var(--amber)'],red:['var(--redb)','var(--red)']};
function tier(r){return r==null?['var(--card)','var(--mut)']:r>=70?V.green:r>=45?V.amber:V.red}
function fmt(x){return x==null?'—':(Math.round(x*10)/10)}
function delta(d){return d==null?'':(d>=0?'+':'')+fmt(d)}
function dcol(d,hiBad){if(d==null)return 'var(--mut)';const bad=hiBad?d>0:d<0;return bad?'var(--red)':'var(--green)'}
const m=DATA.m, vd=DATA.verdict, S=DATA.series, app=document.getElementById('app');
const heroC=V[vd.level];
function metric(label,b,note,hiBad){const val=b?fmt(b.latest):'—';const dl=b?delta(b.delta):'';
 return `<div class="mc"><div class="l">${label}</div><div class="v">${val} <span class="d" style="color:${b?dcol(b.delta,hiBad):'var(--mut)'}">${dl}</span></div><div class="n">${note}</div></div>`}
app.innerHTML=`
<h1>Тренировочная сводка</h1>
<div class="sub">${DATA.range[0]} … ${DATA.range[1]} · HRmax ${DATA.hr_max} · обновлено ${DATA.generated}</div>
<div class="hero" style="background:${heroC[0]};color:${heroC[1]}">
  <div class="t">Готовность на сегодня · ${DATA.today}</div>
  <div class="h">${vd.title}</div>
  <div class="r">${vd.reason}</div></div>
<div class="grid">
  ${metric('Readiness',m.readiness,'из 100 — личная готовность',false)}
  ${metric('Сон, ч',m.sleep,'против твоей нормы',false)}
  ${metric('HRV',m.hrv,'вариабельность пульса',false)}
  ${metric('Пульс покоя',m.rhr,'выше нормы = недовосстановление',true)}
  <div class="mc"><div class="l">ACWR 7:28</div><div class="v">${fmt(m.acwr)}</div><div class="n">остр.${fmt(m.acute7)} / хрон.${fmt(m.chronic28)} — баланс нагрузки</div></div>
  <div class="mc"><div class="l">Monotony / Strain</div><div class="v">${fmt(m.monotony)}</div><div class="n">strain ${fmt(m.strain)} — однообразие недели</div></div>
</div>
<h2>Календарь готовности · 8 недель</h2>
<div class="leg">
  <span><span class="sw" style="background:var(--greenb)"></span>готов ≥70</span>
  <span><span class="sw" style="background:var(--amberb)"></span>средне 45–69</span>
  <span><span class="sw" style="background:var(--redb)"></span>устал &lt;45</span>
  <span>🏋 — тренировка</span></div>
<div class="cal" id="cal"></div>
<h2>Готовность и нагрузка · ${S.length} дней</h2>
<div class="leg"><span><span class="sw" style="background:#1D9E75;height:3px;border-radius:0"></span>Readiness</span><span><span class="sw" style="background:#888780"></span>Нагрузка (TRIMP)</span></div>
<div style="position:relative;height:260px"><canvas id="ch"></canvas></div>
<h2>Объём по видам</h2>
<div class="card">${DATA.sports.map(s=>`<span class="sp">${s[0]} · ${s[1]}</span>`).join('')}</div>
<div class="foot">Сгенерировано <code>tj report</code> из заметок Obsidian. Plaintext — источник правды, эта страница — производное.</div>`;
const cal=document.getElementById('cal');
['пн','вт','ср','чт','пт','сб','вс'].forEach(w=>{const h=document.createElement('div');h.className='hd';h.textContent=w;cal.appendChild(h)});
const pad=(new Date(S[0][0]).getDay()+6)%7;
for(let i=0;i<pad;i++)cal.appendChild(document.createElement('div'));
S.forEach(r=>{const[bg,fg]=tier(r[1]);const c=document.createElement('div');c.className='cell';
 c.title=`${r[0]} · readiness ${r[1]} · сон ${r[2]}ч`+(r[4]?` · нагрузка ${r[3]}`:' · отдых');
 c.style.background=bg;c.style.color=fg;
 c.innerHTML=`<span class="dd">${+r[0].slice(8)}</span>`+(r[4]?'<span class="bb">🏋</span>':'');cal.appendChild(c)});
new Chart(document.getElementById('ch'),{data:{labels:S.map(r=>r[0].slice(5)),datasets:[
 {type:'bar',data:S.map(r=>r[3]),backgroundColor:'#888780',yAxisID:'y1',order:2},
 {type:'line',data:S.map(r=>r[1]),borderColor:'#1D9E75',backgroundColor:'#1D9E75',tension:.3,pointRadius:1.5,yAxisID:'y',order:1}]},
 options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},
 scales:{y:{position:'left',min:0,max:100,ticks:{font:{size:10}}},
 y1:{position:'right',min:0,grid:{drawOnChartArea:false},ticks:{font:{size:10}}},
 x:{ticks:{font:{size:9},maxRotation:0,autoSkip:true,maxTicksLimit:9}}}}});
</script></body></html>
"""
