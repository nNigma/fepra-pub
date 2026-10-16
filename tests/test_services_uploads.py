from __future__ import annotations

import pytest

from svc_common import make_con
from tj.services import uploads
from tj.services.errors import BadRequest, Invalid, NotFound

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
WEBP = b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"\x00" * 32
HEIC = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 32


@pytest.mark.parametrize("data,mime,ext", [
    (JPEG, "image/jpeg", "jpg"), (PNG, "image/png", "png"),
    (WEBP, "image/webp", "webp"), (HEIC, "image/heic", "heic")])
def test_save_accepts_image_types(tmp_path, data, mime, ext):
    con = make_con(tmp_path)
    root = tmp_path / "up"
    r = uploads.save(con, 7, data, kind="board", root=root)
    assert r["mime"] == mime and r["size"] == len(data) and r["url"].endswith(r["id"])
    row = con.execute("SELECT * FROM uploads WHERE id=?", (r["id"],)).fetchone()
    assert row["path"] == f"7/{r['id']}.{ext}" and row["uid"] == 7 and row["deleted_at"] is None
    assert (root / row["path"]).read_bytes() == data     # сохранено как есть


def test_rejects_wrong_type_even_with_image_mime(tmp_path):
    con = make_con(tmp_path)
    with pytest.raises(Invalid) as e:
        uploads.save(con, 1, b"<html>not an image</html>", root=tmp_path / "up",
                     declared_mime="image/jpeg")
    assert e.value.code == "unsupported_type"
    with pytest.raises(Invalid):
        uploads.save(con, 1, b"GIF89a" + b"\x00" * 20, root=tmp_path / "up")


def test_rejects_empty_and_too_large(tmp_path):
    con = make_con(tmp_path)
    with pytest.raises(Invalid) as e:
        uploads.save(con, 1, b"", root=tmp_path / "up")
    assert e.value.code == "empty"
    big = JPEG + b"\x00" * uploads.MAX_BYTES          # на байты больше лимита
    with pytest.raises(Invalid) as e:
        uploads.save(con, 1, big, root=tmp_path / "up")
    assert e.value.code == "too_large"
    ok = JPEG + b"\x00" * (uploads.MAX_BYTES - len(JPEG))     # ровно 10 МБ — можно
    assert uploads.save(con, 1, ok, root=tmp_path / "up")["size"] == uploads.MAX_BYTES


def test_path_traversal_is_impossible(tmp_path):
    con = make_con(tmp_path)
    root = tmp_path / "up"
    r = uploads.save(con, 1, JPEG, root=root)
    # подмена пути в БД на выход из каталога не даёт прочитать чужой файл
    secret = tmp_path / "secret.txt"
    secret.write_bytes(b"top secret")
    con.execute("UPDATE uploads SET path=? WHERE id=?", ("../secret.txt", r["id"]))
    with pytest.raises(BadRequest) as e:
        uploads.read_bytes(con, 1, r["id"], root=root)
    assert e.value.code == "bad_path"
    with pytest.raises(BadRequest):
        uploads._safe_path(root, "../../etc/passwd")
    with pytest.raises(BadRequest):
        uploads._safe_path(root, "/etc/passwd")
    # новый файл всегда внутри <root>/<uid>/, имя — uuid, клиентское имя не участвует
    r2 = uploads.save(con, 2, PNG, root=root)
    p = (root / f"2/{r2['id']}.png").resolve()
    assert root.resolve() in p.parents and p.is_file()


def test_owner_isolation_and_delete(tmp_path):
    con = make_con(tmp_path)
    root = tmp_path / "up"
    r = uploads.save(con, 1, JPEG, root=root)
    assert uploads.read_bytes(con, 1, r["id"], root=root)[0] == JPEG
    with pytest.raises(NotFound):
        uploads.get(con, 2, r["id"])                  # чужая — как несуществующая
    with pytest.raises(NotFound):
        uploads.get(con, 1, "../../x")                # не UUID
    uploads.delete(con, 1, r["id"])
    with pytest.raises(NotFound):
        uploads.get(con, 1, r["id"])


def test_attach_to_meal_photo_path(tmp_path):
    from tjbot import db as botdb
    con = make_con(tmp_path)
    root = tmp_path / "up"
    r = uploads.save(con, 5, JPEG, kind="meal", root=root)
    mid = botdb.add_meal(con, 5, "2026-09-01", "2026-09-01T12:00", [], {"kcal": 500})
    uploads.attach_to_meal(con, 5, mid, r["id"])
    row = con.execute("SELECT photo_id, photo_path FROM meals WHERE id=?", (mid,)).fetchone()
    assert row["photo_path"] == f"5/{r['id']}.jpg" and row["photo_id"] is None
    with pytest.raises(NotFound):
        uploads.attach_to_meal(con, 6, mid, r["id"])  # чужой пользователь


def test_migrations_are_idempotent(tmp_path):
    import importlib
    con = make_con(tmp_path)
    for n in ("0022_uploads", "0023_activity_trash"):
        importlib.import_module(f"tj.migrations.{n}").upgrade(con)
    cols = [c[1] for c in con.execute("PRAGMA table_info(uploads)")]
    assert cols == ["id", "uid", "kind", "path", "mime", "size", "sha256", "created_at", "deleted_at"]
