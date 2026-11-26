# Methodology

## Objective

The project estimates how the CoinPoker PLO pool behaves at strategically defined decision nodes. Its output is descriptive: it helps an analyst find patterns worth reviewing, quantify their sample size and inspect the source hands.

[Follow a PL50 flop from source actions to counted opportunities.](PL50.md)

## Processing stages

1. **Parse** — split the export into hands and extract metadata, seats, positions, boards and ordered actions.
2. **Normalize** — convert actions into consistent categories, reconstruct pot-relative sizes and label pot type and board texture.
3. **Identify opportunities** — emit a record only when the exact preconditions for a named decision node are met.
4. **Aggregate** — group records by stake, pot type and optional context dimensions.
5. **Review** — compare a selected metric with its configured reference range and label the sample size.
6. **Audit** — retain local spot-level records so an analyst can inspect false positives or parsing edge cases.

## Core definitions

- An **opportunity** is a hand state in which the tracked player can take one of the actions defined for a node.
- `bet_pct`, `check_pct`, `fold_pct`, `call_pct` and `raise_pct` use the node's opportunity count as denominator.
- `avg_size_pct` is the mean action size as a percentage of the pot immediately before the action.
- `avg_facing_size_pct` describes the size faced by the responder, not the responder's own action.
- `pot_type` is derived from the number of preflop raises (`limped`, `srp`, `3bet`, `4bet+`).
- Local board splits encode pairing, maximum suit concentration and the maximum number of distinct board ranks in one five-rank straight window. Aces can count low for A–5. Cells pool the underlying action counts within the same stake and pot type. The historical board image lacked cell counts and is omitted from the showcase.

### Action semantics

CoinPoker can encode both a call and a raise as `ALLIN X`. The parser compares the actor's new street contribution with the amount already required to call. An all-in is a raise only when it increases that amount; otherwise it is a call. Preflop all-in raises also update the last preflop aggressor, raise count and pot type.

Straddles alter the preflop price and positional incentives. They are parsed and counted, but straddled hands are excluded by default until separate straddle-specific decision-node definitions are validated.

### Flop c-bet response denominator

`FOLD_TO_FLOP_CBET` currently requires all of the following:

1. a final preflop aggressor is known;
2. exactly two players are active on the flop;
3. no defender donk-bet occurs before the aggressor acts;
4. the preflop aggressor makes the first flop bet;
5. the defender's next meaningful action is a fold, call or raise/all-in.

Multiway flops, missing flop actions, check-throughs, donk leads and malformed or missing responses are excluded with explicit reason codes. The opt-in audit export retains the exact flop action sequence, positions, board, c-bet size and classified response for manual review.

The local analyzer's result does not currently match the comparison CoinPoker HUD range. Until denominator equivalence is established, this spot is marked `audit_required` and must not be used for strategy inference.

### PL50 flop stab and response

The flop must be heads-up in a raised pot. The last preflop raiser must act first and check, followed immediately by the in-position player betting or checking. An immediate OOP fold, call or raise after a bet creates a separate response. Each node applies its own Hero exclusion. A check-back creates no response. The public study selects single-raised and three-bet pots.

The historical total of 19,527 node records included 164 observations also reported under a second name for the same turn response. Removing the redundant definition gives 19,363 node records. The other published frequencies use their original action counts.

## Reference ranges

The analyst sets the reference ranges in `config/benchmarks.default.json` by hand. The CSV field `confidence` is a count-only tier (under 30, 30–99, 100–299 or at least 300 opportunities). The field `exploit_score` weights distance from the range by sample size. Neither field estimates statistical confidence or expected value. A flagged row supplies a question for further study.

- **Below range** (`LOW`) or **Above range** (`HIGH`) when the observed rate is outside its reference range and meets `--min-sample`.
- **Within range** (`OK`) when the observed rate is inside the range, including its endpoints.
- **Low sample** (`low_sample`) when the count falls below the reporting threshold.
- **Audit required** (`audit_required`) when an unresolved definition or external comparison blocks interpretation.

Use reference ranges suited to the research question, stakes and time window. Each run saves the ranges it used alongside the report.

The review score helps prioritize rows by weighting their distance from the reference range by sample size. Estimating probability, expected value or uncertainty takes a separate analysis. Rows marked `audit_required` receive zero deviation and zero review score.

## Four-bet showdown analysis

A four-bet is the third preflop raise. An all-in counts as a raise only when it increases the amount to call. The analyzer reports:

- all qualifying four-bet events after stack and game filters;
- the subset with known/shown hole cards;
- AAxx and broad hand-class composition among known hands;
- the reveal rate, so missing-card selection remains visible.

The `suited_ace` feature requires another card in the ace’s suit. For example, `Ah Kc 8c 3d` has an unsuited ace. The correction affects holding descriptions only. Flop bet and response counts are derived from actions. The historical four-bet display reports AAxx and other known holdings because the full revealed hands needed to reclassify the remaining categories are private.

Unknown hands are excluded from the hand-class denominator. Results are therefore conditional on a hand being revealed and may be distorted by showdown selection.

## Quality controls

- Parse errors are counted and surfaced in `filters_applied.json`.
- Every run records the filters, hand counts and benchmark definition used.
- Synthetic tests cover hand splitting, header parsing, position assignment, board classification, known-card extraction and both report pipelines.
- Targeted fixtures cover IP/OOP c-bet responses, multiway exclusions, donk leads, check-throughs, all-in calls versus raises, preflop all-ins and straddles.
- The c-bet audit supports a deterministic, stratified sample for source-hand validation.
- The PL50 evidence ledger contains position-labeled actions from a pinned public Leak Finder demo. Private exports remain local.
- The population run tallies unknown actor-action lines on otherwise eligible hands and excludes those hands. Pot settlement checks compare net contributions and payouts plus listed fees with the reported pot and tally discrepancies separately. Historical run quality fields predate these checks.

### Verification on the public CoinPoker demo

The pinned Leak Finder export contains 320 hands. Across both analyzers, the comparison checked all 3,055 betting actions by source line, player, action and amount. It checked the pot before each action. One hand contains a ₮7 Splash drop. Its 18 subsequent actions include that external money in the population analyzer’s pot. The comparison adds the recorded drop to the reference engine’s player-funded pot for those actions.

The analyzers agreed on all 129 actor/action decisions across the nine postflop nodes they share, with Hero included on both sides. All five four-bet events matched by actor, starting stack and known holding, using a zero stack threshold for verification. Some decision definitions are shared between the projects. The separately labeled 60-case CoinPoker pack checks the IP flop-stab rule, including 30 exclusions. The regression suite also enumerates 498 synthetic heads-up paths across every configured population node. It checks same-hand opportunities, legal responses, actor filtering and known-card conflicts.

Run the comparisons from the project root with a local checkout of Leak Finder at revision `16d505268c4229ac77bce764a97d499dbf9dd8cd`.

```bash
python tools/check_demo_engines.py path/to/plo-hero-leak-finder
python tools/replay_pl50.py path/to/plo-hero-leak-finder/demo/CoinPoker-HeroDemo.txt --check --reference-cases path/to/plo-hero-leak-finder/tests/fixtures/source-audit.json.gz
```

### Reading run counts

- `raw_hands_before_filters` (population) and `raw_hands` (four-bet) count incoming blocks. Identical copies of a hand ID contribute once. Conflicting copies withhold the entire ID. The manifest reports repeat entries and conflicting IDs separately.
- Invalid community cards exclude the hand from the population run. Invalid heads-up betting rounds suppress that round’s opportunities and any later decisions that depend on it. A separately recorded, valid earlier street can still contribute. The manifest counts invalid rounds by reason.
- The aggregate `avg_size_pct` and `avg_facing_size_pct` use percentage points of the pot. For compatibility, per-event `size_pot_pct` and `facing_size_pot_pct` in `pool_spots.csv` are ratios. A half-pot bet appears as 0.5 in the event export and 50 in the summary. For a raise, chips added include the call portion.
- New reference flags for action frequencies use the full fraction. Displayed percentages are rounded to one decimal place. A partial reference override inherits the remaining fields for that node.
- `pool_filters.json` and `fourbet_filters.json` preserve each analyzer’s settings in a shared output folder. `filters_applied.json` describes the latest run. On rerun, a current-version manifest lets the analyzer retire its own unchanged optional charts and audit files when they no longer apply. Edited or older untracked files stay in place.

## Known limitations

- The parser is format-specific and can require updates if the export wording changes.
- The `FOLD_TO_FLOP_CBET` denominator remains under audit because it differs materially from a comparison CoinPoker HUD result.
- Deterministic texture buckets compress strategically different boards into broad labels.
- Raw frequencies do not control for range composition or opponent selection.
- Small samples and repeated strategic contexts are not independent observations.
- The tool does not calculate uncertainty intervals or adjust for multiple comparisons.
- Population behavior can drift over time; results should be filtered and re-run for the relevant window.
