# Poker intuition

A static site that tests poker instincts on solved flop spots: you estimate your equity, act against a clock,
and a solver grades the choice. Sessions are saved in the browser.

Spot: 100bb cash, BTN opens 2.5bb, BB calls. Each flop has up to eight flop decision points (first to act,
checked to, facing a lead, a c-bet, a check-raise or a raise). Suits are relabelled at random for display.

Live at https://nnm-psd.github.io/poker_intuition/

## Run the site

```
python -m http.server
```

Open http://localhost:8000. The page needs HTTP; opening `index.html` as a file can't load the data.

## Rebuild the data

1. Download [TexasSolver v0.2.0](https://github.com/bupticybee/TexasSolver/releases/tag/v0.2.0) (Windows) and unzip it to
   `vendor/texassolver/`. It's AGPL-3.0 and used only offline to generate data; it isn't part of this repo.
2. `uv venv && uv pip install -r requirements.txt`
3. `python solve_flops.py` solves every flop in `FLOPS` that isn't in `solves/` yet (about 37 minutes each on a 4-core laptop).
4. `.venv/Scripts/python extract_spots.py` turns each raw solve into `data/flops/<board>.json`, with exact equities
   (about 2.5 minutes per flop; unchanged flops are reused), and lists them in `data/index.json`.

`python equity.py` runs the equity self-checks.

## Keep solving

`.venv/Scripts/python keep_solving.py` solves the next unsolved flop, rebuilds the data, commits and pushes it, then
moves on. After the hand-picked `FLOPS` it works through all 1,755 distinct flops, weighted by how often each is dealt.
Create a file named `STOP` in this folder to stop after the current flop.
