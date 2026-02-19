from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import QFileSystemWatcher, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

LOGGER = logging.getLogger("viewer")


class BankViewerWindow(QMainWindow):
    def __init__(self, export_file: Path, debug: bool = False):
        super().__init__()
        self.export_file = export_file
        self.debug = debug

        self.setWindowTitle("RuneLite Bank Memory Viewer")
        self.resize(700, 500)

        central = QWidget(self)
        layout = QVBoxLayout(central)

        self.status_label = QLabel("Waiting for export data...")
        self.summary_label = QLabel("Total items: 0")

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["itemId", "qty"])
        self.table.horizontalHeader().setStretchLastSection(True)

        layout.addWidget(self.status_label)
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

        self.load_data(initial=True)

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
        if not self.export_file.exists():
            self.status_label.setText(
                f"Export not found yet: {self.export_file}. Start exporter first."
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
            self.table.setRowCount(0)
            return

        entries = self._normalize_current(current)
        self.table.setRowCount(len(entries))

        total_qty = 0
        for row, entry in enumerate(entries):
            item_id = entry.get("itemId", entry.get("id", "?"))
            qty = entry.get("qty", entry.get("quantity", 0))
            try:
                total_qty += int(qty)
            except (TypeError, ValueError):
                pass

            self.table.setItem(row, 0, QTableWidgetItem(str(item_id)))
            self.table.setItem(row, 1, QTableWidgetItem(str(qty)))

        self.summary_label.setText(f"Total items: {total_qty}")

        if initial and self.debug:
            LOGGER.debug("Loaded %s entries from %s", len(entries), self.export_file)

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
        required=True,
        help="Folder containing exported JSON file.",
    )
    parser.add_argument(
        "--output-name",
        default="aashiq-bank.json",
        help="Export JSON filename (default: aashiq-bank.json)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logs.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    export_file = Path(args.shared_folder).expanduser() / args.output_name
    app = QApplication([])
    win = BankViewerWindow(export_file=export_file, debug=args.debug)
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
