from tj import i18n


def test_lookup_both_langs():
    i18n.STRINGS["_t.hello"] = {"ru": "Привет", "en": "Hi"}
    assert i18n.t("_t.hello", "ru") == "Привет"
    assert i18n.t("_t.hello", "en") == "Hi"


def test_format_kwargs():
    i18n.STRINGS["_t.greet"] = {"ru": "Привет, {name}", "en": "Hi, {name}"}
    assert i18n.t("_t.greet", "en", name="Sam") == "Hi, Sam"


def test_fallback_to_ru_on_missing_lang():
    i18n.STRINGS["_t.only_ru"] = {"ru": "Только"}
    assert i18n.t("_t.only_ru", "en") == "Только"


def test_unknown_key_returns_key():
    assert i18n.t("_t.nope", "en") == "_t.nope"
