"""Rebuild the public HTML snapshot from its committed aggregate data."""
import csv
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from poker_population_analytics import fourbet, population, report_ui as ui

DOCS = ROOT / "docs"
DEMO = DOCS / "demo"


def read_csv(name):
    with (DEMO / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def navigation(prefix=""):
    return [("Overview", prefix + "index.html"), ("Population", prefix + "demo/pool_dashboard.html"),
            ("Four-bet", prefix + "demo/fourbet_dashboard.html"), ("Methodology", prefix + "methodology.html")]


def overview(summary, filters):
    pl50 = [row for row in summary if row["stake_label"] == "PL50" and row["pot_type"] in {"srp", "3bet"}
            and row["benchmark_flag"] in {"LOW", "HIGH"} and int(row["opportunities"]) >= 30]
    pl50.sort(key=lambda row: int(row["opportunities"]), reverse=True)
    shown = pl50[:8]
    cols = ["spot_id", "pot_type", "opportunities", "observed", "reference_range", "benchmark_flag"]
    grid = '<div class="overview-grid">'
    grid += ui.panel("PL50 · review nodes", ui.html_table(shown, cols, selectable=True, compact=True),
                     '<a href="demo/pool_dashboard.html">All stakes →</a>',
                     '<p class="panel-note">Select a row to see which action the observed rate and reference range measure.</p>')
    grid += ui.node_detail(shown[0]) + "</div>"
    grid += '<div class="summary-grid">'
    grid += ui.panel("Four-bet sample", """<div class="highlight"><div class="small">Known / shown hands</div>
<div class="value">58.9% <span class="muted" style="font-size:14px">AAxx</span></div>
<p>172 of 292 known hands across 468 qualifying events.</p>
<p><a href="demo/fourbet_dashboard.html">Open four-bet report →</a></p></div>""")
    grid += ui.panel("Dataset", f"""<div class="highlight"><div class="stat-row"><span>Raw hands</span><strong>{ui.formatted(filters['raw_hands_before_filters'])}</strong></div>
<div class="stat-row"><span>Included hands</span><strong>{ui.formatted(filters['hands_analyzed_after_filters'])}</strong></div>
<p>Regular PLO4 · PL25 / PL50 / PL100<br>Straddles and hero actions excluded.</p></div>""")
    grid += ui.panel("Definition audit", """<div class="highlight"><h3>Fold to flop c-bet</h3>
<p>PL50 · 44.6% SRP / 43.2% 3-bet. The comparison HUD uses a lower range. Review scoring is withheld pending denominator validation.</p>
<p><a href="methodology.html#audit">Review audit status →</a></p></div>""", classes="notice")
    grid += "</div>"
    return ui.page("Population overview", "Decision frequencies and response patterns from CoinPoker PLO hand histories.",
                   "Overview", grid, [("Hands analyzed", 27701), ("Decision records", 19527), ("Parse errors", 0)],
                   navigation(), "demo/pool_summary.csv", "PLO4 · Snapshot")


def methodology():
    menu = [("definitions", "Definitions"), ("processing", "Processing"), ("review", "Reference ranges"),
            ("audit", "C-bet audit"), ("fourbet", "Four-bet sample"), ("limits", "Data & limitations")]
    content = """<section class="panel" id="definitions"><h2>Definitions</h2><dl class="definitions">
<dt>Opportunity</dt><dd>A hand state where the tracked player can take one of the actions defined for a decision node. Action percentages use this count as their denominator.</dd>
<dt>Bet size</dt><dd>Average size is measured as a percentage of the pot before the action. Facing size measures the bet presented to the responder.</dd>
<dt>Pot type</dt><dd>Preflop raise count determines limped, single-raised, three-bet and four-bet-or-larger pots.</dd>
<dt>Board texture</dt><dd>Boards are grouped into dry, medium, wet, high, paired and monotone buckets for review.</dd>
</dl></section>
<section class="panel" id="processing"><h2>Processing</h2>
<p>The parser extracts seats, positions, stacks, board cards and ordered actions. It reconstructs pot sizes and betting sequences, identifies qualifying decision opportunities, then groups them by stake and pot type.</p>
<p>An ALLIN action is classified by whether it increases the amount to call. Preflop all-in raises update the aggressor and pot type. Straddled hands are detected and excluded by default.</p>
<p>Each local run saves its filters, benchmark definitions and aggregate splits. Hand-level records retain the source actions for manual validation.</p></section>
<section class="panel" id="review"><h2>Reference ranges</h2>
<dl class="definitions"><dt>Below range / Above range</dt><dd>The observed rate falls outside the reference range and the sample meets the reporting threshold.</dd>
<dt>Within range</dt><dd>The observed rate falls within the reference range, including its endpoints.</dd>
<dt>Low sample</dt><dd>The count is below the reporting threshold.</dd>
<dt>Audit required</dt><dd>A definition or comparison remains unresolved. Deviation and review score are set to zero.</dd>
</dl><p>The reference ranges come from the configuration. The review score weights the distance from the range by sample size. Probability, expected value and uncertainty intervals are outside this calculation.</p></section>
<section class="panel notice" id="audit"><h2>Fold-to-flop-c-bet audit</h2>
<p>The node requires a known preflop aggressor, a heads-up flop, the aggressor’s first bet without a donk lead, and a subsequent fold, call or raise from the defender. Missing actions and excluded situations receive reason codes in the local audit.</p>
<p>The PL50 snapshot shows 44.6% folds in single-raised pots (2,102 opportunities) and 43.2% in three-bet pots (837 opportunities). The comparison CoinPoker HUD displays roughly 25–39%.</p>
<p>A stratified review of 100 hands found no action-classification error. Straddles, position, table size and all-in c-bets did not resolve the discrepancy. The node stays marked <strong>Audit required</strong> until the denominators can be reconciled.</p></section>
<section class="panel" id="fourbet"><h2>Four-bet sample</h2>
<p>A four-bet is the third preflop raise. The snapshot uses a minimum stack of 60bb and excludes hero actions and straddles.</p>
<p>Of 468 qualifying events, 292 have known or shown cards. AAxx appears in 172 of those hands (58.9%). The remaining 176 events contribute to coverage, while hand-class percentages use the 292 revealed hands.</p>
<p>Card composition is conditional on reveal and can be affected by showdown selection.</p></section>
<section class="panel" id="limits"><h2>Data &amp; limitations</h2>
<p>The public snapshot contains aggregate data. Raw hand histories and granular audit outputs stay local. Anonymized identifiers support parsing without constructing player profiles.</p>
<p>Export formats can change. Board buckets compress different situations, repeated contexts are not independent observations, and the tool does not calculate uncertainty intervals or adjust for multiple comparisons. Frequencies depend on the sampled stakes, players and time window.</p>
<p><a href="METHODOLOGY.md">Full methodology</a> · <a href="DATA_PRIVACY.md">Data handling notes</a></p></section>"""
    sidebar = '<aside class="panel method-menu">' + "".join(f'<a href="#{key}">{label}</a>' for key, label in menu) + "</aside>"
    return ui.page("Methodology", "Definitions, sample coverage and current validation status.", "Methodology",
                   '<div class="method-grid">' + sidebar + '<div class="method-content">' + content + "</div></div>",
                   [("Raw hands", 38248), ("Included hands", 27701), ("Parse errors", 0)],
                   navigation(), "demo/pool_summary.csv", "Snapshot definitions")


def board_snapshot(data):
    # Only the labeled values survive in the original committed chart. Their
    # provenance and missing sample counts are recorded in snapshot.json.
    import numpy as np
    from matplotlib.colors import LinearSegmentedColormap
    plt = ui.chart_pyplot()
    mat = np.array([[np.nan if value is None else value for value in row] for row in data["values"]])
    colors = LinearSegmentedColormap.from_list("snapshot", ["#31434f", "#7da5c1"])
    fig, ax = plt.subplots(figsize=(8, 4))
    image = ax.imshow(mat, aspect="auto", cmap=colors)
    ax.set_xticks(range(len(data["columns"])), [ui.POTS[x] for x in data["columns"]])
    ax.set_yticks(range(len(data["rows"])), [x.title() for x in data["rows"]])
    ax.set_title("Fold vs flop stab · board texture snapshot")
    for i, row in enumerate(data["values"]):
        for j, value in enumerate(row):
            ax.text(j, i, "—" if value is None else f"{value:.1f}%", ha="center", va="center", color="#eef2f4")
    fig.colorbar(image, ax=ax, label="Observed fold %")
    fig.text(.5, .01, "Original snapshot · per-cell samples and stakes unavailable", ha="center", fontsize=8, color="#aebbc4")
    fig.tight_layout(rect=(0, .045, 1, 1))
    path = DEMO / "charts/board_texture_oop_response_vs_ip_flop_stab_after_missed_cb.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return str(path)


def main():
    snapshot = json.loads((DEMO / "snapshot.json").read_text(encoding="utf-8"))
    summary = read_csv("pool_summary.csv")
    benchmarks = population.load_benchmarks(str(ROOT / "config/benchmarks.default.json"))
    leaks = [row for row in summary if int(row["opportunities"]) >= 30 and row["benchmark_flag"] in {"LOW", "HIGH"}]
    # The published preview uses the same count-first priority as analyze_pool.
    leaks.sort(key=lambda row: (int(row["opportunities"]), abs(float(row["deviation_pp"]))), reverse=True)
    charts = population.generate_pool_charts(DEMO, summary, [], benchmarks, 30)
    charts.append(board_snapshot(snapshot["board_chart"]))
    ui.pool_report(DEMO, snapshot["filters"], summary, leaks, charts, navigation("../"))
    fourbet_summary = read_csv("fourbet_summary.csv")
    charts = fourbet.plot_fourbet_summary(DEMO, fourbet_summary, snapshot["fourbet_classes"])
    ui.fourbet_report(DEMO, fourbet_summary, snapshot["fourbet_classes"], charts, 60, "all", navigation("../"))
    (DOCS / "index.html").write_text(overview(summary, snapshot["filters"]), encoding="utf-8")
    (DOCS / "methodology.html").write_text(methodology(), encoding="utf-8")
    css = (ui.ASSETS / "report.css").read_text(encoding="utf-8")
    js = (ui.ASSETS / "report.js").read_text(encoding="utf-8")
    shutil.copy2(ui.ASSETS / "report.css", DOCS / "assets/site.css")
    shutil.copy2(ui.ASSETS / "report.js", DOCS / "assets/report.js")
    for path in [DOCS/"index.html", DOCS/"methodology.html", DEMO/"pool_dashboard.html",
                 DEMO/"fourbet_dashboard.html", DEMO/"fourbet_report.html"]:
        prefix = "../" if path.parent == DEMO else ""
        text = path.read_text(encoding="utf-8")
        text = text.replace(f"<style>{css}</style>", f'<link rel="stylesheet" href="{prefix}assets/site.css">')
        text = text.replace(f"<script>{js}</script>", f'<script src="{prefix}assets/report.js"></script>')
        text = text.replace("</head>", f'<link rel="icon" href="{prefix}assets/favicon.svg"></head>')
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
