from __future__ import annotations
from tjbot.handlers import menu


def _texts(kb):
    return [b.text for row in kb.keyboard for b in row]


def test_main_kb_clean_for_regular(monkeypatch):
    monkeypatch.setattr(menu, "is_admin", lambda tg: False)
    t = _texts(menu.main_kb(2, "ru"))
    assert "➕ Результат" not in t and "🎯 Цель" not in t and "Pro" not in t
    assert "👑 Admin" not in t
    assert "Программа зала" in t
    assert "Записать тренировку" in t and "📊 Аналитика" in t
    assert "Соревнования" in t
    assert "Питание" in t and "Профиль" in t
    assert "Тренировки" not in t and "Сводка" not in t and "Цели" not in t
    assert "✏️ Редактировать тренировку" not in t


def test_main_kb_admin_extras(monkeypatch):
    monkeypatch.setattr(menu, "is_admin", lambda tg: True)
    t = _texts(menu.main_kb(1, "ru"))
    assert "👑 Admin" in t and "Программа зала" in t
    assert menu.BTN_ADMIN == "👑 Admin" and menu.BTN_BACK == "← Назад"


def test_main_kb_sections(monkeypatch):
    monkeypatch.setattr(menu, "is_admin", lambda tg: True)
    from tjbot.handlers.menu import (main_kb, BTN_ANALYTICS, BTN_RECORD,
                                     BTN_CLUB_SECTION, BTN_COMP_SECTION, BTN_ADMIN)
    texts = [b.text for row in main_kb(11111111, "ru").keyboard for b in row]
    for t in (BTN_ANALYTICS, BTN_RECORD, "Программа зала", BTN_COMP_SECTION,
              "Питание", "Профиль", BTN_ADMIN):
        assert t in texts, t
    for gone in ("Тренировки", "Сводка", "Цели"):
        assert gone not in texts, gone

def test_main_kb_no_admin_for_user():
    from tjbot.handlers.menu import main_kb, BTN_ADMIN
    texts = [b.text for row in main_kb(1, "ru").keyboard for b in row]
    assert BTN_ADMIN not in texts
