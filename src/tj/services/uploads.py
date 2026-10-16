"""Загрузки файлов пользователя: фото доски, фото еды.

Файлы лежат в `<root>/<uid>/<uuid>.<ext>`, в таблице `uploads` (миграция 0020) — метаданные.
Тип определяем по сигнатуре байтов, а не по заявленному mime и не по имени файла;
имя от клиента вообще не используется, поэтому выйти из каталога нельзя. Путь из БД
дополнительно проверяется на вхождение в корень при каждом чтении.
"""
from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .errors import BadRequest, Invalid, NotFound

MAX_BYTES = 10 * 1024 * 1024
KINDS = ("board", "meal", "other")

# сигнатура -> (mime, расширение); heic/heif/webp проверяются отдельно
_HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1", b"heif"}


def uploads_root() -> Path:
    """Каталог загрузок: FEPRA_UPLOADS_DIR или `<каталог БД>/data/uploads`."""
    env = os.environ.get("FEPRA_UPLOADS_DIR")
    if env:
        return Path(env)
    from tjbot import db as botdb
    return botdb.default_db_path().parent / "data" / "uploads"


def sniff(data: bytes) -> tuple[str, str] | None:
    """Байты -> (mime, ext) для jpeg/png/webp/heic, иначе None."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg", "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png", "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    if data[4:8] == b"ftyp" and data[8:12] in _HEIF_BRANDS:
        return "image/heic", "heic"
    return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_path(root: Path, rel: str) -> Path:
    """Относительный путь из БД -> абсолютный, строго внутри root."""
    base = Path(root).resolve()
    p = (base / rel).resolve()
    if p != base and base not in p.parents:
        raise BadRequest("путь вне каталога загрузок", code="bad_path")
    return p


def _uuid(value: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        raise NotFound("загрузка не найдена")


def save(con, uid: int, data: bytes, *, kind: str = "other", root: Path | None = None,
         declared_mime: str | None = None) -> dict:
    """Сохранить файл пользователя -> {id, url, mime, size, sha256, kind}.
    Ошибки: пусто/тип не поддерживается/больше 10 МБ -> Invalid (422)."""
    if kind not in KINDS:
        raise Invalid("неизвестный вид загрузки", code="bad_kind")
    if not data:
        raise Invalid("пустой файл", code="empty")
    if len(data) > MAX_BYTES:
        raise Invalid("файл больше 10 МБ", code="too_large")
    found = sniff(data)
    if not found:
        raise Invalid("поддерживаются jpeg, png, webp, heic", code="unsupported_type")
    mime, ext = found
    root = Path(root) if root is not None else uploads_root()
    uid = int(uid)
    up_id = str(uuid.uuid4())
    rel = f"{uid}/{up_id}.{ext}"
    dest = _safe_path(root, rel)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    con.execute(
        'INSERT INTO uploads ("id","uid","kind","path","mime","size","sha256","created_at") '
        "VALUES (?,?,?,?,?,?,?,?)", (up_id, uid, kind, rel, mime, len(data), sha, _now()))
    con.commit()
    return {"id": up_id, "url": public_url(up_id), "mime": mime, "size": len(data),
            "sha256": sha, "kind": kind}


def public_url(upload_id: str) -> str:
    return f"/api/uploads/{upload_id}"


def get(con, uid: int, upload_id: str) -> dict:
    """Запись загрузки; чужая или удалённая -> NotFound (существование не раскрываем)."""
    row = con.execute(
        'SELECT * FROM uploads WHERE "id"=? AND "uid"=? AND "deleted_at" IS NULL',
        (_uuid(upload_id), int(uid))).fetchone()
    if not row:
        raise NotFound("загрузка не найдена")
    d = dict(row)
    d["url"] = public_url(d["id"])
    return d


def get_any(con, upload_id: str) -> dict:
    """Запись загрузки без проверки владельца (для админа; проверку прав делает роут)."""
    row = con.execute('SELECT * FROM uploads WHERE "id"=? AND "deleted_at" IS NULL',
                      (_uuid(upload_id),)).fetchone()
    if not row:
        raise NotFound("загрузка не найдена")
    d = dict(row)
    d["url"] = public_url(d["id"])
    return d


def read_record(rec: dict, *, root: Path | None = None) -> tuple[bytes, str]:
    """Содержимое файла по записи загрузки -> (bytes, mime); путь проверяется на вхождение в корень."""
    root = Path(root) if root is not None else uploads_root()
    p = _safe_path(root, rec["path"])
    if not p.is_file():
        raise NotFound("файл загрузки утерян")
    return p.read_bytes(), rec["mime"]


def read_bytes(con, uid: int, upload_id: str, *, root: Path | None = None) -> tuple[bytes, str]:
    """Содержимое файла своей загрузки -> (bytes, mime)."""
    return read_record(get(con, uid, upload_id), root=root)


def delete(con, uid: int, upload_id: str) -> None:
    """Мягкое удаление (файл остаётся на диске до чистки)."""
    rec = get(con, uid, upload_id)
    con.execute('UPDATE uploads SET "deleted_at"=? WHERE "id"=?', (_now(), rec["id"]))
    con.commit()


def attach_to_meal(con, uid: int, meal_id: int, upload_id: str) -> None:
    """Привязать загруженное фото к приёму пищи вместо Telegram file_id (meals.photo_path)."""
    rec = get(con, uid, upload_id)
    row = con.execute('SELECT 1 FROM meals WHERE "id"=? AND "tg_id"=?',
                      (int(meal_id), int(uid))).fetchone()
    if not row:
        raise NotFound("приём пищи не найден")
    con.execute('UPDATE meals SET "photo_path"=? WHERE "id"=? AND "tg_id"=?',
                (rec["path"], int(meal_id), int(uid)))
    con.commit()
