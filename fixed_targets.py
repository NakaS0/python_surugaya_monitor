"""`.env` からチェック対象セットを読み込む。"""

from __future__ import annotations

import os
from pathlib import Path

from scraper import DEFAULT_BASE_URL

MAX_TARGET_SETS = 4
TARGET_SET_LABELS = {
    1: "本番用",
    2: "テスト用",
    3: "予備3",
    4: "予備4",
}


def _read_dotenv(path: str = ".env") -> dict[str, str]:
    env_map: dict[str, str] = {}
    dotenv_path = Path(path)
    if not dotenv_path.exists():
        return env_map

    for raw_line in dotenv_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        env_map[key] = value
    return env_map


def _env(key: str, default: str = "") -> str:
    value = os.environ.get(key, "").strip()
    if value:
        return value
    return _read_dotenv().get(key, default)


def default_active_target_set() -> int:
    raw = _env("ACTIVE_TARGET_SET", "1").strip()
    if raw.isdigit():
        value = int(raw)
        if 1 <= value <= MAX_TARGET_SETS:
            return value
    return 1


def available_target_sets() -> list[dict[str, object]]:
    return [
        {"value": index, "label": TARGET_SET_LABELS.get(index, f"セット{index}")}
        for index in range(1, MAX_TARGET_SETS + 1)
    ]


def _default_specs() -> list[tuple[str, str, str]]:
    return [
        ("default", "イラストカード", DEFAULT_BASE_URL),
        ("kobayashi", "小林さんちのメイドラゴン", ""),
        ("fanza_kuji", "FANZAオンラインくじ", ""),
        ("shining_musume", "シャイニング娘", ""),
    ]


def _target_keys(set_no: int, slot_no: int) -> tuple[str, str]:
    return (f"SET_{set_no}_TARGET_{slot_no}_NAME", f"SET_{set_no}_TARGET_{slot_no}_URL")


def _legacy_target_keys(slot_no: int) -> tuple[str, str]:
    return (f"TARGET_{slot_no}_NAME", f"TARGET_{slot_no}_URL")


def get_targets(active_set: int | None = None) -> list[dict[str, str]]:
    set_no = active_set or default_active_target_set()
    if not 1 <= set_no <= MAX_TARGET_SETS:
        set_no = default_active_target_set()

    targets: list[dict[str, str]] = []
    for slot_no, (target_id, default_name, default_url) in enumerate(_default_specs(), start=1):
        name_key, url_key = _target_keys(set_no, slot_no)
        name = _env(name_key, default_name).strip()
        url = _env(url_key, default_url).strip()

        if set_no == 1 and not url:
            legacy_name_key, legacy_url_key = _legacy_target_keys(slot_no)
            name = _env(legacy_name_key, name).strip()
            url = _env(legacy_url_key, url).strip()

        if not url:
            continue
        targets.append({"id": target_id, "name": name, "url": url})

    if not targets:
        raise RuntimeError(
            "No check targets configured. Set ACTIVE_TARGET_SET and SET_n_TARGET_x_URL values in .env."
        )
    return targets
