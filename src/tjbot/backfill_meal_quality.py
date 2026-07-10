"""Разовый бэкфилл quality у приёмов без оценки: Claude оценивает по названиям
блюд (фото уже нет), батчами, с фолбэком на Gemini.
Запуск: PYTHONPATH=src python -m tjbot.backfill_meal_quality [--apply]
На сервере claude не в PATH у SSH-шелла: CLAUDE_BIN=/root/.local/bin/claude PYTHONPATH=src ...
По умолчанию dry-run: печатает план, ничего не пишет."""
from __future__ import annotations

import json
import sys

from tj import llm
from . import db as botdb

_BATCH = 8

_PROMPT = (
    "Оцени качество приёмов пищи по названиям блюд. Шкала: 1 — цельная еда с "
    "белком; 2 — обычная сбалансированная; 3 — жареное/сладкое без криминала; "
    "4 — фастфуд/сахарная бомба. Верни ТОЛЬКО JSON-массив "
    '[{"id": число, "quality": 1-4, "note": "почему, до 60 знаков"}].\n\nПРИЁМЫ:\n%s'
)


def _grade_batch(batch: list[dict]) -> list[dict]:
    items = "\n".join(
        f'- id={r["id"]}: ' + ", ".join(
            f.get("name", "?") for f in json.loads(r["foods"] or "[]"))
        for r in batch)
    prompt = _PROMPT % items
    raw = llm.claude_complete(prompt) or llm.complete(
        "Ты оцениваешь качество еды.", prompt, max_output_tokens=2000)
    if not raw:
        print(f"  батч из {len(batch)}: LLM не ответил, пропуск")
        return []
    i, j = raw.find("["), raw.rfind("]")
    if i == -1 or j <= i:
        print(f"  батч из {len(batch)}: в ответе нет JSON-массива, пропуск")
        return []
    try:
        data = json.loads(raw[i:j + 1])
    except ValueError:
        print(f"  батч из {len(batch)}: JSON битый (похоже, ответ обрезан), пропуск")
        return []
    return data if isinstance(data, list) else []


def main() -> None:
    apply = "--apply" in sys.argv
    con = botdb.connect(botdb.default_db_path())
    try:
        rows = [dict(r) for r in con.execute(
            "SELECT id, foods FROM meals WHERE quality IS NULL ORDER BY id")]
        if not rows:
            print("нечего бэкфиллить")
            return
        print(f"приёмов без оценки: {len(rows)}, батчей: "
              f"{(len(rows) + _BATCH - 1) // _BATCH}")
        graded = 0
        for start in range(0, len(rows), _BATCH):
            for it in _grade_batch(rows[start:start + _BATCH]):
                q = it.get("quality")
                if it.get("id") and q in (1, 2, 3, 4):
                    print(f'#{it["id"]} -> {q} ({it.get("note", "")})')
                    graded += 1
                    if apply:
                        con.execute(
                            "UPDATE meals SET quality=?, quality_note=? WHERE id=?",
                            (q, (it.get("note") or "")[:80], it["id"]))
        if apply:
            con.commit()
            print(f"записано оценок: {graded}")
        else:
            print(f"dry-run: оценок в плане {graded}; добавь --apply чтобы записать")
    finally:
        con.close()


if __name__ == "__main__":
    main()
