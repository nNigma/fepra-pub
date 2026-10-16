from tj import ontology
from tj.analysis import standards
from tj.analysis.wod_program import parse_program, render_template
from tj.analysis.wod_results import extract_maxes
from tjbot import db


def _con(tmp_path):
    con = db.connect(tmp_path / "t.db")
    db.init_schema(con)
    return con


def test_cluster_ontology():
    assert ontology.resolve("кластер") == "cluster"
    assert ontology.resolve("кластеры") == "cluster"
    assert ontology.is_weighted("cluster") is True
    assert ontology.compound("cluster") == ["clean_floor", "thruster"]
    assert ontology.compound("back_squat") is None
    assert ontology.is_compound("cluster") is True
    assert ontology.is_compound("back_squat") is False


def test_thruster_is_tracked_lift():
    d = standards.disciplines()
    assert "thruster" in d
    assert d["thruster"]["kind"] == "lift"
    assert d["thruster"]["ontology"] == "thruster"
    assert len(d["thruster"]["thresholds"]["m"]) == 5
    assert len(d["thruster"]["thresholds"]["f"]) == 5


def test_cluster_is_tracked_lift():
    d = standards.disciplines()
    assert "cluster" in d
    assert d["cluster"]["kind"] == "lift"
    assert d["cluster"]["ontology"] == "cluster"
    assert len(d["cluster"]["thresholds"]["m"]) == 5
    assert len(d["cluster"]["thresholds"]["f"]) == 5


def test_lifts_to_results_expands_cluster(tmp_path):
    con = _con(tmp_path)
    res = db.lifts_to_results(con, [{"movement": "кластер", "weight_kg": 70, "reps": 1}])
    by = {r["discipline"]: r for r in res}
    assert set(by) == {"cluster", "clean_floor", "thruster"}
    assert by["cluster"]["weight"] == 70
    assert by["clean_floor"]["weight"] == 70
    assert by["thruster"]["weight"] == 70


def test_split_lifts_expands_cluster(tmp_path):
    con = _con(tmp_path)
    resolved, ambiguous = db.split_lifts(con, [{"movement": "кластер", "weight_kg": 75, "reps": 3}])
    by = {r["discipline"]: r for r in resolved}
    assert set(by) == {"cluster", "clean_floor", "thruster"}
    assert all(r["weight"] == 75 for r in resolved)
    assert ambiguous == []


def test_findmax_line_becomes_strength_block():
    board = ("WOD N1\nAMRAP 11 мин\n- 100 кал гребля/байк\n"
             "- Найти ПМ в кластере\nза оставшееся время")
    blocks = parse_program(board)
    strength = [b for b in blocks if b["format"] == "strength"]
    assert len(strength) == 1
    assert strength[0]["movements"][0]["canon"] == "cluster"
    assert strength[0]["movements"][0]["name"] == "кластер"  # не «кластере»
    tmpl = render_template(blocks)
    assert "вес×повторы" in tmpl
    assert "___" not in tmpl


def test_findmax_ignores_bodyweight_movement():
    board = "WOD\n- Найти ПМ в подтягиваниях"
    strength = [b for b in parse_program(board) if b["format"] == "strength"]
    assert strength == []


def test_cluster_maxes_end_to_end(tmp_path):
    con = _con(tmp_path)
    board = "WOD N1\nAMRAP 11 мин\n- 100 кал гребля\n- Найти ПМ в кластере"
    blocks = parse_program(board)
    strength = [b for b in blocks if b["format"] == "strength"][0]
    label = strength["movements"][0]["name"]
    filled = f"{label}:\n  раунд 1 (вес×повторы): 72×1"
    maxes = extract_maxes(blocks, filled)
    assert any(m["weight_kg"] == 72 for m in maxes)
    res = db.lifts_to_results(con, maxes)
    assert {r["discipline"] for r in res} >= {"cluster", "clean_floor", "thruster"}
