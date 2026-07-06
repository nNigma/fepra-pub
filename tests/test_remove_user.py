from __future__ import annotations
from tjbot import access


def test_remove_user_roundtrip(tmp_path):
    p = tmp_path / "users_allow.json"
    access.add_user(1, path=p)
    access.add_user(2, path=p)
    assert access.load_allow(path=p) == {1, 2}
    access.remove_user(1, path=p)
    assert access.load_allow(path=p) == {2}
    access.remove_user(999, path=p)
    assert access.load_allow(path=p) == {2}
