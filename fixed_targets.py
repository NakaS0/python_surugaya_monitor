import os
from pathlib import Path

from scraper import DEFAULT_BASE_URL


def _read_dotenv(path: str = ".env") -> dict[str, str]:
    env_map: dict[str, str] = {}
    p = Path(path)
    if not p.exists():
        return env_map

    for raw_line in p.read_text(encoding="utf-8-sig").splitlines():
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


_DOTENV = _read_dotenv()


def _env(key: str, default: str = "") -> str:
    if key in os.environ and os.environ[key]:
        return os.environ[key]
    return _DOTENV.get(key, default)


def _build_targets() -> list[dict[str, str]]:
    specs = [
        ("default", "TARGET_1_NAME", "TARGET_1_URL", "監視対象1", DEFAULT_BASE_URL),
        ("kobayashi", "TARGET_2_NAME", "TARGET_2_URL", "監視対象2", ""),
        ("fanza_kuji", "TARGET_3_NAME", "TARGET_3_URL", "監視対象3", ""),
        ("shining_musume", "TARGET_4_NAME", "TARGET_4_URL", "監視対象4", ""),
    ]
    targets: list[dict[str, str]] = []
    for tid, nkey, ukey, default_name, default_url in specs:
        name = _env(nkey, default_name).strip()
        url = _env(ukey, default_url).strip()
        if not url:
            continue
        targets.append({"id": tid, "name": name, "url": url})

    if not targets:
        raise RuntimeError(
            "No monitoring targets configured. Set TARGET_1_URL (or others) in .env."
        )
    return targets


FIXED_TARGETS = _build_targets()
