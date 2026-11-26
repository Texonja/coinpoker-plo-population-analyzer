# CoinPoker PLO Population Analyzer

**[Open the PL50 case study — When the raiser checks](docs/PL50.md)**

In single-raised pots, the player in position bet **345 times** and checked back **502 times** after the preflop raiser checked. That makes **345 / 847 = 40.7%**. How often did the raiser fold, call or check-raise when facing a bet? The case study follows both decisions through a flop and links to the original actions.

On **8♦ Q♣ K♦**, the hijack bets ₮2.49 into ₮4.98 and the small blind folds. This public example adds one IP bet and one OOP fold to the replay. [Read the original hand.](https://github.com/Texonja/plo-hero-leak-finder/blob/16d505268c4229ac77bce764a97d499dbf9dd8cd/demo/CoinPoker-HeroDemo.txt#L5402-L5435)

The study opens directly on GitHub. For the interactive edition on Windows, choose **Extract all** on the release ZIP and double-click **START.bat** in the extracted folder. On another system, open **docs/index.html**. The demo runs without Python. [Download the latest demo ZIP](https://github.com/Texonja/coinpoker-plo-population-analyzer/releases/latest/download/coinpoker-plo-population-analyzer.zip)

## What the project measures

The Python analyzer reconstructs betting sequences from completed CoinPoker hand histories. It groups opponent decisions by stake, pot type, position, board texture and bet size. The same hand can contain multiple opportunities. Default filters cover regular PLO4, exclude straddles and exclude Hero as the actor of each decision.

- **Historical pool.** The published run included 27,701 of 38,248 hands across PL25, PL50 and PL100. The cleaned summary contains 19,363 node records after removing 164 entries for a duplicate turn-response definition. Several different nodes can still describe the same hand. The original hand histories are private. [Aggregate action counts](docs/demo/pool_summary.csv)
- **Public replay.** A separate 320-hand Leak Finder demo contributes 116 eligible PL50 hands. Nine hands contribute 13 decisions across the two featured nodes in single-raised and three-bet pots. A tenth hand demonstrates an excluded lead. Each counted decision links back to a line of the pinned source. [PL50 examples](docs/PL50.md#every-public-example)
- **Four-bets.** Cards were visible in 292 of 468 qualifying events at the 60bb minimum. Of those 292, 172 contained a pair of aces (58.9%). Which hands reach a reveal affects that estimate. [Four-bet counts](docs/demo/fourbet_summary.csv)
- **Reference ranges.** An analyst sets the ranges by hand. The dashboard shows the opportunity-count band for each row. A gap from the range describes an observation. Establishing a strategic error or a profitable adjustment requires additional evidence.
- **Open audit.** Historical fold-to-flop-c-bet rates differ from the comparison HUD. These rows carry an audit flag and receive no review score. [Denominator and limitations](docs/METHODOLOGY.md#flop-c-bet-response-denominator)

## Reproduce the public replay

Download the pinned [CoinPoker-HeroDemo.txt](https://raw.githubusercontent.com/Texonja/plo-hero-leak-finder/16d505268c4229ac77bce764a97d499dbf9dd8cd/demo/CoinPoker-HeroDemo.txt). From the repository root, give the verification script the path to that file. It checks the source fingerprint, parses every hand and compares every featured decision and source line against the published ledger. Python 3.10 or later is sufficient.

```bash
python tools/replay_pl50.py path/to/CoinPoker-HeroDemo.txt --check
```

For an independent check, download the [pinned Leak Finder reference cases](https://raw.githubusercontent.com/Texonja/plo-hero-leak-finder/16d505268c4229ac77bce764a97d499dbf9dd8cd/tests/fixtures/source-audit.json.gz) and add `--reference-cases path/to/source-audit.json.gz` to that command. The analyzer matched all 60 labeled CoinPoker flop-stab cases by source line, actor and action (7 bets, 23 checks and 30 exclusions). This check covers the IP decision.

The complete demo comparison checks 3,055 betting actions, 129 decisions across nine shared nodes and all five four-bets. The local tests also enumerate 498 heads-up paths from flop to river. [Verification results, test commands and limits](docs/METHODOLOGY.md#verification-on-the-public-coinpoker-demo)

## Analyze a hand history

Install the project in a Python 3.10+ virtual environment. Try the included synthetic hands or supply the path and Hero alias for your own export.

```bash
python -m pip install -e ".[dev]"
plo-population --input examples/synthetic_hands.txt --outdir reports/pool --audit-flop-cbet
plo-fourbet --input examples/synthetic_hands.txt --outdir reports/fourbet --min-stack-bb 60
```

Open `pool_dashboard.html` or `fourbet_dashboard.html` in the output folder. The CSV files contain the breakdowns. `filters_applied.json` records the run settings and quality checks. For the public demo export, use `--hero HeroDemo --stake-filter PL50`.

Run the regression tests with `python -m unittest discover -s tests -v`. Rebuild the HTML reports and GitHub case study with `python tools/refresh_demo.py`. [Methodology](docs/METHODOLOGY.md) · [Data handling](docs/DATA_PRIVACY.md)
