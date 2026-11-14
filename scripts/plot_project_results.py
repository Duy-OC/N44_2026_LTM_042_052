"""Recreate the QoS comparison chart from the three measured run folders."""

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
RUNS = {
    "A1": "A/A1/20261114_155708",
    "B5": "B/B5/20261114_160228",
    "B10": "B/B10/20261114_161227",
}


def read_result(case):
    path = ROOT / "docs" / "ketqua" / RUNS[case] / "result.csv"
    with path.open(newline="", encoding="utf-8-sig") as source:
        return next(csv.DictReader(source))


def main():
    rows = [read_result(case) for case in RUNS]
    summary = ROOT / "docs" / "tong_hop_qos_gateway.csv"
    with summary.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=(
            "case", "loss_set_pct", "loss_up_pct", "loss_down_pct",
            "loss_gateway_pct", "gateway_frames", "gateway_fps",
            "hb_jitter_ms", "offline", "crc"))
        writer.writeheader()
        for row in rows:
            source = ROOT / "docs" / "ketqua" / RUNS[row["case"]] / "gateway.csv"
            with source.open(newline="", encoding="utf-8-sig") as handle:
                gateway_frames = list(csv.DictReader(handle))[-1]["frames"]
            writer.writerow({
                "case": row["case"], "loss_set_pct": row["loss_set"],
                "loss_up_pct": row["loss_up"], "loss_down_pct": row["loss_down"],
                "loss_gateway_pct": row["loss_gw"], "gateway_frames": gateway_frames,
                "gateway_fps": row["fps"], "hb_jitter_ms": row["hb_jitter_ms"],
                "offline": row["offline"], "crc": row["crc"],
            })
    setpoint = [0, 5, 10]
    gateway_loss = [float(row["loss_gw"]) for row in rows]
    upstream_loss = [float("nan")] + [float(row["loss_up"]) for row in rows[1:]]
    downstream_loss = [float("nan")] + [float(row["loss_down"]) for row in rows[1:]]
    fps = [float(row["fps"]) for row in rows]

    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    axes[0].plot(setpoint, setpoint, "--", color="gray", label="Configured level")
    axes[0].plot(setpoint, gateway_loss, "o-", label="Gateway sequence loss")
    axes[0].plot(setpoint, upstream_loss, "s-", label="Proxy upstream drop")
    axes[0].plot(setpoint, downstream_loss, "^-", label="Proxy downstream drop")
    axes[0].set(title="Loss", xlabel="Configured Markov level (%)", ylabel="Measured loss (%)")
    axes[0].set_xticks(setpoint)
    axes[0].set_ylim(bottom=0)
    axes[0].grid(alpha=0.25)
    axes[0].legend(fontsize=8)

    axes[1].bar(["A1: 0%", "B5: 5%", "B10: 10%"], fps,
                color=["#2e7d32", "#f9a825", "#c62828"])
    axes[1].set(title="Gateway receive rate", ylabel="Valid MAVLink frames/s")
    axes[1].set_ylim(0, 65)
    axes[1].grid(axis="y", alpha=0.25)
    for index, rate in enumerate(fps):
        axes[1].text(index, rate + 1, f"{rate:.2f}", ha="center", fontsize=9)

    output = ROOT / "docs" / "bieu_do_qos_gateway.png"
    fig.savefig(output, dpi=180)
    plt.close(fig)
    print(output)
    print(summary)


if __name__ == "__main__":
    main()
