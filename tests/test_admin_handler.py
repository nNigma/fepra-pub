from __future__ import annotations
from tjbot.handlers import admin


def test_removable_excludes_admins():
    out = admin._removable({1, 2, 3}, {1}, {2: "Боб"})
    assert out == [("Боб (2)", 2), ("3", 3)]


def test_removable_empty():
    assert admin._removable({1}, {1}, {}) == []


def test_admin_kb_and_register():
    assert admin.admin_kb() is not None
    assert admin.BTN_ADD_USER == "➕ Добавить в бота"
    assert admin.BTN_DEL_USER == "➖ Удалить из бота"
    assert callable(admin.register)
