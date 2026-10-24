"""Turn raw TexasSolver dumps (solves/*.json) into one compact file for the site (data/spots.json).

Each spot = one flop decision: who acts, what happened before, pot and price, the legal actions, and per
hole-card combo [reach weight, equity vs villain range, hand-name index, solver action frequencies...].
"""
import json
from pathlib import Path

import eval7

from equity import flop_equities
from solve_flops import RANGES

ROOT = Path(__file__).parent
POT, STACK, BB = 55, 975, 10  # solver units are 0.1bb

# (path from flop root, situation used for the per-skill breakdown); the hero is whoever acts at the node
SPOTS = [
    ([], "First to act"),
    (["CHECK"], "Checked to"),
    (["BET 18"], "Facing a lead"),
    (["CHECK", "BET 18"], "Facing a c-bet"),
    (["CHECK", "BET 41"], "Facing a c-bet"),
    (["CHECK", "BET 18", "RAISE 73"], "Facing a check-raise"),
    (["CHECK", "BET 41", "RAISE 123"], "Facing a check-raise"),
    (["BET 18", "RAISE 73"], "Facing a raise"),
]
MIN_REACH = 3.0  # drop spots the hero reaches with fewer than ~3 combos: too rare to be worth testing


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


def texture(board: list) -> str:
    """Coarse board class for the breakdown: Paired, Monotone, Wet (two-tone or connected) or Dry."""
    order = "23456789TJQKA"
    ranks = sorted(order.index(c[0]) + 2 for c in board)
    suits = {c[1] for c in board}
    if len(set(ranks)) < 3:
        return "Paired"
    if len(suits) == 1:
        return "Monotone"
    low = sorted(1 if r == 14 else r for r in ranks)  # ace can play low
    connected = any(b - a <= 1 for a, b in zip(ranks, ranks[1:])) or ranks[2] - ranks[0] <= 4 or low[2] - low[0] <= 4
    return "Wet" if len(suits) == 2 or connected else "Dry"


def label(action: str, put_in: float) -> str:
    """Solver amounts are chips added by the actor; show raise-to totals like a real table does."""
    name, _, amount = action.partition(" ")
    if not amount:
        return name.title()
    total = put_in + float(amount)
    if total >= STACK:
        return "All-in"
    return f"{'Bet' if name == 'BET' else 'Raise to'} {total / BB:g}bb"


def key(action: str) -> str:
    return f"{action}.000000" if " " in action else action


def extract(raw: dict, board: list, cats: list) -> list:
    spots = []
    for path, situation in SPOTS:
        # each player's earlier choices along the path shrink which combos still reach this node
        node, reach = raw, {"BB": {}, "BTN": {}}
        put_in, history = {"BB": 0.0, "BTN": 0.0}, []
        for action in path:
            actor = PREFLOP_PLAYER[node["player"]]
            idx = node["strategy"]["actions"].index(key(action))
            for c, f in node["strategy"]["strategy"].items():
                reach[actor][c] = reach[actor].get(c, 1.0) * f[idx]
            history.append((actor, action, put_in[actor]))
            name, _, amount = action.partition(" ")
            if amount:
                put_in[actor] += float(amount)
            node = node["childrens"][key(action)]
        hero = PREFLOP_PLAYER[node["player"]]
        villain = "BTN" if hero == "BB" else "BB"
        weight = lambda p, c: PREFLOP[p].get(hand_class(c), 0.0) * reach[p].get(c, 1.0)
        # villain combos, named as the solver names them: take them from a node where villain acts
        vnode = raw if PREFLOP_PLAYER[raw["player"]] == villain else raw["childrens"]["CHECK"]
        villain_combos = {c: weight(villain, c) for c in vnode["strategy"]["strategy"]}
        strat = node["strategy"]
        hero_combos = {c: weight(hero, c) for c in strat["strategy"]}
        hero_combos = {c: w for c, w in hero_combos.items() if w >= 0.01}
        if sum(hero_combos.values()) < MIN_REACH:
            print(f"  skip {''.join(board)} {'-'.join(path)}: hero reaches it with {sum(hero_combos.values()):.1f} combos")
            continue
        eq = flop_equities(board, hero_combos, {c: w for c, w in villain_combos.items() if w > 0})
        combos = {}
        for c, w in hero_combos.items():
            cat = hand_category(c, board)
            if cat not in cats:
                cats.append(cat)
            # compact row: [reach weight, equity, hand-name index, action frequencies...]
            combos[c] = [round(w, 2), round(eq[c], 3), cats.index(cat)] + [round(f, 2) for f in strat["strategy"][c]]
        spots.append({
            "id": "-".join(a.replace(" ", "") for a in path) or "root",
            "situation": situation,
            "hero": hero,
            "history": [say(actor, action, before, hero) for actor, action, before in history],
            "pot_bb": round((POT + sum(put_in.values())) / BB, 1),
            "to_call_bb": round((max(put_in.values()) - put_in[hero]) / BB, 1),
            "actions": [label(a, put_in[hero]) for a in strat["actions"]],
            "combos": combos,
        })
    return spots


def say(actor: str, action: str, before: float, hero: str) -> str:
    """'BTN bets 1.8bb' for the opponent, 'you bet 1.8bb' for the hero."""
    name, _, amount = action.partition(" ")
    if actor == hero:
        who, verb = "you", {"CHECK": "check", "BET": "bet", "RAISE": "raise"}[name]
    else:
        who, verb = actor, {"CHECK": "checks", "BET": "bets", "RAISE": "raises"}[name]
    if name == "CHECK":
        return f"{who} {verb}"
    if name == "BET":
        return f"{who} {verb} {float(amount) / BB:g}bb"
    return f"{who} {verb} to {(before + float(amount)) / BB:g}bb"


def main():
    assert hand_class("Ah7h") == "A7s" and hand_class("7hAd") == "A7o" and hand_class("2h2d") == "22"
    assert hand_category("Kh2h", ["Ks", "7d", "2c"]) == "Two pair"
    assert hand_category("KhTh", ["Qs", "Jh", "2h"]) == "Flush draw and open-ended straight draw"
    assert hand_category("Ad3c", ["7h", "5h", "2d"]) == "Gutshot"
    assert hand_category("4h4d", ["Td", "Tc", "4h"]) == "Full house"
    assert [texture(b) for b in (["Ks", "7d", "2c"], ["Td", "Tc", "4h"], ["8h", "7h", "6h"], ["9s", "8s", "6d"],
                                 ["Ac", "5d", "4h"], ["Qh", "7s", "5c"])] == ["Dry", "Paired", "Monotone", "Wet", "Wet", "Dry"]
    assert label("RAISE 176.000000", 18) == "Raise to 19.4bb" and label("RAISE 957.000000", 18) == "All-in"
    assert say("BB", "RAISE 73", 0, "BTN") == "BB raises to 7.3bb" and say("BTN", "BET 18", 0, "BTN") == "you bet 1.8bb"
    # one file per flop, so a session only downloads the flops it deals; plus a small index
    out_dir = ROOT / "data/flops"
    out_dir.mkdir(parents=True, exist_ok=True)
    index = []
    for f in sorted((ROOT / "solves").glob("*.json")):
        out = out_dir / f.name
        board = [f.stem[i:i + 2] for i in (0, 2, 4)]
        if out.exists() and out.stat().st_mtime > max(f.stat().st_mtime, Path(__file__).stat().st_mtime):
            flop = json.loads(out.read_text())  # unchanged since last run
        else:
            cats = []
            flop = {"board": board, "texture": texture(board), "cats": cats,
                    "spots": extract(json.loads(f.read_text()), board, cats)}
            for s in flop["spots"]:
                for c, (w, eq, cat, *freqs) in s["combos"].items():
                    assert abs(sum(freqs) - 1) < 0.03, (f.stem, s["id"], c)
                    assert 0 < w <= 1 and 0 <= eq <= 1, (f.stem, s["id"], c)
            out.write_text(json.dumps(flop, separators=(",", ":")))
        print(f"{f.stem}: {flop['texture']}, {len(flop['spots'])} spots, {out.stat().st_size // 1024} KB")
        index.append({"file": f"flops/{f.name}", "board": board, "texture": flop["texture"]})
    (ROOT / "data/index.json").write_text(json.dumps(
        {"spot": "100bb cash, BTN opens 2.5bb, BB calls", "flops": index}, separators=(",", ":")))
    print(f"{len(index)} flops -> data/index.json")


if __name__ == "__main__":
    main()
