"""
Слой 3: точка входа CLI (SPEC §6).
Команды: seed (бэкфилл) / sync (свежее) / build / analyze / report.
seed и sync делят ОДИН путь raw/ -> канон -> заметки, отличаются диапазоном дат.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

from . import config as cfgmod
from .adapters.garmin import GarminAdapter
from .analysis.dashboard import build_html
from .analysis.engine import analyze as analyze_db, format_report
from .analysis.report import build_day_summaries, build_overview
from .store.build import OWNER_TG_ID
from .store.build import build as build_db
from .vault import notes as vault_notes
from .vault import templates as tpl


def _build_adapter(cfg, env):
    creds = cfgmod.garmin_creds(env)
    paths = cfgmod.data_paths(cfg)
    return GarminAdapter(
        email=creds.email,
        password=creds.password,
        tokenstore=creds.tokenstore,
        tz=cfgmod.timezone(cfg),
        raw_dir=paths["raw"],
        data_dir=paths["data"],
    )


def _ingest(cfg, env, start: date, end: date, with_series: bool) -> int:
    """Единый путь raw/ -> канон -> заметки (общий для seed и sync, SPEC §6)."""
    adapter = _build_adapter(cfg, env)
    vp = cfgmod.vault_paths(cfg)

    n_daily = n_workout = 0

    day = start
    while day <= end:
        metrics = adapter.fetch_daily(day)
        base, owned = tpl.daily_frontmatter(day, metrics)
        vault_notes.upsert_note(vp["daily"] / tpl.daily_filename(day), base, owned)
        n_daily += 1
        day += timedelta(days=1)

    for act in adapter.fetch_activities(start, end, with_series=with_series):
        base, owned = tpl.workout_frontmatter(act)
        vault_notes.upsert_note(vp["workout"] / tpl.workout_filename(act), base, owned)
        n_workout += 1

    print(f"ingest {start}..{end}: дней {n_daily}, активностей {n_workout} -> {vp['base']}")
    return 0


def _load(args):
    env_path = args.env or cfgmod.default_env_path()
    cfg = cfgmod.load_config(args.config)
    env = cfgmod.load_dotenv(env_path)
    return cfg, env


def cmd_seed(args):
    """Одноразовый бэкфилл истории: from..сегодня -> raw/ -> заметки."""
    cfg, env = _load(args)
    return _ingest(cfg, env, date.fromisoformat(args.from_date), date.today(), args.series)


def cmd_sync(args):
    """Регулярная подкачка свежих дней (узкий диапазон, тот же механизм)."""
    cfg, env = _load(args)
    end = date.today()
    return _ingest(cfg, env, end - timedelta(days=args.days), end, args.series)


def cmd_build(args):
    """Заметки -> SQLite/DuckDB (пересобираемый кэш)."""
    cfg, _env = _load(args)
    vp = cfgmod.vault_paths(cfg)
    backend, db_path = cfgmod.store_settings(cfg)
    counts = build_db(vp["base"], db_path, backend)
    print(f"build [{backend}] {vp['base']} -> {db_path}")
    for t, n in counts.items():
        print(f"  {t}: {n}")
    return 0


def cmd_analyze(args):
    """Расчёты поверх БД: ACWR, monotony/strain, базлайны восстановления (SPEC §7)."""
    cfg, _env = _load(args)
    backend, db_path = cfgmod.store_settings(cfg)
    hr_max, sex = cfgmod.athlete(cfg)
    if args.hr_max:
        hr_max = args.hr_max
    try:
        rep = analyze_db(db_path, backend, hr_max, sex, tg_id=OWNER_TG_ID)
    except Exception as e:
        print(f"Не удалось прочитать кэш {db_path}. Сначала собери: tj build\n  ({e})")
        return 1
    print(format_report(rep, hr_max))
    return 0


def cmd_report(args):
    """Сводки в vault: папка Сводка/ — обзор + заметка на каждый день (SPEC §6)."""
    cfg, _env = _load(args)
    backend, db_path = cfgmod.store_settings(cfg)
    hr_max, sex = cfgmod.athlete(cfg)
    folder = cfgmod.vault_paths(cfg)["base"] / "Сводка"
    folder.mkdir(parents=True, exist_ok=True)
    try:
        overview = build_overview(db_path, backend, hr_max, sex, date.today(), OWNER_TG_ID)
        html = build_html(db_path, backend, hr_max, sex, date.today(), OWNER_TG_ID)
        notes = build_day_summaries(db_path, backend, hr_max, sex, tg_id=OWNER_TG_ID,
                                    days_window=args.days, all_days=args.all)
    except Exception as e:
        print(f"Не удалось собрать отчёт из {db_path}. Сначала: tj build\n  ({e})")
        return 1
    (folder / "_Обзор.md").write_text(overview, encoding="utf-8")
    (folder / "dashboard.html").write_text(html, encoding="utf-8")
    for day, md in notes.items():
        (folder / f"{day}.md").write_text(md, encoding="utf-8")
    old = folder.parent / "_Сводка.md"
    if old.exists():
        old.unlink()
    print(f"report -> {folder}  (_Обзор + dashboard.html + {len(notes)} дн.)")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tj", description="Training Journal")
    p.add_argument("--config", default="config.toml", help="путь к config.toml")
    p.add_argument("--env", default=None,
                   help="путь к env-файлу с кредами (по умолч.: .env, см. .env.example)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("seed", help="бэкфилл истории")
    s.add_argument("--from", dest="from_date", required=True, help="YYYY-MM-DD")
    s.add_argument("--series", action="store_true", help="качать тяжёлые ряды в parquet (медленно)")
    s.set_defaults(func=cmd_seed)

    sy = sub.add_parser("sync", help="свежие дни")
    sy.add_argument("--days", type=int, default=3, help="сколько последних дней (по умолч. 3)")
    sy.add_argument("--series", action="store_true", help="качать тяжёлые ряды в parquet")
    sy.set_defaults(func=cmd_sync)

    sub.add_parser("build", help="заметки -> БД").set_defaults(func=cmd_build)
    an = sub.add_parser("analyze", help="нагрузка (ACWR/monotony) + тренды восстановления")
    an.add_argument("--hr-max", type=int, default=None, help="HRmax (по умолч. из config: 220-age)")
    an.set_defaults(func=cmd_analyze)
    rp = sub.add_parser("report", help="сводки в vault: папка Сводка/ (обзор + по дням)")
    rp.add_argument("--days", type=int, default=3, help="последних дней с заметкой по дню (по умолч. 3)")
    rp.add_argument("--all", action="store_true", help="заметки по ВСЕМ дням истории")
    rp.set_defaults(func=cmd_report)

    args = p.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
