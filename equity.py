"""Exact flop all-in equity of every hero combo vs a weighted villain range (enumerates all turn+river runouts)."""
from itertools import combinations

import eval7
import numpy as np

DECK = [r + s for r in "23456789TJQKA" for s in "shdc"]


def flop_equities(board: list, hero: dict, villain: dict) -> dict:
    """board: ['Ks','7d','2c']; hero/villain: {'AhKh': weight}. Returns {hero combo: equity in [0, 1]}."""
    hc, vc = list(hero), list(villain)
    vw = np.array([villain[c] for c in vc])
    runouts = list(combinations([c for c in DECK if c not in board], 2))
    cards = lambda combo: {combo[:2], combo[2:]}
    hero_cards, vill_cards = [cards(c) for c in hc], [cards(c) for c in vc]
    # hero and villain can't share a card
    disjoint = np.array([[not (h & v) for v in vill_cards] for h in hero_cards])
    base = [eval7.Card(c) for c in board]
    score = {}
    win = np.zeros(len(hc))
    total = np.zeros(len(hc))
    for t, r in runouts:
        b = base + [eval7.Card(t), eval7.Card(r)]
        def ranks(combos):
            out = np.empty(len(combos))
            for i, c in enumerate(combos):
                if c not in score:
                    score[c] = eval7.evaluate(b + [eval7.Card(c[:2]), eval7.Card(c[2:])])
                out[i] = score[c]
            return out
        h_ok = np.array([t not in hs and r not in hs for hs in hero_cards])
        v_ok = np.array([t not in vs and r not in vs for vs in vill_cards])
        hr, vr = ranks(hc), ranks(vc)
        score.clear()
        w = disjoint * (vw * v_ok) * h_ok[:, None]
        cmp = (hr[:, None] > vr[None, :]) + 0.5 * (hr[:, None] == vr[None, :])
        win += (w * cmp).sum(1)
        total += w.sum(1)
    return {c: float(win[i] / total[i]) if total[i] else 0.0 for i, c in enumerate(hc)}


def _brute(board, h, v):
    """Independent slow check: one hand vs one hand."""
    win = n = 0
    rest = [c for c in DECK if c not in board and c not in (h[:2], h[2:], v[:2], v[2:])]
    for t, r in combinations(rest, 2):
        b = [eval7.Card(x) for x in board + [t, r]]
        a = eval7.evaluate(b + [eval7.Card(h[:2]), eval7.Card(h[2:])])
        z = eval7.evaluate(b + [eval7.Card(v[:2]), eval7.Card(v[2:])])
        win += (a > z) + 0.5 * (a == z)
        n += 1
    return win / n


if __name__ == "__main__":
    board = ["Ks", "7d", "2c"]
    # hand-derived: AK beats a set of 7s only on KK (quads), AA (3), AK (6), K2 (6) runouts -> 16/990
    eq = flop_equities(board, {"AhKh": 1}, {"7s7c": 1})["AhKh"]
    assert abs(eq - 16 / 990) < 1e-9, eq
    # weighted range == weighted average of brute-force single matchups
    v = {"7s7c": 1.0, "9h8h": 0.5, "QdJd": 0.25}
    want = sum(w * _brute(board, "AhKh", c) for c, w in v.items()) / sum(v.values())
    got = flop_equities(board, {"AhKh": 1, "QhJh": 1}, v)
    assert abs(got["AhKh"] - want) < 1e-9, (got, want)
    print("ok", got)
