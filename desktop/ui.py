"""Shared Qt widgets of the desktop UI: unit-aware inputs, ISO 286 tolerance editor, result
cards, status table, schematic view and matplotlib canvas.

All values are held in SI (m, K, Pa); widgets show and accept the units chosen in the
toolbar (``UNITS``) and convert when the unit changes, so a page never re-reads its inputs.
"""

from __future__ import annotations

import math
from functools import lru_cache

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from PySide6.QtCore import QByteArray, QObject, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFrame, QGridLayout,
                               QGroupBox, QHBoxLayout, QHeaderView, QLabel, QSizePolicy, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from oring_designer import fits, units
from oring_designer.checks import CheckResult, Status
from oring_designer.i18n import render_check, t
from oring_designer.loader import Dataset, load_dataset
from oring_designer.viz.schematic import gland_schematic

STATUS_STYLE = {"PASS": ("✔", "#cdebcd"), "WARN": ("⚠", "#fde3a7"), "FAIL": ("✖", "#f4c7c7")}
T_LABEL = {"degC": "°C", "K": "K", "degF": "°F"}


@lru_cache(maxsize=1)
def dataset() -> Dataset:
    return load_dataset()


# --------------------------------------------------------------------------- units
class Units(QObject):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.L, self.T, self.P = "mm", "degC", "bar"
        self.T_ref_K = 293.15

    def set(self, L: str | None = None, T: str | None = None, P: str | None = None) -> None:
        self.L, self.T, self.P = L or self.L, T or self.T, P or self.P
        self.changed.emit()

    @property
    def T_label(self) -> str:
        return T_LABEL[self.T]

    @property
    def nd(self) -> int:
        return 3 if self.L == "mm" else 4

    def num_L(self, x_m: float | None, tol: float | tuple[float, float] | None = None) -> str | None:
        """Length number in the display unit (no unit text); ``tol`` = ±value or (lower, upper)."""
        if x_m is None:
            return None
        nd = self.nd
        txt = f"{units.length_from_m(x_m, self.L):.{nd}f}"
        if isinstance(tol, tuple):
            lo, hi = (units.length_from_m(v, self.L) for v in tol)
            if abs(lo + hi) < 1e-12 and hi > 0:
                txt += f" ±{hi:.{nd}f}"
            elif lo or hi:
                txt += f" {hi:+.{nd}f}/{lo:+.{nd}f}"
        elif tol:
            txt += f" ±{units.length_from_m(tol, self.L):.{nd}f}"
        return txt

    def fmt_L(self, x_m: float) -> str:
        return f"{self.num_L(x_m)} {self.L}"

    def fmt_T(self, T_K: float) -> str:
        return f"{units.temperature_from_K(T_K, self.T):.1f} {self.T_label}"

    def fmt_p(self, p_Pa: float) -> str:
        return f"{units.pressure_from_Pa(p_Pa, self.P):.3g} {self.P}"


UNITS = Units()


# --------------------------------------------------------------------------- inputs
class UnitSpin(QDoubleSpinBox):
    """Number input holding an SI value; ``kind`` = length | temp | dtemp | pressure | plain."""

    edited = Signal()

    def __init__(self, kind: str, value_si: float, signed: bool = False, plain_range=(0.0, 1e6),
                 decimals: int = 3, step: float = 1.0, parent=None):
        super().__init__(parent)
        self.kind, self.signed, self._si = kind, signed, float(value_si)
        self._plain = (plain_range, decimals, step)
        self.setKeyboardTracking(False)
        self.setAlignment(Qt.AlignRight)
        self.setMinimumWidth(110)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._refresh()
        self.valueChanged.connect(self._on_value)
        if kind != "plain":
            UNITS.changed.connect(self._refresh)

    # conversions
    def _to_si(self, v: float) -> float:
        k = self.kind
        if k == "length":
            return units.length_to_m(v, UNITS.L)
        if k == "temp":
            return units.temperature_to_K(v, UNITS.T)
        if k == "dtemp":
            return v * (5 / 9 if UNITS.T == "degF" else 1.0)
        if k == "pressure":
            return units.pressure_to_Pa(v, UNITS.P)
        return v

    def _from_si(self, v: float) -> float:
        k = self.kind
        if k == "length":
            return units.length_from_m(v, UNITS.L)
        if k == "temp":
            return units.temperature_from_K(v, UNITS.T)
        if k == "dtemp":
            return v * (9 / 5 if UNITS.T == "degF" else 1.0)
        if k == "pressure":
            return units.pressure_from_Pa(v, UNITS.P)
        return v

    def _refresh(self) -> None:
        self.blockSignals(True)
        k = self.kind
        if k == "length":
            nd = UNITS.nd
            big = 10000.0 if UNITS.L == "mm" else 400.0
            self.setDecimals(nd)
            self.setRange(-big if self.signed else 0.0, big)
            self.setSingleStep(0.01 if UNITS.L == "mm" else 0.001)
            self.setSuffix(f" {UNITS.L}")
        elif k in ("temp", "dtemp"):
            self.setDecimals(2 if k == "temp" else 1)
            if k == "temp":
                self.setRange(self._from_si(0.0), self._from_si(2000.0))
            else:
                self.setRange(-1000.0, 1000.0)
            self.setSingleStep(1.0)
            self.setSuffix(f" {UNITS.T_label}")
        elif k == "pressure":
            self.setDecimals(3)
            self.setRange(0.0, self._from_si(1e9))
            self.setSingleStep(1.0)
            self.setSuffix(f" {UNITS.P}")
        else:
            rng, dec, step = self._plain
            self.setDecimals(dec)
            self.setRange(*rng)
            self.setSingleStep(step)
        self.setValue(self._from_si(self._si))
        self.blockSignals(False)

    def _on_value(self, v: float) -> None:
        self._si = self._to_si(v)
        self.edited.emit()

    def si(self) -> float:
        return self._si

    def set_si(self, v: float) -> None:
        self._si = float(v)
        self._refresh()


class OptionalValue(QWidget):
    """Checkbox + value: ``si()`` is None while unticked."""

    edited = Signal()

    def __init__(self, spin: QWidget, checked: bool = False, parent=None):
        super().__init__(parent)
        self.box, self.spin = QCheckBox(), spin
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.box)
        lay.addWidget(spin, 1)
        self.box.setChecked(checked)
        spin.setEnabled(checked)
        self.box.toggled.connect(spin.setEnabled)
        self.box.toggled.connect(lambda *_: self.edited.emit())
        (spin.edited if hasattr(spin, "edited") else spin.currentIndexChanged).connect(
            lambda *_: self.edited.emit())

    def si(self):
        if not self.box.isChecked():
            return None
        return self.spin.si() if hasattr(self.spin, "si") else self.spin.currentData()


def combo(items: list[tuple[str, object]], current=None) -> QComboBox:
    c = QComboBox()
    for text, data in items:
        c.addItem(text, data)
    if current is not None:
        i = c.findData(current)
        if i >= 0:
            c.setCurrentIndex(i)
    c.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    return c


class ToleranceEditor(QWidget):
    """ISO 286 class (H7, f7 ...) or custom deviations for one dimension.

    ``feature`` orders the class list: "hole" (internal: bores, groove outer diameters,
    groove widths) or "shaft" (external: pistons, rods, groove bottom diameters) first.
    """

    edited = Signal()

    def __init__(self, default_dev_m: tuple[float, float], feature: str | None, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.cls = QComboBox()
        self.cls.addItem(t("desktop.tol_custom"), None)
        if feature is not None:
            other = "shaft" if feature == "hole" else "hole"
            for c in fits.classes(feature) + fits.classes(other):
                self.cls.addItem(c, c)
        else:
            self.cls.setEnabled(False)
        self.cls.setMaximumWidth(90)
        self.lo = UnitSpin("length", default_dev_m[0], signed=True)
        self.hi = UnitSpin("length", default_dev_m[1], signed=True)
        for w in (self.lo, self.hi):
            w.setMinimumWidth(95)
        lay.addWidget(self.cls)
        lay.addWidget(self.lo, 1)
        lay.addWidget(self.hi, 1)
        self._nominal = None
        self.cls.currentIndexChanged.connect(self._apply)
        self.lo.edited.connect(self.edited.emit)
        self.hi.edited.connect(self.edited.emit)

    def set_nominal(self, nominal_m: float) -> None:
        self._nominal = nominal_m
        if self.cls.currentData():
            self._apply(emit=False)

    def _apply(self, *_, emit: bool = True) -> None:
        c = self.cls.currentData()
        custom = c is None
        self.lo.setEnabled(custom)
        self.hi.setEnabled(custom)
        self.setToolTip("")
        self.cls.setStyleSheet("")
        if not custom and self._nominal is not None:
            try:
                d = fits.deviation(c, self._nominal)
                self.lo.set_si(d.lower_m)
                self.hi.set_si(d.upper_m)
            except fits.FitRangeError:
                self.lo.setEnabled(True)
                self.hi.setEnabled(True)
                self.cls.setStyleSheet("color: #b3261e;")
                self.setToolTip(t("desktop.fit_range"))
        if emit:
            self.edited.emit()

    def deviations(self) -> tuple[float, float]:
        lo, hi = self.lo.si(), self.hi.si()
        return min(lo, hi), max(lo, hi)

    def label(self) -> str | None:
        return self.cls.currentData()


# --------------------------------------------------------------------------- outputs
def heading(text: str, size: int = 15) -> QLabel:
    lab = QLabel(text)
    lab.setStyleSheet(f"font-size: {size}px; font-weight: 600; margin-top: 8px;")
    return lab


def note(text: str = "", color: str = "#52514e") -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
    lab.setStyleSheet(f"color: {color};")
    return lab


class Banner(QLabel):
    """Coloured message bar (info / warn / error); hidden when empty."""

    STYLE = {"info": ("#e8f0fb", "#1f4e8c"), "warn": ("#fff4d6", "#6b4a00"), "error": ("#fde7e7", "#8c1d18")}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.hide()

    def show_text(self, text: str, kind: str = "info") -> None:
        if not text:
            self.hide()
            return
        bg, fg = self.STYLE[kind]
        self.setStyleSheet(f"background: {bg}; color: {fg}; padding: 8px 10px; border-radius: 6px;")
        self.setText(text)
        self.show()


class Card(QFrame):
    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setStyleSheet("#card { background: white; border: 1px solid #dddcd6; border-radius: 8px; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        self.title, self.value, self.caption = QLabel(title), QLabel("–"), QLabel("")
        self.title.setStyleSheet("color: #52514e;")
        self.value.setStyleSheet("font-size: 22px; font-weight: 600;")
        self.caption.setStyleSheet("color: #52514e; font-size: 11px;")
        self.caption.setWordWrap(True)
        self.value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        for w in (self.title, self.value, self.caption):
            lay.addWidget(w)
        lay.addStretch(1)

    def set(self, title: str, value: str, caption: str = "") -> None:
        self.title.setText(title)
        self.value.setText(value)
        self.caption.setText(caption)
        self.caption.setVisible(bool(caption))


class Table(QTableWidget):
    """Read-only table sized to its content (no inner scroll bar)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.verticalHeader().hide()
        self.setWordWrap(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAlternatingRowColors(False)

    def fill(self, header: list[str], rows: list[list[str]], colors: list[str | None] | None = None,
             color_col: int = 0, stretch_col: int | None = None) -> None:
        self.clear()
        self.setColumnCount(len(header))
        self.setRowCount(len(rows))
        self.setHorizontalHeaderLabels(header)
        for i, row in enumerate(rows):
            for j, v in enumerate(row):
                it = QTableWidgetItem(str(v))
                it.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                if colors and colors[i] and j == color_col:
                    it.setBackground(QColor(colors[i]))
                self.setItem(i, j, it)
        hh = self.horizontalHeader()
        for j in range(len(header)):
            hh.setSectionResizeMode(j, QHeaderView.ResizeToContents)
        if stretch_col is not None:
            hh.setSectionResizeMode(stretch_col, QHeaderView.Stretch)
        else:
            hh.setStretchLastSection(True)
        QTimer.singleShot(0, self.fit_height)

    def fit_height(self) -> None:
        self.resizeRowsToContents()
        h = self.horizontalHeader().height() + sum(self.rowHeight(i) for i in range(self.rowCount()))
        self.setFixedHeight(h + 2 * self.frameWidth() + 2)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self.fit_height)


def status_text(status: Status | str) -> str:
    s = status.value if isinstance(status, Status) else status
    return f"{STATUS_STYLE[s][0]} {t('status.' + s)}"


class StatusTable(Table):
    def set_rows(self, rows: list[tuple[Status, str, str | None]]) -> None:
        has_T = any(r[2] for r in rows)
        header = [t("ui.col_status"), t("ui.col_check")] + ([t("ui.col_T")] if has_T else [])
        data = [[status_text(r[0]), r[1]] + ([r[2] or ""] if has_T else []) for r in rows]
        self.fill(header, data, [STATUS_STYLE[r[0].value][1] for r in rows], stretch_col=1)


def result_rows(results: list[CheckResult]) -> list[tuple[Status, str, None]]:
    order = {Status.FAIL: 0, Status.WARN: 1, Status.PASS: 2}
    return [(r.status, render_check(r), None) for r in sorted(results, key=lambda r: order[r.status])]


def data_banner_text(needs: bool, material_ids: tuple[str, ...] = ()) -> str:
    if not needs:
        return ""
    ds = dataset()
    mats = {**ds.seal_materials, **ds.housing_materials}
    lines = []
    for mid in dict.fromkeys(material_ids):
        m = mats.get(mid)
        for seg in (m.thermal_strain.segments if m else []):
            if seg.data_quality.needs_warning:
                T = [p[0] for p in seg.points] if hasattr(seg, "points") else list(seg.range_K)
                lines.append(t("ui.data_banner_item", material=m.name, T_lo=min(T), T_hi=max(T),
                               quality=seg.data_quality.value, source=seg.source))
    return "⚠ " + t("ui.data_banner") + "".join(f"\n• {x}" for x in lines)


class SvgView(QWidget):
    """SVG drawn at the widget width, aspect ratio kept (height follows the width)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.renderer = QSvgRenderer(self)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._ratio = 1.0

    def set_svg(self, svg: str) -> None:
        self.renderer.load(QByteArray(svg.encode("utf-8")))
        s = self.renderer.defaultSize()
        self._ratio = s.height() / max(s.width(), 1)
        self.updateGeometry()
        self.setMinimumHeight(int(self.width() * self._ratio))
        self.update()

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, w: int) -> int:
        return int(w * self._ratio)

    def sizeHint(self) -> QSize:
        return QSize(520, int(520 * self._ratio))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        h = int(self.width() * self._ratio)
        if abs(self.minimumHeight() - h) > 1:
            self.setMinimumHeight(h)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        h = w * self._ratio
        if h > self.height():
            h = self.height()
            w = h / self._ratio
        self.renderer.render(p, QRectF(0, 0, w, h))
        p.end()


class SchematicBox(QGroupBox):
    def __init__(self, parent=None):
        super().__init__(t("schematic.heading"), parent)
        lay = QVBoxLayout(self)
        self.view = SvgView()
        lay.addWidget(self.view)
        lay.addStretch(1)

    def show_gland(self, kind: str, dims: dict, direction: str = "internal", seal: str = "oring") -> None:
        self.view.set_svg(gland_schematic(kind, dims, UNITS.L, direction, seal, tiny=True))


class PlotHolder(QWidget):
    """Holds one matplotlib figure; ``set_figure`` replaces it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.canvas = None

    def set_figure(self, fig) -> None:
        if self.canvas is not None:
            self.lay.removeWidget(self.canvas)
            self.canvas.setParent(None)
            self.canvas.deleteLater()
        self.canvas = FigureCanvasQTAgg(fig)
        w, h = fig.get_size_inches()
        self.canvas.setMinimumHeight(int(h * 92))
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.canvas.setFixedHeight(int(h * 92))
        self.lay.addWidget(self.canvas)

    def clear(self) -> None:
        if self.canvas is not None:
            self.lay.removeWidget(self.canvas)
            self.canvas.setParent(None)
            self.canvas.deleteLater()
            self.canvas = None


def form_grid() -> QGridLayout:
    g = QGridLayout()
    g.setHorizontalSpacing(10)
    g.setVerticalSpacing(6)
    g.setColumnStretch(1, 1)
    return g


def add_row(grid: QGridLayout, label: str, *widgets: QWidget) -> int:
    r = grid.rowCount()
    lab = QLabel(label)
    lab.setWordWrap(True)
    grid.addWidget(lab, r, 0)
    for j, w in enumerate(widgets):
        grid.addWidget(w, r, 1 + j)
    return r


def debounce(parent: QObject, fn, ms: int = 250) -> QTimer:
    timer = QTimer(parent)
    timer.setSingleShot(True)
    timer.setInterval(ms)
    timer.timeout.connect(fn)
    return timer


def pct(v: float, nd: int = 1) -> str:
    return "–" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:.{nd}%}"


# --------------------------------------------------------------------------- page skeleton
class Page(QWidget):
    """Inputs on the left, schematic on the right, results below; recompute is debounced."""

    def __init__(self, title: str, intro: str = "", parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QApplication  # noqa: F401  (cursor handling below)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 12, 20, 20)
        root.setSpacing(8)
        root.addWidget(heading(title, 22))
        if intro:
            root.addWidget(note(intro))
        top = QHBoxLayout()
        top.setSpacing(18)
        self.form_widget = QWidget()
        self.form = QVBoxLayout(self.form_widget)
        self.form.setContentsMargins(0, 0, 0, 0)
        top.addWidget(self.form_widget, 1)
        right = QVBoxLayout()
        self.schematic = SchematicBox()
        right.addWidget(self.schematic)
        right.addStretch(1)
        top.addLayout(right, 1)
        root.addLayout(top)
        self.error = Banner()
        root.addWidget(self.error)
        self.results_widget = QWidget()
        self.results = QVBoxLayout(self.results_widget)
        self.results.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.results_widget)
        root.addStretch(1)
        self._timer = debounce(self, self._run)

    def group(self, title: str) -> QGridLayout:
        box = QGroupBox(title)
        grid = form_grid()
        box.setLayout(grid)
        self.form.addWidget(box)
        return grid

    def watch(self, *widgets) -> None:
        for w in widgets:
            for sig in ("edited", "currentIndexChanged", "toggled", "idToggled", "valueChanged"):
                if hasattr(w, sig):
                    getattr(w, sig).connect(lambda *_: self.schedule())
                    break

    def schedule(self) -> None:
        self._timer.start()

    def _run(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.error.show_text("")
            self.recompute()
        except Exception as exc:  # shown on the page; the program keeps running
            self.error.show_text(t("ui.invalid_input", error=exc), "error")
            self.results_widget.setEnabled(False)
        else:
            self.results_widget.setEnabled(True)
        finally:
            QApplication.restoreOverrideCursor()

    def recompute(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError


def save_bytes(parent: QWidget, title: str, filename: str, filt: str, data: bytes) -> str | None:
    from PySide6.QtWidgets import QFileDialog

    path, _ = QFileDialog.getSaveFileName(parent, title, filename, filt)
    if not path:
        return None
    with open(path, "wb") as f:
        f.write(data)
    return path


def radio_row(options: list[tuple[str, str]], current: str):
    """Horizontal radio buttons; returns (widget, group). ``group.checkedButton().property('key')``."""
    from PySide6.QtWidgets import QButtonGroup, QRadioButton

    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    grp = QButtonGroup(w)
    for i, (key, text) in enumerate(options):
        b = QRadioButton(text)
        b.setProperty("key", key)
        grp.addButton(b, i)
        lay.addWidget(b)
        if key == current:
            b.setChecked(True)
    lay.addStretch(1)
    w.group = grp
    w.key = lambda: grp.checkedButton().property("key")
    w.idToggled = grp.idToggled
    return w
