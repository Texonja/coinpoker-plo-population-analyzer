"""Render the HTML landing page and GitHub case study from the same two datasets."""
from collections import Counter
from html import escape
import json
from pathlib import Path

from replay_pl50 import LEDGER, RESPONSE, STAB

DOCS = Path(__file__).resolve().parents[1] / "docs"
POTS = {"srp": "Single-raised pot", "3bet": "Three-bet pot"}
NODES = {STAB: "IP after a check", RESPONSE: "OOP facing a bet"}
ACTIONS = {STAB: ("bet", "check"), RESPONSE: ("fold", "call", "raise")}
SUITS = {"s": "♠", "h": "♥", "d": "♦", "c": "♣"}
FEATURED = "9000002879"


def panel_rows(summary, ledger):
    output = []
    for pot in POTS:
        for node in NODES:
            row = next(r for r in summary if r["stake_label"] == "PL50" and r["pot_type"] == pot and r["spot_id"] == node)
            counts = json.loads(row["raw_action_counts"])
            historical = Counter({k.replace("raise_or_allin", "raise"): v for k, v in counts.items()})
            demo = Counter(d["action"] for hand in ledger["hands"] if hand["pot"] == pot
                           for d in hand["decisions"] if d["node"] == node)
            if sum(historical.values()) != int(row["opportunities"]) or set(historical) - set(ACTIONS[node]):
                raise ValueError(f"Invalid snapshot counts for {pot} / {node}")
            output.append((pot, node, historical, demo))
    return output


def rate(value, n):
    return f"{100*value/n:.1f}%" if n else "—"


def mix(counts, node, show_rate=True):
    n = sum(counts.values())
    parts = []
    for action in ACTIONS[node]:
        entry = f"{action} {counts[action]}/{n}"
        if show_rate:
            entry += f" ({rate(counts[action], n)})"
        parts.append(entry)
    return " · ".join(parts)


def board_text(hand):
    return " ".join(c[:-1] + SUITS[c[-1]] for c in hand["board"])


def cards(hand):
    return "".join(f'<span class="card suit-{c[-1]}">{escape(c[:-1])}<small>{SUITS[c[-1]]}</small></span>'
                   for c in hand["board"])


def source_link(ledger, hand):
    return f'{ledger["source"]}#L{hand["first_line"]}-L{hand["last_line"]}'


def trace_note(hand):
    if not hand["decisions"]:
        return "The caller leads before the in-position preflop raiser can act. Neither featured decision occurs."
    if hand["trace"][1]["action"] == "check":
        return "The check-back adds one IP check. OOP faces no bet on this flop."
    if hand["trace"][1]["hero"]:
        return "Hero makes the bet. Only the opponent’s response enters the population counts."
    if hand["trace"][2]["hero"]:
        return "The opponent makes the bet. Hero responds, so only the IP bet enters the population counts."
    return "Both actors are opponents. This hand supplies one IP bet and one OOP response."


def action_text(event):
    actor = event["position"] + (" (Hero)" if event["hero"] else "")
    return f'{actor} {event["text"]}'


def hand_view(ledger, hand, expanded=False):
    scored = {d["line"]: NODES[d["node"]] + " · " + d["action"] for d in hand["decisions"]}
    steps = "".join(f'<li><span>{escape(action_text(e))}</span><small>{escape(scored.get(e["line"], ""))}</small></li>'
                    for e in hand["trace"])
    return f'''<details class="hand" id="h{hand['id']}"{' open' if expanded else ''}>
<summary><span class="hand-label">#{hand['id']}<small>{POTS[hand['pot']]} · {hand['pfa']} raised last preflop</small></span>
<span class="cards" aria-label="{board_text(hand)}">{cards(hand)}</span></summary>
<div class="hand-body"><p>Flop pot <b>₮{hand['trace'][0]['pot_before']:.2f}</b></p><ol>{steps}</ol>
<p>{trace_note(hand)}</p><a href="{source_link(ledger, hand)}">Read the original hand · lines {hand['first_line']}–{hand['last_line']} ↗</a></div></details>'''


def html(rows, ledger, focus):
    focus_total = sum(focus.values())
    hand = next(h for h in ledger["hands"] if h["id"] == FEATURED)
    others = sorted((h for h in ledger["hands"] if h is not hand), key=lambda h: (not h["decisions"], h["id"]))
    table = []
    for pot, node, historical, demo in rows:
        for a in ACTIONS[node]:
            members = [(h, d["action"]) for h in ledger["hands"] if h["pot"] == pot
                       for d in h["decisions"] if d["node"] == node]
            eligible = "".join(f'<li><a href="#h{h["id"]}">#{h["id"]}</a> · {action}</li>'
                               for h, action in members)
            sample = (f'<details class="proof"><summary>{demo[a]} / {len(members)}</summary>'
                      f'<p>Every eligible decision</p><ul>{eligible}</ul></details>')
            n = sum(historical.values())
            arithmetic = " + ".join(f"{historical[k]} {k}{'s' if historical[k] != 1 else ''}" for k in ACTIONS[node])
            archive = (f'<details class="proof"><summary><b>{rate(historical[a], n)}</b> '
                       f'<small>{historical[a]} / {n}</small></summary><p>{arithmetic} = {n} opportunities.</p>'
                       f'<p><a href="demo/pool_summary.csv">PL50 · {POTS[pot]} · {NODES[node]} (CSV)</a></p></details>')
            table.append(f'<tr><td>{POTS[pot]}</td><td>{NODES[node]}</td><th scope="row">{a.title()}</th>'
                         f'<td>{archive}</td><td>{sample}</td></tr>')
    css = (DOCS / "assets/showcase.css").read_text(encoding="utf-8")
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>When the raiser checks · PL50 | CoinPoker Population Analyzer</title><style>{css}</style></head>
<body><header><div class="shell top"><a class="brand" href="#top"><b aria-hidden="true">♠</b> CoinPoker <span>/ Population Analyzer</span></a>
<nav aria-label="Reports"><a href="#counts">Counts</a><a href="#replay">Hands</a><a href="demo/pool_dashboard.html">Population</a><a href="demo/fourbet_dashboard.html">Four-bets</a></nav></div></header>
<main id="top"><section class="lead"><div class="shell intro"><div><p class="kicker">POT-LIMIT OMAHA · PL50</p>
<h1>When the raiser checks.</h1><p class="deck">Heads-up on the flop, the preflop raiser checks out of position. How often does the player behind bet, and what happens when they do?</p>
<a class="button" href="#first-hand">Follow one hand <span>↓</span></a></div>
<div class="hero-stat"><p>IP bet · single-raised pots</p><strong>{rate(focus['bet'], focus_total)}</strong>
<div class="bar" aria-hidden="true"><i style="width:{100*focus['bet']/focus_total:.2f}%"></i></div>
<div class="legend"><b>{focus['bet']} bets</b><span>{focus['check']} checks</span></div><a href="#counts">{focus_total} opportunities in the historical sample ↓</a></div></div></section>
<div class="shell content"><section id="first-hand" class="split"><div><p class="kicker">SOURCE HAND · LEAK FINDER</p><h2>From a flop to two records</h2>
<p>The small blind was the last preflop raiser. The hijack bets half pot after the check. Count one bet for the hijack and one fold for the small blind.</p>
<p class="aside">IP acts last on the flop. OOP acts first. A bet by IP after the raiser checks is called a <em>stab</em>.</p></div>
{hand_view(ledger, hand, True)}</section>
<section id="counts"><p class="kicker">PL50 · DECISION FREQUENCIES</p><h2>How the counts add up</h2>
<p>The historical column uses published action counts. The replay column counts decisions in all {ledger['pl50_hands']} eligible PL50 hands from the public Leak Finder demo. Open a historical percentage for its arithmetic or a replay count for every hand in its denominator.</p>
<div class="table-wrap" tabindex="0" aria-label="Decision counts"><table><thead><tr><th>Pot</th><th>Decision</th><th>Action</th><th>Historical pool</th><th>Public replay</th></tr></thead><tbody>{''.join(table)}</tbody></table></div>
<p class="aside">Each action is divided by the opportunities in its own decision. The actor filter applies separately to IP and OOP. An opponent can respond to a Hero bet, which explains why the number of OOP responses can exceed the number of counted IP bets.</p>
<a href="demo/pool_summary.csv">Historical action counts (CSV) ↗</a> <span class="sep">/</span> <a href="demo/pl50_replay.json">Public decision ledger (JSON) ↗</a></section>
<section id="replay"><p class="kicker">PUBLIC REPLAY · HAND INDEX</p><h2>Inspect the decisions</h2><p>The demo has {ledger['raw_hands']} hands across stakes. PL50 contributes {ledger['pl50_hands']} regular PLO4 hands, including {ledger['by_ante']['0.08']} with a ₮0.08 ante and {ledger['by_ante']['0.00']} without an ante. The index covers every scored hand in these two pot types and one excluded lead. All nine scored hands reconcile to the published pots and awards. Across PL50, {ledger['settlement_counts']['mismatch']} other hands have a payout discrepancy.</p>
<p><a href="#h{FEATURED}">Return to the first example ↑</a></p><div class="hand-grid">{''.join(hand_view(ledger,h) for h in others)}</div></section>
<section><p class="kicker">INTERPRETATION</p><h2>What changes in a three-bet pot?</h2>
<p>{interpret(rows)}</p><p>The historical pool contains aggregate rows from a private export. The hand examples come from a separate public demo and illustrate the counting rule. The demo is small and selected for study. The dashboard’s reference ranges are set by hand and its sample tiers use opportunity counts alone. Estimating bluff profitability requires ranges, sizing and later-street outcomes.</p>
<a href="methodology.html">Definitions &amp; audit status ↗</a></section></div></main>
<footer><div class="shell">CoinPoker PLO Population Analyzer · Completed hand histories</div></footer>
<script>function openHand(){{const el=document.getElementById(location.hash.slice(1));if(el?.matches('details')){{el.open=true;el.scrollIntoView();}}}}
window.addEventListener('hashchange',openHand);document.addEventListener('click',e=>{{const a=e.target.closest('a');if(a?.hash===location.hash)openHand();}});if(location.hash)openHand();</script>
</body></html>'''


def interpret(rows):
    rates = {(pot, node): counts for pot, node, counts, _ in rows}
    def pct(pot, node, action):
        c = rates[pot, node]
        return rate(c[action], sum(c.values()))
    return (f"IP bet frequencies were close in single-raised and three-bet pots "
            f"({pct('srp', STAB, 'bet')} and {pct('3bet', STAB, 'bet')}). "
            f"Once OOP faced a bet, check-raises occurred in {pct('srp', RESPONSE, 'raise')} of single-raised pots "
            f"and {pct('3bet', RESPONSE, 'raise')} of three-bet pots. The latter estimate comes from "
            f"{sum(rates['3bet', RESPONSE].values())} responses. Stack depth, board and bet size can differ between the groups.")


def render(summary):
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    rows = panel_rows(summary, ledger)
    focus = rows[0][2]
    (DOCS / "index.html").write_text(html(rows, ledger, focus), encoding="utf-8")
    hand = next(h for h in ledger["hands"] if h["id"] == FEATURED)
    md = ["# When the raiser checks", "",
          "A PL50 study of heads-up flops in CoinPoker PLO4. The last preflop raiser checks out of position (OOP). "
          "How often does the player in position (IP) bet, and how does OOP respond?", "",
          f"**{rate(focus['bet'],sum(focus.values()))}** of single-raised opportunities produced an IP bet in the historical pool. "
          f"The source row contains **{focus['bet']} bets + {focus['check']} checks = {sum(focus.values())} opportunities**.", "",
          "## Follow one hand", "", f"**#{FEATURED} · {board_text(hand)} · ₮{hand['trace'][0]['pot_before']:.2f} on the flop.** "
          "The small blind raised preflop. The hijack bets half pot after the small blind checks. "
          "That adds one IP bet. The small blind folds, adding one OOP fold. "
          f"[Read the source actions.]({source_link(ledger,hand)})", "",
          "## Published counts and public replay", "",
          "The historical column uses the published PL50 aggregate CSV. "
          f"The independent replay scans all {ledger['pl50_hands']} eligible PL50 hands in the {ledger['raw_hands']}-hand Leak Finder demo. "
          "Each column has its own denominator.", "",
          "| Pot | Decision | Historical pool | Public replay |", "|---|---|---|---|"]
    md.extend(f"| {POTS[p]} | {NODES[node]} | {mix(hist,node)} | {mix(demo,node,show_rate=False)} |" for p,node,hist,demo in rows)
    md += ["", "Hero’s actions are excluded separately for each decision. A Hero bet can still produce a counted opponent response. "
           "A check-back counts once for IP and creates no OOP response opportunity. "
           "The private hands behind the historical aggregate are unavailable for individual replay. "
           "[Inspect the historical CSV.](demo/pool_summary.csv)", "", interpret(rows), "",
           "## Every public example", "",
           "Each link opens the preflop and flop source lines. The last column identifies the exact contribution to the replay. "
           f"The {ledger['pl50_hands']} PL50 hands include {ledger['by_ante']['0.08']} with an ante and {ledger['by_ante']['0.00']} without one. "
           f"The last row illustrates an excluded caller lead. All nine scored hands reconcile to the source pots and awards. Across PL50, {ledger['settlement_counts']['mismatch']} other hands have payout discrepancies.", "",
           "| Source hand | Pot / flop | Flop action in order | Counted decisions |", "|---|---|---|---|"]
    for h in sorted(ledger["hands"], key=lambda x: (not x["decisions"], x["id"])):
        events = " → ".join(action_text(e) for e in h["trace"])
        scored = " · ".join(f"{NODES[d['node']]} ({d['action']})" for d in h["decisions"]) or trace_note(h)
        md.append(f"| [#{h['id']}]({source_link(ledger,h)}) | {POTS[h['pot']]} · {board_text(h)} | {events} | {scored} |")
    md += ["", "The demo is selected for study and has few eligible responses. Use it to verify the decision rules. "
           "The dashboard uses hand-set reference ranges and count-only sample tiers. Estimating the profitability of a stab also requires ranges, bet sizes and later-street outcomes.", "",
           "[Machine-readable replay](demo/pl50_replay.json) · [Methodology](METHODOLOGY.md) · [How to reproduce](../README.md#reproduce-the-public-replay)", ""]
    (DOCS / "PL50.md").write_text("\n".join(md), encoding="utf-8")
