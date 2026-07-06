"""
Загрузка конфигурации и кредов (SPEC §6).

config.toml — tz, пути vault, бэкенд кэша, приоритеты мёрджа.
.env        — креды Garmin (НЕ в git). Парсим без зависимостей.
Пути с ~ / $VAR разворачиваются.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


def _expand(p: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(p)))


def load_config(path: str | os.PathLike = "config.toml") -> dict:
    """Прочитать config.toml -> dict. Бросает, если файла нет."""
    cfg_path = _expand(str(path))
    if not cfg_path.exists():
        raise FileNotFoundError(
            f"Нет {cfg_path}. Скопируй config.example.toml -> config.toml (SPEC §6)."
        )
    with cfg_path.open("rb") as f:
        return tomllib.load(f)


def load_dotenv(path: str | os.PathLike = ".env") -> dict[str, str]:
    """
    Минимальный парсер .env (KEY=VALUE), без python-dotenv.
    Значения из реального окружения перекрывают файл.
    """
    env: dict[str, str] = {}
    p = _expand(str(path))
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            env[key.strip()] = val.strip().strip('"').strip("'")
    for key in ("GARMIN_EMAIL", "GARMIN_PASSWORD", "GARMIN_TOKENSTORE"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    return env


_ENV_CANDIDATES = (
    ".env",
)


def default_env_path() -> Path:
    """Первый существующий env-файл (проектный .env)."""
    for c in _ENV_CANDIDATES:
        p = _expand(c)
        if p.exists():
            return p
    return _expand(".env")


@dataclass
class GarminCreds:
    email: str
    password: str
    tokenstore: str


def garmin_creds(env: dict[str, str]) -> GarminCreds:
    try:
        email = env["GARMIN_EMAIL"]
        password = env["GARMIN_PASSWORD"]
    except KeyError as e:
        raise RuntimeError(
            f"Нет {e.args[0]} в .env. Скопируй .env.example -> .env и заполни."
        ) from None
    tokenstore = env.get("GARMIN_TOKENSTORE", "~/.garminconnect")
    return GarminCreds(
        email=email, password=password, tokenstore=str(_expand(tokenstore))
    )


def vault_paths(cfg: dict) -> dict[str, Path]:
    """Развёрнутые пути vault + подпапки по типам заметок."""
    v = cfg.get("vault", {})
    base = _expand(v.get("path", "~/Obsidian/Training"))
    return {
        "base": base,
        "daily": base / v.get("daily_dir", "daily"),
        "workout": base / v.get("workout_dir", "workouts"),
        "competition": base / v.get("competition_dir", "competitions"),
    }


def data_paths(cfg: dict) -> dict[str, Path]:
    """Bronze (raw/) и sidecar parquet (data/). См. SPEC §4, §8."""
    p = cfg.get("paths", {})
    return {
        "raw": _expand(p.get("raw", "./raw")),
        "data": _expand(p.get("data", "./data")),
    }


def store_settings(cfg: dict) -> tuple[str, Path]:
    """(backend, db_path) для пересобираемого кэша build (SPEC §6)."""
    s = cfg.get("store", {})
    return s.get("backend", "duckdb"), _expand(s.get("path", "./cache.duckdb"))


def athlete(cfg: dict) -> tuple[int, str]:
    """(hr_max, sex) для расчётов нагрузки. hr_max из config или 220-age."""
    u = cfg.get("user", {})
    hr_max = u.get("hr_max")
    if not hr_max:
        age = u.get("age")
        hr_max = 220 - age if age else 190
    return int(hr_max), (u.get("sex") or "m").lower()


def timezone(cfg: dict) -> str:
    return cfg.get("user", {}).get("timezone", "UTC")
