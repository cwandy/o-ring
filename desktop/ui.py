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
        self.setMinimumWidth(86)
        self.setMaximumWidth(118)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
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
        lay.addWidget(spin)
        lay.addStretch(1)
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


SHORE_A = (50, 60, 70, 75, 80, 90)


class ShoreCombo(QComboBox):
    """Shore A hardness picked from a list (elastomers); same si()/set_si()/edited API as UnitSpin."""

    edited = Signal()

    def __init__(self, value: float = 70.0, parent=None):
        super().__init__(parent)
        for h in SHORE_A:
            self.addItem(f"{h} ShA", float(h))
        self.set_si(value)
        self.setMaximumWidth(110)
        self.currentIndexChanged.connect(lambda *_: self.edited.emit())

    def si(self) -> float:
        return float(self.currentData())

    def set_si(self, v: float) -> None:
        i = min(range(self.count()), key=lambda k: abs(self.itemData(k) - v))
        self.blockSignals(True)
        self.setCurrentIndex(i)
        self.blockSignals(False)


def combo(items: list[tuple[str, object]], current=None) -> QComboBox:
    c = QComboBox()
    for text, data in items:
        c.addItem(text, data)
    if current is not None:
        i = c.findData(current)
        if i >= 0:
            c.setCurrentIndex(i)
    c.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    c.setMaximumWidth(210)
    c.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    c.setMinimumContentsLength(12)
    style_popup(c)
    return c


def style_popup(c: QComboBox) -> None:
    """White list, navy highlight under the mouse (independent of the Windows theme)."""
    from PySide6.QtGui import QPalette
    from PySide6.QtWidgets import QListView

    view = QListView()
    c.setView(view)
    pal = view.palette()
    pal.setColor(QPalette.Base, QColor("white"))
    pal.setColor(QPalette.Text, QColor("#1f1f1d"))
    pal.setColor(QPalette.Highlight, QColor("#1d3557"))
    pal.setColor(QPalette.HighlightedText, QColor("white"))
    view.setPalette(pal)


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
        style_popup(self.cls)
        self.cls.addItem(t("desktop.tol_custom"), None)
        if feature is not None:
            other = "shaft" if feature == "hole" else "hole"
            for c in fits.classes(feature) + fits.classes(other):
                self.cls.addItem(c, c)
        else:
            self.cls.setVisible(False)
        self.cls.setMaximumWidth(72)
        # upper deviation on top, lower below, both in the height of one input row
        self.hi = UnitSpin("length", default_dev_m[1], signed=True)
        self.lo = UnitSpin("length", default_dev_m[0], signed=True)
        stack = QWidget()
        sv = QVBoxLayout(stack)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(0)
        self.hi_lab, self.lo_lab = QLabel(), QLabel()
        for w in (self.hi, self.lo):
            w.setFixedHeight(20)
            w.setMinimumWidth(72)
            w.setMaximumWidth(84)
            f = w.font()
            f.setPixelSize(11)
            w.setFont(f)
            # (NoButtons + style sheet hides the text in Qt; zero-width buttons instead)
            w.setStyleSheet("QDoubleSpinBox { padding: 0px 2px; min-height: 0px; border: 1px solid #c9d0db;"
                            " border-radius: 3px; background: white; }"
                            " QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 0px; border: none; }")
            w.setPrefix("")
            sv.addWidget(w)
        for lab in (self.hi_lab, self.lo_lab):
            lab.setFixedHeight(20)
            lab.setStyleSheet("font-size: 11px; color: #39424e;")
            sv.addWidget(lab)
            lab.hide()
        lay.addWidget(self.cls)
        lay.addWidget(stack)
        lay.addStretch(1)
        self._fixed = False
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

    def set_fixed(self, lo_m: float, hi_m: float, tip: str = "") -> None:
        """Show fixed (automatic) deviations as text instead of input boxes."""
        self.lo.set_si(lo_m)
        self.hi.set_si(hi_m)
        for w in (self.lo, self.hi):
            w.hide()
        self.hi_lab.setText(f"{UNITS.num_L(hi_m):>}" if hi_m < 0 else f"+{UNITS.num_L(hi_m)}")
        self.lo_lab.setText(f"{UNITS.num_L(lo_m)}" if lo_m < 0 else f"+{UNITS.num_L(lo_m)}")
        for lab in (self.hi_lab, self.lo_lab):
            lab.show()
        self.setToolTip(tip)

    def set_editable(self) -> None:
        for w in (self.lo, self.hi):
            w.show()
            w.setEnabled(True)
        for lab in (self.hi_lab, self.lo_lab):
            lab.hide()

    def deviations(self) -> tuple[float, float]:
        lo, hi = self.lo.si(), self.hi.si()
        return min(lo, hi), max(lo, hi)

    def label(self) -> str | None:
        return self.cls.currentData()


# --------------------------------------------------------------------------- outputs
def heading(text: str, size: int = 15) -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
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
        self.setStyleSheet("#card { background: #f8fafd; border: 1px solid #dfe5ee; border-left: 4px solid #2a78d6;"
                           " border-radius: 8px; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(1)
        self.title, self.value, self.caption = QLabel(title), QLabel("–"), QLabel("")
        self.title.setStyleSheet("color: #5b6270; font-size: 11px;")
        self.title.setWordWrap(True)
        self.value.setStyleSheet("font-size: 18px; font-weight: 700; color: #1d3557;")
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
        self.fit = True  # False: fixed height with its own scroll bar

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
        if not self.fit:
            return
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


def data_banner_text(needs: bool, material_ids: tuple[str, ...] = (),
                     T_range: tuple[float, float] | None = None) -> str:
    """One line: which material is estimated in which temperature range (only ranges that
    overlap ``T_range`` when given)."""
    if not needs:
        return ""
    ds = dataset()
    mats = {**ds.seal_materials, **ds.housing_materials}
    items = []
    for mid in dict.fromkeys(material_ids):
        m = mats.get(mid)
        for seg in (m.thermal_strain.segments if m else []):
            if seg.data_quality.needs_warning:
                T = [p[0] for p in seg.points] if hasattr(seg, "points") else list(seg.range_K)
                lo, hi = min(T), max(T)
                if T_range is not None and (hi < T_range[0] or lo > T_range[1]):
                    continue
                items.append(t("desktop.data_item", material=m.name, T_lo=lo, T_hi=hi))
    if T_range is not None:  # K28: outside the data range the end slope is extended
        for mid in dict.fromkeys(material_ids):
            m = mats.get(mid)
            if m is None:
                continue
            cv = ds.curve(mid)
            if cv.has_data and (T_range[0] < cv.T_min_K - 1e-6 or T_range[1] > cv.T_max_K + 1e-6):
                items.append(t("desktop.data_outside", material=m.name, T_lo=cv.T_min_K, T_hi=cv.T_max_K))
    if not items and T_range is not None:  # estimated data used via an adjacent gap: list all
        return data_banner_text(needs, material_ids, None)
    if not items:
        return ""
    return "⚠ " + t("desktop.data_short", items="; ".join(items))


class SvgView(QWidget):
    """SVG drawn at the widget width, aspect ratio kept (height follows the width, at most MAX_H)."""

    MAX_H = 380

    def __init__(self, parent=None):
        super().__init__(parent)
        self.renderer = QSvgRenderer(self)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._ratio = 1.0

    def set_svg(self, svg: str) -> None:
        self.renderer.load(QByteArray(svg.encode("utf-8")))
        s = self.renderer.defaultSize()
        self._ratio = s.height() / max(s.width(), 1)
        self.setFixedHeight(min(int(max(self.width(), 100) * self._ratio), self.MAX_H))
        self.updateGeometry()
        self.update()

    def heightForWidth(self, w: int) -> int:
        return int(w * self._ratio)

    def sizeHint(self) -> QSize:
        return QSize(520, int(520 * self._ratio))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        h = min(int(self.width() * self._ratio), self.MAX_H)
        if abs(self.height() - h) > 1:
            self.setFixedHeight(h)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        h = w * self._ratio
        if h > self.height():
            h = self.height()
            w = h / self._ratio
        self.renderer.render(p, QRectF((self.width() - w) / 2, 0, w, h))
        p.end()


class SchematicBox(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        cap = QLabel(t("schematic.heading"))
        cap.setObjectName("panelTitle")
        lay.addWidget(cap)
        self.view = SvgView()
        lay.addWidget(self.view)

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
    g.setColumnStretch(1, 0)
    g.setColumnStretch(4, 1)  # spare space goes to the right, inputs keep their size
    return g


def inline(*widgets: QWidget) -> QWidget:
    """Several inputs side by side in one form cell (e.g. value and its tolerance)."""
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)
    for x in widgets:
        lay.addWidget(x)
    lay.addStretch(1)
    return w


def add_row(grid: QGridLayout, label: str, *widgets: QWidget) -> int:
    r = grid.rowCount()
    lab = QLabel(label)
    lab.setWordWrap(True)
    lab.setMinimumWidth(118)
    lab.setMaximumWidth(165)
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
    """Header (title, Formülasyon, Detaylar) / [inputs | schematic | summary] / details.

    Without details the page fits one screen: inputs and summary scroll inside their own
    panels if needed. Details (charts, sections, tables) appear only after "Detaylar".
    """

    def __init__(self, title: str, intro: str = "", parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QPushButton, QScrollArea, QTabWidget

        self.setObjectName("page")
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 10, 16, 12)
        root.setSpacing(8)

        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(0)
        tl = QLabel(title)
        tl.setObjectName("pageTitle")
        titles.addWidget(tl)
        if intro:
            il = QLabel(intro)
            il.setObjectName("pageIntro")
            il.setWordWrap(True)
            titles.addWidget(il)
        head.addLayout(titles, 1)
        self.formula_btn = QPushButton("∑  " + t("desktop.formulas"))
        self.formula_btn.setObjectName("secondary")
        self.formula_btn.clicked.connect(lambda: show_formulas(self))
        self.details_btn = QPushButton(t("desktop.details_show"))
        self.details_btn.setCheckable(True)
        self.details_btn.toggled.connect(self._toggle_details)
        head.addWidget(self.formula_btn)
        head.addWidget(self.details_btn)
        root.addLayout(head)

        self.body = QWidget()
        self.body.setMinimumHeight(520)
        body = QHBoxLayout(self.body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(10)
        # inputs: one panel, two columns of groups, everything visible without scrolling
        lw = QFrame()
        lw.setObjectName("panel")
        left = QVBoxLayout(lw)
        left.setContentsMargins(10, 8, 10, 8)
        left.setSpacing(4)
        cap = QLabel(t("desktop.inputs"))
        cap.setObjectName("panelTitle")
        left.addWidget(cap)
        cols = QHBoxLayout()
        cols.setSpacing(10)
        self._cols = [QVBoxLayout(), QVBoxLayout()]
        for c in self._cols:
            c.setSpacing(6)
            cols.addLayout(c, 1)
        left.addLayout(cols)
        self.form = QVBoxLayout()
        left.addLayout(self.form)
        left.addStretch(1)
        body.addWidget(lw, 0)
        # middle column: schematic at its natural height, page-specific results below it
        mid = QVBoxLayout()
        mid.setSpacing(10)
        self.schematic = SchematicBox()
        self.schematic.setMinimumWidth(180)
        self.schematic.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        mid.addWidget(self.schematic)
        self.under_panel = QFrame()
        self.under_panel.setObjectName("panel")
        upl = QVBoxLayout(self.under_panel)
        upl.setContentsMargins(10, 8, 6, 8)
        usa = QScrollArea()
        usa.setWidgetResizable(True)
        usa.setFrameShape(QFrame.NoFrame)
        usa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        uin = QWidget()
        uin.setObjectName("panelInner")
        self.under = QVBoxLayout(uin)
        self.under.setContentsMargins(0, 0, 4, 0)
        self.under.setSpacing(6)
        usa.setWidget(uin)
        upl.addWidget(usa)
        self.under_panel.setMinimumHeight(140)
        mid.addWidget(self.under_panel, 1)
        body.addLayout(mid, 5)
        sw = QFrame()
        sw.setObjectName("panel")
        sl = QVBoxLayout(sw)
        sl.setContentsMargins(12, 8, 12, 8)
        cap = QLabel(t("desktop.summary"))
        cap.setObjectName("panelTitle")
        sl.addWidget(cap)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        inner.setObjectName("panelInner")
        self.summary = QVBoxLayout(inner)
        self.summary.setContentsMargins(0, 0, 4, 0)
        self.summary.setSpacing(6)
        sa.setWidget(inner)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sl.addWidget(sa, 1)
        sw.setMinimumWidth(320)
        sw.setMaximumWidth(560)
        body.addWidget(sw, 4)
        root.addWidget(self.body, 1)

        self.error = Banner()
        root.addWidget(self.error)
        self.details_widget = QFrame()
        self.details_widget.setObjectName("panel")
        self.details = QVBoxLayout(self.details_widget)
        self.details.setContentsMargins(14, 10, 14, 14)
        self.details_widget.hide()
        root.addWidget(self.details_widget)
        self.results_widget = self.details_widget  # compatibility: disabled on error
        self.groups: dict[str, QGroupBox] = {}
        self._timer = debounce(self, self._run)

    def hasHeightForWidth(self) -> bool:  # wrapped labels must not make the scroll area taller
        return False

    def _toggle_details(self, on: bool) -> None:
        self.details_widget.setVisible(on)
        self.details_btn.setText(t("desktop.details_hide" if on else "desktop.details_show"))

    def group(self, title: str, col: int = 0, optional: bool = False) -> QGridLayout:
        """A titled box of inputs in column ``col``. ``optional``: collapsed until ticked."""
        box = QGroupBox(title)
        inner = QWidget()
        grid = form_grid()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setVerticalSpacing(3)
        inner.setLayout(grid)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(8, 4, 8, 6)
        lay.addWidget(inner)
        if optional:
            box.setCheckable(True)
            box.setChecked(False)
            inner.setVisible(False)
            box.toggled.connect(inner.setVisible)
        self._cols[col].addWidget(box)
        self.groups[title] = box
        return grid

    def end_columns(self) -> None:
        for c in self._cols:
            c.addStretch(1)

    def set_group_visible(self, title: str, on: bool) -> None:
        self.groups[title].setVisible(on)

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
        finally:
            QApplication.restoreOverrideCursor()

    def recompute(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError


class StatusPill(QLabel):
    """Overall result as a coloured badge."""

    COLORS = {"PASS": ("#1e7d32", "#e3f4e4"), "WARN": ("#8a5a00", "#fff1cc"), "FAIL": ("#a4231b", "#fde4e1")}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWordWrap(True)
        self.hide()

    def set_status(self, status, prefix: str = "") -> None:
        s = status.value if isinstance(status, Status) else status
        fg, bg = self.COLORS[s]
        self.setStyleSheet(f"background:{bg}; color:{fg}; border:1px solid {fg}; border-radius:8px;"
                           "padding:8px 12px; font-size:16px; font-weight:700;")
        self.setText(f"{prefix or t('ui.overall')}: {status_text(s)}")
        self.show()


def show_formulas(parent: QWidget) -> None:
    from html import escape

    from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser

    from oring_designer.i18n import _load

    sections = _load("tr")["formulas.sections"]
    parts = [f"<h2 style='color:#1d3557'>{escape(t('formulas.title'))}</h2>",
             f"<p style='color:#52514e'>{escape(t('formulas.intro'))}</p>"]
    for sec in sections:
        parts.append(f"<h3 style='color:#1d4f91;margin-top:18px'>{escape(sec['title'])}</h3>")
        for it in sec["items"]:
            parts.append(
                "<table width='100%' cellspacing='0' cellpadding='8' style='margin:6px 0'><tr><td "
                "style='background:#eef4fc;border-left:4px solid #2a78d6;font-family:Cambria Math,Cambria,"
                f"Times New Roman,serif;font-size:15px'>{escape(it['eq'])}</td></tr>"
                f"<tr><td style='color:#3d3d3a'>{escape(it['note'])}</td></tr></table>")
    dlg = QDialog(parent)
    dlg.setWindowTitle(t("desktop.formulas"))
    dlg.resize(900, 760)
    lay = QVBoxLayout(dlg)
    tb = QTextBrowser()
    tb.setOpenExternalLinks(True)
    tb.setHtml("".join(parts))
    lay.addWidget(tb)
    bb = QDialogButtonBox(QDialogButtonBox.Close)
    bb.rejected.connect(dlg.reject)
    lay.addWidget(bb)
    dlg.exec()


STYLE = """
QMainWindow, QWidget#page, QScrollArea, QScrollArea > QWidget > QWidget#page { background: #f2f4f8; }
QWidget#tabPage, QWidget#panelInner { background: white; }
QLabel#pageTitle { font-size: 22px; font-weight: 700; color: #1d3557; }
QLabel#pageIntro { color: #5b6270; }
QLabel#panelTitle { font-size: 14px; font-weight: 700; color: #1d3557; }
QFrame#panel { background: white; border: 1px solid #d9dee7; border-radius: 10px; }
QGroupBox { background: #fbfcfe; border: 1px solid #e1e6ee; border-radius: 8px; margin-top: 12px; padding: 6px 4px 4px 4px; }
QGroupBox::indicator { width: 14px; height: 14px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; color: #1d3557; font-weight: 700; }
QTabWidget::pane { border: 1px solid #d9dee7; border-radius: 8px; background: white; top: -1px; }
QTabBar::tab { background: #e7ebf2; color: #39424e; padding: 7px 14px; margin-right: 2px;
               border-top-left-radius: 6px; border-top-right-radius: 6px; }
QTabBar::tab:selected { background: white; color: #1d4f91; font-weight: 700; }
QTabBar::tab:hover:!selected { background: #dce3ee; }
QTabWidget#mainTabs > QTabBar::tab { padding: 9px 22px; font-size: 14px; }
QTabWidget#mainTabs > QTabBar::tab:selected { border-bottom: 3px solid #2a78d6; }
QPushButton { background: #2a78d6; color: white; border: none; border-radius: 7px; padding: 8px 16px; font-weight: 600; }
QPushButton:hover { background: #2367bb; }
QPushButton:checked { background: #1d3557; }
QPushButton:disabled { background: #b8c2d0; }
QPushButton#secondary { background: white; color: #1d4f91; border: 1px solid #2a78d6; }
QPushButton#secondary:hover { background: #eef4fc; }
QComboBox, QDoubleSpinBox, QSpinBox { background: white; border: 1px solid #c9d0db; border-radius: 5px; padding: 1px 4px; min-height: 20px; }
QComboBox QAbstractItemView { background: white; color: #1f1f1d; border: 1px solid #c9d0db;
    selection-background-color: #1d3557; selection-color: white; outline: 0; }
QComboBox QAbstractItemView::item { min-height: 22px; padding: 2px 6px; color: #1f1f1d; }
QComboBox QAbstractItemView::item:hover, QComboBox QAbstractItemView::item:selected { background: #1d3557; color: white; }
QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus { border: 1px solid #2a78d6; }
QComboBox:disabled, QDoubleSpinBox:disabled, QSpinBox:disabled { background: #e9ecf1; color: #8a929e; }
QHeaderView::section { background: #eef2f7; color: #1d3557; border: none; border-bottom: 1px solid #d9dee7; padding: 5px; font-weight: 700; }
QTableWidget { background: white; border: 1px solid #d9dee7; border-radius: 6px; gridline-color: #eef0f3; }
QTableWidget::item:selected { background: #d6e6fa; color: black; }
QToolBar#topBar { background: #1d3557; border: none; padding: 6px 10px; spacing: 6px; }
QToolBar#topBar QLabel { color: white; }
QToolBar#topBar QLabel#appTitle { font-size: 16px; font-weight: 700; }
QToolBar#topBar QComboBox, QToolBar#topBar QDoubleSpinBox { min-width: 70px; }
QCheckBox, QRadioButton { spacing: 6px; }
QAbstractSpinBox, QAbstractSpinBox QLineEdit, QComboBox, QComboBox QLineEdit, QLineEdit { background: white; }
QAbstractSpinBox:disabled, QAbstractSpinBox:disabled QLineEdit, QComboBox:disabled, QLineEdit:disabled
    { background: #e9ecf1; color: #8a929e; }
"""


def save_bytes(parent: QWidget, title: str, filename: str, filt: str, data: bytes) -> str | None:
    from PySide6.QtWidgets import QFileDialog

    path, _ = QFileDialog.getSaveFileName(parent, title, filename, filt)
    if not path:
        return None
    with open(path, "wb") as f:
        f.write(data)
    return path


def radio_row(options: list[tuple[str, str]], current: str, vertical: bool = False):
    """Horizontal radio buttons; returns (widget, group). ``group.checkedButton().property('key')``."""
    from PySide6.QtWidgets import QButtonGroup, QRadioButton

    w = QWidget()
    lay = QVBoxLayout(w) if vertical else QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(2 if vertical else 8)
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
