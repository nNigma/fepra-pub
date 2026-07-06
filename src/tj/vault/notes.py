"""
Слой vault: чтение/запись Obsidian-заметок (md + YAML-frontmatter).
Заметки — источник правды (SPEC §4). build парсит их в БД.

Ключевое правило (SPEC §4): данные с часов МЁРДЖАТСЯ в заметку, не затирая
ручной ввод (wod/performed/субъективку/тело). sync дописывает, а не перезаписывает.
"""
from __future__ import annotations

from pathlib import Path


def _frontmatter():
    try:
        import frontmatter
    except ImportError as e:
        raise RuntimeError(
            "Нужен python-frontmatter: pip install -e . (см. README)."
        ) from e
    return frontmatter


def read_note(path: Path) -> tuple[dict, str]:
    """Прочитать md -> (frontmatter dict, body)."""
    fm = _frontmatter()
    post = fm.load(str(path))
    return dict(post.metadata), post.content


def write_note(path: Path, frontmatter_data: dict, body: str = "") -> None:
    """Записать md с frontmatter (создаёт родительские папки)."""
    fm = _frontmatter()
    path.parent.mkdir(parents=True, exist_ok=True)
    post = fm.Post(body or "", **frontmatter_data)
    path.write_text(fm.dumps(post), encoding="utf-8")


def upsert_note(path: Path, base: dict, owned: dict, default_body: str = "") -> None:
    """
    Создать или обновить заметку, не затирая ручной ввод (SPEC §4):
      - base  — ключи заголовка (date/type/sport): ставим, только если их ещё нет;
      - owned — данные с часов (watch/endurance/биометрия): всегда обновляем (None пропускаем);
      - тело и прочий frontmatter (wod/performed/субъективка) сохраняются как есть.
    """
    if path.exists():
        meta, body = read_note(path)
    else:
        meta, body = {}, default_body
    for k, v in base.items():
        meta.setdefault(k, v)
    for k, v in owned.items():
        if v is not None:
            meta[k] = v
    write_note(path, meta, body)


def iter_notes(vault_dir: Path):
    """Итерировать все .md в vault (для build)."""
    if not vault_dir.exists():
        return
    for p in sorted(vault_dir.rglob("*.md")):
        yield p
