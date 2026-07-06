from __future__ import annotations
from tjbot import access


def test_pro_roundtrip(tmp_path):
    p = tmp_path / "pro_users.json"
    assert access.is_pro(1, path=p) is False
    access.add_pro(1, path=p)
    access.add_pro(2, path=p)
    assert access.is_pro(1, path=p) and access.is_pro(2, path=p)
    assert access.load_pro(path=p) == {1, 2}
    access.remove_pro(1, path=p)
    assert access.is_pro(1, path=p) is False
    assert access.load_pro(path=p) == {2}
