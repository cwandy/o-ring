"""Yaylı Conta: spring-energised seal check from catalogue dimensions over temperature
(desktop version of app/pages/4)."""

from __future__ import annotations

from PySide6.QtWidgets import QPushButton

from oring_designer.export.figures import se_fig
from oring_designer.i18n import render_check, t
from oring_designer.spring_energized import SeDesign, SeGland, SeLimits, SeSeal, se_frame, se_sweep
from oring_designer.sweep import summary_status, temperatures, worst_by_family
from ui import (UNITS, Banner, StatusPill, OptionalValue, Page, PlotHolder, StatusTable, UnitSpin, add_row, combo,
                data_banner_text, dataset, heading, note, radio_row, save_bytes, status_text)


class SpringPage(Page):
    def __init__(self):
        super().__init__(t("ui.page_se"), t("ui.se_intro") + " " + t("ui.se_example_note"))
        ds = dataset()

        g = self.group(t("ui.materials"))
        self.jacket = combo([(m.name, k) for k, m in ds.seal_materials.items() if m.group == "thermoplastic"])
        self.groove = combo([(m.name, k) for k, m in ds.housing_materials.items()], "ss304")
        self.mating = OptionalValue(combo([(m.name, k) for k, m in ds.housing_materials.items()], "ss304"))
        self.mating_delta = UnitSpin("dtemp", 0.0, signed=True)
        add_row(g, t("ui.jacket_material"), self.jacket)
        add_row(g, t("ui.groove_material"), self.groove)
        add_row(g, t("ui.mating_material"), self.mating)
        add_row(g, t("ui.mating_delta"), self.mating_delta)

        g = self.group(t("ui.se_gland"))
        self.kind = radio_row([(k, t(f"ui.{k}")) for k in ("piston", "rod", "face")], "piston")
        add_row(g, t("ui.gland_type"), self.kind)
        self.direction = radio_row([("internal", t("ui.internal")), ("external", t("ui.external"))], "internal")
        self.dir_row = add_row(g, t("ui.pressure_direction"), self.direction)
        # piston: bore / piston / groove bottom; rod: rod / throat / groove; face: groove wall + depth
        self.v = {
            ("piston", "mate"): UnitSpin("length", 50.0e-3), ("piston", "part"): UnitSpin("length", 49.9e-3),
            ("piston", "groove"): UnitSpin("length", 43.6e-3), ("rod", "mate"): UnitSpin("length", 20.0e-3),
            ("rod", "part"): UnitSpin("length", 20.1e-3), ("rod", "groove"): UnitSpin("length", 26.4e-3),
            ("face", "groove_internal"): UnitSpin("length", 40.0e-3),
            ("face", "groove_external"): UnitSpin("length", 30.0e-3), ("face", "depth"): UnitSpin("length", 3.2e-3),
        }
        labels = {("piston", "mate"): "ui.bore_diameter", ("piston", "part"): "ui.piston_diameter",
                  ("piston", "groove"): "ui.groove_diameter_piston", ("rod", "mate"): "ui.rod_diameter",
                  ("rod", "part"): "ui.throat_diameter", ("rod", "groove"): "ui.groove_diameter_rod",
                  ("face", "groove_internal"): "ui.se_groove_wall_face_internal",
                  ("face", "groove_external"): "ui.se_groove_wall_face_external", ("face", "depth"): "ui.groove_depth"}
        self.rows = {k: add_row(g, t(labels[k]), w) for k, w in self.v.items()}
        self.width = UnitSpin("length", 4.5e-3)
        add_row(g, t("ui.groove_width"), self.width)
        self.full_ecc = OptionalValue(UnitSpin("length", 0.0))
        self.ecc_row = add_row(g, t("ui.eccentricity") + " (" + t("desktop.tol_custom").lower() + ")", self.full_ecc)
        self.gg = g

        g = self.group(t("ui.se_seal"))
        self.h = UnitSpin("length", 3.4e-3)
        self.b = UnitSpin("length", 4.0e-3)
        self.d_static = {("piston", "internal"): UnitSpin("length", 43.6e-3), ("rod", "internal"): UnitSpin("length", 26.4e-3),
                         ("face", "internal"): UnitSpin("length", 40.0e-3), ("face", "external"): UnitSpin("length", 30.0e-3)}
        add_row(g, t("ui.se_free_height"), self.h)
        add_row(g, t("ui.se_width"), self.b)
        st_labels = {("piston", "internal"): "ui.se_static_piston", ("rod", "internal"): "ui.se_static_rod",
                     ("face", "internal"): "ui.se_static_face_internal", ("face", "external"): "ui.se_static_face_external"}
        self.st_rows = {k: add_row(g, t(st_labels[k]), w) for k, w in self.d_static.items()}
        self.sg = g

        g = self.group(t("ui.se_limits"))
        self.cmin = OptionalValue(UnitSpin("length", 0.10e-3))
        self.cmax = OptionalValue(UnitSpin("length", 0.40e-3))
        self.gmax = OptionalValue(UnitSpin("length", 0.10e-3))
        self.axmin = UnitSpin("length", 0.0)
        self.fit = OptionalValue(UnitSpin("plain", 0.0, plain_range=(-1.0, 1.0), decimals=4, step=0.001))
        add_row(g, t("ui.se_comp_min"), self.cmin)
        add_row(g, t("ui.se_comp_max"), self.cmax)
        self.gmax_row = add_row(g, t("ui.se_gap_max"), self.gmax)
        add_row(g, t("ui.se_axial_min"), self.axmin)
        add_row(g, t("ui.se_fit_min"), self.fit)
        self.lg = g

        g = self.group(t("ui.sweep"))
        self.T_min = UnitSpin("temp", 77.0)
        self.T_max = UnitSpin("temp", 300.0)
        self.step = UnitSpin("dtemp", 5.0)
        self.mode = radio_row([(k, t(f"ui.mode_{k}")) for k in ("equilibrium", "lag")], "equilibrium")
        self.delta = UnitSpin("dtemp", 10.0, signed=True)
        for label, w in ((t("ui.T_min"), self.T_min), (t("ui.T_max"), self.T_max), (t("ui.T_step"), self.step),
                         (t("ui.mode"), self.mode), (t("ui.delta_T"), self.delta)):
            add_row(g, label, w)
        self.watch(self.jacket, self.groove, self.mating, self.mating_delta, self.kind, self.direction, *self.v.values(),
                   self.width, self.full_ecc, self.h, self.b, *self.d_static.values(), self.cmin, self.cmax, self.gmax,
                   self.axmin, self.fit, self.T_min, self.T_max, self.step, self.mode, self.delta)

        sm = self.summary
        self.overall = StatusPill()
        self.banner = Banner()
        self.table = StatusTable()
        for w in (self.overall, self.banner, heading(t("ui.se_results"), 13), self.table):
            sm.addWidget(w)
        sm.addStretch(1)
        r = self.details
        self.plot = PlotHolder()
        btn = QPushButton(t("ui.download_csv"))
        btn.clicked.connect(self._save_csv)
        r.addWidget(self.plot)
        r.addWidget(btn)
        self._df = None
        self.schedule()

    def _show(self, grid, row: int, on: bool) -> None:
        for c in (0, 1):
            item = grid.itemAtPosition(row, c)
            if item is not None:
                item.widget().setVisible(on)

    def recompute(self) -> None:
        kind = self.kind.key()
        face = kind == "face"
        direction = self.direction.key() if face else "internal"
        self._show(self.gg, self.dir_row, face)
        for (k, name), row in self.rows.items():
            on = k == kind and (not face or name == "depth" or name == f"groove_{direction}")
            self._show(self.gg, row, on)
        self._show(self.gg, self.ecc_row, not face)
        self._show(self.lg, self.gmax_row, not face)
        for key, row in self.st_rows.items():
            self._show(self.sg, row, key == (kind, direction))
        mode = self.mode.key()
        self.delta.setEnabled(mode == "lag")

        U = UNITS
        Ln = U.num_L
        if face:
            mate = part = 0.0
            groove = self.v[("face", f"groove_{direction}")].si()
            depth = self.v[("face", "depth")].si()
            ecc = None
        else:
            mate, part, groove = (self.v[(kind, n)].si() for n in ("mate", "part", "groove"))
            depth = 0.0
            ecc = self.full_ecc.si()
        width, h, b = self.width.si(), self.h.si(), self.b.si()
        d_static = self.d_static[(kind, direction)].si()
        if kind == "piston":
            sk = {"bore": Ln(mate), "piston": Ln(part), "groove_d": Ln(groove), "depth": Ln((mate - groove) / 2),
                  "gap": Ln(mate - part)}
        elif kind == "rod":
            sk = {"rod": Ln(mate), "throat": Ln(part), "groove_d": Ln(groove), "depth": Ln((groove - mate) / 2),
                  "gap": Ln(part - mate)}
        else:
            sk = {("groove_od" if direction == "internal" else "groove_id"): Ln(groove), "depth": Ln(depth)}
        sk |= {"width": Ln(width), "seal_h": Ln(h), "seal_b": Ln(b), "static_d": Ln(d_static)}
        self.schematic.show_gland(kind, sk, direction, seal="spring")

        mating = self.mating.si()
        design = SeDesign(gland=SeGland(kind, mate, part, groove, width, depth, direction, ecc),
                          seal=SeSeal(h, b, d_static),
                          limits=SeLimits(self.cmin.si(), self.cmax.si(), None if face else self.gmax.si(),
                                          self.axmin.si(), self.fit.si()),
                          jacket_material=self.jacket.currentData(), groove_material=self.groove.currentData(),
                          mating_material=mating)
        T_lo, T_hi = sorted((self.T_min.si(), self.T_max.si()))
        delta = self.delta.si() if mode == "lag" else 0.0
        pts = se_sweep(design, dataset(), temperatures(T_lo, T_hi, max(self.step.si(), 0.1)), mode, delta,
                       self.mating_delta.si() if mating else 0.0, U.T_ref_K)
        df = se_frame(pts)
        self._df = df
        worst = worst_by_family(pts)
        mats = (design.jacket_material, design.groove_material) + ((mating,) if mating else ())
        self.banner.show_text(data_banner_text(df["no_data"].notna().any() or any(
            w.result.data_quality is not None and w.result.data_quality.needs_warning for w in worst), mats), "warn")
        self.overall.set_status(summary_status(pts))
        self.table.set_rows([(w.result.status, render_check(w.result), f"{U.fmt_T(w.T_housing_K)} / {U.fmt_T(w.T_seal_K)}")
                             for w in worst])
        self.plot.set_figure(se_fig(df, U.T, U.L, (self.cmin.si(), self.cmax.si()), None if face else self.gmax.si()))

    def _save_csv(self) -> None:
        if self._df is not None:
            save_bytes(self, t("ui.download_csv"), "yayli_conta.csv", "CSV (*.csv)",
                       self._df.to_csv(index=False).encode("utf-8"))
