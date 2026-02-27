#!/usr/bin/env python3
"""
DM Puppeteer - Animated NPC Portrait Overlay for D&D Streaming for my friend Raph

Usage:
    python run.py
"""

import sys
from PyQt6.QtWidgets import QApplication


def main():
    # Create Qt application FIRST - required before any QPixmap/QFont usage
    app = QApplication(sys.argv)
    app.setApplicationName("DM Puppeteer")
    app.setQuitOnLastWindowClosed(False)

    # Import after QApplication exists
    from dm_puppeteer.models import AppState
    from dm_puppeteer.app_window import AppWindow

    # Load saved state
    state = AppState.load()

    # Create and show the control panel
    window = AppWindow(state)
    window.show()

    # Clean shutdown
    app.aboutToQuit.connect(window.shutdown)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
