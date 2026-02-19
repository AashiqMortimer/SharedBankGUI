from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

LOGGER = logging.getLogger("viewer.item_mapping")

MAPPING_URL = "https://prices.runescape.wiki/api/v1/osrs/mapping"
USER_AGENT = "SharedBankGUI/1.0 (item-mapping-cache)"


class ItemMappingUnavailableError(RuntimeError):
    """Raised when item mapping cannot be downloaded or loaded from cache."""


def get_item_mapping_cache_path() -> Path:
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return base / "SharedBankGUI" / "item_mapping.json"
    return Path.home() / ".cache" / "sharedbankgui" / "item_mapping.json"


def load_item_mapping(force_refresh: bool = False) -> dict[int, str]:
    cache_path = get_item_mapping_cache_path()

    if not force_refresh:
        cached = _read_mapping_cache(cache_path)
        if cached:
            return cached

    try:
        mapping = _download_item_mapping()
        _write_mapping_cache(cache_path, mapping)
        return mapping
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Failed to download item mapping: %s", exc)
        cached = _read_mapping_cache(cache_path)
        if cached:
            return cached
        raise ItemMappingUnavailableError("Unable to load item mapping") from exc


def _download_item_mapping() -> dict[int, str]:
    request = Request(
        MAPPING_URL,
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except URLError as exc:
        raise RuntimeError(f"Network error downloading item mapping: {exc}") from exc

    if not isinstance(payload, list):
        raise RuntimeError("Unexpected mapping response format")

    mapping: dict[int, str] = {}
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        item_id = entry.get("id")
        name = entry.get("name")
        if isinstance(item_id, int) and isinstance(name, str) and name:
            mapping[item_id] = name
    if not mapping:
        raise RuntimeError("Downloaded mapping was empty")
    return mapping


def _read_mapping_cache(cache_path: Path) -> dict[int, str]:
    if not cache_path.exists():
        return {}

    try:
        payload: Any = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.warning("Failed to read cached item mapping from %s: %s", cache_path, exc)
        return {}

    if not isinstance(payload, dict):
        return {}

    mapping: dict[int, str] = {}
    for item_id, name in payload.items():
        try:
            parsed_id = int(item_id)
        except (TypeError, ValueError):
            continue
        if isinstance(name, str) and name:
            mapping[parsed_id] = name
    return mapping


def _write_mapping_cache(cache_path: Path, mapping: dict[int, str]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    serializable = {str(item_id): name for item_id, name in mapping.items()}
    cache_path.write_text(json.dumps(serializable, ensure_ascii=False), encoding="utf-8")
