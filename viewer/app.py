from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import threading
from typing import Any

from PySide6.QtCore import QFileSystemWatcher, QSettings, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .item_mapping import ItemMappingUnavailableError, load_item_mapping

LOGGER = logging.getLogger("viewer")
DEFAULT_OUTPUT_NAME = "aashiq-bank.json"
CONFIG_RELATIVE_PATH = Path("SharedBankGUI") / "config.json"


class BankViewerWindow(QMainWindow):
    def __init__(self, export_file: Path, shared_folder: Path, output_name: str, debug: bool = False):
        super().__init__()
        self.export_file = export_file
        self.shared_folder = shared_folder
        self.output_name = output_name
        self.debug = debug
        self.settings = QSettings("SharedBankGUI", "BankViewer")

        self.item_mapping: dict[int, str] = {}
        self._mapping_warning: str | None = None
        self._active_entries: list[dict[str, Any]] = []
        self._load_item_mapping()

        self.setWindowTitle("RuneLite Bank Memory Viewer")
        self.resize(800, 560)

        central = QWidget(self)
        layout = QVBoxLayout(central)

        self.status_label = QLabel("Waiting for export data...")
        self.mapping_banner = QLabel("")
        self.mapping_banner.setStyleSheet("color: #c62828;")
        self.mapping_banner.setVisible(False)

        self.selection_label = QLabel("Save: -")
        self.selection_combo = QComboBox()
        self.selection_combo.currentIndexChanged.connect(self._on_selection_changed)

        self.auto_export_checkbox = QCheckBox("Auto-export on launch")
        auto_export_enabled = self.settings.value("auto_export_on_launch", True, type=bool)
        self.auto_export_checkbox.setChecked(auto_export_enabled)
        self.auto_export_checkbox.toggled.connect(self._on_toggle_auto_export)

        actions_row = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search by item name...")
        self.search_box.textChanged.connect(self._apply_table_filter)

        self.refresh_mapping_btn = QPushButton("Refresh item names")
        self.refresh_mapping_btn.clicked.connect(self._on_refresh_item_names)
        actions_row.addWidget(self.search_box)
        actions_row.addWidget(self.refresh_mapping_btn)

        self.summary_label = QLabel("Total items: 0")
        self._current_options: list[dict[str, Any]] = []
        self._pending_payload: dict[str, Any] | None = None

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Name", "itemId", "qty"])
        self.table.horizontalHeader().setStretchLastSection(True)

        layout.addWidget(self.status_label)
        layout.addWidget(self.mapping_banner)
        layout.addWidget(self.selection_label)
        layout.addWidget(self.selection_combo)
        layout.addWidget(self.auto_export_checkbox)
        layout.addLayout(actions_row)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.table)
        self.setCentralWidget(central)

        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self._on_file_changed)
        self.watcher.directoryChanged.connect(self._on_directory_changed)

        parent_dir = str(self.export_file.parent)
        if self.export_file.parent.exists():
            self.watcher.addPath(parent_dir)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.timeout.connect(self.load_data)

        if auto_export_enabled:
            self._run_one_shot_export()

        self.load_data(initial=True)

    def _on_toggle_auto_export(self, checked: bool) -> None:
        self.settings.setValue("auto_export_on_launch", checked)

    def _run_one_shot_export(self) -> None:
        if getattr(sys, "frozen", False):
            self._run_embedded_exporter()
            return

        cmd = [
            sys.executable,
            "-m",
            "exporter",
            "--shared-folder",
            str(self.shared_folder),
            "--output-name",
            self.output_name,
            "--once",
        ]
        if self.debug:
            cmd.append("--debug")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            LOGGER.warning("Failed to run one-shot exporter: %s", exc)
            return

        if result.returncode != 0:
            LOGGER.warning(
                "One-shot exporter exited with code %s: %s",
                result.returncode,
                result.stderr.strip(),
            )

    def _run_embedded_exporter(self) -> None:
        def _run() -> None:
            try:
                from exporter.cli import main as exporter_main
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Embedded exporter is unavailable: %s", exc)
                return

            args = [
                "--shared-folder",
                str(self.shared_folder),
                "--output-name",
                self.output_name,
                "--once",
            ]
            if self.debug:
                args.append("--debug")

            try:
                exit_code = exporter_main(args)
                if exit_code != 0:
                    LOGGER.warning("Embedded one-shot exporter exited with code %s", exit_code)
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Embedded one-shot exporter failed: %s", exc)

        threading.Thread(target=_run, name="embedded-exporter", daemon=True).start()

    def _load_item_mapping(self, force_refresh: bool = False) -> None:
        try:
            self.item_mapping = load_item_mapping(force_refresh=force_refresh)
            self._mapping_warning = None
        except ItemMappingUnavailableError:
            self.item_mapping = {}
            self._mapping_warning = (
                "Unable to download item names and no cache was found. "
                "Showing Unknown (id) labels."
            )

    def _on_refresh_item_names(self) -> None:
        self._load_item_mapping(force_refresh=True)
        self._update_mapping_banner()
        if self._pending_payload is not None:
            self._render_selected_save(self._get_selected_save(self._pending_payload))

    def _update_mapping_banner(self) -> None:
        if self._mapping_warning:
            self.mapping_banner.setText(self._mapping_warning)
            self.mapping_banner.setVisible(True)
            return
        self.mapping_banner.setText("")
        self.mapping_banner.setVisible(False)

    def _on_file_changed(self, _path: str) -> None:
        self.refresh_timer.start(200)

    def _on_directory_changed(self, _path: str) -> None:
        self.refresh_timer.start(200)

    def _ensure_watch_file(self) -> None:
        current_paths = set(self.watcher.files())
        export_path = str(self.export_file)
        if self.export_file.exists() and export_path not in current_paths:
            self.watcher.addPath(export_path)

    def load_data(self, initial: bool = False) -> None:
        self._ensure_watch_file()
        self._update_mapping_banner()

        if not self.export_file.exists():
            self.status_label.setText(
                f"Export not found yet: {self.export_file}."
            )
            self.summary_label.setText("Total items: 0")
            self.table.setRowCount(0)
            return

        try:
            payload = json.loads(self.export_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            self.status_label.setText(f"Invalid JSON: {exc}")
            if self.debug:
                LOGGER.exception("Failed to parse %s", self.export_file)
            return
        except OSError as exc:
            self.status_label.setText(f"Could not read file: {exc}")
            return

        current = payload.get("current")
        exported_at = payload.get("exportedAt", "unknown")
        self.status_label.setText(f"Last export: {exported_at}")

        if current is None:
            self.summary_label.setText("No bank data yet – open bank in-game")
            self.selection_label.setText("Save: -")
            self.selection_combo.clear()
            self.table.setRowCount(0)
            return

        self._pending_payload = payload
        self._refresh_selection_options(payload)
        selected = self._get_selected_save(payload)
        self._render_selected_save(selected)

        if initial and self.debug:
            LOGGER.debug("Loaded selected bank save from %s", self.export_file)

    def _on_selection_changed(self, _index: int) -> None:
        if self._pending_payload is None:
            return
        self._render_selected_save(self._get_selected_save(self._pending_payload))

    def _apply_table_filter(self) -> None:
        filter_text = self.search_box.text().strip().lower()
        filtered_entries: list[dict[str, Any]] = []

        if not filter_text:
            filtered_entries = self._active_entries
        else:
            for entry in self._active_entries:
                name = entry.get("name", "")
                if isinstance(name, str) and filter_text in name.lower():
                    filtered_entries.append(entry)

        self.table.setRowCount(len(filtered_entries))
        total_qty = 0

        for row, entry in enumerate(filtered_entries):
            item_id = entry.get("itemId", "?")
            qty = entry.get("qty", 0)
            name = entry.get("name", f"Unknown ({item_id})")

            try:
                total_qty += int(qty)
            except (TypeError, ValueError):
                pass

            self.table.setItem(row, 0, QTableWidgetItem(str(name)))
            self.table.setItem(row, 1, QTableWidgetItem(str(item_id)))
            self.table.setItem(row, 2, QTableWidgetItem(str(qty)))

        self.summary_label.setText(f"Total items: {total_qty}")

    def _refresh_selection_options(self, payload: dict[str, Any]) -> None:
        entries = payload.get("allCurrentParsed")
        if not isinstance(entries, list):
            entries = []

        self._current_options = [entry for entry in entries if isinstance(entry, dict)]
        previous_key = self.selection_combo.currentData()
        self.selection_combo.blockSignals(True)
        self.selection_combo.clear()

        for entry in self._current_options:
            label = self._selection_label(entry)
            key = str(entry.get("id", ""))
            self.selection_combo.addItem(label, key)

        if self.selection_combo.count() == 0:
            self.selection_combo.blockSignals(False)
            return

        matched_index = self.selection_combo.findData(previous_key)
        self.selection_combo.setCurrentIndex(matched_index if matched_index >= 0 else 0)
        self.selection_combo.blockSignals(False)

    def _get_selected_save(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        if self.selection_combo.count() == 0:
            selected = payload.get("currentParsed")
            return selected if isinstance(selected, dict) else None

        selected_key = self.selection_combo.currentData()
        for entry in self._current_options:
            if str(entry.get("id", "")) == str(selected_key):
                return entry

        selected = payload.get("currentParsed")
        return selected if isinstance(selected, dict) else None

    def _render_selected_save(self, selected: dict[str, Any] | None) -> None:
        if not isinstance(selected, dict):
            self.selection_label.setText("Save: -")
            self.summary_label.setText("Total items: 0")
            self.table.setRowCount(0)
            self._active_entries = []
            return

        account_name = selected.get("accountName", "unknown")
        world_type = selected.get("worldType", "unknown")
        date_string = selected.get("dateTimeString", "unknown")
        self.selection_label.setText(
            f"Viewing: {account_name} | {world_type} | {date_string}"
        )

        entries = self._normalize_current(selected.get("items"))
        normalized_entries: list[dict[str, Any]] = []

        for entry in entries:
            raw_item_id = entry.get("itemId", entry.get("id", "?"))
            item_id: int | str = raw_item_id
            try:
                item_id = int(raw_item_id)
            except (TypeError, ValueError):
                pass

            qty = entry.get("qty", entry.get("quantity", 0))
            name = self.item_mapping.get(item_id) if isinstance(item_id, int) else None
            if not name:
                name = f"Unknown ({item_id})"

            normalized_entries.append({"name": name, "itemId": item_id, "qty": qty})

        self._active_entries = normalized_entries
        self._apply_table_filter()

    @staticmethod
    def _selection_label(entry: dict[str, Any]) -> str:
        account_name = entry.get("accountName", entry.get("accountIdentifier", ""))
        world_type = entry.get("worldType", "")
        date_string = entry.get("dateTimeString", "")
        return f"{account_name} ({world_type}) - {date_string}"

    @staticmethod
    def _normalize_current(current: Any) -> list[dict[str, Any]]:
        if isinstance(current, list):
            return [c for c in current if isinstance(c, dict)]
        if isinstance(current, dict):
            for key in ("items", "itemList", "entries"):
                maybe = current.get(key)
                if isinstance(maybe, list):
                    return [c for c in maybe if isinstance(c, dict)]
            return [current]
        return []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m viewer",
        description="View exported RuneLite bank memory JSON.",
    )
    parser.add_argument(
        "--shared-folder",
        help="Folder containing exported JSON file.",
    )
    parser.add_argument(
        "--output-name",
        default=DEFAULT_OUTPUT_NAME,
        help=f"Export JSON filename (default: {DEFAULT_OUTPUT_NAME})",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logs.",
    )
    return parser


def _config_path() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / CONFIG_RELATIVE_PATH

    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / CONFIG_RELATIVE_PATH

    return Path.home() / ".config" / CONFIG_RELATIVE_PATH


def _load_config(config_path: Path) -> dict[str, Any] | None:
    if not config_path.exists():
        return None

    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        LOGGER.warning("Ignoring unreadable config file: %s", config_path)
        return None

    if not isinstance(payload, dict):
        return None

    return payload


def _save_config(config_path: Path, shared_folder: Path, output_name: str) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "shared_folder": str(shared_folder),
        "output_name": output_name,
    }
    config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _auto_detect_shared_folder() -> Path | None:
    home = Path.home()
    userprofile = Path(os.environ.get("USERPROFILE", str(home)))
    candidates = [
        home / "Library" / "CloudStorage" / "Dropbox" / "OSRS Bank Share",
        home / "Dropbox" / "OSRS Bank Share",
        userprofile / "Dropbox" / "OSRS Bank Share",
        userprofile / "OneDrive" / "OSRS Bank Share",
    ]

    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def _select_shared_folder_via_dialog() -> Path | None:
    selected = QFileDialog.getExistingDirectory(
        None,
        "Select your shared OSRS Bank folder",
        str(Path.home()),
    )
    if not selected:
        return None
    return Path(selected).expanduser()


def _resolve_paths(args: argparse.Namespace) -> tuple[Path, str] | None:
    if args.shared_folder:
        shared_folder = Path(args.shared_folder).expanduser()
        return shared_folder, args.output_name

    config_path = _config_path()
    config = _load_config(config_path)
    if config:
        configured_folder = config.get("shared_folder")
        if isinstance(configured_folder, str) and configured_folder.strip():
            configured_path = Path(configured_folder).expanduser()
            if configured_path.exists() and configured_path.is_dir():
                output_name = config.get("output_name")
                if not isinstance(output_name, str) or not output_name.strip():
                    output_name = DEFAULT_OUTPUT_NAME
                return configured_path, output_name

    detected = _auto_detect_shared_folder()
    if detected is not None:
        _save_config(config_path, detected, args.output_name)
        return detected, args.output_name

    selected_folder = _select_shared_folder_via_dialog()
    if selected_folder is None:
        QMessageBox.information(
            None,
            "Shared folder required",
            "No shared folder was selected. The app will now exit.",
        )
        return None

    _save_config(config_path, selected_folder, args.output_name)
    return selected_folder, args.output_name


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    app = QApplication([])
    resolved = _resolve_paths(args)
    if resolved is None:
        return 1

    shared_folder, output_name = resolved
    export_file = shared_folder / output_name

    win = BankViewerWindow(
        export_file=export_file,
        shared_folder=shared_folder,
        output_name=output_name,
        debug=args.debug,
    )
    win.show()

    if args.debug:
        LOGGER.debug("Watching export file: %s", export_file)

    try:
        return app.exec()
    except Exception as exc:  # noqa: BLE001
        QMessageBox.critical(None, "Viewer Error", str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
