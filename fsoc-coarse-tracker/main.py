"""Entry point: launches the GUI (Section 8.2)."""
from __future__ import annotations

import os
import sys

import yaml
from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.main_window import MainWindow


def load_config(path: str = None) -> dict:
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "default_config.yaml")
    with open(path) as f:
        return yaml.safe_load(f)


def main():
    config = load_config()
    app = QApplication(sys.argv)
    window = MainWindow(config)
    window.resize(1400, 800)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
