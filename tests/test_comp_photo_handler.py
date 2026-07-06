from __future__ import annotations
from tjbot.handlers import competition


def test_comp_photo_handlers_exist():
    assert hasattr(competition, "fill_stage_photo")
    assert hasattr(competition, "fill_result_photo")
    assert hasattr(competition, "confirm_stage_save")
    assert hasattr(competition, "confirm_result_save")
    assert competition.handler() is not None
