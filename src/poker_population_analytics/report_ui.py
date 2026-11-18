"""Presentation shared by the local snapshot and generated HTML reports."""
from html import escape
import json
from pathlib import Path

ASSETS = Path(__file__).parent
LABELS = {
    "spot_id": "Decision node", "spot_name": "Decision node", "stake_label": "Stake",
    "pot_type": "Pot", "opportunities": "Opps", "benchmark_metric": "Metric",
    "deviation_pp": "Diff. pp", "exploit_score": "Review score", "confidence": "Sample",
    "benchmark_flag": "Status", "leak_note": "Review note", "bet_pct": "Bet %",
    "check_pct": "Check %", "fold_pct": "Fold %", "call_pct": "Call %",
    "raise_pct": "Raise %", "avg_size_pct": "Avg. size %", "observed": "Observed %",
    "reference_range": "Reference range",
    "fourbettor_position": "Position", "total_4bets_stack_filtered": "4-bets",
    "known_4bettor_hands": "Known", "known_rate_pct": "Reveal %",
    "known_AAxx": "AAxx", "AAxx_pct_of_known": "AAxx %", "unknown_4bettor_hands": "Unknown",
    "hand_class": "Hand class", "count": "Hands", "pct": "Share %",
}
TEXT_COLUMNS = {"spot_id", "spot_name", "stake_label", "pot_type", "benchmark_metric",
                "confidence", "benchmark_flag", "leak_note", "fourbettor_position", "hand_class"}
STATUS = {"LOW": "Below range", "HIGH": "Above range", "OK": "Within range",
          "low_sample": "Low sample", "audit_required": "Audit required"}
POTS = {"srp": "SRP", "3bet": "3-bet", "4bet+": "4-bet+", "limped": "Limped"}
CHART_NAMES = {"key_leaks": "Observed frequencies & reference ranges",
               "spot_pottype_heatmap": "Deviation by decision node",
               "response_mix": "Fold / call / raise",
               "aaxx_by_position": "AAxx by position",
               "hand_class_composition": "Known hand composition"}


def e(value):
    return escape(str(value), quote=True)


def formatted(value):
    if value is None or value == "":
        return "—"
    try:
        n = float(str(value).rstrip("%"))
        if str(value).endswith("%"):
            return f"{n:.1f}"
        return f"{n:,.0f}" if n.is_integer() else f"{n:,.1f}"
    except (ValueError, TypeError):
        return str(value)


def node_name(row):
    return row.get("spot_name") or str(row.get("spot_id", "")).replace("_", " ").capitalize()


def metric_name(key):
    return LABELS.get(key, str(key).replace("_", " ").capitalize()).removesuffix(" %")


def reference_range(row):
    low, high = row.get("benchmark_low"), row.get("benchmark_high")
    return "—" if low in ("", None) or high in ("", None) else f"{formatted(low)}–{formatted(high)}%"


def detail_data(row):
    metric = row.get("benchmark_metric") or "fold_pct"
    data = {
        "name": node_name(row), "context": f"{row.get('stake_label', 'All stakes')} · {POTS.get(row.get('pot_type'), row.get('pot_type', ''))}",
        "observed": formatted(row.get(metric)) + "%", "metric": metric_name(metric).lower(),
        "opportunities": formatted(row.get("opportunities")),
        "reference_range": reference_range(row),
        "status": STATUS.get(row.get("benchmark_flag"), row.get("benchmark_flag", "—")),
        "note": row.get("leak_note") or "Observed action frequencies in this decision node.",
    }
    for action in ("bet", "check", "fold", "call", "raise"):
        data[action] = formatted(row.get(action + "_pct", 0)) + "%"
    return data


def html_table(rows, columns, max_rows=None, selectable=False, compact=False):
    shown = rows if max_rows is None else rows[:max_rows]
    if not shown:
        return '<div class="empty">No matching observations in this report.</div>'
    attr = ' data-review-table data-detail="node-detail"' if selectable else ""
    classes = "compact-table" if compact else "data-table"
    if selectable:
        classes += " selectable"
    parts = [f'<div class="table-wrap" tabindex="0" aria-label="Scrollable results"><table class="{classes}"{attr}><thead><tr>']
    for col in columns:
        alignment = "" if col in TEXT_COLUMNS else ' class="numeric"'
        parts.append(f'<th scope="col"{alignment}>{e(LABELS.get(col, col))}</th>')
    parts.append("</tr></thead><tbody>")
    for index, row in enumerate(shown):
        attrs = ""
        if selectable:
            attrs = (f' tabindex="{0 if index == 0 else -1}" aria-selected="{str(index == 0).lower()}"'
                     f' data-detail="{e(json.dumps(detail_data(row)))}"')
        parts.append(f"<tr{attrs}>")
        for col in columns:
            value = row.get(col, "")
            classes = ""
            if col in {"spot_id", "spot_name"}:
                cell = f'<span title="{e(row.get("spot_id", ""))}">{e(node_name(row))}</span>'
                classes = "spot-cell"
            elif col == "pot_type":
                cell = e(POTS.get(value, value))
            elif col == "benchmark_flag":
                cell = f'<span class="status {e(str(value).lower())}">{e(STATUS.get(value, value))}</span>'
            elif col == "benchmark_metric":
                cell = e(metric_name(value))
            elif col == "observed":
                cell = e(formatted(row.get(row.get("benchmark_metric", ""), "")))
                classes = "numeric blue"
            elif col == "reference_range":
                cell = e(reference_range(row))
                classes = "numeric"
            elif col not in TEXT_COLUMNS:
                cell = e(formatted(value))
                classes = "numeric accent" if col == "deviation_pp" else "numeric"
            else:
                cell = e(value)
            parts.append(f'<td class="{classes}">{cell}</td>')
        parts.append("</tr>")
    parts.append("</tbody></table></div>")
    return "".join(parts)


def panel(title, body, meta="", extra="", classes=""):
    return (f'<section class="panel {classes}"><div class="panel-head"><h2>{e(title)}</h2>'
            f'<span class="meta">{meta}</span></div>{body}{extra}</section>')


def node_detail(row):
    data = detail_data(row) if row else {}
    def field(key):
        return f'<span data-field="{key}">{e(data.get(key, "—"))}</span>'
    bars = []
    for action in ("bet", "check", "fold", "call", "raise"):
        value = data.get(action, "0%")
        width = max(0, min(100, float(value.rstrip("%").replace(",", ""))))
        bars.append(f'<div class="bar-row"><span>{action.title()}</span><div class="track">'
                    f'<i data-bar="{action}" style="width:{width}%"></i></div><b>{field(action)}</b></div>')
    body = (f'<div id="node-detail" class="spot-detail" aria-live="polite"><h3>{field("name")}</h3>'
            f'<div class="detail-context">{field("context")}</div>'
            f'<div class="detail-result"><strong>{field("observed")}</strong>{field("metric")}</div>'
            f'<div class="stat-row"><span>Opportunities</span><strong>{field("opportunities")}</strong></div>'
            f'<div class="stat-row"><span>Reference range</span><strong>{field("reference_range")}</strong></div>'
            f'<div class="stat-row"><span>Status</span><strong>{field("status")}</strong></div>'
            '<div class="mini-title">Action distribution</div><div class="mini-chart">'
            '<div class="axis"><span>0</span><span>50</span><span>100%</span></div>'
            + "".join(bars) + f'</div><p class="detail-note">{field("note")}</p></div>')
    return panel("Node detail", body, "Selected row")


def chart_gallery(paths, outdir):
    if not paths:
        return '<div class="panel empty">Charts are unavailable for this run.</div>'
    figures = []
    for path in paths:
        path = Path(path)
        try:
            source = path.relative_to(outdir).as_posix()
        except ValueError:
            source = path.as_posix()
        name = CHART_NAMES.get(path.stem, "Response by board texture")
        figures.append(panel(name, f'<figure><a class="chart-open" href="{e(source)}" target="_blank">'
                             f'<img src="{e(source)}" alt="{e(name)}" loading="lazy"></a>'
                             '<figcaption>Open chart for full-size view</figcaption></figure>'))
    return '<div class="chart-grid">' + "".join(figures) + "</div>"


def page(title, subtitle, active, body, metrics, nav=None, csv_link=None, context=""):
    nav = nav or [(active, "#overview"), ("Methodology", "#method")]
    links = "".join(f'<a href="{e(href)}"{" aria-current=page" if label == active else ""}>{e(label)}</a>'
                    for label, href in nav)
    tools = []
    for label, href in nav:
        if label in {"Population", "Four-bet"}:
            selected = " current" if label == active else ""
            tools.append(f'<a class="ribbon-tool{selected}" href="{e(href)}">'
                         f'<span class="tool-icon chart" aria-hidden="true"></span>{e(label)}</a>')
    if csv_link:
        tools.append(f'<a class="ribbon-tool" href="{e(csv_link)}" download>'
                     '<span class="tool-icon export" aria-hidden="true"></span>Export CSV</a>')
    summary = "".join(f'<div class="metric"><strong>{e(v if str(v).endswith("%") else formatted(v))}</strong><span>{e(k)}</span></div>'
                      for k, v in metrics)
    css = (ASSETS / "report.css").read_text(encoding="utf-8")
    js = (ASSETS / "report.js").read_text(encoding="utf-8")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)} · CoinPoker PLO</title><style>{css}</style></head>
<body><header>
<div class="titlebar"><span class="app-mark" aria-hidden="true">PLO</span>
<div class="app-name">CoinPoker <span>/</span> Population Analyzer</div><span class="local-label">Aggregate reports</span></div>
<div class="ribbon"><div class="ribbon-tools">{''.join(tools)}</div><div class="run-description">CoinPoker hand-history analysis<br>Population &amp; four-bet reports</div>
<div class="metrics">{summary}</div></div>
<nav class="tabs" aria-label="Report navigation">{links}<span class="tab-end">{e(context)}</span></nav>
</header><main id="overview"><div class="page-heading"><div><h1>{e(title)}</h1><p>{e(subtitle)}</p></div></div>
{body}</main><footer class="report-footer"><span><i class="dot"></i>Report ready</span><span>CoinPoker · Population analysis</span></footer>
<script>{js}</script></body></html>"""


METHOD_NOTE = """<details id="method"><summary>Definitions &amp; review notes</summary><div class="detail-body">
<p>Percentages use the opportunities recorded for each decision node. Average size is measured against the pot before the action.</p>
<p>Status compares the observed rate with the reference range set for that metric. The review score weights the distance from the range by sample size.</p>
<p>Audit required marks unresolved definitions and suppresses review scoring. Fold-to-flop-c-bet results remain under audit pending comparison with the CoinPoker HUD denominator.</p>
<p>Exact filters, benchmark definitions and aggregate splits are saved alongside each generated report. Local hand-level audit files support source review and contain private data.</p>
</div></details>"""


def pool_report(outdir, filters, summary, leak_rows, chart_paths, nav=None):
    columns = ["spot_id", "stake_label", "pot_type", "opportunities", "benchmark_metric",
               "observed", "reference_range", "deviation_pp", "benchmark_flag"]
    top = leak_rows[:12]
    table = panel("Priority review", html_table(top, columns, selectable=True),
                  f"{len(top)} nodes", '<p class="panel-note">Select a row to inspect its sample and action distribution.</p>')
    body = '<div class="report-grid">' + table + '<aside class="sticky">' + node_detail(top[0] if top else None) + "</aside></div>"
    cols = ["spot_id", "stake_label", "pot_type", "opportunities", "bet_pct", "check_pct",
            "fold_pct", "call_pct", "raise_pct", "avg_size_pct", "benchmark_metric", "reference_range",
            "benchmark_flag", "confidence", "exploit_score"]
    body += '<div class="subsection">' + panel("All decision nodes", html_table(summary, cols),
                                             f"{len(summary)} rows") + "</div>"
    body += '<h2 class="section-title">Charts</h2>' + chart_gallery(chart_paths, outdir) + METHOD_NOTE
    metrics = [("Hands", filters.get("hands_analyzed_after_filters", "—")),
               ("Decision records", filters.get("pool_spot_records", "—")),
               ("Parse errors", filters.get("parse_errors", "—"))]
    stake = filters.get("stake_filter")
    context = f'{str(filters.get("game_filter", "")).upper()} · {"All stakes" if stake in (None, "", "all") else stake}'
    html = page("Population report", "Decision frequencies by stake and pot type.", "Population",
                body, metrics, nav, "pool_summary.csv", context)
    (outdir / "pool_dashboard.html").write_text(html, encoding="utf-8")


def fourbet_report(outdir, summary, classes, chart_paths, min_stack, stake, nav=None):
    totals = [row for row in summary if row.get("fourbettor_position") == "ALL"]
    if not totals:
        totals = summary
    total = sum(int(row.get("total_4bets_stack_filtered") or 0) for row in totals)
    known = sum(int(row.get("known_4bettor_hands") or 0) for row in totals)
    aaxx = sum(int(row.get("known_AAxx") or 0) for row in totals)
    share = f"{100*aaxx/known:.1f}%" if known else "—"
    cols = ["stake_label", "fourbettor_position", "total_4bets_stack_filtered", "known_4bettor_hands",
            "known_rate_pct", "known_AAxx", "AAxx_pct_of_known", "unknown_4bettor_hands"]
    table = panel("Position summary", html_table(summary, cols), f"{len(summary)} rows",
                  '<p class="panel-note">AAxx % uses known / shown hands as its denominator.</p>')
    composition = panel("Known hand classes", html_table(classes, ["hand_class", "count", "pct"], compact=True),
                        f"{formatted(known)} hands")
    body = '<div class="report-grid">' + table + '<aside>' + composition
    body += f'<details open><summary>Sample coverage</summary><div class="detail-body"><p>{formatted(known)} of {formatted(total)} qualifying four-bets have known cards. {formatted(total-known)} hands have unknown cards.</p><p>Composition depends on cards being revealed and is affected by showdown selection.</p></div></details></aside></div>'
    body += '<h2 class="section-title">Composition charts</h2>' + chart_gallery(chart_paths, outdir)
    body += '<details id="method"><summary>Four-bet definitions</summary><div class="detail-body"><p>A four-bet is the third preflop raise. An all-in counts when it increases the amount to call. Hero is excluded by default.</p><p>Known hand percentages use the revealed-card subset. Unknown hands remain in the coverage count.</p></div></details>'
    metrics = [("4-bets", total), ("Known hands", known), ("AAxx / known", share)]
    html = page("Four-bet report", "Known hand composition and reveal coverage.", "Four-bet", body,
                metrics, nav, "fourbet_summary.csv", f"{min_stack:g}bb minimum · {'All stakes' if stake in (None, '', 'all') else stake}")
    for name in ("fourbet_dashboard.html", "fourbet_report.html"):
        (outdir / name).write_text(html, encoding="utf-8")

def chart_pyplot():
    import matplotlib
    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt
    from cycler import cycler
    plt.rcParams.update({
        "font.family": "sans-serif", "font.sans-serif": ["Segoe UI", "DejaVu Sans"],
        "font.size": 10, "figure.facecolor": "#272d32", "axes.facecolor": "#272d32",
        "savefig.facecolor": "#272d32", "text.color": "#dce4e9", "axes.labelcolor": "#b4c1ca",
        "axes.edgecolor": "#56616a", "xtick.color": "#aab9c3", "ytick.color": "#c2ced7",
        "grid.color": "#72808c", "grid.alpha": 0.18, "axes.axisbelow": True,
        "axes.spines.top": False, "axes.spines.right": False, "axes.titleweight": "normal",
        "axes.titlesize": 12, "axes.titlepad": 15, "legend.facecolor": "#303940",
        "legend.edgecolor": "#53606a", "axes.prop_cycle": cycler(color=["#86b1ce", "#dbb17b", "#a8b1bb"]),
    })
    return plt


def chart_label(row):
    import textwrap
    name = "\n".join(textwrap.wrap(node_name(row), 35))
    context = f"{row.get('stake_label', '')} · {POTS.get(row.get('pot_type'), row.get('pot_type', ''))}"
    audit = ' · audit required' if row.get('benchmark_flag') == 'audit_required' else ''
    return f"{name}\n{context} · n={formatted(row.get('opportunities'))}{audit}"
