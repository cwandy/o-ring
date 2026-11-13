"""Design report (SPEC §11 Faz 8): inputs, results, figures and data sources.

``build_report`` evaluates the design once (operating point, temperature sweep, optional
tolerance analysis) and collects everything into a :class:`Report`; ``to_markdown_zip``
and ``to_pdf`` render it. Texts come from ``i18n`` (Turkish).
"""

from __future__ import annotations

import datetime as _dt
import io
import zipfile
from dataclasses import dataclass, field

from .. import __version__
from ..checks import CheckResult, Design, overall_status, run_checks
from ..gland_types import FaceGland, PistonGland, RodGland, ThermalState
from ..i18n import render_check, t, t_list
from ..loader import Dataset, verification_list
from ..models import DataQuality
from ..sweep import summary_status, sweep, temperatures, to_frame, worst_by_family
from ..thermal import ThermalDataError
from ..tolerance import Tolerance, monte_carlo, rss, worst_case
from . import figures

LENGTH = {"mm": (1e3, 3), "in": (1 / 0.0254, 4)}
TEMP_LABEL = {"K": "K", "degC": "°C", "degF": "°F"}


@dataclass(frozen=True)
class ReportInput:
    design: Design
    T_ref_K: float = 293.15
    point: ThermalState | None = None  # default: T_ref
    T_min_K: float = 293.15
    T_max_K: float = 293.15
    T_step_K: float = 5.0
    mode: str = "equilibrium"
    delta_T_K: float = 0.0
    mating_delta_K: float = 0.0
    length_unit: str = "mm"
    temp_unit: str = "degC"
    pressure_unit: str = "bar"
    title: str = ""
    oring_label: str = ""  # e.g. standard size
    tolerances: dict[str, Tolerance] | None = None
    mc_samples: int = 20_000
    mc_distribution: str = "normal"
    mc_seed: int = 1


@dataclass
class Report:
    title: str
    generated: str
    inputs: list[tuple[str, str]]
    point_status: str
    point_rows: list[tuple[str, str]]
    sweep_status: str
    sweep_rows: list[tuple[str, str, str]]
    figures: dict[str, bytes] = field(default_factory=dict)
    tolerance_text: list[str] = field(default_factory=list)
    tolerance_rows: list[tuple[str, str, str, str]] = field(default_factory=list)
    sources: list[tuple[str, str, str]] = field(default_factory=list)
    verify: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- formatting helpers


def _fmt_T(T_K: float, unit: str) -> str:
    v = {"K": T_K, "degC": T_K - 273.15, "degF": (T_K - 273.15) * 9 / 5 + 32}[unit]
    return f"{v:.1f} {TEMP_LABEL[unit]}"


def _fmt_L(x_m: float, unit: str) -> str:
    k, nd = LENGTH[unit]
    return f"{x_m * k:.{nd}f} {unit}"


def _fmt_p(p_Pa: float, unit: str) -> str:
    k = {"bar": 1e-5, "MPa": 1e-6, "psi": 1 / 6894.757293168361}[unit]
    return f"{p_Pa * k:.2f} {unit}"


def _gland_dims(d: Design, u: str) -> str:
    g = d.gland
    if isinstance(g, PistonGland):
        parts = [(t("ui.bore_diameter"), g.bore_diameter_m), (t("ui.piston_diameter"), g.piston_diameter_m),
                 (t("ui.groove_diameter_piston"), g.groove_diameter_m), (t("ui.groove_width"), g.groove_width_m)]
    elif isinstance(g, RodGland):
        parts = [(t("ui.rod_diameter"), g.rod_diameter_m), (t("ui.throat_diameter"), g.throat_diameter_m),
                 (t("ui.groove_diameter_rod"), g.groove_diameter_m), (t("ui.groove_width"), g.groove_width_m)]
    else:
        parts = [(t("ui.groove_id"), g.groove_id_m), (t("ui.groove_od"), g.groove_od_m),
                 (t("ui.groove_depth"), g.groove_depth_m)]
    parts.append((t("ui.corner_radius"), g.corner_radius_m))
    return "; ".join(f"{name} {_fmt_L(v, u)}" for name, v in parts)


def _status_text(status) -> str:
    return t(f"status.{status.value}")


# --------------------------------------------------------------------------- build


def build_report(inp: ReportInput, ds: Dataset) -> Report:
    d = inp.design
    seal = ds.seal_materials[d.seal_material]
    groove = ds.housing_materials[d.groove_material]
    mating = ds.housing_materials[d.mating_material or d.groove_material]
    kind = {"PistonGland": "piston", "RodGland": "rod", "FaceGland": "face"}[type(d.gland).__name__]
    lu, tu = inp.length_unit, inp.temp_unit
    point = inp.point or ThermalState(inp.T_ref_K, inp.T_ref_K, None, inp.T_ref_K)

    ecc = getattr(d.gland, "eccentricity_m", None)
    inputs = [
        (t("report.gland_type"), t(f"ui.{kind}") + (f" ({t('ui.' + d.gland.pressure_direction)})"
                                                  if isinstance(d.gland, FaceGland) else "")),
        (t("report.seal"), seal.name),
        (t("report.groove_part"), groove.name),
        (t("report.mating_part"), mating.name),
        (t("report.oring"), f"{inp.oring_label + ': ' if inp.oring_label else ''}"
                            f"{_fmt_L(d.oring.id_m, lu)} × {_fmt_L(d.oring.cs_m, lu)}"),
        (t("report.dims"), _gland_dims(d, lu)),
        (t("report.pressure"), _fmt_p(d.pressure_Pa, inp.pressure_unit)),
        (t("report.hardness"), "–" if d.hardness_shore_a is None else f"{d.hardness_shore_a:.0f} Shore A"),
        (t("report.fluid"), "–" if d.fluid is None else ds.fluids[d.fluid].name),
        (t("report.T_ref"), _fmt_T(inp.T_ref_K, tu)),
        (t("report.point_state"), f"{_fmt_T(point.T_seal_K, tu)} / {_fmt_T(point.T_housing_K, tu)}"),
        (t("report.sweep_range"), f"{_fmt_T(inp.T_min_K, tu)} … {_fmt_T(inp.T_max_K, tu)}"),
        (t("report.sweep_mode"), t(f"ui.mode_{inp.mode}") + (f", ΔT = {inp.delta_T_K:+.1f} K"
                                                           if inp.mode == "lag" else "")),
        (t("report.cs_method"), t(f"ui.cs_{d.cs_method}")),
    ]
    if kind != "face":
        inputs.append((t("report.eccentricity"), t("report.full_ecc") if ecc is None else _fmt_L(ecc, lu)))

    # operating point
    used: list[CheckResult] = []
    try:
        st_point, res_point = run_checks(d, ds, point)
        order = {"FAIL": 0, "WARN": 1, "PASS": 2}
        res_point = sorted(res_point, key=lambda r: order[r.status.value])
        point_rows = [(_status_text(r.status), render_check(r)) for r in res_point]
        point_status = _status_text(overall_status(res_point))
        used += res_point
    except ThermalDataError as exc:
        st_point, point_rows, point_status = None, [("–", t("ui.no_data_point") + f" ({exc})")], "–"

    # sweep
    pts = sweep(d, ds, temperatures(min(inp.T_min_K, inp.T_max_K), max(inp.T_min_K, inp.T_max_K),
                                    max(inp.T_step_K, 0.1)),
                inp.mode, inp.delta_T_K, inp.mating_delta_K, inp.T_ref_K)
    worst = worst_by_family(pts)
    sweep_rows = [(_status_text(w.result.status), render_check(w.result),
                   f"{_fmt_T(w.T_housing_K, tu)} / {_fmt_T(w.T_seal_K, tu)}") for w in worst]
    used += [w.result for w in worst]
    df = to_frame(pts)

    rules = ds.rule_set(seal.group, "static_face" if kind == "face" else "static_radial")
    band = rules.recommended_squeeze.band_for(d.oring.cs_m) if rules.recommended_squeeze else None
    figs = {
        "squeeze_fill.png": figures.squeeze_fill_png(
            df, tu, (band.min, band.max) if band else None,
            rules.squeeze_max.value if rules.squeeze_max else None,
            (rules.fill_min.value, rules.fill_max.value)
            if rules.fill_min and rules.fill_min.value is not None and rules.fill_max else None,
            rules.fill_hard_max.value if rules.fill_hard_max else None,
            seal.low_temp_limit_K.value if seal.group == "elastomer" and seal.low_temp_limit_K else None,
            ds.common_rules.low_temp_warning_band_K.value, inp.delta_T_K if inp.mode == "lag" else 0.0),
    }
    if kind != "face":
        figs["clearance.png"] = figures.clearance_png(df, tu, lu)
    panels = []
    for T in (min(inp.T_min_K, inp.T_max_K), inp.T_ref_K, max(inp.T_min_K, inp.T_max_K)):
        off = inp.delta_T_K if inp.mode == "lag" else 0.0
        try:
            panels.append((_fmt_T(T, tu), run_checks(d, ds, ThermalState(T + off, T, T + inp.mating_delta_K,
                                                                         inp.T_ref_K))[0]))
        except ThermalDataError:
            panels.append((_fmt_T(T, tu), None))
    figs["section.png"] = figures.section_png(panels, kind, "nominal", lu,
                                              getattr(d.gland, "pressure_direction", "internal"))

    rep = Report(
        title=inp.title or t("report.title"),
        generated=t("report.generated", date=_dt.date.today().isoformat(), version=__version__),
        inputs=inputs, point_status=point_status, point_rows=point_rows,
        sweep_status=_status_text(summary_status(pts)), sweep_rows=sweep_rows, figures=figs,
        assumptions=t_list("report.assumptions"),
    )

    # tolerance analysis (optional)
    if inp.tolerances:
        wc = worst_case(d, inp.tolerances, ds, point)
        r = rss(d, inp.tolerances, ds, point)
        mc = monte_carlo(d, inp.tolerances, ds, point, inp.mc_samples, inp.mc_distribution, inp.mc_seed)
        rep.tolerance_text = [
            t("report.tol_method", n=inp.mc_samples, dist=t(f"ui.dist_{inp.mc_distribution}"), seed=inp.mc_seed),
            t("report.pass_rate", rate=mc.overall_rates["PASS"]),
        ]
        for key in ("squeeze_min", "squeeze_max", "fill", "stretch", "max_extrusion_gap_m"):
            if key == "max_extrusion_gap_m" and kind == "face":
                continue
            f = (lambda v: _fmt_L(v, lu)) if key.endswith("_m") else (lambda v: f"{v:.2%}")
            s = mc.samples[key]
            rep.tolerance_rows.append((t(f"ui.out_{key}"), f"{f(wc.output_min[key])} – {f(wc.output_max[key])}",
                                       f"{f(r.low(key))} – {f(r.high(key))}", f"{f(s.min())} – {f(s.max())}"))
        used += [res for res, _ in wc.worst_results.values()]

    rep.sources = _sources(d, ds, seal, groove, mating, rules)
    rep.verify = _verify(ds, d, used)
    return rep


def _sources(d, ds, seal, groove, mating, rules) -> list[tuple[str, str, str]]:
    uses: dict[str, set[str]] = {}

    def add(ref, use):
        if ref:
            uses.setdefault(ref, set()).add(use)

    for m in {seal.id: seal, groove.id: groove, mating.id: mating}.values():
        for seg in m.thermal_strain.segments:
            add(seg.source, f"{m.name}: {t('report.use_thermal')} ({seg.data_quality.value})")
    for q in (seal.low_temp_limit_K, seal.high_temp_limit_K):
        if q is not None:
            add(q.source, f"{seal.name}: {t('report.use_limits')} ({q.data_quality.value})")
    for name in ("squeeze_max", "fill_max", "fill_hard_max", "stretch_max"):
        lim = getattr(rules, name)
        if lim is not None:
            add(lim.source, f"{t('report.use_rules')} ({lim.data_quality.value})")
    add(ds.extrusion_limits.source, f"{t('report.use_extrusion')} ({ds.extrusion_limits.data_quality.value})")
    if d.fluid:
        c = ds.fluids[d.fluid].compatibility_with(d.seal_material)
        add(c.source, f"{t('report.use_fluid')} ({c.data_quality.value})")
    out = []
    for ref_id, u in sorted(uses.items()):
        ref = ds.references.get(ref_id)
        cit = ref.citation + (f" {ref.url}" if ref and ref.url else "") if ref else ref_id
        out.append((ref_id, cit, "; ".join(sorted(u))))
    return out


def _verify(ds: Dataset, d: Design, used: list[CheckResult]) -> list[str]:
    ids = {d.seal_material, d.groove_material, d.mating_material or d.groove_material}
    items = [str(i) for i in verification_list(ds)
             if i.origin == "auto" and any(f"[{x}]" in i.location for x in ids)]
    flagged = {render_check(r) for r in used
               if r.data_quality in (DataQuality.PLACEHOLDER, DataQuality.EXTRAPOLATED)}
    return sorted(flagged) + items


# --------------------------------------------------------------------------- Markdown


def _md_table(header: list[str], rows: list[tuple]) -> str:
    esc = lambda s: str(s).replace("|", "\\|")  # noqa: E731
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def to_markdown(rep: Report, figure_dir: str = "figures") -> str:
    out = [f"# {rep.title}", "", rep.generated, "",
           f"## {t('report.s_inputs')}", "", _md_table([t("report.parameter"), t("report.value")], rep.inputs), "",
           f"## {t('report.s_point')}", "", f"**{t('report.overall')}: {rep.point_status}**", "",
           _md_table([t("report.status"), t("report.message")], rep.point_rows), "",
           f"## {t('report.s_sweep')}", "", f"**{t('report.overall')}: {rep.sweep_status}**", "",
           _md_table([t("report.status"), t("report.message"), t("report.temperature")], rep.sweep_rows), "",
           f"![squeeze/fill]({figure_dir}/squeeze_fill.png)", ""]
    if "clearance.png" in rep.figures:
        out += [f"![clearance]({figure_dir}/clearance.png)", ""]
    out += [f"## {t('report.s_section')}", "", f"![section]({figure_dir}/section.png)", "",
            f"## {t('report.s_tolerance')}", ""]
    if rep.tolerance_rows:
        out += [*rep.tolerance_text, "",
                _md_table([t("ui.col_output"), t("ui.col_wc"), t("ui.col_rss"), t("ui.col_mc")],
                          rep.tolerance_rows), ""]
    else:
        out += [t("report.no_tolerance"), ""]
    out += [f"## {t('report.s_sources')}", "",
            _md_table([t("report.ref_id"), t("report.citation"), t("report.used_for")], rep.sources), "",
            f"## {t('report.s_verify')}", ""]
    out += [f"- {v}" for v in rep.verify] or [t("report.no_verify")]
    out += ["", f"## {t('report.s_assumptions')}", ""] + [f"- {a}" for a in rep.assumptions] + [""]
    return "\n".join(out)


def to_markdown_zip(rep: Report) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("rapor.md", to_markdown(rep))
        for name, data in rep.figures.items():
            z.writestr(f"figures/{name}", data)
    return buf.getvalue()


# --------------------------------------------------------------------------- PDF


def to_pdf(rep: Report) -> bytes:
    import os

    import matplotlib
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    font_dir = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")
    if "DejaVu" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("DejaVu", os.path.join(font_dir, "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", os.path.join(font_dir, "DejaVuSans-Bold.ttf")))
    body = ParagraphStyle("body", fontName="DejaVu", fontSize=8.5, leading=11)
    small = ParagraphStyle("small", parent=body, fontSize=7.5, leading=9.5)
    h1 = ParagraphStyle("h1", fontName="DejaVu-Bold", fontSize=15, leading=19, spaceAfter=4)
    h2 = ParagraphStyle("h2", fontName="DejaVu-Bold", fontSize=11, leading=14, spaceBefore=8, spaceAfter=4)
    status_bg = {t("status.PASS"): colors.Color(12 / 255, 163 / 255, 12 / 255, 0.18),
                 t("status.WARN"): colors.Color(250 / 255, 178 / 255, 25 / 255, 0.30),
                 t("status.FAIL"): colors.Color(208 / 255, 59 / 255, 59 / 255, 0.22)}

    def esc(s: str) -> str:
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def table(header, rows, widths, status_col=None):
        data = [[Paragraph(f"<b>{esc(h)}</b>", small) for h in header]]
        data += [[Paragraph(esc(c), small) for c in r] for r in rows]
        tb = Table(data, colWidths=widths, repeatRows=1)
        style = [("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d6d5d0")),
                 ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0efec")),
                 ("VALIGN", (0, 0), (-1, -1), "TOP")]
        if status_col is not None:
            for i, r in enumerate(rows, start=1):
                if r[status_col] in status_bg:
                    style.append(("BACKGROUND", (status_col, i), (status_col, i), status_bg[r[status_col]]))
        tb.setStyle(TableStyle(style))
        return tb

    def image(name, width_mm):
        from reportlab.lib.utils import ImageReader

        data = rep.figures[name]
        iw, ih = ImageReader(io.BytesIO(data)).getSize()
        w = width_mm * mm
        return Image(io.BytesIO(data), width=w, height=w * ih / iw)

    W = 180 * mm
    story = [Paragraph(esc(rep.title), h1), Paragraph(esc(rep.generated), small), Spacer(1, 6),
             Paragraph(esc(t("report.s_inputs")), h2),
             table([t("report.parameter"), t("report.value")], rep.inputs, [50 * mm, 130 * mm]),
             Paragraph(esc(t("report.s_point")), h2),
             Paragraph(f"<b>{esc(t('report.overall'))}: {esc(rep.point_status)}</b>", body), Spacer(1, 3),
             table([t("report.status"), t("report.message")], rep.point_rows, [22 * mm, 158 * mm], 0),
             Paragraph(esc(t("report.s_sweep")), h2),
             Paragraph(f"<b>{esc(t('report.overall'))}: {esc(rep.sweep_status)}</b>", body), Spacer(1, 3),
             table([t("report.status"), t("report.message"), t("report.temperature")], rep.sweep_rows,
                   [22 * mm, 118 * mm, 40 * mm], 0),
             Spacer(1, 4), image("squeeze_fill.png", 150)]
    if "clearance.png" in rep.figures:
        story += [image("clearance.png", 150)]
    story += [Paragraph(esc(t("report.s_section")), h2), image("section.png", 175),
              Paragraph(esc(t("report.s_tolerance")), h2)]
    if rep.tolerance_rows:
        story += [Paragraph(esc(x), body) for x in rep.tolerance_text] + [Spacer(1, 3),
                  table([t("ui.col_output"), t("ui.col_wc"), t("ui.col_rss"), t("ui.col_mc")],
                        rep.tolerance_rows, [40 * mm, 47 * mm, 47 * mm, 46 * mm])]
    else:
        story.append(Paragraph(esc(t("report.no_tolerance")), body))
    story += [Paragraph(esc(t("report.s_sources")), h2),
              table([t("report.ref_id"), t("report.citation"), t("report.used_for")], rep.sources,
                    [28 * mm, 92 * mm, 60 * mm]),
              Paragraph(esc(t("report.s_verify")), h2)]
    story += [Paragraph("• " + esc(v), small) for v in rep.verify] or [Paragraph(esc(t("report.no_verify")), body)]
    story += [Paragraph(esc(t("report.s_assumptions")), h2)]
    story += [Paragraph("• " + esc(a), small) for a in rep.assumptions]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm, title=rep.title)
    doc.build(story)
    assert W  # page width used for column sizing above
    return buf.getvalue()
