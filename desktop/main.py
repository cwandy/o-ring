"""O-Ring gland design program: desktop (Qt) user interface.

Run:  uv run python desktop/main.py
Windows package: O-Ring.exe starts python\\pythonw.exe desktop\\main.py (no console, no browser).
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for p in (str(HERE), str(ROOT / "src")):
    if p not in sys.path:
        sys.path.insert(0, p)

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QFont, QIcon  # noqa: E402
from PySide6.QtWidgets import (QApplication, QComboBox, QLabel, QMainWindow, QMessageBox, QScrollArea,  # noqa: E402
                               QTabWidget, QToolBar, QWidget)

from oring_designer.i18n import t  # noqa: E402

APP_ICON = HERE / "assets" / "icon.png"


class PageArea(QScrollArea):
    """Scroll area that fits the page to the window while the details are closed (wrapped
    labels would otherwise ask for more height than needed and add a scroll bar)."""

    def __init__(self, page: QWidget):
        super().__init__()
        self.setWidgetResizable(True)
        self.setWidget(page)
        self.setFrameShape(QScrollArea.NoFrame)
        self.page = page
        if hasattr(page, "details_btn"):
            page.details_btn.toggled.connect(lambda *_: self._fit())

    def _fit(self) -> None:
        page = self.page
        details = getattr(page, "details_widget", None)
        if details is not None and not details.isHidden():
            page.setMinimumHeight(0)
            page.setMaximumHeight(16777215)
        else:
            page.setFixedHeight(max(self.viewport().height(), page.minimumSizeHint().height()))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()


def scroll(page: QWidget) -> QScrollArea:
    return PageArea(page)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        from page_calc import CalcPage
        from page_check import CheckPage
        from page_se import SpringPage
        from page_size import SizePage
        from ui import T_LABEL, UNITS, UnitSpin

        self.setWindowTitle(t("app.title"))
        if APP_ICON.exists():
            self.setWindowIcon(QIcon(str(APP_ICON)))
        self.resize(1440, 920)

        bar = QToolBar(t("ui.units"))
        bar.setObjectName("topBar")
        bar.setMovable(False)
        self.addToolBar(bar)
        title = QLabel(f"  ◯  {t('app.title')}")
        title.setObjectName("appTitle")
        bar.addWidget(title)
        spacer = QWidget()
        from PySide6.QtWidgets import QSizePolicy
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bar.addWidget(spacer)
        bar.addWidget(QLabel(f"  {t('ui.length_unit')}: "))
        self.len_box = QComboBox()
        self.len_box.addItems(["mm", "in"])
        bar.addWidget(self.len_box)
        bar.addWidget(QLabel(f"   {t('ui.temp_unit')}: "))
        self.temp_box = QComboBox()
        for k, v in T_LABEL.items():
            self.temp_box.addItem(v, k)
        bar.addWidget(self.temp_box)
        bar.addWidget(QLabel(f"   {t('ui.pressure_unit')}: "))
        self.p_box = QComboBox()
        self.p_box.addItems(["bar", "MPa", "psi"])
        bar.addWidget(self.p_box)
        bar.addWidget(QLabel(f"   {t('ui.T_ref')}: "))
        self.T_ref = UnitSpin("temp", UNITS.T_ref_K)
        self.T_ref.setMaximumWidth(130)
        bar.addWidget(self.T_ref)
        from ui import style_popup
        for c in (self.len_box, self.temp_box, self.p_box):
            style_popup(c)
        self.len_box.currentTextChanged.connect(lambda v: UNITS.set(L=v))
        self.temp_box.currentIndexChanged.connect(lambda *_: UNITS.set(T=self.temp_box.currentData()))
        self.p_box.currentTextChanged.connect(lambda v: UNITS.set(P=v))
        self.T_ref.edited.connect(self._t_ref)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("mainTabs")
        self.tabs.setDocumentMode(True)
        self.pages = [CalcPage(), CheckPage(), SizePage(), SpringPage()]
        for page, key in zip(self.pages, ("ui.page_calc", "ui.page_check", "ui.page_size", "ui.page_se")):
            self.tabs.addTab(scroll(page), t(key))
        self.setCentralWidget(self.tabs)
        UNITS.changed.connect(self._refresh_all)
        self._units = UNITS

    def _t_ref(self) -> None:
        self._units.T_ref_K = self.T_ref.si()
        self._refresh_all()

    def _refresh_all(self) -> None:
        for p in self.pages:
            p.schedule()


def _excepthook(exc_type, exc, tb):  # keep the window alive and show what happened
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    if sys.stderr is not None:
        sys.stderr.write(text)
    box = QMessageBox(QMessageBox.Critical, t("app.title"), t("desktop.unexpected", error=exc))
    box.setDetailedText(text)
    box.exec()


def _log_when_windowless() -> None:
    """pythonw.exe has no console: send output to %LOCALAPPDATA%\\o-ring\\masaustu.log."""
    if sys.stderr is not None and sys.stdout is not None:
        return
    import os
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "o-ring"
    base.mkdir(parents=True, exist_ok=True)
    f = open(base / "masaustu.log", "w", encoding="utf-8", buffering=1)  # noqa: SIM115
    sys.stdout = sys.stderr = f


def main() -> int:
    _log_when_windowless()
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("O-Ring")
    app.setStyle("Fusion")
    from PySide6.QtGui import QColor, QPalette
    pal = app.palette()
    for group in (QPalette.Active, QPalette.Inactive):
        pal.setColor(group, QPalette.Base, QColor("white"))  # active input boxes white on every Windows theme
    pal.setColor(QPalette.Disabled, QPalette.Base, QColor("#e9ecf1"))  # inactive boxes grey
    app.setPalette(pal)
    f = QFont("Segoe UI", 10) if sys.platform == "win32" else app.font()
    app.setFont(f)
    sys.excepthook = _excepthook
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import QSplashScreen

    pm = QPixmap(520, 200)
    pm.fill(Qt.white)
    splash = QSplashScreen(pm)
    splash.showMessage(f"\n\n{t('app.title')}\n\n{t('desktop.starting')}", Qt.AlignCenter, Qt.black)
    splash.show()
    app.processEvents()
    from ui import STYLE

    app.setStyleSheet(STYLE)
    win = MainWindow()
    win.showMaximized()
    splash.finish(win)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
