"""Питание как фактор готовности: отсечка недолога и знак вклада."""
from __future__ import annotations

from tj.analysis import nutrition as n

TARGETS = {"kcal": 2357, "protein_g": 140, "fat_g": 70, "carb_g": 292}


def _meals(n_meals, kcal_total, protein_total):
    """n приёмов, поровну делящих день."""
    return [{"kcal": kcal_total / n_meals, "protein_g": protein_total / n_meals}
            for _ in range(n_meals)]


def test_nedolog_ne_schitaetsya_golodaniem():
    # реальный день из базы: один приём на 280 ккал — записан кусок, а не голод
    assert n.readiness_contrib(_meals(1, 280, 9), TARGETS) is None
    assert n.readiness_contrib(_meals(2, 227, 5), TARGETS) is None


def test_pustoy_den_i_bez_norm():
    assert n.readiness_contrib([], TARGETS) is None
    assert n.readiness_contrib(_meals(5, 2400, 140), None) is None
    assert n.readiness_contrib(_meals(5, 2400, 140), {"kcal": 0, "protein_g": 0}) is None


def test_schitaem_po_kaloriyam_a_ne_po_chislu_priyomov():
    # один приём на 72% нормы — записанный день; три перекуса на 20% — нет
    assert n.day_logged(_meals(1, 1700, 100), TARGETS["kcal"]) is True
    assert n.day_logged(_meals(3, 470, 20), TARGETS["kcal"]) is False


def test_granica_50_procentov():
    half = TARGETS["kcal"] * 0.5
    assert n.day_logged(_meals(3, half + 1, 60), TARGETS["kcal"]) is True
    assert n.day_logged(_meals(3, half - 1, 60), TARGETS["kcal"]) is False
    # 1119 ккал = 47% нормы: раньше проходило по числу приёмов, теперь отсекается
    assert n.readiness_contrib(_meals(3, 1119, 44), TARGETS) is None


def test_popal_v_obe_tseli_plus_dva():
    assert n.readiness_contrib(_meals(5, 2640, 148), TARGETS) == 2


def test_kalorii_v_norme_belok_nedobran():
    # 2484 ккал в норме (+1), белок 100/140 = 0.71 (-1) -> ноль
    assert n.readiness_contrib(_meals(6, 2484, 100), TARGETS) == 0


def test_perebor_kaloriy_minus():
    # 3120 ккал = 132% нормы -> -1, белок 124/140 = 0.89 -> 0
    assert n.readiness_contrib(_meals(5, 3120, 124), TARGETS) == -1


def test_silny_deficit_i_belka_i_kaloriy():
    # 1254 ккал (53%) и белок 66 (47%) — обе метрики в минус
    assert n.readiness_contrib(_meals(4, 1254, 66), TARGETS) == -3


def test_vklad_ne_vyhodit_za_granicy():
    # ровно на пороге лога, но белка нет совсем -> минимум
    assert n.readiness_contrib(_meals(4, 1180, 0), TARGETS) == -3
    assert n.readiness_contrib(_meals(4, 2357, 400), TARGETS) == 2
