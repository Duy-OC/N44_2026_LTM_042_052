"""Resume round 2: exactly three completed 120-second live runs per case."""

import argparse
import time
from pathlib import Path

from run_k_live import ROOT, CASES, run_once, aggregate, rows
from run_k6_live import run_once as run_commands


def completed(folder):
    runs = []
    for path in sorted(folder.glob("*/result.csv")):
        journal = path.parent / "run.log"
        data = rows(path)
        if (journal.exists() and "status=PASS" in journal.read_text(encoding="utf-8")
                and data and float(data[0].get("seconds", 0)) == 120):
            runs.append(path)
    return runs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "docs/ketqua_lan2")
    args = parser.parse_args()
    base = args.output_root.resolve()
    for case in CASES:
        done = completed(base / case)
        for repeat in range(len(done) + 1, 4):
            print(f"{case}: {repeat}/3, 120s, real PX4", flush=True)
            folder, result = run_once(case, repeat, 120, 30, base)
            aggregate(base / case)
            print(f"PASS {folder}: {result}", flush=True)
            time.sleep(1)
    for loss in (0, 5, 10):
        done = completed(base / "K6" / f"L{loss}")
        for repeat in range(len(done) + 1, 4):
            print(f"K6 L{loss}: {repeat}/3, 120s, real PX4 ACK", flush=True)
            folder, result = run_commands(loss, repeat, base / "K6")
            print(f"PASS {folder}: {result}", flush=True)
            time.sleep(1)
    print("Automatic cases complete. K8 requires operator-controlled interruption; see README.", flush=True)


if __name__ == "__main__":
    main()
