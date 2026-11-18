# CoinPoker PLO Population Analyzer

See how often players take common lines in CoinPoker PLO, from delayed c-bets and turn probes to river barrels. The analyzer rebuilds the betting sequence from hand histories so each rate has a clear denominator. Reports are grouped by stake, pot type, position, board texture and bet size.

[Overview](docs/index.html) · [Population dashboard](docs/demo/pool_dashboard.html) · [Four-bet dashboard](docs/demo/fourbet_dashboard.html) · [Methodology](docs/methodology.html)

On Windows, double-click `START.bat` to open the included demo in your browser. The demo needs no Python setup and contains only aggregate results.

## What I found in the sample

I started with **38,248 hands**. The default filters kept **27,701 regular PLO4 hands without straddles** and produced **19,527 decision records**. The parser reported no errors. I checked 100 flop c-bet opportunities against the original action sequences.

- At PL50, the original bettor re-raised **30.0%** of the time after a flop check-raise (90 spots in three-bet pots). That figure was **48.9%** before I fixed all-in calls that had been counted as raises.
- My PL50 fold-to-flop-c-bet rates were **44.6%** in single-raised pots (2,102 spots) and **43.2%** in three-bet pots (837 spots). The CoinPoker HUD showed roughly **25–39%**. I couldn't explain the gap with straddles, all-ins, position or table size. Those rows are marked `audit_required` and left out of the strategy rankings.
- In the four-bet sample, cards were known in **292 of 468** qualifying hands. **172 of the 292** were AAxx (58.9%). That rate describes the hands we could see, and the unseen hands may have a different mix.

## Run it locally

Use Python 3.10 or later. In an active virtual environment, install the project from the repository root.

```bash
python -m pip install -e ".[dev]"
```

Try both reports on the included synthetic hands.

```bash
plo-population --input examples/synthetic_hands.txt --outdir reports/synthetic_pool --game-filter plo4 --min-sample 1
plo-fourbet --input examples/synthetic_hands.txt --outdir reports/synthetic_fourbet --game-filter plo4 --min-stack-bb 60
```

To check which hands count toward fold-to-flop-c-bet in your own export, run the audit.

```bash
plo-population --input path/to/hands.txt --outdir reports/audit --audit-flop-cbet --audit-sample-size 100
```

Open `pool_dashboard.html` or `fourbet_dashboard.html` in the output folder. The CSVs hold the breakdowns, and `filters_applied.json` records the run settings. Keep real hand histories and hand-level audit files out of version control. See the [data privacy notes](docs/DATA_PRIVACY.md).

## Scope and tests

The default analysis covers regular PLO4 hands and excludes Hero's own decisions. PLO5, bomb pots and straddles need separate validation. The review thresholds are configurable and meant for finding spots worth a closer look.

```bash
python -m unittest discover -s tests -v
```

## AI assistance

I defined the poker questions, rules and checks, and reviewed sample hands against the source. I used AI to help write the code and edit the documentation.
