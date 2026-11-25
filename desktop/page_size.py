"""Ölçü Öner: scan standard O-rings for a given diameter and conditions, design and rank a
gland for each (desktop version of app/pages/3). Proposals are computed on demand."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QCheckBox, QHBoxLayout, QPushButton, QSpinBox, QWidget

from oring_designer.checks import run_checks
from oring_designer.export.figures import section_fig, squeeze_fill_fig
from oring_designer.export.report import ReportInput
from oring_designer.gland_types import ThermalState
from oring_designer.i18n import render_check, t
from oring_designer.selector import SelectorInput, select
from oring_designer.sweep import sweep, temperatures, to_frame
from oring_designer.thermal import ThermalDataError
from ui import (UNITS, ShoreCombo, inline, Banner, StatusPill, OptionalValue, Page, PlotHolder, StatusTable, Table, UnitSpin, add_row, combo,
                data_banner_text, dataset, heading, note, radio_row, save_bytes, status_text)

STANDARDS = ["AS568", "ISO3601-1 A", "ISO3601-1 G"]


class SizePage(Page):
    def __init__(self):
        super().__init__(t("ui.page_size"), t("ui.size_intro"))
        ds = dataset()
        self._props, self._ok, self._inp = None, [], None

        g = self.group(t("ui.gland"), 0)
        self.kind = radio_row([(k, t(f"ui.{k}")) for k in ("piston", "rod", "face")], "piston")
        add_row(g, t("ui.gland_type"), self.kind)
        self.direction = radio_row([("internal", t("ui.internal")), ("external", t("ui.external"))], "internal")
        self.dir_row = add_row(g, t("ui.pressure_direction"), self.direction)
        self.D = UnitSpin("length", 50e-3)
        self.tol_nom = UnitSpin("length", 0.025e-3)
        self.tol_nom.setPrefix("± ")
        self.D_row = add_row(g, t("ui.nominal_piston"), inline(self.D, self.tol_nom))
        self.cs_min = UnitSpin("length", 1.7e-3)
        self.cs_max = UnitSpin("length", 3.6e-3)
        add_row(g, t("ui.cs_min"), self.cs_min)
        add_row(g, t("ui.cs_max"), self.cs_max)
        std_w = QWidget()
        sl = QHBoxLayout(std_w)
        sl.setContentsMargins(0, 0, 0, 0)
        self.std = {}
        for s in STANDARDS:
            b = QCheckBox(s)
            b.setChecked(True)
            sl.addWidget(b)
            self.std[s] = b
        add_row(g, t("ui.standards"), std_w)
        self.gg = g

        g = self.group(t("ui.materials"), 1)
        elastomers = [(m.name, k) for k, m in ds.seal_materials.items() if m.group == "elastomer"]
        self.seal = combo(elastomers, "vmq")
        self.groove = combo([(m.name, k) for k, m in ds.housing_materials.items()], "al6061")
        self.mating = OptionalValue(combo([(m.name, k) for k, m in ds.housing_materials.items()], "al6061"))
        add_row(g, t("ui.seal_material"), self.seal)
        g.addWidget(note(t("ui.only_elastomers")), g.rowCount(), 0, 1, 2)
        add_row(g, t("ui.groove_material"), self.groove)
        self.mat_row = add_row(g, t("ui.mating_material"), self.mating)
        self.mg = g

        g = self.group(t("ui.operating"), 1)
        self.pressure = UnitSpin("pressure", 50e5)
        self.hardness = ShoreCombo(70.0)
        self.fluid = combo([(t("ui.no_fluid"), None)] + [(f.name, k) for k, f in ds.fluids.items()])
        add_row(g, t("ui.pressure"), self.pressure)
        add_row(g, t("ui.hardness"), self.hardness)

        g = self.group(t("ui.sweep"), 1)
        self.T_min = UnitSpin("temp", 240.0)
        self.T_max = UnitSpin("temp", 300.0)
        self.n_T = QSpinBox()
        self.n_T.setMaximumWidth(118)
        self.n_T.setRange(2, 15)
        self.n_T.setValue(5)
        self.lag = UnitSpin("dtemp", 0.0, signed=True)
        add_row(g, t("ui.T_min"), self.T_min)
        add_row(g, t("ui.T_max"), self.T_max)
        add_row(g, t("ui.n_temps"), self.n_T)
        add_row(g, t("ui.lag_delta"), self.lag)

        g = self.gg  # machined-dimension tolerances belong to the gland
        self.tol_d = UnitSpin("length", 0.025e-3)
        self.tol_w = UnitSpin("length", 0.10e-3)
        self.tol_depth = UnitSpin("length", 0.025e-3)
        self.cl_min = OptionalValue(UnitSpin("length", 0.05e-3))
        self.cl_max = UnitSpin("length", 0.10e-3)
        add_row(g, t("ui.tol_diameter"), self.tol_d)
        add_row(g, t("ui.tol_width"), self.tol_w)
        add_row(g, t("ui.tol_depth"), self.tol_depth)
        self.cl_rows = [add_row(g, t("ui.clearance_min"), self.cl_min),
                        add_row(g, t("ui.clearance_max"), self.cl_max)]
        self.tg = g
        self.end_columns()
        self.run_btn = QPushButton(t("desktop.run_size"))
        self.run_btn.setStyleSheet("font-weight: 600; padding: 6px 14px;")
        self.run_btn.clicked.connect(self._compute)
        self.form.addWidget(self.run_btn)

        self.watch(self.kind, self.direction, self.D, self.cs_min, self.cs_max, *self.std.values(), self.seal,
                   self.groove, self.mating, self.pressure, self.hardness, self.fluid, self.T_min, self.T_max,
                   self.n_T, self.lag, self.tol_nom, self.tol_d, self.tol_w, self.tol_depth, self.cl_min, self.cl_max)

        # ------------------------------------------------------------------ results
        sm = self.summary
        self.stale = Banner()
        self.warn = Banner()
        sm.addWidget(self.stale)
        sm.addWidget(self.warn)
        sm.addWidget(heading(t("ui.proposals"), 13))
        self.table = Table()
        self.table.fit = False
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.setMinimumHeight(170)
        self.table.setMaximumHeight(250)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.itemSelectionChanged.connect(self._show_detail)
        sm.addWidget(self.table)
        self.status = StatusPill()
        sm.addWidget(self.status)
        self.banner = Banner()
        sm.addWidget(self.banner)
        self.checks = StatusTable()
        sm.addStretch(0)

        r = self.details
        self.detail_title = heading("", 13)
        sm.addWidget(self.detail_title)
        self.dims = Table()
        sm.addWidget(self.dims)
        sm.addStretch(1)
        self.under.addWidget(heading(t("ui.wc_checks"), 13))
        self.under.addWidget(self.checks)
        self.under.addStretch(1)
        self.plot = PlotHolder()
        r.addWidget(self.plot)
        r.addWidget(heading(t("ui.section")))
        self.side = radio_row([(k, t(f"plots.side_{k}")) for k in ("nominal", "tight", "wide")], "nominal")
        self.side.idToggled.connect(lambda *_: self._show_detail())
        r.addWidget(self.side)
        self.section = PlotHolder()
        r.addWidget(self.section)
        out = QHBoxLayout()
        for text, fn in ((t("desktop.save_pdf"), self._save_pdf), (t("desktop.save_dxf"), self._save_dxf)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            out.addWidget(b)
        r.addLayout(out)
        self.out_msg = note()
        r.addWidget(self.out_msg)
        self._detail_widgets = [self.detail_title, self.dims, self.banner, self.status, self.checks, self.plot,
                                self.side, self.section]
        self.schedule()
        self._compute()

    # ---------------------------------------------------------------------- inputs
    def _input(self) -> SelectorInput:
        kind = self.kind.key()
        direction = self.direction.key() if kind == "face" else "internal"
        U = UNITS
        inch = U.L == "in"
        clearance = None
        if kind != "face" and self.cl_min.si() is not None:
            clearance = (self.cl_min.si(), self.cl_max.si())
        return SelectorInput(
            gland_type=kind, nominal_diameter_m=self.D.si(), seal_material=self.seal.currentData(),
            groove_material=self.groove.currentData(),
            mating_material=self.mating.si() if kind != "face" else None,
            pressure_Pa=self.pressure.si(), hardness_shore_a=self.hardness.si(), fluid=self.fluid.currentData(),
            face_pressure_direction=direction, T_min_K=min(self.T_min.si(), self.T_max.si()),
            T_max_K=max(self.T_min.si(), self.T_max.si()), T_ref_K=U.T_ref_K, n_temperatures=self.n_T.value(),
            lag_delta_K=self.lag.si(), cs_min_m=min(self.cs_min.si(), self.cs_max.si()),
            cs_max_m=max(self.cs_min.si(), self.cs_max.si()),
            standards=tuple(s for s, b in self.std.items() if b.isChecked()), nominal_tol_m=self.tol_nom.si(),
            diameter_tol_m=self.tol_d.si(), width_tol_m=self.tol_w.si(), depth_tol_m=self.tol_depth.si(),
            clearance_m=clearance, round_diameter_m=0.0005 * 0.0254 if inch else 0.01e-3,
            round_width_m=0.001 * 0.0254 if inch else 0.05e-3)

    def recompute(self) -> None:
        """Cheap part: visibility, label, schematic with the given diameter; marks results stale."""
        kind = self.kind.key()
        face = kind == "face"
        direction = self.direction.key() if face else "internal"
        for w in (self.direction, self.gg.itemAtPosition(self.dir_row, 0).widget()):
            w.setVisible(face)
        for w in (self.mating, self.mg.itemAtPosition(self.mat_row, 0).widget()):
            w.setVisible(not face)
        for r in self.cl_rows:
            for c in (0, 1):
                self.tg.itemAtPosition(r, c).widget().setVisible(not face)
        self.cl_max.setEnabled(self.cl_min.si() is not None)
        label = t(f"ui.nominal_{kind}" if not face else f"ui.nominal_face_{direction}")
        self.gg.itemAtPosition(self.D_row, 0).widget().setText(label)
        if self._inp is not None and self._input() != self._inp:
            self.stale.show_text(t("desktop.size_stale"), "info")
            if self.table.currentRow() < 0:
                known = {"piston": "bore", "rod": "rod"}.get(kind) or ("groove_od" if direction == "internal"
                                                                       else "groove_id")
                self.schematic.show_gland(kind, {known: UNITS.num_L(self.D.si()), "width": "…", "depth": "…",
                                                 "cs": "…", "ring_id": "…"}, direction)
        elif self._inp is None:
            self.stale.show_text("")
        self._show_detail()

    def _compute(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            inp = self._input()
            props = select(inp, dataset())
            self._inp = inp
            self._props = props
            self.stale.show_text("")
            self.error.show_text("")
            self._fill_table()
        except Exception as exc:  # noqa: BLE001
            self.error.show_text(t("ui.invalid_input", error=exc), "error")
        finally:
            QApplication.restoreOverrideCursor()

    def _fill_table(self) -> None:
        props = self._props or []
        self._ok = [p for p in props if p.error is None]
        errs = [t("ui.proposal_error", size=p.size, error=p.error) for p in props if p.error is not None]
        if not props:
            errs = [t("ui.no_candidates")]
        self.warn.show_text("\n".join(errs), "warn")
        U = UNITS

        def pm(v, tol):
            return f"{U.fmt_L(v)} ± {U.num_L(tol)}"

        rows = []
        for p in self._ok:
            wc = p.wc
            rows.append([status_text(p.status), p.size, U.fmt_L(p.ring.id_m), U.fmt_L(p.ring.cs_m),
                         f"{wc.output_min['squeeze_min']:.1%} – {wc.output_max['squeeze_max']:.1%}",
                         f"{wc.output_min['fill']:.1%} – {wc.output_max['fill']:.1%}",
                         f"{wc.output_min['stretch']:.2%} – {wc.output_max['stretch']:.2%}", f"{p.score:.2f}"])
        from ui import STATUS_STYLE

        self.table.fill([t("ui.col_status"), t("ui.col_size"), t("ui.oring_id"), t("ui.oring_cs"), t("ui.col_squeeze"),
                         t("ui.col_fill"), t("ui.col_stretch"), t("ui.col_score")], rows,
                        [STATUS_STYLE[p.status.value][1] for p in self._ok])
        if self._ok:
            self.table.selectRow(0)
        self._show_detail()

    # ---------------------------------------------------------------------- detail
    def _show_detail(self) -> None:
        i = self.table.currentRow()
        has = bool(self._ok) and 0 <= i < len(self._ok)
        for w in self._detail_widgets:
            w.setVisible(has)
        if not has:
            return
        p = self._ok[i]
        inp = self._inp
        U = UNITS
        ds = dataset()
        kind = inp.gland_type
        g = p.design.gland
        tol = p.tolerances

        def tnum(field, value):
            tv = tol.get(f"gland.{field}")
            return U.num_L(value, (tv.lower_m, tv.upper_m) if tv else None)

        if kind == "piston":
            sk = {"bore": tnum("bore_diameter_m", g.bore_diameter_m), "piston": tnum("piston_diameter_m", g.piston_diameter_m),
                  "groove_d": tnum("groove_diameter_m", g.groove_diameter_m)}
            dims = [("ui.bore_diameter", "bore_diameter_m"), ("ui.piston_diameter", "piston_diameter_m"),
                    ("ui.groove_diameter_piston", "groove_diameter_m"), ("ui.groove_width", "groove_width_m")]
        elif kind == "rod":
            sk = {"rod": tnum("rod_diameter_m", g.rod_diameter_m), "throat": tnum("throat_diameter_m", g.throat_diameter_m),
                  "groove_d": tnum("groove_diameter_m", g.groove_diameter_m)}
            dims = [("ui.rod_diameter", "rod_diameter_m"), ("ui.throat_diameter", "throat_diameter_m"),
                    ("ui.groove_diameter_rod", "groove_diameter_m"), ("ui.groove_width", "groove_width_m")]
        else:
            sk = {"groove_id": tnum("groove_id_m", g.groove_id_m), "groove_od": tnum("groove_od_m", g.groove_od_m)}
            dims = [("ui.groove_id", "groove_id_m"), ("ui.groove_od", "groove_od_m"), ("ui.groove_depth", "groove_depth_m")]
        sk["width"] = tnum("groove_width_m", g.groove_width_m) if kind != "face" else U.num_L(
            (g.groove_od_m - g.groove_id_m) / 2)
        sk["depth"] = tnum("groove_depth_m", g.groove_depth_m) if kind == "face" else U.num_L(p.depth_m)
        sk |= {"radius": U.num_L(p.radius_m), "gap": U.num_L(p.clearance_m),
               "cs": U.num_L(p.ring.cs_m, p.ring_tol[1]), "ring_id": U.num_L(p.ring.id_m, p.ring_tol[0])}
        direction = inp.face_pressure_direction if kind == "face" else "internal"
        self.schematic.show_gland(kind, sk, direction)

        self.detail_title.setText(f"{t('ui.proposal_detail')}: {p.size} — {U.fmt_L(p.ring.id_m)} × {U.fmt_L(p.ring.cs_m)}")
        rows = []
        for key, field in dims:
            tv = tol.get(f"gland.{field}")
            if tv is None:
                tt = "–"
            elif tv.lower_m == 0:
                tt = f"+{U.num_L(tv.upper_m)} / 0"
            else:
                tt = f"± {U.num_L(tv.upper_m)}"
            rows.append([t(key), U.fmt_L(getattr(g, field)), tt])
        rows.append([t("ui.gland_depth_ref"), U.fmt_L(p.depth_m), "–"])
        rows.append([t("ui.corner_radius"), U.fmt_L(p.radius_m), "–"])
        if p.clearance_m is not None:
            rows.append([t("ui.diametral_clearance_nom"), U.fmt_L(p.clearance_m), "–"])
        self.dims.fill([t("ui.col_dim"), t("ui.col_value"), t("ui.col_tol")], rows)

        worst = [r for r, _ in p.wc.worst_results.values()]
        mats = (p.design.seal_material, p.design.groove_material)
        self.banner.show_text(data_banner_text(any(r.data_quality is not None and r.data_quality.needs_warning
                                                   for r in worst), mats), "warn")
        self.status.set_status(p.status, f"{p.size} — {t('ui.wc_checks')}")
        order = {"FAIL": 0, "WARN": 1, "PASS": 2}
        self.checks.set_rows([(r.status, render_check(r), None) for r in sorted(worst, key=lambda r: order[r.status.value])])

        seal = ds.seal_materials[p.design.seal_material]
        rules = ds.rule_set(seal.group, "static_face" if kind == "face" else "static_radial")
        T_ref = inp.T_ref_K
        pts = sweep(p.design, ds, temperatures(inp.T_min_K, inp.T_max_K, max((inp.T_max_K - inp.T_min_K) / 40, 0.5)),
                    T_ref_K=T_ref)
        self.plot.set_figure(squeeze_fill_fig(
            to_frame(pts), U.T, squeeze_band=p.band, squeeze_max=rules.squeeze_max.value if rules.squeeze_max else None,
            fill_band=(rules.fill_min.value, rules.fill_max.value), fill_hard_max=rules.fill_hard_max.value,
            low_temp_limit_K=seal.low_temp_limit_K.value if seal.low_temp_limit_K else None,
            low_temp_band_K=ds.common_rules.low_temp_warning_band_K.value))
        panels = []
        for T in (inp.T_min_K, T_ref, inp.T_max_K):
            try:
                panels.append((U.fmt_T(T), run_checks(p.design, ds, ThermalState(T, T, None, T_ref))[0]))
            except ThermalDataError:
                panels.append((U.fmt_T(T), None))
        self.side.setVisible(kind != "face")
        side = self.side.key() if kind != "face" else "nominal"
        self.section.set_figure(section_fig(panels, kind, side, U.L, direction, g.corner_radius_m))
        self._report = ReportInput(p.design, T_ref, None, inp.T_min_K, inp.T_max_K,
                                   max((inp.T_max_K - inp.T_min_K) / 40, 0.5), "equilibrium", 0.0, 0.0, U.L, U.T, U.P,
                                   oring_label=p.size, tolerances=p.tolerances, mc_samples=5000)
        self._design, self._label = p.design, p.size

    def _save_pdf(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication

        from oring_designer.export.report import build_report, to_pdf

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            data = to_pdf(build_report(self._report, dataset()))
        finally:
            QApplication.restoreOverrideCursor()
        path = save_bytes(self, t("ui.build_report"), f"o_ring_rapor_{self._label}.pdf", "PDF (*.pdf)", data)
        if path:
            self.out_msg.setText(t("desktop.saved", path=path))

    def _save_dxf(self) -> None:
        from oring_designer.export.dxf import gland_profile, to_bytes

        path = save_bytes(self, t("ui.download_dxf"), f"yuva_profili_{self._label}.dxf", "DXF (*.dxf)",
                          to_bytes(gland_profile(self._design, UNITS.L, self._label)))
        if path:
            self.out_msg.setText(t("desktop.saved", path=path))
