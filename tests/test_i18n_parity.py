import re

from tj import i18n

_CYR = re.compile("[А-Яа-яЁё]")
_EN_CYRILLIC_OK = {"btn.lang"}


def test_every_key_has_ru_and_en():
    missing = [
        k
        for k, v in i18n.STRINGS.items()
        if not k.startswith("_t.") and (not v.get("ru") or not v.get("en"))
    ]
    assert not missing, f"ключи без перевода: {missing}"


def test_en_values_have_no_cyrillic():
    bad = [
        k
        for k, v in i18n.STRINGS.items()
        if not k.startswith("_t.") and k not in _EN_CYRILLIC_OK and _CYR.search(v.get("en", ""))
    ]
    assert not bad, f"кириллица в EN: {bad}"
