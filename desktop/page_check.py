"""Yuva Kontrol: check an existing gland at one point, over a temperature sweep, and with its
drawing tolerances (worst case / RSS / Monte Carlo) - the former "Tolerans Analizi" page is
part of this page. Tolerances are ISO 286 classes (H7, f7 ...) or custom deviations."""

from __future__ import annotations

import pandas as pd
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QLabel, QPushButton, QSpinBox, QTabBar,
                               QVBoxLayout, QWidget)

from oring_designer.checks import Design, allowed_extrusion_gap_m, overall_status, run_checks, with_rule_overrides
from oring_designer.export.figures import clearance_fig, histogram_fig, section_fig, squeeze_fill_fig
from oring_designer.export.report import ReportInput
from oring_designer.gland_types import FaceGland, ORing, PistonGland, RodGland, ThermalState
from oring_designer.i18n import family_label, render_check, t
from oring_designer.sweep import summary_status, sweep, temperatures, to_frame, worst_by_family
from oring_designer.thermal import ThermalDataError
from oring_designer.tolerance import DEFAULT_MC_SAMPLES, Tolerance, monte_carlo, rss, worst_case
from ui import (UNITS, Banner, Card, OptionalValue, Page, PlotHolder, StatusTable, Table, ToleranceEditor,
                UnitSpin, add_row, combo, data_banner_text, dataset, heading, note, radio_row, result_rows,
                save_bytes, status_text)

# (key, label key, default mm, ISO feature, tolerance path) per gland type
DIMS = {
    "piston": [("bore", "ui.bore_diameter", 50.0, "hole", "gland.bore_diameter_m"),
               ("piston", "ui.piston_diameter", 49.9, "shaft", "gland.piston_diameter_m"),
               ("groove_d", "ui.groove_diameter_piston", 44.2, "shaft", "gland.groove_diameter_m"),
               ("width", "ui.groove_width", 4.8, "hole", "gland.groove_width_m"),
               ("radius", "ui.corner_radius", 0.3, None, "gland.corner_radius_m")],
    "rod": [("rod", "ui.rod_diameter", 20.0, "shaft", "gland.rod_diameter_m"),
            ("throat", "ui.throat_diameter", 20.1, "hole", "gland.throat_diameter_m"),
            ("groove_d", "ui.groove_diameter_rod", 26.0, "hole", "gland.groove_diameter_m"),
            ("width", "ui.groove_width", 4.8, "hole", "gland.groove_width_m"),
            ("radius", "ui.corner_radius", 0.3, None, "gland.corner_radius_m")],
    "face": [("groove_id", "ui.groove_id", 27.5, "shaft", "gland.groove_id_m"),
             ("groove_od", "ui.groove_od", 36.8, "hole", "gland.groove_od_m"),
             ("depth", "ui.groove_depth", 2.65, None, "gland.groove_depth_m"),
             ("radius", "ui.corner_radius", 0.3, None, "gland.corner_radius_m")],
}
RING_DEFAULT = {"piston": (43.7, 3.53), "rod": (19.8, 3.53), "face": (29.87, 3.53)}
DEFAULT_TOL_MM = {"radius": 0.0}  # others: +/-0.025 mm; O-ring: ID +/-0.30, CS +/-0.10
FIELD_LABEL = {"bore_diameter_m": "ui.bore_diameter", "piston_diameter_m": "ui.piston_diameter",
               "rod_diameter_m": "ui.rod_diameter", "throat_diameter_m": "ui.throat_diameter",
               "groove_width_m": "ui.groove_width", "corner_radius_m": "ui.corner_radius",
               "groove_id_m": "ui.groove_id", "groove_od_m": "ui.groove_od", "groove_depth_m": "ui.groove_depth",
               "id_m": "ui.oring_id", "cs_m": "ui.oring_cs"}


class Tabs(QWidget):
    """Tab bar + pages where only the current page takes space (fits a scrolling page)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bar = QTabBar()
        self.bar.setExpanding(False)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.addWidget(self.bar)
        self.pages: list[QWidget] = []
        self.bar.currentChanged.connect(self._show)

    def add(self, title: str) -> QVBoxLayout:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        self.pages.append(w)
        self.lay.addWidget(w)
        self.bar.addTab(title)
        self._show(self.bar.currentIndex())
        return lay

    def _show(self, i: int) -> None:
        for j, w in enumerate(self.pages):
            w.setVisible(i == j)


class CheckPage(Page):
    def __init__(self):
        super().__init__(t("ui.page_check"))
        ds = dataset()
        self._tol_result = None
        self._tol_sig = ""

        g = self.group(t("ui.materials"))
        self.seal = combo([(m.name, k) for k, m in ds.seal_materials.items()], "vmq")
        self.groove = combo([(m.name, k) for k, m in ds.housing_materials.items()], "al6061")
        self.temper = QComboBox()
        add_row(g, t("ui.seal_material"), self.seal)
        add_row(g, t("ui.groove_material"), self.groove)
        add_row(g, t("ui.temper"), self.temper)
        self.mating_on = QCheckBox(t("ui.mating_separate"))
        g.addWidget(self.mating_on, g.rowCount(), 0, 1, 2)
        self.mating = combo([(m.name, k) for k, m in ds.housing_materials.items()], "al6061")
        self.mating_delta = UnitSpin("dtemp", 0.0, signed=True)
        self.mat_rows = [add_row(g, t("ui.mating_material"), self.mating),
                         add_row(g, t("ui.mating_delta"), self.mating_delta)]
        self.mg = g
        self.groove.currentIndexChanged.connect(self._fill_tempers)
        self._fill_tempers()

        g = self.group(t("ui.gland"))
        self.kind = radio_row([(k, t(f"ui.{k}")) for k in ("piston", "rod", "face")], "piston")
        add_row(g, t("ui.gland_type"), self.kind)
        self.direction = radio_row([("internal", t("ui.internal")), ("external", t("ui.external"))], "internal")
        self.dir_row = add_row(g, t("ui.pressure_direction"), self.direction)
        self.full_ecc = QCheckBox(t("ui.full_eccentricity"))
        self.full_ecc.setChecked(True)
        g.addWidget(self.full_ecc, g.rowCount(), 0, 1, 3)
        self.ecc = UnitSpin("length", 0.0)
        self.ecc_row = add_row(g, t("ui.eccentricity"), self.ecc)
        self.gg = g
        hint = note(t("desktop.tol_note"))
        g.addWidget(hint, g.rowCount(), 0, 1, 3)
        # one dimension grid per gland type; only the active one is shown
        self.dim_boxes, self.dim_value, self.dim_tol = {}, {}, {}
        for kind, rows in DIMS.items():
            box = QWidget()
            grid = QGridLayout(box)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setColumnStretch(1, 1)
            grid.setColumnStretch(2, 2)
            for i, (key, label, mm, feat, _) in enumerate(rows):
                v = UnitSpin("length", mm * 1e-3)
                d = DEFAULT_TOL_MM.get(key, 0.025) * 1e-3
                tol = ToleranceEditor((-d, d), feat)
                lab = QLabel(t(label))
                lab.setWordWrap(True)
                grid.addWidget(lab, i, 0)
                grid.addWidget(v, i, 1)
                grid.addWidget(tol, i, 2)
                self.dim_value[(kind, key)] = v
                self.dim_tol[(kind, key)] = tol
                v.edited.connect(lambda tol=tol, v=v: tol.set_nominal(v.si()))
                tol.set_nominal(v.si())
                self.watch(v, tol)
            g.addWidget(box, g.rowCount(), 0, 1, 3)
            self.dim_boxes[kind] = box

        g = self.group(t("ui.oring"))
        self.ring = {}
        for kind, (id_mm, cs_mm) in RING_DEFAULT.items():
            self.ring[kind] = (UnitSpin("length", id_mm * 1e-3), ToleranceEditor((-0.30e-3, 0.30e-3), None),
                               UnitSpin("length", cs_mm * 1e-3), ToleranceEditor((-0.10e-3, 0.10e-3), None))
        self.ring_box = {}
        for kind, (rid, rid_t, rcs, rcs_t) in self.ring.items():
            box = QWidget()
            grid = QGridLayout(box)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setColumnStretch(1, 1)
            grid.setColumnStretch(2, 2)
            for i, (lab, v, tol) in enumerate(((t("ui.oring_id"), rid, rid_t), (t("ui.oring_cs"), rcs, rcs_t))):
                grid.addWidget(QLabel(lab), i, 0)
                grid.addWidget(v, i, 1)
                grid.addWidget(tol, i, 2)
                self.watch(v, tol)
            g.addWidget(box, g.rowCount(), 0, 1, 3)
            self.ring_box[kind] = box
        self.hardness = UnitSpin("plain", 70.0, plain_range=(30.0, 95.0), decimals=0, step=5.0)
        self.swell = UnitSpin("plain", 0.0, plain_range=(-0.2, 0.5), decimals=2, step=0.01)
        self.cs_method = combo([(t(f"ui.cs_{k}"), k) for k in ("volume_centroid", "volume_id", "parker_observed")])
        add_row(g, t("ui.hardness"), self.hardness)
        add_row(g, t("ui.swell"), self.swell)
        add_row(g, t("ui.cs_method"), self.cs_method)

        g = self.group(t("ui.operating"))
        self.pressure = UnitSpin("pressure", 50e5)
        self.fluid = combo([(t("ui.no_fluid"), None)] + [(f.name, k) for k, f in ds.fluids.items()])
        add_row(g, t("ui.pressure"), self.pressure)
        add_row(g, t("ui.fluid"), self.fluid)

        g = self.group(t("ui.tp_limits"))
        self.tp = {}
        for name, label in (("squeeze_max", "ui.out_squeeze_max"), ("fill_max", "ui.fill_max_label"),
                            ("fill_hard_max", "ui.fill_hard_max_label"), ("stretch_max", "ui.out_stretch")):
            self.tp[name] = OptionalValue(UnitSpin("plain", 0.0, plain_range=(0.0, 1.0), decimals=3, step=0.01))
            add_row(g, t(label), self.tp[name])
        self.tp_box = g.parentWidget()
        self.form.addStretch(1)

        self.watch(self.seal, self.groove, self.temper, self.mating_on, self.mating, self.mating_delta, self.kind,
                   self.direction, self.full_ecc, self.ecc, self.hardness, self.swell, self.cs_method,
                   self.pressure, self.fluid, *self.tp.values())

        # ------------------------------------------------------------------ results
        self.tabs = Tabs()
        self.results.addWidget(self.tabs)
        self._build_point(self.tabs.add(t("desktop.tab_point")))
        self._build_sweep(self.tabs.add(t("desktop.tab_sweep")))
        self._build_tol(self.tabs.add(t("desktop.tab_tol")))
        self._build_section(self.tabs.add(t("desktop.tab_section")))
        self._build_outputs(self.tabs.add(t("desktop.tab_outputs")))
        self.schedule()

    # ---------------------------------------------------------------------- result tabs
    def _build_point(self, lay: QVBoxLayout) -> None:
        g = QGridLayout()
        self.T_seal = UnitSpin("temp", UNITS.T_ref_K)
        self.T_housing = UnitSpin("temp", UNITS.T_ref_K)
        add_row(g, t("ui.T_seal"), self.T_seal)
        add_row(g, t("ui.T_housing"), self.T_housing)
        g.setColumnStretch(2, 2)
        lay.addLayout(g)
        self.watch(self.T_seal, self.T_housing)
        self.point_banner = Banner()
        self.point_overall = heading("")
        self.point_summary = note()
        self.point_table = StatusTable()
        for w in (self.point_banner, self.point_overall, self.point_summary, self.point_table):
            lay.addWidget(w)

    def _build_sweep(self, lay: QVBoxLayout) -> None:
        g = QGridLayout()
        self.T_min = UnitSpin("temp", 200.0)
        self.T_max = UnitSpin("temp", 300.0)
        self.T_step = UnitSpin("dtemp", 5.0)
        self.mode = radio_row([(k, t(f"ui.mode_{k}")) for k in ("equilibrium", "lag")], "equilibrium")
        self.delta = UnitSpin("dtemp", 10.0, signed=True)
        add_row(g, t("ui.T_min"), self.T_min)
        add_row(g, t("ui.T_max"), self.T_max)
        add_row(g, t("ui.T_step"), self.T_step)
        add_row(g, t("ui.mode"), self.mode)
        add_row(g, t("ui.delta_T"), self.delta)
        g.setColumnStretch(2, 2)
        lay.addLayout(g)
        self.watch(self.T_min, self.T_max, self.T_step, self.mode, self.delta)
        self.sweep_banner = Banner()
        self.sweep_overall = heading("")
        self.sweep_table = StatusTable()
        self.sweep_plot = PlotHolder()
        self.clear_plot = PlotHolder()
        btn = QPushButton(t("ui.download_csv"))
        btn.clicked.connect(self._save_csv)
        for w in (self.sweep_banner, self.sweep_overall, heading(t("ui.results_sweep"), 13), self.sweep_table,
                  self.sweep_plot, self.clear_plot, btn):
            lay.addWidget(w)
        self._df = None

    def _build_tol(self, lay: QVBoxLayout) -> None:
        lay.addWidget(note(t("desktop.tol_not_run")))
        g = QGridLayout()
        self.tol_T_seal = UnitSpin("temp", UNITS.T_ref_K)
        self.tol_T_housing = UnitSpin("temp", UNITS.T_ref_K)
        self.wc_temps = QCheckBox(t("desktop.wc_temps_range"))
        self.mc_n = QSpinBox()
        self.mc_n.setRange(100, 200_000)
        self.mc_n.setSingleStep(1000)
        self.mc_n.setValue(DEFAULT_MC_SAMPLES)
        self.mc_dist = radio_row([(k, t(f"ui.dist_{k}")) for k in ("normal", "uniform")], "normal")
        self.mc_seed = QSpinBox()
        self.mc_seed.setRange(0, 10**6)
        self.mc_seed.setValue(1)
        add_row(g, t("ui.T_seal"), self.tol_T_seal)
        add_row(g, t("ui.T_housing"), self.tol_T_housing)
        g.addWidget(self.wc_temps, g.rowCount(), 0, 1, 2)
        add_row(g, t("ui.mc_n"), self.mc_n)
        add_row(g, t("ui.mc_dist"), self.mc_dist)
        add_row(g, t("ui.mc_seed"), self.mc_seed)
        g.setColumnStretch(2, 2)
        lay.addLayout(g)
        for w in (self.tol_T_seal, self.tol_T_housing, self.wc_temps, self.mc_n, self.mc_dist, self.mc_seed):
            self.watch(w)
        self.run_btn = QPushButton(t("desktop.run_tol"))
        self.run_btn.setStyleSheet("font-weight: 600; padding: 6px 14px;")
        self.run_btn.clicked.connect(self._run_tol)
        lay.addWidget(self.run_btn)
        self.tol_banner = Banner()
        lay.addWidget(self.tol_banner)
        self.tol_out = QWidget()
        out = QVBoxLayout(self.tol_out)
        out.setContentsMargins(0, 0, 0, 0)
        self.tol_summary = Table()
        self.tol_wc = StatusTable()
        self.tol_rate = Card()
        self.tol_family = Table()
        self.tol_hist = QGridLayout()
        self.tol_sens = Table()
        for w in (heading(t("ui.summary_table"), 13), self.tol_summary, heading(t("ui.wc_results"), 13), self.tol_wc,
                  heading(t("ui.mc_rates"), 13), self.tol_rate, self.tol_family, heading(t("ui.histograms"), 13)):
            out.addWidget(w)
        out.addLayout(self.tol_hist)
        out.addWidget(heading(t("ui.sensitivities"), 13))
        out.addWidget(self.tol_sens)
        self.tol_out.hide()
        lay.addWidget(self.tol_out)
        self._hist = []

    def _build_section(self, lay: QVBoxLayout) -> None:
        self.side = radio_row([(k, t(f"plots.side_{k}")) for k in ("nominal", "tight", "wide")], "nominal")
        self.watch(self.side)
        lay.addWidget(self.side)
        self.section = PlotHolder()
        lay.addWidget(self.section)

    def _build_outputs(self, lay: QVBoxLayout) -> None:
        for text, fn in ((t("desktop.save_pdf"), self._save_pdf), (t("desktop.save_zip"), self._save_zip),
                         (t("desktop.save_dxf"), self._save_dxf)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            lay.addWidget(b)
        self.out_msg = note()
        lay.addWidget(self.out_msg)

    # ---------------------------------------------------------------------- inputs -> design
    def _fill_tempers(self) -> None:
        h = dataset().housing_materials[self.groove.currentData()]
        self.temper.blockSignals(True)
        self.temper.clear()
        for x in h.tempers:
            self.temper.addItem(x.name, x.id)
        self.temper.blockSignals(False)

    def _visibility(self, kind: str) -> None:
        for k, box in self.dim_boxes.items():
            box.setVisible(k == kind)
        for k, box in self.ring_box.items():
            box.setVisible(k == kind)
        face = kind == "face"
        for w in (self.direction, self.gg.itemAtPosition(self.dir_row, 0).widget()):
            w.setVisible(face)
        self.full_ecc.setVisible(not face)
        ecc_on = not face and not self.full_ecc.isChecked()
        for w in (self.ecc, self.gg.itemAtPosition(self.ecc_row, 0).widget()):
            w.setVisible(ecc_on)
        on = self.mating_on.isChecked()
        for r in self.mat_rows:
            for c in (0, 1):
                self.mg.itemAtPosition(r, c).widget().setVisible(on)
        tp = dataset().seal_materials[self.seal.currentData()].group == "thermoplastic"
        self.tp_box.setVisible(tp)
        self.side.setVisible(not face)
        self.clear_plot.setVisible(not face)

    def design(self) -> tuple[Design, str, dict[str, Tolerance], float]:
        kind = self.kind.key()
        v = {key: self.dim_value[(kind, key)].si() for key, *_ in DIMS[kind]}
        ecc = None if kind == "face" or self.full_ecc.isChecked() else self.ecc.si()
        if kind == "piston":
            gland = PistonGland(v["bore"], v["piston"], v["groove_d"], v["width"], v["radius"], ecc)
        elif kind == "rod":
            gland = RodGland(v["rod"], v["throat"], v["groove_d"], v["width"], v["radius"], ecc)
        else:
            gland = FaceGland(v["groove_id"], v["groove_od"], v["depth"], self.direction.key(), v["radius"])
        rid, rid_t, rcs, rcs_t = self.ring[kind]
        mating = self.mating.currentData() if self.mating_on.isChecked() else None
        seal = self.seal.currentData()
        design = Design(gland=gland, oring=ORing(rid.si(), rcs.si()), seal_material=seal,
                        groove_material=self.groove.currentData(), mating_material=mating,
                        pressure_Pa=self.pressure.si(), hardness_shore_a=self.hardness.si(),
                        fluid=self.fluid.currentData(), cs_method=self.cs_method.currentData(),
                        swell=self.swell.si())
        tols: dict[str, Tolerance] = {}
        for key, _, _, _, path in DIMS[kind]:
            lo, hi = self.dim_tol[(kind, key)].deviations()
            if lo or hi:
                tols[path] = Tolerance(lo, hi)
        for tol, path in ((rid_t, "oring.id_m"), (rcs_t, "oring.cs_m")):
            lo, hi = tol.deviations()
            if lo or hi:
                tols[path] = Tolerance(lo, hi)
        mating_delta = self.mating_delta.si() if self.mating_on.isChecked() else 0.0
        return design, kind, tols, mating_delta

    def _dataset(self, design: Design, kind: str):
        ds = dataset()
        if ds.seal_materials[design.seal_material].group != "thermoplastic":
            return ds
        vals = {k: w.si() for k, w in self.tp.items() if w.si() is not None}
        return with_rule_overrides(ds, "thermoplastic", "static_face" if kind == "face" else "static_radial", vals)

    # ---------------------------------------------------------------------- compute
    def recompute(self) -> None:
        kind = self.kind.key()
        self._visibility(kind)
        design, kind, tols, mating_delta = self.design()
        U = UNITS
        Ln = U.num_L
        g = design.gland

        def tl(path, value):
            tv = tols.get(path)
            return Ln(value, (tv.lower_m, tv.upper_m) if tv else None)

        if kind == "piston":
            dims = {"bore": tl("gland.bore_diameter_m", g.bore_diameter_m),
                    "piston": tl("gland.piston_diameter_m", g.piston_diameter_m),
                    "groove_d": tl("gland.groove_diameter_m", g.groove_diameter_m),
                    "width": tl("gland.groove_width_m", g.groove_width_m),
                    "depth": Ln((g.bore_diameter_m - g.groove_diameter_m) / 2),
                    "gap": Ln(g.bore_diameter_m - g.piston_diameter_m)}
        elif kind == "rod":
            dims = {"rod": tl("gland.rod_diameter_m", g.rod_diameter_m),
                    "throat": tl("gland.throat_diameter_m", g.throat_diameter_m),
                    "groove_d": tl("gland.groove_diameter_m", g.groove_diameter_m),
                    "width": tl("gland.groove_width_m", g.groove_width_m),
                    "depth": Ln((g.groove_diameter_m - g.rod_diameter_m) / 2),
                    "gap": Ln(g.throat_diameter_m - g.rod_diameter_m)}
        else:
            dims = {"groove_id": tl("gland.groove_id_m", g.groove_id_m), "groove_od": tl("gland.groove_od_m", g.groove_od_m),
                    "width": Ln((g.groove_od_m - g.groove_id_m) / 2), "depth": tl("gland.groove_depth_m", g.groove_depth_m)}
        dims |= {"radius": tl("gland.corner_radius_m", g.corner_radius_m), "cs": tl("oring.cs_m", design.oring.cs_m),
                 "ring_id": tl("oring.id_m", design.oring.id_m)}
        self.schematic.show_gland(kind, dims, getattr(g, "pressure_direction", "internal"))

        ds = self._dataset(design, kind)
        T_ref = U.T_ref_K
        mats = (design.seal_material, design.groove_material) + ((design.mating_material,) if design.mating_material else ())

        # operating point
        state = ThermalState(self.T_seal.si(), self.T_housing.si(), self.T_housing.si() + mating_delta, T_ref)
        try:
            st_point, res_point = run_checks(design, ds, state)
        except ThermalDataError as exc:
            self.point_banner.show_text(f"{t('ui.no_data_point')} ({exc})", "error")
            self.point_overall.setText("")
            self.point_summary.setText("")
            self.point_table.fill([], [])
        else:
            self.point_banner.show_text(data_banner_text(any(r.data_quality is not None and r.data_quality.needs_warning
                                                             for r in res_point), mats), "warn")
            self.point_overall.setText(f"{t('ui.overall')}: {status_text(overall_status(res_point))}")
            k = 1e3 if U.L == "mm" else 1 / 0.0254
            self.point_summary.setText(t("ui.geometry_summary", sq_min=st_point.squeeze_min, sq_max=st_point.squeeze_max,
                                         fill=st_point.fill, stretch=st_point.stretch, cs=st_point.cs_eff_m * k,
                                         unit=U.L))
            self.point_table.set_rows(result_rows(res_point))

        # sweep
        T_lo, T_hi = sorted((self.T_min.si(), self.T_max.si()))
        mode = self.mode.key()
        delta = self.delta.si() if mode == "lag" else 0.0
        self.delta.setEnabled(mode == "lag")
        pts = sweep(design, ds, temperatures(T_lo, T_hi, max(self.T_step.si(), 0.1)), mode, delta, mating_delta, T_ref)
        df = to_frame(pts)
        self._df = df
        worst = worst_by_family(pts)
        self.sweep_banner.show_text(data_banner_text(any(w.result.data_quality is not None and
                                                         w.result.data_quality.needs_warning for w in worst)
                                                     or df["no_data"].notna().any(), mats), "warn")
        self.sweep_overall.setText(f"{t('ui.overall')}: {status_text(summary_status(pts))}")
        self.sweep_table.set_rows([(w.result.status, render_check(w.result),
                                    f"{U.fmt_T(w.T_housing_K)} / {U.fmt_T(w.T_seal_K)}") for w in worst])
        seal = ds.seal_materials[design.seal_material]
        rules = ds.rule_set(seal.group, "static_face" if kind == "face" else "static_radial")
        band = rules.recommended_squeeze.band_for(design.oring.cs_m) if rules.recommended_squeeze else None
        low = seal.low_temp_limit_K.value if seal.low_temp_limit_K else None
        self.sweep_plot.set_figure(squeeze_fill_fig(
            df, U.T, squeeze_band=(band.min, band.max) if band else None,
            squeeze_max=rules.squeeze_max.value if rules.squeeze_max else None,
            fill_band=(rules.fill_min.value, rules.fill_max.value)
            if rules.fill_min and rules.fill_min.value is not None and rules.fill_max else None,
            fill_hard_max=rules.fill_hard_max.value if rules.fill_hard_max else None,
            low_temp_limit_K=low if seal.group == "elastomer" else None,
            low_temp_band_K=ds.common_rules.low_temp_warning_band_K.value, seal_offset_K=delta))
        if kind != "face":
            self.clear_plot.set_figure(clearance_fig(df, U.T, U.L))

        # section
        panels = []
        for T in (T_lo, T_ref, T_hi):
            label = U.fmt_T(T) + ("" if mode == "equilibrium" else f" / {U.fmt_T(T + delta)}")
            try:
                panels.append((label, run_checks(design, ds, ThermalState(T + delta, T, T + mating_delta, T_ref))[0]))
            except ThermalDataError:
                panels.append((label, None))
        side = self.side.key() if kind != "face" else "nominal"
        self.section.set_figure(section_fig(panels, kind, side, U.L, getattr(g, "pressure_direction", "internal"),
                                            g.corner_radius_m))

        self._report = ReportInput(design, T_ref, state, T_lo, T_hi, self.T_step.si(), mode, delta, mating_delta,
                                   U.L, U.T, U.P, tolerances=tols or None, mc_samples=self.mc_n.value(),
                                   mc_distribution=self.mc_dist.key(), mc_seed=self.mc_seed.value())
        self._design = design
        if self._tol_result is not None and self._tol_sig != self._signature():
            self.tol_banner.show_text(t("desktop.tol_stale"), "info")
        elif self._tol_result is not None:
            self.tol_banner.show_text("")

    def _signature(self) -> str:
        design, kind, tols, mating_delta = self.design()
        return repr((design, tols, mating_delta, self.tol_T_seal.si(), self.tol_T_housing.si(), self.wc_temps.isChecked(),
                     self.T_min.si(), self.T_max.si(), self.mc_n.value(), self.mc_dist.key(), self.mc_seed.value(),
                     UNITS.T_ref_K, {k: w.si() for k, w in self.tp.items()}))

    # ---------------------------------------------------------------------- tolerance analysis
    def _run_tol(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self._tol()
            self.tol_banner.show_text("")
        except Exception as exc:  # noqa: BLE001
            self.tol_banner.show_text(t("ui.tol_error", error=exc), "error")
        finally:
            QApplication.restoreOverrideCursor()

    def _tol(self) -> None:
        design, kind, tols, mating_delta = self.design()
        if not tols:
            raise ValueError(t("ui.tolerances"))
        ds = self._dataset(design, kind)
        U = UNITS
        T_ref = U.T_ref_K
        state = ThermalState(self.tol_T_seal.si(), self.tol_T_housing.si(), self.tol_T_housing.si() + mating_delta, T_ref)
        states = [state]
        if self.wc_temps.isChecked():
            states += [ThermalState(T, T, T + mating_delta, T_ref) for T in sorted((self.T_min.si(), self.T_max.si()))]
        n, dist, seed = self.mc_n.value(), self.mc_dist.key(), self.mc_seed.value()
        wc = worst_case(design, tols, ds, states)
        rs = rss(design, tols, ds, state)
        mc = monte_carlo(design, tols, ds, state, n, dist, seed)
        self._tol_result = (wc, rs, mc)
        self._tol_sig = self._signature()

        nominal = wc.table[wc.table.corner == "nominal"].iloc[0]
        outputs = ["squeeze_min", "squeeze_max", "fill", "stretch", "max_extrusion_gap_m"]
        if kind != "piston":
            outputs.append("circumferential_compression")
        if kind == "face":
            outputs.remove("max_extrusion_gap_m")

        def fmt(key, v):
            if pd.isna(v):
                return "–"
            return U.fmt_L(v) if key.endswith("_m") else f"{v:.2%}"

        rows = []
        for k in outputs:
            s = mc.samples[k]
            rows.append([t(f"ui.out_{k}"), fmt(k, nominal[k]), f"{fmt(k, wc.output_min[k])} – {fmt(k, wc.output_max[k])}",
                         f"{fmt(k, rs.low(k))} – {fmt(k, rs.high(k))}", f"{fmt(k, s.min())} – {fmt(k, s.max())}",
                         fmt(k, s.mean())])
        self.tol_summary.fill([t("ui.col_output"), t("ui.col_nominal"), t("ui.col_wc"), t("ui.col_rss"), t("ui.col_mc"),
                               t("ui.col_mc_mean")], rows)
        order = {"FAIL": 0, "WARN": 1, "PASS": 2}
        items = sorted(wc.worst_results.values(), key=lambda rv: order[rv[0].status.value])
        self.tol_wc.set_rows([(r.status, render_check(r), None) for r, _ in items])
        self.tol_rate.set(t("ui.overall_pass_rate"), f"{mc.overall_rates['PASS']:.1%}")
        fr = mc.family_rates
        self.tol_family.fill([t("ui.col_family"), status_text("PASS"), status_text("WARN"), status_text("FAIL")],
                             [[family_label(f)] + [f"{fr.loc[f, c]:.1%}" if c in fr.columns else "–"
                                                   for c in ("PASS", "WARN", "FAIL")] for f in fr.index])

        seal = ds.seal_materials[design.seal_material]
        rules = ds.rule_set(seal.group, "static_face" if kind == "face" else "static_radial")
        band = rules.recommended_squeeze.band_for(design.oring.cs_m) if rules.recommended_squeeze else None

        def lim(rule):
            return rule.value if rule is not None and rule.value is not None else None

        limits = {"squeeze_min": [(band.min, t("ui.band_min"))] if band else [],
                  "squeeze_max": ([(band.max, t("ui.band_max"))] if band else [])
                  + ([(lim(rules.squeeze_max), t("ui.limit"))] if lim(rules.squeeze_max) else []),
                  "fill": [(v, t("ui.limit")) for v in (lim(rules.fill_max), lim(rules.fill_hard_max)) if v],
                  "stretch": [(lim(rules.stretch_max), t("ui.limit"))] if lim(rules.stretch_max) else []}
        if design.hardness_shore_a is not None and seal.group == "elastomer":
            allowed, _ = allowed_extrusion_gap_m(ds.extrusion_limits, design.pressure_Pa, design.hardness_shore_a,
                                                 seal.id in ("vmq", "pvmq"))
            if allowed is not None:
                limits["max_extrusion_gap_m"] = [(allowed, t("ui.allowed"))]
        for h in self._hist:
            h.setParent(None)
            h.deleteLater()
        self._hist = []
        for i, k in enumerate(outputs):
            is_len = k.endswith("_m")
            scale = (1e3 if U.L == "mm" else 1 / 0.0254) if is_len else 1.0
            ph = PlotHolder()
            ph.set_figure(histogram_fig(mc.samples[k], t(f"ui.out_{k}"), limits.get(k),
                                        [(wc.output_min[k], wc.output_max[k], t("ui.wc_range")),
                                         (rs.low(k), rs.high(k), t("ui.rss_range"))],
                                        scale=scale, percent=not is_len, unit=f"[{U.L}]" if is_len else ""))
            self.tol_hist.addWidget(ph, i // 2, i % 2)
            self._hist.append(ph)
        per_unit = 1e-3 if U.L == "mm" else 0.0254
        sens = rs.sensitivities.loc[outputs].copy()
        for k in outputs:
            if not k.endswith("_m"):
                sens.loc[k] *= per_unit
        cols = list(sens.columns)
        self.tol_sens.fill([t("ui.col_output")] + [t(FIELD_LABEL.get(c.split(".")[1], "ui.groove_diameter_piston"))
                                                  if c.split(".")[1] != "groove_diameter_m" else
                                                  t("ui.groove_diameter_piston" if kind == "piston" else "ui.groove_diameter_rod")
                                                  for c in cols],
                           [[t(f"ui.out_{k}") + ("" if k.endswith("_m") else f" / {U.L}")] +
                            [f"{sens.loc[k, c]:.4g}" for c in cols] for k in outputs])
        self.tol_out.show()

    # ---------------------------------------------------------------------- outputs
    def _save_csv(self) -> None:
        if self._df is not None:
            save_bytes(self, t("ui.download_csv"), "tarama.csv", "CSV (*.csv)", self._df.to_csv(index=False).encode("utf-8"))

    def _save_pdf(self) -> None:
        from oring_designer.export.report import build_report, to_pdf

        self._save_report(lambda rep: to_pdf(rep), "o_ring_rapor.pdf", "PDF (*.pdf)", build_report)

    def _save_zip(self) -> None:
        from oring_designer.export.report import build_report, to_markdown_zip

        self._save_report(lambda rep: to_markdown_zip(rep), "o_ring_rapor.zip", "ZIP (*.zip)", build_report)

    def _save_report(self, conv, name, filt, build) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            data = conv(build(self._report, dataset()))
        finally:
            QApplication.restoreOverrideCursor()
        path = save_bytes(self, t("ui.build_report"), name, filt, data)
        if path:
            self.out_msg.setText(t("desktop.saved", path=path))

    def _save_dxf(self) -> None:
        from oring_designer.export.dxf import gland_profile, to_bytes

        path = save_bytes(self, t("ui.download_dxf"), "yuva_profili.dxf", "DXF (*.dxf)",
                          to_bytes(gland_profile(self._design, UNITS.L, "")))
        if path:
            self.out_msg.setText(t("desktop.saved", path=path))
