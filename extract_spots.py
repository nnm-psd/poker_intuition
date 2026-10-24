"""Turn raw TexasSolver dumps (solves/*.json) into one compact file for the site (data/spots.json).

Each spot = one flop decision: who acts, what happened before, the legal actions, and per
hole-card combo the reach weight (for dealing), equity vs villain range and solver action frequencies.
"""
import json
from pathlib import Path

import eval7

from equity import flop_equities
from solve_flops import RANGES

ROOT = Path(__file__).parent
POT, STACK, BB = 55, 975, 10  # solver units are 0.1bb

# (path from flop root, hero, history shown to the player)
SPOTS = [
    ([], "BB", []),
    (["CHECK"], "BTN", ["BB checks"]),
    (["BET 18.000000"], "BTN", ["BB bets 1.8bb"]),
    (["CHECK", "BET 18.000000"], "BB", ["BB checks", "BTN bets 1.8bb"]),
    (["CHECK", "BET 41.000000"], "BB", ["BB checks", "BTN bets 4.1bb"]),
]


PREFLOP_PLAYER = {1: "BB", 0: "BTN"}  # TexasSolver: player 1 = OOP


def load_range(path: Path) -> dict:
    return {k: float(v) for k, v in (p.split(":") for p in path.read_text().strip().split(","))}


PREFLOP = {
    "BB": load_range(RANGES / "BB/BTN_2.5bb_BB_Call.txt"),
    "BTN": load_range(RANGES / "BTN/BTN_2.5bb.txt"),
}


def hand_class(combo: str) -> str:
    """'Ah7h' -> 'A7s', '7hAd' -> 'A7o', '2h2d' -> '22'."""
    order = "23456789TJQKA"
    (r1, s1), (r2, s2) = combo[:2], combo[2:]
    hi, lo = sorted((r1, r2), key=order.index, reverse=True)
    if hi == lo:
        return hi + lo
    return hi + lo + ("s" if s1 == s2 else "o")


RANK_NAME = dict(zip("23456789TJQKA", ["Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
                                       "Ten", "Jack", "Queen", "King", "Ace"]))


def hand_category(combo: str, board: list) -> str:
    """Plain-English flop hand, e.g. 'Top pair, plus a flush draw'."""
    order = "23456789TJQKA"
    hole = [combo[:2], combo[2:]]
    cards = hole + board
    made = eval7.handtype(eval7.evaluate([eval7.Card(c) for c in cards]))
    h = [c[0] for c in hole]
    b = sorted({c[0] for c in board}, key=order.index, reverse=True)
    if made in ("Straight", "Flush", "Full House", "Quads", "Straight Flush"):
        return made.capitalize()
    if made == "Trips":
        name = "Set" if h[0] == h[1] else "Trips"
    elif h[0] != h[1] and h[0] in b and h[1] in b:
        name = "Two pair"
    elif h[0] == h[1]:
        name = "Overpair" if order.index(h[0]) > order.index(b[0]) else "Pocket pair under the top card"
    elif h[0] in b or h[1] in b:
        i = b.index(h[0] if h[0] in b else h[1])
        name = "Top pair" if i == 0 else "Bottom pair" if i == len(b) - 1 else "Middle pair"
    else:
        name = None
    draws = []
    for suit in "shdc":
        if sum(c[1] == suit for c in cards) == 4 and any(c[1] == suit for c in hole):
            draws.append("flush draw")
    # 4 of the 5 ranks of a straight, with a hole card among them
    vals = {order.index(c[0]) + 2 for c in cards} | ({1} if any(c[0] == "A" for c in cards) else set())
    hv = {order.index(r) + 2 for r in h} | ({1} if "A" in h else set())
    windows = sum(len(vals & set(range(lo, lo + 5))) == 4 and bool(hv & set(range(lo, lo + 5)))
                  for lo in range(1, 11))
    if windows:
        draws.append("open-ended straight draw" if windows >= 2 else "gutshot")
    if name is None:
        if not draws:
            return f"{RANK_NAME[max(h, key=order.index)]} high"
        return " and ".join(draws).capitalize()
    return name + (", plus a " + " and ".join(draws) if draws else "")


def label(action: str) -> str:
    name, _, amount = action.partition(" ")
    if not amount:
        return name.title()
    chips = float(amount)
    if chips >= STACK:
        return "All-in"
    return f"{'Bet' if name == 'BET' else 'Raise to'} {chips / BB:g}bb"


def extract(raw: dict, board: list) -> list:
    spots = []
    for path, hero, history in SPOTS:
        villain = "BTN" if hero == "BB" else "BB"
        # each player's earlier choices along the path shrink which combos still reach this node
        node, reach = raw, {"BB": {}, "BTN": {}}
        for action in path:
            r = reach[PREFLOP_PLAYER[node["player"]]]
            idx = node["strategy"]["actions"].index(action)
            for c, f in node["strategy"]["strategy"].items():
                r[c] = r.get(c, 1.0) * f[idx]
            node = node["childrens"][action]
        assert PREFLOP_PLAYER[node["player"]] == hero, (path, hero)
        weight = lambda p, c: PREFLOP[p].get(hand_class(c), 0.0) * reach[p].get(c, 1.0)
        # villain combos, named as the solver names them: take them from a node where villain acts
        vnode = raw if PREFLOP_PLAYER[raw["player"]] == villain else raw["childrens"]["CHECK"]
        villain_combos = {c: weight(villain, c) for c in vnode["strategy"]["strategy"]}
        strat = node["strategy"]
        hero_combos = {c: weight(hero, c) for c in strat["strategy"]}
        hero_combos = {c: w for c, w in hero_combos.items() if w >= 0.01}
        eq = flop_equities(board, hero_combos, {c: w for c, w in villain_combos.items() if w > 0})
        combos = {}
        for c, w in hero_combos.items():
            combos[c] = {"w": round(w, 3), "eq": round(eq[c], 3), "cat": hand_category(c, board),
                         "f": [round(f, 3) for f in strat["strategy"][c]]}
        spots.append({
            "id": "-".join(a.replace(".000000", "").replace(" ", "") for a in path) or "root",
            "hero": hero,
            "history": history,
            "pot_bb": (POT + sum(float(a.split()[1]) for a in path if a.startswith("BET"))) / BB,
            "actions": [label(a) for a in strat["actions"]],
            "combos": combos,
        })
    return spots


def main():
    flops = []
    for f in sorted((ROOT / "solves").glob("*.json")):
        board = [f.stem[i:i + 2] for i in (0, 2, 4)]
        spots = extract(json.loads(f.read_text()), board)
        flops.append({"board": board, "pot_bb": POT / BB,
                      "stack_bb": STACK / BB, "spots": spots})
        for s in spots:
            for c, v in s["combos"].items():
                assert abs(sum(v["f"]) - 1) < 0.01, (f.stem, s["id"], c)
                assert 0 < v["w"] <= 1, (f.stem, s["id"], c)
    assert hand_class("Ah7h") == "A7s" and hand_class("7hAd") == "A7o" and hand_class("2h2d") == "22"
    assert hand_category("Kh2h", ["Ks", "7d", "2c"]) == "Two pair"
    assert hand_category("KhTh", ["Qs", "Jh", "2h"]) == "Flush draw and open-ended straight draw"
    assert hand_category("Ad3c", ["7h", "5h", "2d"]) == "Gutshot"
    assert hand_category("4h4d", ["Td", "Tc", "4h"]) == "Full house"
    out = ROOT / "data/spots.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"spot": "100bb cash, BTN opens 2.5bb, BB calls", "flops": flops},
                              separators=(",", ":")))
    print(f"{len(flops)} flops, {sum(len(x['spots']) for x in flops)} spots -> {out} "
          f"({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
