"""Rebuild the public HTML snapshot from its committed aggregate data."""
import csv
import json
from pathlib import Path
import shutil

from showcase import render
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
    return [("PL50 study", prefix + "index.html"), ("Population", prefix + "demo/pool_dashboard.html"),
            ("Four-bet", prefix + "demo/fourbet_dashboard.html"), ("Methodology", prefix + "methodology.html")]


def methodology():
    menu = [("definitions", "Definitions"), ("processing", "Processing"), ("review", "Reference ranges"),
            ("audit", "C-bet audit"), ("fourbet", "Four-bet sample"), ("limits", "Data & limitations")]
    content = """<section class="panel" id="definitions"><h2>Definitions</h2><dl class="definitions">
<dt>Opportunity</dt><dd>A hand state where the tracked player can take one of the actions defined for a decision node. Action percentages use this count as their denominator.</dd>
<dt>Bet size</dt><dd>Average size is measured as a percentage of the pot before the action. Facing size measures the bet presented to the responder.</dd>
<dt>Pot type</dt><dd>Preflop raise count determines limped, single-raised, three-bet and four-bet-or-larger pots.</dd>
<dt>Board texture</dt><dd>New local runs record rank pairing, maximum suit count and the number of distinct ranks sharing a five-rank straight window, including the wheel. Historical board cells lack sample counts and are omitted.</dd>
</dl></section>
<section class="panel" id="processing"><h2>Processing</h2>
<p>The parser extracts seats, positions, stacks, board cards and ordered actions. It reconstructs pot sizes and betting sequences, identifies qualifying decision opportunities, then groups them by stake and pot type.</p>
<p>An ALLIN action is classified by whether it increases the amount to call. Preflop all-in raises update the aggressor and pot type. Straddled hands are detected and excluded by default.</p>
<p>Local runs count repeated hand IDs once and withhold conflicting versions. Heads-up decision rules check turn order and the actions available at the current price. Each local run saves its filters, benchmark definitions and aggregate splits. Hand-level records retain the source actions for manual validation.</p></section>
<section class="panel" id="review"><h2>Reference ranges</h2>
<dl class="definitions"><dt>Below range / Above range</dt><dd>The observed rate falls outside the reference range and the sample meets the reporting threshold.</dd>
<dt>Within range</dt><dd>The observed rate falls within the reference range, including its endpoints.</dd>
<dt>Low sample</dt><dd>The count is below the reporting threshold.</dd>
<dt>Audit required</dt><dd>A definition or comparison remains unresolved. Deviation and review score are set to zero.</dd>
</dl><p>The analyst sets the reference ranges by hand. Sample tiers depend only on opportunity count (under 30, 30–99, 100–299 or at least 300). The review score weights the distance from the range by sample size. Probability, expected value and uncertainty intervals are outside this calculation.</p></section>
<section class="panel notice" id="audit"><h2>Fold-to-flop-c-bet audit</h2>
<p>The node requires a known preflop aggressor, a heads-up flop, the aggressor’s first bet without a donk lead, and a subsequent fold, call or raise from the defender. Missing actions and excluded situations receive reason codes in the local audit.</p>
<p>The PL50 snapshot shows 44.6% folds in single-raised pots (2,102 opportunities) and 43.2% in three-bet pots (837 opportunities). The comparison CoinPoker HUD displays roughly 25–39%.</p>
<p>The original snapshot documents a 100-hand stratified review. Its source hands are private. Straddles, position, table size and all-in c-bets did not resolve the discrepancy. The node stays marked <strong>Audit required</strong> until the denominators can be reconciled.</p></section>
<section class="panel" id="fourbet"><h2>Four-bet sample</h2>
<p>A four-bet is the third preflop raise. The snapshot uses a minimum stack of 60bb and excludes hero actions and straddles.</p>
<p>Of 468 qualifying events, 292 have known or shown cards. AAxx appears in 172 of those hands (58.9%). The remaining 176 events contribute to coverage, while hand-class percentages use the 292 revealed hands.</p>
<p>Card composition is conditional on reveal and can be affected by showdown selection. The historical display groups all known non-AAxx holdings together. The corrected suited-ace test requires a second card in the ace’s suit. Flop action frequencies are independent of that classification.</p></section>
<section class="panel" id="limits"><h2>Data &amp; limitations</h2>
<p>The historical snapshot publishes aggregate data. The PL50 case study also includes independently replayable examples from the public Leak Finder demo. Private hand histories and local audit outputs stay local. Anonymized identifiers support parsing without constructing player profiles.</p>
<p>Export formats can change. Board buckets compress different situations, repeated contexts are not independent observations, and the tool does not calculate uncertainty intervals or adjust for multiple comparisons. Frequencies depend on the sampled stakes, players and time window.</p>
<p>The public import was cross-checked against Leak Finder across 320 hands and 3,055 betting actions. The local regression suite also covers 498 heads-up betting paths.</p>
<p><a href="METHODOLOGY.md">Full methodology</a> · <a href="DATA_PRIVACY.md">Data handling notes</a></p></section>"""
    sidebar = '<aside class="panel method-menu">' + "".join(f'<a href="#{key}">{label}</a>' for key, label in menu) + "</aside>"
    return ui.page("Methodology", "Definitions, sample coverage and current validation status.", "Methodology",
                   '<div class="method-grid">' + sidebar + '<div class="method-content">' + content + "</div></div>",
                   [("Raw hands", 38248), ("Included hands", 27701), ("Parse errors", 0)],
                   navigation(), "demo/pool_summary.csv", "Snapshot definitions")


def main():
    snapshot = json.loads((DEMO / "snapshot.json").read_text(encoding="utf-8"))
    summary = read_csv("pool_summary.csv")
    benchmarks = population.load_benchmarks(str(ROOT / "config/benchmarks.default.json"))
    leaks = [row for row in summary if int(row["opportunities"]) >= 30 and row["benchmark_flag"] in {"LOW", "HIGH"}]
    # The published preview uses the same count-first priority as analyze_pool.
    leaks.sort(key=lambda row: (int(row["opportunities"]), abs(float(row["deviation_pp"]))), reverse=True)
    charts = population.generate_pool_charts(DEMO, summary, [], benchmarks, 30)
    ui.pool_report(DEMO, snapshot["filters"], summary, leaks, charts, navigation("../"))
    fourbet_summary = read_csv("fourbet_summary.csv")
    charts = fourbet.plot_fourbet_summary(DEMO, fourbet_summary, snapshot["fourbet_classes"])
    ui.fourbet_report(DEMO, fourbet_summary, snapshot["fourbet_classes"], charts, 60, "all", navigation("../"))
    render(summary)
    (DOCS / "methodology.html").write_text(methodology(), encoding="utf-8")
    css = (ui.ASSETS / "report.css").read_text(encoding="utf-8")
    js = (ui.ASSETS / "report.js").read_text(encoding="utf-8")
    shutil.copy2(ui.ASSETS / "report.css", DOCS / "assets/site.css")
    shutil.copy2(ui.ASSETS / "report.js", DOCS / "assets/report.js")
    for path in [DOCS/"methodology.html", DEMO/"pool_dashboard.html",
                 DEMO/"fourbet_dashboard.html", DEMO/"fourbet_report.html"]:
        prefix = "../" if path.parent == DEMO else ""
        text = path.read_text(encoding="utf-8")
        text = text.replace(f"<style>{css}</style>", f'<link rel="stylesheet" href="{prefix}assets/site.css">')
        text = text.replace(f"<script>{js}</script>", f'<script src="{prefix}assets/report.js"></script>')
        text = text.replace("</head>", f'<link rel="icon" href="{prefix}assets/favicon.svg"></head>')
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
