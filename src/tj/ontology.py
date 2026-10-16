"""
Онтология движений (SPEC §10): аббревиатуры/синонимы RU+EN -> канонический id.
Растёт со временем, переиспользуется между залами. Стартовый словарь.
"""
from __future__ import annotations

# canonical_id -> список вариантов написания (lowercase)
MOVEMENTS: dict[str, list[str]] = {
    "thruster":            ["thruster", "thrusters", "трастер", "трастеры"],
    "cluster":             ["cluster", "clusters", "кластер", "кластеры", "кластере"],
    "pull_up":             ["pull-up", "pull up", "pullups", "подтягивание", "подтягивания"],
    "chest_to_bar":        ["c2b", "chest-to-bar", "подтягивания до груди"],
    "toes_to_bar":         ["t2b", "toes-to-bar", "нкп", "ноги к перекладине", "носки к перекладине"],
    "hspu":                ["hspu", "handstand push-up", "отжимания в стойке"],
    "wall_walk":           ["хпс", "wall walk", "хождение по стене", "хождение на руках"],
    "double_under":        ["du", "дп", "double under", "двойные прыжки", "двойные"],
    "single_under":        ["ос", "оп", "su", "single under", "одинарные прыжки", "одиночные прыжки"],
    "bar_muscle_up":       ["bar muscle-up", "bar muscle up", "bmu", "бму", "выход силой",
                            "выход силой на турнике", "выходы силой", "выход на турнике",
                            "выходы на турнике", "выход на две", "выход на перекладине",
                            "выход", "выходы", "выходов"],
    "muscle_up":           ["muscle-up", "muscle up", "mu", "мап", "выход на кольцах",
                            "выход силой на кольцах", "выходы на кольцах", "выход на кольца"],
    "push_up":             ["push-up", "push up", "pushup", "push-ups", "отжимание", "отжимания",
                            "отжиманий", "отжимания от пола"],
    "burpee":              ["burpee", "burpees", "бёрпи", "берпи"],
    "burpee_over_bar":     ["бчш", "б.чш", "burpee over bar", "бёрпи через штангу", "берпи через штангу"],
    "burpee_over_parapet": ["бчп", "burpee over parapet", "бёрпи через парапет", "берпи через парапет"],
    "box_jump":            ["box jump", "выпрыгивания на тумбу", "запрыгивания"],
    "box_jump_over":       ["пчб", "box jump over", "прыжки через бокс", "прыжки через тумбу"],
    "deadlift":            ["deadlift", "dl", "становая", "становая тяга", "дэдлифт", "дедлифт",
                            "становую", "становой тяги", "тяга становая", "стан. тяга", "ст. тяга"],
    "back_squat":          ["back squat", "back-squat", "bs", "присед", "приседание", "приседания",
                            "приседания со штангой", "приседание со штангой", "присед на спине", "бэк сквот",
                            "бэк-сквот", "бэксквот", "псшнс", "приседы", "приседов", "присед со штангой",
                            "присед на спину", "присед со штангой на спине", "приседания со штангой на спине",
                            "присед со штангой на спину"],
    "bench_press":         ["bench", "bench press", "bp", "бенч", "бенч пресс", "бенч-пресс", "жим лёжа",
                            "жим лежа", "жим штанги лёжа", "жимов лёжа", "жима лёжа", "жимы лёжа",
                            "жимов лёжа штанги", "жим лёжа штанги", "жимов лежа", "жим лежа штанги"],
    "shoulder_press":      ["shoulder press", "strict press", "стрикт пресс", "overhead press", "ohp",
                            "military press", "жим стоя", "армейский жим", "военный жим", "милитари жим",
                            "жим над головой стоя", "жим штанги стоя", "жим с груди стоя", "жим плечами"],
    "push_press":          ["push press", "швунг", "швунги", "швунгов", "жимовой швунг", "толчковый швунг", "пуш пресс"],
    "clean_and_jerk":      ["clean and jerk", "c&j", "cj", "клин джерк", "клин-джерк", "взятие и толчок",
                            "взятие+толчок", "взятие + толчок", "взятие и толчок штанги", "толчок",
                            "толчок штанги", "толчок в ножницы",
                            "толчок в разножку", "взятие на грудь и толчок",
                            "взятие + швунг", "взятие+швунг", "взятие со швунгом",
                            "взятие + толчок в ножницы", "взятие+толчок в ножницы"],
    "front_squat":         ["фр.пр", "фр пр", "фр. пр", "фр. пр.", "front squat", "fs", "фронтальные приседания",
                            "фронтальный присед", "фронт присед", "фронт. присед", "фронтальный сквот",
                            "фронт сквот", "фронтальные приседы", "фсшнс", "присед со штангой на груди",
                            "приседания со штангой на груди", "присед на груди"],
    "overhead_squat":      ["ohs", "оверхэд", "оверхед", "оверхэд-присед", "оверхед-присед",
                            "оверхэд присед", "оверхед присед", "оверхедный присед", "overhead squat",
                            "присед над головой", "присед со штангой над головой", "присед над головой со штангой"],
    "clean":               ["clean", "взятие", "тяга на грудь"],
    "snatch":              ["snatch", "рывок", "рывки", "рывков"],
    "squat_snatch":        ["рывок в сед", "рывок в разножку", "сед-рывок", "squat snatch",
                            "рывок в глубокий сед", "рывок в присед", "рывок в разножку со штангой", "сквот снатч"],
    "power_snatch":        ["рывок в стойку", "рывок в силовую", "пауэр рывок", "power snatch",
                            "силовой рывок", "рывок в полуподсед", "рывок в полуприсед", "пауэр сноуч"],
    "clean_floor":         ["взятие с пола", "взятие на грудь", "взятие на грудь с пола", "pc",
                            "взятие штанги на грудь", "взятие в сед", "взятие с пола в сед", "взятие в разножку"],
    "power_clean":         ["power clean", "pc", "силовое взятие", "пауэр клин", "пауэр-клин",
                            "взятие в стойку", "взятие на грудь в стойку", "взятие в полуприсед",
                            "взятие в полуподсед", "взятие с пола в стойку"],
    "jerk":                ["jerk", "jerks", "split jerk", "sj", "push jerk", "power jerk", "джерк",
                            "толчок со стоек", "толчок с груди", "толчок от груди", "толчок со стоек в ножницы",
                            "толчок с плеч", "jerk со стоек"],
    "snatch_pull":         ["snatch pull", "тяга рывковая", "рывковая тяга", "тяга на рывок",
                            "тяга для рывка", "тяга рывок"],
    "clean_pull":          ["clean pull", "тяга классическая", "классическая тяга", "тяга на взятие",
                            "тяга для взятия", "тяга толчковая", "толчковая тяга"],
    "hang_snatch":         ["hang snatch", "рывок с виса", "рывок из виса", "рывок с виса в сед",
                            "хэнг сноуч", "хенг сноуч"],
    "hang_clean":          ["взятие с виса", "взятие с виса на грудь", "взятий с виса на грудь", "hang clean",
                            "hpc", "хэнг клин", "хенг клин", "взятие на грудь с виса", "взятие с виса в сед"],
    "devil_press":         ["дж", "devil press", "дьявольский жим", "дьявольские жимы"],
    "kb_clean_jerk":       ["взятие и толчок гирь", "взятие+толчок гирь", "толчок гирь", "kb clean and jerk"],
    "wall_ball":           ["wall ball", "wb", "бм", "вол болл", "броски мяча"],
    "bike":                ["байк", "bike", "эйрбайк", "air bike", "велоэргометр"],
    "row":                 ["гребля", "row", "гребной", "rowing"],
    "walking_lunge":       ["выпады", "walking lunge", "выпады с мячом", "lunges"],
    "shuttle_run":         ["чб", "челночный бег", "челнок", "shuttle run", "shuttle"],
}

_LOOKUP = {alias: cid for cid, aliases in MOVEMENTS.items() for alias in aliases}

CATEGORY: dict[str, str] = {
    "thruster": "barbell", "cluster": "barbell", "deadlift": "barbell", "back_squat": "barbell",
    "bench_press": "barbell", "shoulder_press": "barbell", "push_press": "barbell", "clean_and_jerk": "barbell",
    "front_squat": "barbell", "overhead_squat": "barbell", "clean": "barbell",
    "snatch": "barbell", "squat_snatch": "barbell", "power_snatch": "barbell",
    "clean_floor": "barbell", "hang_clean": "barbell",
    "power_clean": "barbell", "jerk": "barbell", "snatch_pull": "barbell",
    "clean_pull": "barbell", "hang_snatch": "barbell",
    "devil_press": "dumbbell", "kb_clean_jerk": "kb",
    "wall_ball": "medball", "walking_lunge": "dumbbell",
    "pull_up": "gymnastics", "chest_to_bar": "gymnastics", "toes_to_bar": "gymnastics",
    "hspu": "gymnastics", "wall_walk": "gymnastics", "double_under": "gymnastics",
    "single_under": "gymnastics", "burpee": "gymnastics", "burpee_over_bar": "gymnastics",
    "burpee_over_parapet": "gymnastics", "box_jump": "gymnastics", "box_jump_over": "gymnastics",
    "bar_muscle_up": "gymnastics", "muscle_up": "gymnastics", "push_up": "gymnastics",
    "bike": "cardio", "row": "cardio", "shuttle_run": "cardio",
}
_WEIGHTED_CATS = {"barbell", "dumbbell", "kb", "medball"}
WEIGHTED = {cid for cid, cat in CATEGORY.items() if cat in _WEIGHTED_CATS}

# Общий канон, требующий уточнения варианта при записи в цели.
_VARIANT_FAMILY = {"snatch": "snatch", "clean": "clean"}

# Компаунд = 2 упражнения в одном: макс кластера засчитывается в обе дисциплины.
COMPOUND: dict[str, list[str]] = {"cluster": ["clean_floor", "thruster"]}


def variant_family(canon: str | None) -> str | None:
    """'snatch'|'clean' если движение общее и нужен вопрос о варианте, иначе None."""
    return _VARIANT_FAMILY.get(canon)


def is_compound(canon: str | None) -> bool:
    return canon in COMPOUND


def compound(canon: str | None) -> list[str] | None:
    """Компоненты компаунда (кластер -> [взятие с пола, трастер]), иначе None."""
    return COMPOUND.get(canon) if canon else None


def category(canon: str | None) -> str | None:
    return CATEGORY.get(canon) if canon else None


def is_weighted(canon: str | None) -> bool:
    return canon in WEIGHTED


def base_ru(canon: str | None) -> str | None:
    """Базовое русское написание канона (первый кириллический алиас) для меток шаблона."""
    for a in MOVEMENTS.get(canon or "", []):
        if any("а" <= ch.lower() <= "я" for ch in a):
            return a
    return None


def resolve(text: str, aliases: dict[str, str] | None = None) -> str | None:
    """Канонический id движения по варианту написания. aliases — runtime-словарь
    (из БД), перекрывает/дополняет статический. Иначе None."""
    key = text.strip().lower()
    if aliases and key in aliases:
        return aliases[key]
    return _LOOKUP.get(key)


def find(text: str, aliases: dict[str, str] | None = None) -> list[str]:
    """Найти канон-движения ВНУТРИ свободной фразы (описательные названия из ИИ):
    длинные алиасы первыми, с маскированием найденного. Возвращает канон-id в порядке нахождения."""
    norm = " ".join(w.strip(" .,:;()") for w in
                    (text or "").lower().replace("+", " ").replace("-", " ").split())
    hay = f" {norm} "
    lookup = dict(_LOOKUP)
    if aliases:
        lookup.update(aliases)
    found: list[str] = []
    for alias, canon in sorted(lookup.items(), key=lambda p: len(p[0].split()), reverse=True):
        needle = f" {alias} "
        if needle in hay:
            if canon not in found:
                found.append(canon)
            hay = hay.replace(needle, " ")
    return found
