"""Keep the site growing: solve the next flop, rebuild the data, commit and push it. Repeat.

Run with the venv's Python (extraction needs eval7). Create a file named STOP here to stop after the current flop.
"""
import subprocess
from pathlib import Path

import extract_spots
from solve_flops import next_flops, solve

ROOT = Path(__file__).parent


def publish(board: str):
    git = lambda *args: subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    git("add", "data")
    if git("diff", "--cached", "--quiet").returncode == 0:
        return  # nothing new (e.g. every spot on the flop was skipped)
    n = len(list((ROOT / "data/flops").glob("*.json")))
    git("commit", "-m", f"Add solved flop {board} ({n} flops)\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>")
    push = git("push", "-q")
    print("pushed" if push.returncode == 0 else f"push failed, will retry next flop: {push.stderr.strip()}", flush=True)


def main():
    for board in next_flops():
        if (ROOT / "STOP").exists():
            print("STOP file found, stopping")
            break
        solve(board)
        extract_spots.main()
        publish(board)


if __name__ == "__main__":
    main()
