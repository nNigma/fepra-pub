from __future__ import annotations

from tj import i18n
from tjbot.handlers import menu


def test_profile_kb_astro_button_reflects_state():
    off = [b.text for row in menu._profile_kb("ru", False, False).inline_keyboard for b in row]
    assert i18n.t("profile.btn_astro_off", "ru") in off
    on = [b.text for row in menu._profile_kb("ru", True, True).inline_keyboard for b in row]
    assert i18n.t("profile.btn_astro_on", "ru") in on
