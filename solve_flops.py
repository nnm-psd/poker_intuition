"""Pre-solve a small library of flop spots with TexasSolver (console build).

Spot: 100bb cash, BTN opens 2.5bb, BB calls. Units are 0.1bb (pot 5.5bb = 55).
Usage: python solve_flops.py            # solves every flop in FLOPS not yet in solves/
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SOLVER_DIR = ROOT / "vendor/texassolver/TexasSolver-v0.2.0-Windows"
RANGES = SOLVER_DIR / "ranges/qb_ranges/100bb 2.5x 500rake"
OUT = ROOT / "solves"

# ponytail: hand-picked texture sample; upgrade path = all 1755 iso flops once solve time allows
FLOPS = ["Ks,7d,2c", "Ah,8d,3c", "Qs,Jh,2h", "9s,8s,6d", "Td,Tc,4h", "7h,5h,2d",
         "As,Ks,4d", "Ad,7c,7h", "Kh,Qd,Th", "Jc,8d,4s", "Ts,9h,4c", "8h,7h,6h", "Qd,8d,3d",
         "6c,4d,2s", "5s,5d,2h", "Jh,Td,9c", "Ac,5d,4h", "Kd,Kc,8s", "9d,6c,3h", "Qh,7s,5c"]

SIZES = """\
set_bet_sizes oop,flop,bet,33
set_bet_sizes oop,flop,raise,60
set_bet_sizes oop,flop,allin
set_bet_sizes ip,flop,bet,33,75
set_bet_sizes ip,flop,raise,60
set_bet_sizes ip,flop,allin
set_bet_sizes oop,turn,bet,66
set_bet_sizes oop,turn,raise,60
set_bet_sizes oop,turn,allin
set_bet_sizes ip,turn,bet,66
set_bet_sizes ip,turn,raise,60
set_bet_sizes ip,turn,allin
set_bet_sizes oop,river,bet,75
set_bet_sizes oop,river,raise,60
set_bet_sizes oop,river,allin
set_bet_sizes ip,river,bet,75
set_bet_sizes ip,river,raise,60
set_bet_sizes ip,river,allin"""


def config(board: str, out_json: Path) -> str:
    oop = (RANGES / "BB/BTN_2.5bb_BB_Call.txt").read_text().strip()
    ip = (RANGES / "BTN/BTN_2.5bb.txt").read_text().strip()
    return f"""set_pot 55
set_effective_stack 975
set_board {board}
set_range_oop {oop}
set_range_ip {ip}
{SIZES}
set_allin_threshold 0.67
set_raise_limit 2
build_tree
set_thread_num 8
set_accuracy 0.5
set_max_iteration 200
set_print_interval 20
set_use_isomorphism 1
start_solve
set_dump_rounds 1
dump_result {out_json.as_posix()}
"""


def main():
    OUT.mkdir(exist_ok=True)
    for board in FLOPS:
        out_json = OUT / f"{board.replace(',', '')}.json"
        if out_json.exists():
            continue
        cfg = OUT / f"{out_json.stem}.txt"
        cfg.write_text(config(board, out_json))
        print(f"solving {board} ...", flush=True)
        subprocess.run(
            [str(SOLVER_DIR / "console_solver.exe"), "--input_file", str(cfg),
             "--resource_dir", str(SOLVER_DIR / "resources"), "--mode", "holdem"],
            cwd=SOLVER_DIR, check=True, stdout=sys.stdout,
        )
        cfg.unlink()


if __name__ == "__main__":
    main()
