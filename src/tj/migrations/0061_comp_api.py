"""0060: соревнования через API — индексы под идемпотентность и быстрый доступ.

Только индексы (таблицы comp_* создаёт схема бота). Уникальный (division_id, source_ref)
даёт идемпотентное подтверждение этапов, распознанных с фото (source_ref = upload:<id>#<n>);
у старых этапов source_ref пустой и в индекс не попадает.
"""
from __future__ import annotations


def _has_table(con, name: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                       (name,)).fetchone() is not None


def upgrade(con) -> None:
    if _has_table(con, "comp_participants"):
        con.execute('CREATE INDEX IF NOT EXISTS comp_participants_div_idx '
                    'ON comp_participants ("division_id","tg_id")')
    if _has_table(con, "comp_results"):
        con.execute('CREATE INDEX IF NOT EXISTS comp_results_stage_idx '
                    'ON comp_results ("stage_id","athlete")')
    if _has_table(con, "comp_stages"):
        try:
            con.execute('CREATE UNIQUE INDEX IF NOT EXISTS comp_stages_source_idx '
                        'ON comp_stages ("division_id","source_ref") '
                        'WHERE "source_ref" IS NOT NULL')
        except Exception:      # в БД уже есть дубли source_ref — хватит обычного индекса
            con.execute('CREATE INDEX IF NOT EXISTS comp_stages_source_idx2 '
                        'ON comp_stages ("division_id","source_ref")')
    con.commit()
