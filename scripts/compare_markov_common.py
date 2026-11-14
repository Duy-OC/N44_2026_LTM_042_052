"""Compare gateway sequence loss and proxy decisions on their common time span."""

import argparse
import csv
from pathlib import Path


def unique(folder, suffix):
    matches = list(folder.glob(f"*{suffix}"))
    if len(matches) != 1:
        raise ValueError(f"Expected one *{suffix}: found {len(matches)}")
    return matches[0]


def load(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    folder = args.folder
    gateway = [row for row in load(unique(folder, "_gateway_ingress_trace.csv"))
               if row["sysid"] == "1" and row["compid"] == "1"]
    proxy = [row for row in load(unique(folder, "_decision_trace.csv"))
             if row["in_window"] == "1" and row["sysid"] == "1" and row["compid"] == "1"]
    if not gateway or not proxy:
        raise ValueError("No common gateway/proxy frames")
    start = max(int(gateway[0]["epoch_ms"]), int(proxy[0]["epoch_ms"]))
    end = min(int(gateway[-1]["epoch_ms"]), int(proxy[-1]["epoch_ms"]))
    if end <= start:
        raise ValueError("Measurement windows do not overlap")
    gateway = [row for row in gateway if start <= int(row["epoch_ms"]) <= end]
    proxy = [row for row in proxy if start <= int(row["epoch_ms"]) <= end]
    gateway_gap = sum(int(row["gap_before"]) for row in gateway[1:])
    proxy_drop = sum(row["decision"] == "DROP" for row in proxy)
    result = {
        "common_s": round((end - start) / 1000, 3),
        "proxy_pre": len(proxy), "proxy_drop": proxy_drop,
        "proxy_loss_pct": round(100 * proxy_drop / len(proxy), 3),
        "gateway_rx": len(gateway), "gateway_gap": gateway_gap,
        "gateway_loss_pct": round(100 * gateway_gap / (len(gateway) + gateway_gap), 3),
    }
    with (folder / "common.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=result)
        writer.writeheader()
        writer.writerow(result)
    print(folder / "common.csv", result)


if __name__ == "__main__":
    main()
