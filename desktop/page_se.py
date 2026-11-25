"""Yaylı Conta: Trelleborg Variseal (M2 rod / piston, HF face) groove from the catalogue for a
given rod / bore / face groove diameter, checked over the temperature range.

Inputs: gland type, the one diameter the catalogue is entered with, jacket and housing
materials, pressure, temperature range. Optional: own groove dimensions (checked against the
catalogue) and the seal section h x b (needed for the compression checks). The radial
clearance is taken equal to the catalogue S_max (user decision 2026-11-25)."""

from __future__ import annotations

from PySide6.QtWidgets import QPushButton

from oring_designer.checks import CheckResult, Status
from oring_designer.export.figures import se_fig
from oring_designer.i18n import render_check, t
from oring_designer.models import DataQuality
from oring_designer.spring_energized import SeDesign, SeGland, SeLimits, SeSeal, se_frame, se_sweep
from oring_designer.sweep import summary_status, temperatures, worst_by_family
from oring_designer.variseal import VarisealRangeError, face_groove, groove
from ui import (UNITS, Banner, Page, PlotHolder, StatusPill, StatusTable, UnitSpin, add_row, combo,
                data_banner_text, dataset, heading, radio_row, save_bytes)


class SpringPage(Page):
    def __init__(self):
        super().__init__(t("ui.page_se"), t("desktop.se_intro"))
        ds = dataset()

        g = self.group(t("ui.materials"), 0)
        self.jacket = combo([(m.name, k) for k, m in ds.seal_materials.items() if m.group == "thermoplastic"])
        self.groove_mat = combo([(m.name, k) for k, m in ds.housing_materials.items()], "ss304")
        add_row(g, t("ui.jacket_material"), self.jacket)
        add_row(g, t("ui.groove_material"), self.groove_mat)

        g = self.group(t("ui.se_gland"), 0)
        self.kind = radio_row([(k, t(f"ui.{k}")) for k in ("piston", "rod", "face")], "piston")
        add_row(g, t("ui.gland_type"), self.kind)
        self.direction = radio_row([("internal", t("ui.internal")), ("external", t("ui.external"))], "internal")
        self.dir_row = add_row(g, t("ui.pressure_direction"), self.direction)
        self.D = UnitSpin("length", 50e-3)
        self.D_row = add_row(g, t("ui.bore_diameter"), self.D)
        self.gg = g

        g = self.group(t("desktop.se_manual"), 1, optional=True)
        self.m_groove = UnitSpin("length", 40.6e-3)
        self.m_part = UnitSpin("length", 49.8e-3)
        self.m_width = UnitSpin("length", 7.1e-3)
        self.m_depth = UnitSpin("length", 4.7e-3)
        self.mrow = {"groove": add_row(g, t("ui.groove_diameter_piston"), self.m_groove),
                     "part": add_row(g, t("ui.piston_diameter"), self.m_part),
                     "width": add_row(g, t("ui.groove_width"), self.m_width),
                     "depth": add_row(g, t("ui.groove_depth"), self.m_depth)}
        self.mg = g

        g = self.group(t("desktop.se_seal_dims"), 1, optional=True)
        self.h = UnitSpin("length", 4.9e-3)
        self.b = UnitSpin("length", 6.9e-3)
        add_row(g, t("ui.se_free_height"), self.h)
        add_row(g, t("ui.se_width"), self.b)

        g = self.group(t("ui.operating"), 1)
        self.pressure = UnitSpin("pressure", 50e5)
        self.T_min = UnitSpin("temp", 77.0)
        self.T_max = UnitSpin("temp", 300.0)
        add_row(g, t("ui.pressure"), self.pressure)
        add_row(g, t("ui.T_min"), self.T_min)
        add_row(g, t("ui.T_max"), self.T_max)
        self.end_columns()
        self.watch(self.jacket, self.groove_mat, self.kind, self.direction, self.D, self.groups[t("desktop.se_manual")],
                   self.m_groove, self.m_part, self.m_width, self.m_depth, self.groups[t("desktop.se_seal_dims")],
                   self.h, self.b, self.pressure, self.T_min, self.T_max)

        sm = self.summary
        self.overall = StatusPill()
        self.cat_banner = Banner()
        self.banner = Banner()
        self.seal_note = Banner()
        self.table = StatusTable()
        for w in (self.overall, self.cat_banner, self.banner, self.seal_note, heading(t("ui.se_results"), 13),
                  self.table):
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
        U = UNITS
        Ln = U.num_L
        kind = self.kind.key()
        face = kind == "face"
        direction = self.direction.key() if face else "internal"
        self._show(self.gg, self.dir_row, face)
        label = {"piston": "ui.bore_diameter", "rod": "ui.rod_diameter"}.get(kind) or \
            ("ui.groove_od" if direction == "internal" else "ui.groove_id")
        self.gg.itemAtPosition(self.D_row, 0).widget().setText(t(label))
        self._show(self.mg, self.mrow["groove"], not face)
        self._show(self.mg, self.mrow["part"], not face)
        self._show(self.mg, self.mrow["depth"], face)
        self.mg.itemAtPosition(self.mrow["groove"], 0).widget().setText(
            t("ui.groove_diameter_piston" if kind == "piston" else "ui.groove_diameter_rod"))
        self.mg.itemAtPosition(self.mrow["part"], 0).widget().setText(
            t("ui.piston_diameter" if kind == "piston" else "ui.throat_diameter"))

        D, p = self.D.si(), self.pressure.si()
        manual = self.groups[t("desktop.se_manual")].isChecked()
        msgs, extra = [], []
        try:
            cat = face_groove(direction, D, p) if face else groove(kind, D, p)
        except VarisealRangeError as exc:
            raise ValueError(str(exc)) from None
        if face:
            cat_groove, cat_width, cat_depth, s_max = D, cat.width_min_m, cat.depth_m, cat.s_max_m
            msgs.append(t("desktop.se_series_face", series=cat.series, h=U.fmt_L(cat.depth_m),
                          htol=Ln(cat.depth_tol_m), b=U.fmt_L(cat.width_min_m), r1=U.fmt_L(cat.r1_max_m),
                          dcls=cat.diameter_class, smax=U.fmt_L(s_max) if s_max else "–"))
        else:
            cat_groove, cat_width, s_max = cat.groove_diameter_m, cat.groove_width_m, cat.s_max_m
            cat_depth = None
            msgs.append(t("desktop.se_series", series=cat.series, groove=U.fmt_L(cat.groove_diameter_m),
                          gcls=cat.groove_class, width=U.fmt_L(cat.groove_width_m),
                          mcls=f"{t('ui.rod_diameter' if kind == 'rod' else 'ui.bore_diameter')} {cat.mating_class}",
                          r1=U.fmt_L(cat.r1_max_m), smax=U.fmt_L(s_max) if s_max else "–"))
        if not cat.standard_range:
            msgs.append(t("desktop.se_extended"))
        if s_max is None:
            msgs.append(t("desktop.se_backup"))
        if max(self.T_min.si(), self.T_max.si()) >= 353.15:
            msgs.append(t("desktop.se_hot"))
        c_cat = s_max or 0.0  # radial clearance = S_max (user decision 2026-11-25)

        if manual:
            groove_d = D if face else self.m_groove.si()
            width = self.m_width.si()
            depth = self.m_depth.si() if face else 0.0
            part = 0.0 if face else self.m_part.si()
            if not face and abs(groove_d - cat_groove) > 1e-6:
                extra.append(CheckResult("se_cat_groove", Status.WARN, groove_d, cat_groove,
                                         {"value": U.fmt_L(groove_d), "cat": U.fmt_L(cat_groove)}, DataQuality.VENDOR))
            if width < cat_width - 1e-9:
                extra.append(CheckResult("se_cat_width", Status.WARN, width, cat_width,
                                         {"value": U.fmt_L(width), "cat": U.fmt_L(cat_width)}, DataQuality.VENDOR))
            if face and abs(depth - cat_depth) > 1e-6:
                extra.append(CheckResult("se_cat_depth", Status.WARN, depth, cat_depth,
                                         {"value": U.fmt_L(depth), "cat": U.fmt_L(cat_depth)}, DataQuality.VENDOR))
        else:
            groove_d, width, depth = cat_groove, cat_width, (cat_depth or 0.0)
            part = 0.0 if face else (D - c_cat if kind == "piston" else D + c_cat)
            for w, v in ((self.m_groove, cat_groove), (self.m_width, cat_width), (self.m_part, part),
                         (self.m_depth, cat_depth or 0.0)):
                w.blockSignals(True)
                w.set_si(v)
                w.blockSignals(False)
        self.cat_banner.show_text("\n".join(msgs), "info")

        seal_on = self.groups[t("desktop.se_seal_dims")].isChecked()
        h, b = (self.h.si(), self.b.si()) if seal_on else (None, None)
        self.seal_note.show_text("" if seal_on else t("desktop.se_seal_dims_note"), "info")
        if kind == "piston":
            sk = {"bore": f"{Ln(D)} {cat.mating_class}", "piston": Ln(part),
                  "groove_d": f"{Ln(groove_d)} {cat.groove_class}", "depth": Ln((D - groove_d) / 2),
                  "gap": Ln(D - part)}
        elif kind == "rod":
            sk = {"rod": f"{Ln(D)} {cat.mating_class}", "throat": Ln(part),
                  "groove_d": f"{Ln(groove_d)} {cat.groove_class}", "depth": Ln((groove_d - D) / 2),
                  "gap": Ln(part - D)}
        else:
            sk = {("groove_od" if direction == "internal" else "groove_id"): f"{Ln(D)} {cat.diameter_class}",
                  "depth": Ln(depth)}
        sk["width"] = Ln(width) + (" min" if face else " +0.2/0")
        if seal_on:
            sk |= {"seal_h": Ln(h), "seal_b": Ln(b)}
        self.schematic.show_gland(kind, sk, direction, seal="spring")

        limits = SeLimits(extrusion_gap_max_m=None if face else s_max, gap_quality=DataQuality.VENDOR)
        design = SeDesign(gland=SeGland(kind, 0.0 if face else D, part, groove_d, width, depth, direction, None),
                          seal=SeSeal(h, b, None), limits=limits,
                          jacket_material=self.jacket.currentData(), groove_material=self.groove_mat.currentData())
        T_lo, T_hi = sorted((self.T_min.si(), self.T_max.si()))
        pts = se_sweep(design, dataset(), temperatures(T_lo, T_hi, max((T_hi - T_lo) / 60, 0.5)), "equilibrium",
                       0.0, 0.0, U.T_ref_K)
        df = se_frame(pts)
        self._df = df
        worst = [w for w in worst_by_family(pts) if w.result.code != "se_no_catalog_limits"]
        mats = (design.jacket_material, design.groove_material)
        self.banner.show_text(data_banner_text(df["no_data"].notna().any() or any(
            w.result.data_quality is not None and w.result.data_quality.needs_warning for w in worst), mats,
            (T_lo, T_hi)), "warn")
        rows = [(w.result.status, render_check(w.result), f"{U.fmt_T(w.T_housing_K)} / {U.fmt_T(w.T_seal_K)}")
                for w in worst] + [(r.status, render_check(r), "") for r in extra]
        status = summary_status(pts)
        if extra and status is Status.PASS:
            status = Status.WARN
        self.overall.set_status(status)
        self.table.set_rows(rows)
        self.plot.set_figure(se_fig(df, U.T, U.L, (None, None), None if face else s_max))

    def _save_csv(self) -> None:
        if self._df is not None:
            save_bytes(self, t("ui.download_csv"), "yayli_conta.csv", "CSV (*.csv)",
                       self._df.to_csv(index=False).encode("utf-8"))
