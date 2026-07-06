from tjbot.handlers.self_feel import _parse_score


def test_parse_score():
    assert _parse_score("feel:7") == 7
    assert _parse_score("feel:10") == 10
    assert _parse_score("feel:x") is None
