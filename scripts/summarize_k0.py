"""Summarize the three synthetic Markov runs for each K0 configuration."""

import argparse
import csv
import statistics
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    with (args.folder / "result.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    output = []
    for case in sorted({row["case"] for row in rows}):
        group = [row for row in rows if row["case"] == case]
        if len(group) != 3:
            raise ValueError(f"{case}: expected three seeds, got {len(group)}")
        for metric in ("loss_actual_pct", "burst_mean_packets", "burst_max_packets"):
            values = [float(row[metric]) for row in group]
            output.append({"case": case, "metric": metric, "runs": 3,
                           "mean": round(statistics.mean(values), 4),
                           "std": round(statistics.stdev(values), 4),
                           "target_loss_pct": group[0]["loss_target_pct"],
                           "target_burst_packets": group[0]["burst_target_packets"]})
    with (args.folder / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=output[0])
        writer.writeheader()
        writer.writerows(output)
    print(args.folder / "summary.csv")


if __name__ == "__main__":
    main()
