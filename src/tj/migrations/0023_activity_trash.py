"""0021: корзина тренировок (мягкое удаление ручных записей).

Удалённая тренировка переезжает из activities в activity_trash вместе со своими
авто-результатами (discipline_results), с меткой deleted_at; восстановление кладёт
всё обратно. Так отчёты и аналитика (и бот) не знают про «удалённые» строки и не
требуют фильтра по deleted_at в десятке запросов.
"""
from __future__ import annotations


def upgrade(con) -> None:
    con.execute(
        '''CREATE TABLE IF NOT EXISTS activity_trash (
            "uid" INTEGER NOT NULL, "activity_id" TEXT NOT NULL,
            "row_json" TEXT NOT NULL, "results_json" TEXT,
            "deleted_at" TEXT NOT NULL,
            PRIMARY KEY ("uid","activity_id") )''')
    con.commit()
