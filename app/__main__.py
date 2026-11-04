"""Ponto de entrada da aplicação desktop."""

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow
from app.paths import resource_root


def main() -> None:
    """Inicializa o loop Qt na thread principal."""
    if "--update-helper" in sys.argv[1:]:
        from app.update_helper import main as update_helper_main

        helper_args = [argument for argument in sys.argv[1:] if argument != "--update-helper"]
        raise SystemExit(update_helper_main(helper_args))

    application = QApplication.instance() or QApplication(sys.argv)
    icon_path = resource_root() / "icon" / "logo.ico"
    if icon_path.is_file():
        application.setWindowIcon(QIcon(str(icon_path)))
    window = MainWindow()
    window.show()
    sys.exit(application.exec())


if __name__ == "__main__":
    main()
