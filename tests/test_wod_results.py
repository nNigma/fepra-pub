from __future__ import annotations

from tj.analysis.wod_results import _rounds, _time_sec, summarize_filled


def test_helpers():
    assert _time_sec("8:36") == 516
    assert _rounds("5+3") == (5, 3)
    assert _rounds("4") == (4, 0)
    assert _rounds("нет") is None


def test_summarize_amrap_and_time():
    blocks = [{"format": "amrap_interval", "header": "AMRAP"},
              {"format": "for_time", "header": "WOD"}]
    text = (
        "AMRAP (5×3мин):\n"
        "  вес «рывки»: 22.5\n"
        "  круги, амрап 1: 5+3\n"
        "  круги, амрап 2: 4\n"
        "  круги, амрап 3: 4\n"
        "  круги, амрап 4: 3+2\n"
        "  круги, амрап 5: 3\n"
        "WOD:\n"
        "  время (мм:сс): 8:36\n"
    )
    data, lines = summarize_filled(blocks, text)
    assert data["amrap"]["total_rounds"] == 19          # 5+4+4+3+3
    assert data["amrap"]["total_reps"] == 5             # 3+0+0+2+0
    assert data["times_sec"] == [516]
    assert any(l.startswith("AMRAP") and "19" in l for l in lines)
    assert any(l.startswith("WOD") and "8:36" in l for l in lines)


def test_block_labeled_summary_wod_and_amrap():
    blocks = [
        {"format": "emom_strength", "header": "ТА", "benchmark": None,
         "movements": [{"name": "приседание со штангой на спине"}]},
        {"format": "for_time", "header": "WOD", "benchmark": None, "movements": []},
        {"format": "amrap_interval", "header": "AMRAP", "rounds": 5, "work_min": 3.0,
         "benchmark": None, "movements": [{"name": "рывки", "weighted": True}]},
    ]
    text = (
        "приседание со штангой на спине:\n"
        "  раунд 1 (вес×повторы): 75 х 5\n"
        "WOD:\n"
        "  вес «фронтальный присед с гантелью»: 20\n"
        "  время (мм:сс): 8:36\n"
        "AMRAP (5×3мин):\n"
        "  круги, амрап 1: 2\n  вес «рывков»: 20\n"
        "  круги, амрап 2: 2\n  вес «рывков»: 20\n"
        "  круги, амрап 3: 2\n  вес «рывков»: 20\n"
        "  круги, амрап 4: 2\n  вес «рывков»: 20\n"
        "  круги, амрап 5: 2\n  вес «рывков»: 20\n"
    )
    data, lines = summarize_filled(blocks, text)
    joined = "\n".join(lines)
    assert any(l.startswith("WOD") and "8:36" in l for l in lines)       # время помечено как WOD
    assert any(l.startswith("AMRAP") and "10" in l for l in lines)        # круги помечены как AMRAP
    assert not any(l.startswith("AMRAP") and "8:36" in l for l in lines)  # время НЕ приписано AMRAP


def test_summarize_gym_skill_reps():
    # BUG 2026-07-23: ответ на «выполнено выходов» должен попадать в сводку
    blocks = [{"format": "other", "header": "Гимнастика", "benchmark": None,
               "movements": [{"name": "Bar Muscle-Up"}]}]
    text = "Гимнастика:\n  выполнено выходов: 12\n"
    data, lines = summarize_filled(blocks, text)
    assert any(l.startswith("Гимнастика") and "12" in l for l in lines)


def test_summarize_gym_skill_per_set_rounds():
    blocks = [{"format": "other", "header": "Гимнастика", "benchmark": None,
               "movements": [{"name": "Bar Muscle-Up ×5"}]}]
    text = "Гимнастика:\n  кругов (по 5 выходов): 4\n"
    data, lines = summarize_filled(blocks, text)
    assert any(l.startswith("Гимнастика") and "4 кругов" in l for l in lines)


def test_summarize_benchmark_and_score():
    blocks = [{"kind": "for_time", "name": "Fran", "benchmark": "Fran"},
              {"kind": "tabata", "name": "Табата"}]
    text = "Fran:\n  время (мм:сс): 3:12\nТабата:\n  счёт (мин. раунд): 12\n"
    data, lines = summarize_filled(blocks, text)
    assert data["benchmarks"] == ["Fran"]
    assert any("Бенчмарк: Fran" in l for l in lines)
    assert any(l.startswith("Табата") and "счёт" in l and "12" in l for l in lines)


def test_summarize_ignores_blank_template():
    blocks = [{"kind": "amrap", "name": "AMRAP"}]
    text = "AMRAP:\n  кол-во кругов: ___\n  вес «рывки»: ___\n"
    data, lines = summarize_filled(blocks, text)
    assert "amrap" not in data
    assert lines == []


def test_single_amrap_rounds_reps():
    blocks = [{"format": "amrap", "header": "AMRAP", "benchmark": None}]
    text = "AMRAP:\n  кругов: 18\n  повторов (неполный круг): 12\n"
    data, lines = summarize_filled(blocks, text)
    assert data["amrap"]["total_rounds"] == 18
    assert data["amrap"]["total_reps"] == 12
    assert any(l.startswith("AMRAP") and "18" in l and "12" in l for l in lines)


def test_death_by_minute():
    blocks = [{"format": "death_by", "header": "Death by", "benchmark": None}]
    text = "Death by:\n  дошёл до минуты: 22\n  повторов в незавершённой: 5\n"
    data, lines = summarize_filled(blocks, text)
    assert any(l.startswith("Death by") and "22" in l for l in lines)
