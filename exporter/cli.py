from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import time
from typing import Any

LOGGER = logging.getLogger("exporter")

BANK_GROUP = "bankMemory"
DEFAULT_POLL_SECONDS = 10


class ExporterError(RuntimeError):
    """Raised when exporter cannot continue."""


@dataclass(slots=True)
class RuneLiteSource:
    profile: str
    config_file: Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m exporter",
        description="Export RuneLite Bank Memory data to a shared JSON file.",
    )
    parser.add_argument(
        "--shared-folder",
        required=True,
        help="Folder where export JSON should be written.",
    )
    parser.add_argument(
        "--output-name",
        default="aashiq-bank.json",
        help="Output JSON file name (default: aashiq-bank.json)",
    )
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=DEFAULT_POLL_SECONDS,
        help="Polling interval when watchdog is unavailable (default: 10)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging and print keys found in config file.",
    )
    return parser


def parse_properties(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("!"):
                continue
            match = re.split(r"(?<!\\)[=:]", line, maxsplit=1)
            if len(match) == 2:
                key, value = match
            else:
                key, value = line, ""
            key = key.strip().replace("\\=", "=").replace("\\:", ":")
            value = value.strip()
            data[key] = value
    return data


def profile_name_from_path(path: Path, runelite_root: Path) -> str:
    try:
        rel = path.relative_to(runelite_root)
        return str(rel.parent)
    except ValueError:
        return str(path.parent)


def find_candidate_properties(runelite_root: Path) -> list[Path]:
    if not runelite_root.exists():
        return []
    return sorted(runelite_root.glob("profiles2/**/*.properties"))


def find_bankmemory_source(runelite_root: Path, debug: bool = False) -> RuneLiteSource:
    candidates = find_candidate_properties(runelite_root)
    if not candidates:
        raise ExporterError(
            f"No profile .properties files found under {runelite_root / 'profiles2'}"
        )

    matches: list[tuple[Path, dict[str, str]]] = []
    for file in candidates:
        props = parse_properties(file)
        has_current = f"{BANK_GROUP}.currentList" in props
        if has_current:
            matches.append((file, props))

    if not matches:
        raise ExporterError(
            "Could not find any RuneLite profile properties with bankMemory.currentList. "
            "Open bank in-game with RuneLite + Bank Memory plugin enabled."
        )

    matches.sort(key=lambda item: item[0].stat().st_mtime, reverse=True)
    selected_path, selected_props = matches[0]
    if debug:
        present = [k for k in selected_props.keys() if k.startswith(f"{BANK_GROUP}.")]
        LOGGER.debug("Using config file: %s", selected_path)
        LOGGER.debug("bankMemory keys present: %s", present)

    profile = profile_name_from_path(selected_path, runelite_root)
    return RuneLiteSource(profile=profile, config_file=selected_path)


def parse_json_value(raw: str | None, default: Any) -> Any:
    if raw is None or raw == "":
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExporterError(f"Failed to parse JSON value: {exc}") from exc


def _parse_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def parse_item_data(item_data: str) -> list[dict[str, int]]:
    tokens = [token.strip() for token in item_data.split(",") if token.strip()]
    if len(tokens) % 2 != 0:
        raise ExporterError(
            "Invalid bankMemory itemData: expected itemId,qty pairs but got odd token count"
        )

    items: list[dict[str, int]] = []
    for index in range(0, len(tokens), 2):
        item_id = _parse_int(tokens[index])
        qty = _parse_int(tokens[index + 1])
        items.append({"itemId": item_id, "qty": qty})
    return items


def parse_current_entries(current: Any, name_map: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(current, list):
        return []

    parsed_entries: list[dict[str, Any]] = []
    for entry in current:
        if not isinstance(entry, dict):
            continue
        account_identifier = str(entry.get("accountIdentifier", ""))
        account_name = name_map.get(account_identifier, account_identifier)
        item_data = entry.get("itemData", "")
        parsed_entries.append(
            {
                "id": _parse_int(entry.get("id")),
                "worldType": str(entry.get("worldType", "")),
                "dateTimeString": str(entry.get("dateTimeString", "")),
                "accountIdentifier": account_identifier,
                "accountName": str(account_name),
                "items": parse_item_data(str(item_data)),
            }
        )
    return parsed_entries


def default_current_selection(all_current_parsed: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not all_current_parsed:
        return None

    account_order: list[str] = []
    for entry in all_current_parsed:
        identifier = entry.get("accountIdentifier", "")
        if identifier not in account_order:
            account_order.append(identifier)

    selected_account = account_order[0] if account_order else ""
    account_entries = [
        entry
        for entry in all_current_parsed
        if entry.get("accountIdentifier", "") == selected_account
    ]

    default_world_entries = [
        entry for entry in account_entries if entry.get("worldType") == "DEFAULT"
    ]
    candidates = default_world_entries or account_entries

    def _sort_key(entry: dict[str, Any]) -> tuple[int, str]:
        return (_parse_int(entry.get("id")), str(entry.get("dateTimeString", "")))

    return max(candidates, key=_sort_key) if candidates else None


def build_export_payload(source: RuneLiteSource, props: dict[str, str]) -> dict[str, Any]:
    current = parse_json_value(props.get(f"{BANK_GROUP}.currentList"), None)
    snapshots = parse_json_value(props.get(f"{BANK_GROUP}.snapshotList"), [])
    name_map = parse_json_value(props.get(f"{BANK_GROUP}.nameMap"), {})
    all_current_parsed = parse_current_entries(current, name_map)
    current_parsed = default_current_selection(all_current_parsed)
    return {
        "exportedAt": datetime.now(timezone.utc).isoformat(),
        "source": {
            "os": "macOS",
            "profile": source.profile,
            "configFile": str(source.config_file),
        },
        "current": current,
        "allCurrentParsed": all_current_parsed,
        "currentParsed": current_parsed,
        "snapshots": snapshots,
        "nameMap": name_map,
    }


def write_export_file(payload: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
    temp_path.replace(output_path)


class ExportLoop:
    def __init__(self, runelite_root: Path, output_path: Path, poll_seconds: int, debug: bool):
        self.runelite_root = runelite_root
        self.output_path = output_path
        self.poll_seconds = max(1, poll_seconds)
        self.debug = debug
        self._source: RuneLiteSource | None = None
        self._last_mtime: float | None = None

    def _refresh_source(self) -> RuneLiteSource:
        source = find_bankmemory_source(self.runelite_root, debug=self.debug)
        if self._source is None or source.config_file != self._source.config_file:
            LOGGER.info("Selected RuneLite config file: %s", source.config_file)
        self._source = source
        return source

    def export_once(self) -> None:
        source = self._source or self._refresh_source()
        if not source.config_file.exists():
            LOGGER.warning("Config file disappeared, rescanning...")
            source = self._refresh_source()

        props = parse_properties(source.config_file)
        if self.debug:
            keys = [k for k in props if k.startswith(f"{BANK_GROUP}.")]
            LOGGER.debug("Current bankMemory keys present: %s", keys)

        payload = build_export_payload(source, props)
        write_export_file(payload, self.output_path)
        LOGGER.info("Exported bank data to %s", self.output_path)

    def run_polling(self) -> None:
        LOGGER.info("Starting polling mode every %s seconds", self.poll_seconds)
        self._refresh_source()
        while True:
            try:
                if self._source is None:
                    self._refresh_source()
                assert self._source is not None
                mtime = self._source.config_file.stat().st_mtime if self._source.config_file.exists() else None
                if mtime is None:
                    self._refresh_source()
                    self.export_once()
                elif self._last_mtime is None or mtime > self._last_mtime:
                    self._last_mtime = mtime
                    self.export_once()
            except ExporterError as exc:
                LOGGER.error("%s", exc)
                self._source = None
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("Unexpected exporter error: %s", exc)
            time.sleep(self.poll_seconds)

    def run_watchdog(self) -> None:
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("watchdog unavailable (%s); falling back to polling.", exc)
            self.run_polling()
            return

        loop = self

        class Handler(FileSystemEventHandler):
            def on_any_event(self, event):  # type: ignore[override]
                if event.is_directory:
                    return
                path = Path(event.src_path)
                if path.suffix != ".properties":
                    return
                try:
                    loop._refresh_source()
                    if loop._source and path.resolve() == loop._source.config_file.resolve():
                        loop.export_once()
                except ExporterError as exc:
                    LOGGER.error("%s", exc)
                except Exception as exc:  # noqa: BLE001
                    LOGGER.exception("Unexpected watchdog handler error: %s", exc)

        self._refresh_source()
        self.export_once()

        observer = Observer()
        profiles_dir = self.runelite_root / "profiles2"
        observer.schedule(Handler(), str(profiles_dir), recursive=True)
        observer.start()
        LOGGER.info("watchdog started on %s", profiles_dir)

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            LOGGER.info("Stopping exporter...")
        finally:
            observer.stop()
            observer.join(timeout=5)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    output_path = Path(args.shared_folder).expanduser() / args.output_name
    runelite_root = Path.home() / ".runelite"

    LOGGER.info("RuneLite root: %s", runelite_root)
    LOGGER.info("Output file: %s", output_path)

    loop = ExportLoop(
        runelite_root=runelite_root,
        output_path=output_path,
        poll_seconds=args.poll_seconds,
        debug=args.debug,
    )

    try:
        loop.run_watchdog()
    except ExporterError as exc:
        LOGGER.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        LOGGER.info("Exporter stopped by user.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
