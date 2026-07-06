import re, pathlib
TXT = pathlib.Path("src/tjapp/static/strings.js").read_text(encoding="utf-8")
def _keys(block):
    return set(re.findall(r'"([\w.]+)"\s*:', block))
def _split():
    ru = TXT.split("ru:",1)[1].split("en:",1)[0]
    en = TXT.split("en:",1)[1]
    return ru, en
def test_front_catalog_ru_en_parity():
    ru, en = _split()
    kr, ke = _keys(ru), _keys(en)
    assert kr == ke, f"RU/EN key mismatch: {kr ^ ke}"
def test_front_en_no_cyrillic():
    _, en = _split()
    vals = re.findall(r':\s*"((?:[^"\\]|\\.)*)"', en)
    bad = [v for v in vals if re.search("[А-Яа-яЁё]", v) and "Язык" not in v]
    assert not bad, f"cyrillic in EN front strings: {bad}"
