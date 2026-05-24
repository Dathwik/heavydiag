# Entry point for the heavydiag application
"""
main.py
-------
HeavyDiag entry point.

Run with:
    python -m heavydiag.main
    OR
    python heavydiag/main.py
"""

import sys
import os

# Ensure the project root is on the path when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from heavydiag.ui.main_window import MainWindow


def main():
    # Enable High DPI scaling for crisp rendering on 4K/Retina displays
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("HeavyDiag")
    app.setOrganizationName("PACCAR Portfolio Project")

    # Base font
    font = QFont("Segoe UI", 11)
    app.setFont(font)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()