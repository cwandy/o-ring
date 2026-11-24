"""Yuva Hesaplayıcı: groove depth, width, tolerances, temperature behaviour and forces from
material, cross-section, temperature range and pressure (desktop version of app/pages/0)."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QGridLayout, QHBoxLayout

from oring_designer.checks import Status, run_checks
from oring_designer.export.figures import envelope_fig, section_fig
from oring_designer.force import face_clamp_load, load_per_length
from oring_designer.gland_types import ThermalState
from oring_designer.groove_calc import GrooveInput, TemperatureRangeError, calculate
from oring_designer.i18n import render_check, t, t_list
from oring_designer.thermal import ThermalDataError
from ui import (UNITS, Banner, Card, StatusPill, OptionalValue, Page, PlotHolder, StatusTable, Table, UnitSpin, add_row,
                combo, data_banner_text, dataset, heading, note, radio_row, save_bytes, status_text)

CS_STD = [("AS568", v) for v in (1.78, 2.62, 3.53, 5.33, 6.99)] + [("ISO 3601", v) for v in (1.80, 2.65, 3.55, 5.30, 7.00)]


class CalcPage(Page):
    def __init__(self):
        super().__init__(t("ui.page_calc"), t("ui.calc_intro"))
        ds = dataset()

        g = self.group(t("ui.materials"), 0)
        self.seal = combo([(m.name, k) for k, m in ds.seal_materials.items()], "vmq")
        self.housing = combo([(m.name, k) for k, m in ds.housing_materials.items()], "ss304")
        self.compound = QComboBox()
        add_row(g, t("ui.seal_material"), self.seal)
        add_row(g, t("desktop.compound"), self.compound)
        add_row(g, t("ui.housing_material"), self.housing)
        self.seal.currentIndexChanged.connect(self._fill_compounds)
        self.compound.currentIndexChanged.connect(self._apply_compound)

        g = self.group(t("ui.gland"), 0)
        self.cs_std = combo([(f"{v:.2f} mm ({std})", (std, v)) for std, v in CS_STD] + [(t("ui.cs_custom"), None)])
        self.cs_std.setCurrentIndex(CS_STD.index(("AS568", 3.53)))
        self.cs_custom = UnitSpin("length", 2.5e-3)
        self.cs_tol = UnitSpin("length", 0.1e-3)  # thermoplastic rings only (elastomers: AS568 / ISO table)
        add_row(g, t("ui.cross_section"), self.cs_std)
        add_row(g, t("ui.cs_custom_value"), self.cs_custom)
        self.cs_tol_row = add_row(g, t("ui.cs_tol_opt").split(",")[0], self.cs_tol)
        self.gland = radio_row([("face", t("ui.gland_face")), ("radial", t("ui.gland_radial"))], "face")
        add_row(g, t("ui.gland_type"), self.gland)
        self.direction = radio_row([("internal", t("ui.internal")), ("external", t("ui.external"))], "internal")
        self.dir_row = add_row(g, t("ui.pressure_direction"), self.direction)
        self.g = g

        g = self.group(t("ui.force_title").split(" ve ")[0], 0)
        self.ring_id = OptionalValue(UnitSpin("length", 30e-3))
        self.q_manual = OptionalValue(UnitSpin("plain", 1.0, plain_range=(0.0, 1000.0), decimals=2, step=0.1))
        add_row(g, t("ui.ring_id_opt"), self.ring_id)
        add_row(g, t("desktop.force_manual"), self.q_manual)

        g = self.group(t("ui.operating"), 1)
        self.pressure = UnitSpin("pressure", 50e5)
        self.T_lo = UnitSpin("temp", 220.0)
        self.T_hi = UnitSpin("temp", 300.0)
        self.hardness = UnitSpin("plain", 70.0, plain_range=(50.0, 90.0), decimals=0, step=5.0)
        self.fluid = combo([(t("ui.no_fluid"), None)] + [(f.name, k) for k, f in ds.fluids.items()])
        add_row(g, t("ui.pressure"), self.pressure)
        add_row(g, t("ui.T_low"), self.T_lo)
        add_row(g, t("ui.T_high"), self.T_hi)
        self.hard_row = add_row(g, t("ui.hardness"), self.hardness)
        add_row(g, t("ui.fluid"), self.fluid)
        self.op = g
        self._fill_compounds()

        g = self.group(t("ui.optional_inputs"), 1, optional=True)
        self.tmin = OptionalValue(UnitSpin("plain", 0.15, plain_range=(0.0, 0.9), decimals=3, step=0.01))
        self.tmax = OptionalValue(UnitSpin("plain", 0.25, plain_range=(0.0, 0.9), decimals=3, step=0.01))
        self.fill_lim = OptionalValue(UnitSpin("plain", 0.85, plain_range=(0.3, 0.95), decimals=2, step=0.01))
        self.depth_tol = OptionalValue(UnitSpin("length", 0.05e-3))
        self.width_tol = OptionalValue(UnitSpin("length", 0.10e-3))
        self.stretch = UnitSpin("plain", 0.0, plain_range=(0.0, 0.05), decimals=3, step=0.005)
        for label, w in ((t("ui.target_min"), self.tmin), (t("ui.target_max"), self.tmax),
                         (t("ui.fill_limit_opt"), self.fill_lim), (t("ui.depth_tol_opt"), self.depth_tol),
                         (t("ui.width_tol_opt"), self.width_tol)):
            add_row(g, label, w)
        self.stretch_row = add_row(g, t("ui.install_stretch_opt"), self.stretch)
        self.optg = g
        self.end_columns()

        self.watch(self.compound, self.seal, self.housing, self.cs_std, self.cs_custom, self.cs_tol, self.gland, self.direction,
                   self.pressure, self.T_lo, self.T_hi, self.hardness, self.ring_id, self.q_manual, self.fluid,
                   self.tmin, self.tmax, self.fill_lim, self.depth_tol, self.width_tol, self.stretch)

        # ------------------------------------------------------------------ results
        sm = self.summary
        self.overall = StatusPill()
        self.banner = Banner()
        self.notes = Banner()
        sm.addWidget(self.overall)
        sm.addWidget(self.banner)
        sm.addWidget(self.notes)
        grid = QGridLayout()
        grid.setSpacing(6)
        self.cards = [Card() for _ in range(9)]  # 8: force (total / clamp)
        for i, c in enumerate(self.cards):
            grid.addWidget(c, i // 2, i % 2)
        sm.addLayout(grid)
        self.force_hint = Banner()
        sm.addWidget(self.force_hint)
        sm.addWidget(heading(t("ui.calc_checks"), 13))
        self.checks = StatusTable()
        sm.addWidget(self.checks)
        sm.addStretch(1)

        r = self.details
        r.addWidget(heading(t("ui.section_title_calc")))
        self.side = radio_row([(k, t(f"plots.side_{k}")) for k in ("nominal", "tight", "wide")], "nominal")
        self.watch(self.side)
        r.addWidget(self.side)
        self.section = PlotHolder()
        r.addWidget(self.section)
        r.addWidget(heading(t("ui.force_title")))
        self.force_table = Table()
        r.addWidget(self.force_table)
        fl = QHBoxLayout()
        self.force_cards = [Card() for _ in range(3)]
        for c in self.force_cards:
            fl.addWidget(c)
        r.addLayout(fl)
        self.force_note = note()
        r.addWidget(self.force_note)
        r.addWidget(heading(t("ui.temp_behaviour")))
        self.envelope = PlotHolder()
        r.addWidget(self.envelope)
        self.temp_table = Table()
        r.addWidget(self.temp_table)
        from PySide6.QtWidgets import QPushButton

        self.csv_btn = QPushButton(t("ui.download_csv"))
        self.csv_btn.clicked.connect(self._save_csv)
        r.addWidget(self.csv_btn)
        r.addWidget(heading(t("ui.method")))
        r.addWidget(note("\n".join(f"• {x}" for x in t_list("ui.method_items"))))
        self._per_T = None
        self.schedule()

    def _fill_compounds(self) -> None:
        from oring_designer.compounds import for_material

        from ui import style_popup
        self.compound.blockSignals(True)
        self.compound.clear()
        self.compound.addItem(t("desktop.compound_none"), None)
        for c in for_material(self.seal.currentData()):
            self.compound.addItem(c.name, c.id)
        self.compound.setCurrentIndex(1 if self.compound.count() > 1 else 0)
        self.compound.blockSignals(False)
        style_popup(self.compound)
        self._apply_compound()

    def _apply_compound(self) -> None:
        """A compound fixes the hardness (datasheet / specification grade)."""
        from oring_designer.compounds import compounds

        cid = self.compound.currentData()
        c = compounds().get(cid) if cid else None
        if c is not None and c.hardness_shore_a is not None:
            self.hardness.set_si(c.hardness_shore_a)
        self.hardness.setEnabled(c is None or c.hardness_shore_a is None)

    def _set_visible(self) -> None:
        face = self.gland.key() == "face"
        for w in (self.direction, self.g.itemAtPosition(self.dir_row, 0).widget()):
            w.setVisible(face)
        is_el = dataset().seal_materials[self.seal.currentData()].group == "elastomer"
        for w in (self.hardness, self.op.itemAtPosition(self.hard_row, 0).widget()):
            w.setVisible(is_el)
        for w in (self.cs_tol, self.g.itemAtPosition(self.cs_tol_row, 0).widget()):
            w.setVisible(not is_el)
        for w in (self.stretch, self.optg.itemAtPosition(self.stretch_row, 0).widget()):
            w.setVisible(not face)
        self.cs_custom.setEnabled(self.cs_std.currentData() is None)
        self.side.setVisible(not face)

    # ---------------------------------------------------------------------- compute
    def recompute(self) -> None:
        self._set_visible()
        ds = dataset()
        U = UNITS
        seal_id, housing_id = self.seal.currentData(), self.housing.currentData()
        is_el = ds.seal_materials[seal_id].group == "elastomer"
        gland = self.gland.key()
        direction = self.direction.key() if gland == "face" else "internal"
        std = self.cs_std.currentData()
        cs_m = std[1] * 1e-3 if std else self.cs_custom.si()
        ring_id = self.ring_id.si()
        cs_tol = None if is_el else self.cs_tol.si()  # elastomers: AS568 / ISO 3601-1 table
        sketch = "face" if gland == "face" else "piston"
        pending = {"depth": "…", "width": "…", "radius": "…", "cs": U.num_L(cs_m, cs_tol), "ring_id": U.num_L(ring_id)}
        self.schematic.show_gland(sketch, pending, direction)

        tmin, tmax = self.tmin.si(), self.tmax.si()
        target = (tmin, tmax) if tmin is not None and tmax is not None and tmin < tmax else None
        rules = ds.rule_set(ds.seal_materials[seal_id].group, "static_face" if gland == "face" else "static_radial")
        if target is None and rules.recommended_squeeze is None:
            raise ValueError(t("ui.target_required"))
        T_ref = U.T_ref_K
        inp = GrooveInput(
            seal_material=seal_id, cs_m=cs_m, gland=gland, T_min_K=min(self.T_lo.si(), self.T_hi.si()),
            T_max_K=max(self.T_lo.si(), self.T_hi.si()), T_ref_K=T_ref, pressure_Pa=self.pressure.si(),
            hardness_shore_a=self.hardness.si() if is_el else None, housing_material=housing_id,
            fluid=self.fluid.currentData(), face_direction=direction, cs_tol_m=cs_tol, target_squeeze=target,
            fill_limit=self.fill_lim.si(), depth_tol_m=self.depth_tol.si(), width_tol_m=self.width_tol.si(),
            install_stretch=self.stretch.si() if gland == "radial" else 0.0,
            compound=self.compound.currentData(),
            round_depth_m=0.0001 * 0.0254 if U.L == "in" else 0.01e-3,
            round_width_m=0.001 * 0.0254 if U.L == "in" else 0.05e-3,
        )
        try:
            res = calculate(inp, ds)
        except TemperatureRangeError as exc:
            if exc.usable is None:
                raise ValueError(t("ui.no_thermal_data")) from None
            raise ValueError(t("ui.usable_range", lo=U.fmt_T(exc.usable[0]), hi=U.fmt_T(exc.usable[1]))) from None

        worst = [r for r, _ in res.wc.worst_results.values()]
        self.banner.show_text(data_banner_text(any(r.data_quality is not None and r.data_quality.needs_warning
                                                   for r in worst), (seal_id, housing_id),
                                               (inp.T_min_K, inp.T_max_K)), "warn")
        notes = []
        for n in res.notes:
            if n == "backup_ring_required":
                notes.append(t("ui.backup_required"))
            elif n == "parker_row_nearest":
                notes.append(t("ui.parker_nearest"))
            elif n == "below_tr10":
                from oring_designer.compounds import compounds
                c = compounds()[self.compound.currentData()]
                notes.append(t("desktop.below_tr10", name=c.name, T=U.fmt_T(c.tr10_K)))
        if res.band_basis == "formula":
            from oring_designer.compounds import compounds
            c = compounds()[self.compound.currentData()]
            pb = res.parker_band
            notes.append(t("desktop.band_formula", cset=c.compression_set, cond=c.compression_set_conditions,
                           lo=res.target[0], hi=res.target[1])
                         + (t("desktop.band_parker_cmp", lo=pb[0], hi=pb[1]) if pb else ""))
        self.notes.show_text("\n".join(notes), "error" if {"backup_ring_required", "below_tr10"} & set(res.notes)
                             else "info")

        L, Ln = U.fmt_L, U.num_L
        pr = res.parker_ref
        sq_lo, sq_hi = res.squeeze_range
        nom_ref = res.nominal_at(T_ref)
        c = self.cards
        c[0].set(t("ui.kpi_depth_face" if gland == "face" else "ui.kpi_depth_radial"), L(res.depth_m),
                 t("ui.cap_depth", tol=Ln(res.depth_tol_m), a=Ln(pr["depth_min_m"]), b=Ln(pr["depth_max_m"])))
        c[1].set(t("ui.kpi_width"), L(res.width_m),
                 t("ui.cap_width", tol=Ln(res.width_tol_m), gmin=Ln(res.width_min_m), a=Ln(pr["width_min_m"]),
                   b=Ln(pr["width_max_m"])))
        c[2].set(t("ui.kpi_squeeze"), f"{sq_lo * 100:.1f}–{sq_hi * 100:.1f} %",
                 t("ui.cap_squeeze", a=res.target[0], b=res.target[1],
                   n=(nom_ref.squeeze_min + nom_ref.squeeze_max) / 2, T=U.fmt_T(T_ref)))
        c[3].set(t("ui.kpi_fill"), f"{res.fill_max:.1%}",
                 t("ui.cap_fill", lim=res.fill_limit, head=res.fill_limit - res.fill_max))
        fluid = self.fluid.currentData()
        if gland == "radial":
            c[4].set(t("ui.kpi_machine_depth"), L(res.machine_depth_m), t("ui.cap_machine"))
            c[5].set(t("ui.kpi_clearance"), f"{Ln(res.clearance_m[0])}–{L(res.clearance_m[1])}",
                     t("ui.cap_clearance", gap=L(res.allowed_gap_m)) if res.allowed_gap_m else
                     t("ui.cap_clearance_nogap"))
        if gland != "radial":
            c[4].hide()
            c[5].hide()
        else:
            c[4].show()
            c[5].show()
        c[6].set(t("ui.kpi_radius"), L(res.radius_m), t("ui.cap_radius", a=Ln(pr["radius_min_m"]),
                                                          b=Ln(pr["radius_max_m"])))
        per_T = res.per_temperature
        lo_row, hi_row = per_T.iloc[0], per_T.iloc[-1]
        c[7].set(t("ui.kpi_volume"), f"{lo_row.volume_change:+.2%}",
                 t("ui.cap_volume", Tlo=U.fmt_T(lo_row.T_K), vlo=lo_row.volume_change, Thi=U.fmt_T(hi_row.T_K),
                   vhi=hi_row.volume_change))
        self.overall.set_status(res.status)

        gap_txt = f"{Ln(res.clearance_m[0])}–{Ln(res.clearance_m[1])}" if res.clearance_m else None
        self.schematic.show_gland(sketch, {
            "depth": Ln(res.depth_m, res.depth_tol_m), "width": Ln(res.width_m, (0.0, res.width_tol_m)),
            "radius": Ln(res.radius_m), "cs": Ln(cs_m, res.cs_tol_m), "gap": gap_txt,
            "machine_depth": Ln(res.machine_depth_m) if gland == "radial" else None,
            "ring_id": Ln(ring_id)}, direction)

        # section
        panels = []
        for T in (inp.T_min_K, T_ref, inp.T_max_K):
            try:
                panels.append((U.fmt_T(T), run_checks(res.design, ds, ThermalState(T, T, None, T_ref))[0]))
            except ThermalDataError:
                panels.append((U.fmt_T(T), None))
        side = self.side.key() if gland == "radial" else "nominal"
        self.section.set_figure(section_fig(panels, sketch, side, U.L, direction, res.radius_m))

        self._forces(res, cs_m, ring_id, sq_hi, nom_ref, direction, gland, is_el)

        rules_hard = rules.fill_hard_max.value if rules.fill_hard_max and rules.fill_hard_max.value else None
        self.envelope.set_figure(envelope_fig(per_T, U.T, res.target, res.fill_limit, rules_hard))
        header = [t("ui.col_T"), t("ui.col_cs_T"), t("ui.col_sq_range"), t("ui.col_sq_nom"), t("ui.col_fill_max"),
                  t("ui.col_dv")] + ([t("ui.col_gap")] if gland == "radial" else [])
        rows = []
        for _, row in per_T.iterrows():
            rows.append([U.fmt_T(row.T_K), L(row.cs_m), f"{row.squeeze_lo:.1%} – {row.squeeze_hi:.1%}",
                         f"{row.squeeze_nominal:.1%}", f"{row.fill_max:.1%}", f"{row.volume_change:+.2%}"]
                        + ([L(row.gap_max_m)] if gland == "radial" else []))
        self.temp_table.fill(header, rows)
        self._per_T = per_T
        order = {Status.FAIL: 0, Status.WARN: 1, Status.PASS: 2}
        self.checks.set_rows([(r.status, render_check(r), None) for r in sorted(worst, key=lambda r: order[r.status])])

    def _forces(self, res, cs_m, ring_id, sq_hi, nom_ref, direction, gland, is_el) -> None:
        """Parker chart load per length (elastomers within the chart ranges) or, where the
        charts give nothing, the load per length entered by the user."""
        from oring_designer.force import LoadRange

        U = UNITS
        ds = dataset()
        for c in self.force_cards:
            c.hide()
        sq_nom = (nom_ref.squeeze_min + nom_ref.squeeze_max) / 2
        q_nom = q_max = None
        if is_el:
            hardness = self.hardness.si()
            q_nom = load_per_length(ds, cs_m, sq_nom, hardness, ring_id)
            q_max = load_per_length(ds, cs_m, sq_hi, hardness, ring_id)
        manual = self.q_manual.si()
        msgs = []
        if is_el and manual is None and (q_nom is None or q_max is None):
            # outside the Parker charts: Lindley (1966) toroidal-ring formula from material hardness
            from oring_designer.seal_mechanics import load_per_length as lindley, modulus

            ql = [lindley(cs_m, s_, self.hardness.si()) for s_ in (sq_nom, sq_hi)]
            q_nom, q_max = (LoadRange(q, q, q, q) for q in ql)
            msgs.append(t("desktop.force_lindley", E=modulus(self.hardness.si()).E_Pa / 1e6))
        if manual is not None:
            q = manual * 1000.0  # N/mm -> N/m
            q_nom = q_max = LoadRange(q, q, q, q)
            msgs.append(t("desktop.force_manual_used", q=manual))
        elif q_nom is None or q_max is None:
            msgs.append(t("desktop.force_manual_needed"))
        to_unit = (lambda q: f"{q / 1000:.2f} N/mm") if U.L == "mm" else (lambda q: f"{q / 175.1268:.1f} lbf/in")
        rows = []
        for label, q in ((t("ui.force_at_nominal", sq=sq_nom, T=U.fmt_T(U.T_ref_K)), q_nom),
                         (t("ui.force_at_max", sq=sq_hi), q_max)):
            rows.append([label, "–" if q is None else f"{to_unit(q.min_N_per_m)} – {to_unit(q.max_N_per_m)}",
                         "–" if q is None else f"{to_unit(q.typical_min_N_per_m)} – {to_unit(q.typical_max_N_per_m)}"])
        self.force_table.fill([t("ui.force_cond"), t("ui.force_range"), t("ui.force_typical")], rows)
        self.clamp_text = None
        if ring_id is None:
            msgs.append(t("ui.force_need_id"))
        elif q_max is not None:
            fN = (lambda f: f"{f / 1000:.2f} kN") if U.L == "mm" else (lambda f: f"{f / 4.4482216:.0f} lbf")
            D_seal = ring_id + 2 * cs_m
            clamp = face_clamp_load(q_max, ring_id, cs_m, D_seal, self.pressure.si(), direction)
            self.force_cards[0].set(t("ui.force_total"), f"{fN(clamp.compression_N[0])} – {fN(clamp.compression_N[1])}")
            self.force_cards[0].show()
            if gland == "face":
                self.force_cards[1].set(t("ui.force_pressure", d=U.fmt_L(D_seal)), fN(clamp.pressure_N))
                self.force_cards[2].set(t("ui.force_clamp"), fN(clamp.clamp_min_N))
                self.force_cards[1].show()
                self.force_cards[2].show()
                self.clamp_text = (t("ui.force_clamp"), fN(clamp.clamp_min_N))
                msgs.append(t("ui.force_clamp_note") + ("" if direction == "internal" else " " + t("ui.force_external")))
            else:
                self.clamp_text = (t("ui.force_total"), fN(clamp.compression_N[1]))
                msgs.append(t("ui.force_radial_note"))
        self.force_note.setText("\n".join(msgs))
        self.cards[8].setVisible(bool(self.clamp_text))
        if self.clamp_text:
            self.cards[8].set(*self.clamp_text)
        self.force_hint.show_text("" if self.clamp_text else msgs[0] if msgs else "", "info")

    def _save_csv(self) -> None:
        if self._per_T is not None:
            save_bytes(self, t("ui.download_csv"), "yuva_sicaklik.csv", "CSV (*.csv)",
                       self._per_T.to_csv(index=False).encode("utf-8"))



