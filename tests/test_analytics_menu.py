from __future__ import annotations


def test_analytics_kb_layout():
    from tj import i18n
    from tjbot.handlers.menu import analytics_kb, BTN_COMP_SUMMARY, BTN_BACK
    texts = [b.text for row in analytics_kb("ru").keyboard for b in row]
    for t in ("Тренировки", "Сводка", BTN_COMP_SUMMARY, BTN_BACK, i18n.t("btn.tseli", "ru")):
        assert t in texts, t
    for t in (i18n.t("btn.goal_single", "ru"), i18n.t("btn.feel", "ru")):
        assert t not in texts, t


def test_goal_and_feel_in_main_menu():
    from tj import i18n
    from tjbot.handlers.menu import main_kb
    texts = [b.text for row in main_kb(12345678, "ru").keyboard for b in row]
    for t in (i18n.t("btn.goal_single", "ru"), i18n.t("btn.feel", "ru")):
        assert t in texts, t
