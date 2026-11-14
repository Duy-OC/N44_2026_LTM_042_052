"""Build H1-H6 charts directly from K scenario CSV files."""

import csv
import statistics
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/ketqua"
OUT = BASE / "charts"
OUT.mkdir(exist_ok=True)
plt.rcParams.update({"figure.dpi": 130, "savefig.dpi": 170, "font.size": 10})


def rows(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def runs(case):
    return [rows(path)[0] for path in sorted((BASE / case).glob("*/result.csv"))]


def values(data, key):
    return [float(row[key]) for row in data if row.get(key) not in (None, "")]


def mean_std(data, key):
    sample = values(data, key)
    return statistics.mean(sample), statistics.stdev(sample) if len(sample) > 1 else 0


def first_file(case, suffix):
    matches = sorted((BASE / case).glob(f"*/*{suffix}"))
    if not matches:
        raise FileNotFoundError(f"{case} *{suffix}")
    return matches[0]


def finish(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name)
    plt.close(fig)
    print(OUT / name)


def h1():
    cases = [("K1", 0, "o"), ("K2", 5, "o"), ("K3", 5, "s"), ("K4", 10, "o")]
    fig, ax = plt.subplots(figsize=(6.4, 4.7))
    ax.plot([0, 12], [0, 12], "--", color="gray", label="Reference y=x")
    for case, target, marker in cases:
        data = runs(case)
        if not data:
            continue
        mean, std = mean_std(data, "loss_gateway_pct")
        ax.errorbar(target, mean, yerr=std, marker=marker, capsize=4,
                    linestyle="none", label=f"{case}: gateway ({len(data)} runs)")
        if case != "K1":
            proxy_mean, _ = mean_std(data, "proxy_loss_pct")
            ax.scatter(target, proxy_mean, marker="x", s=65, label=f"{case}: proxy actual")
    ax.set(xlabel="Configured loss (%)", ylabel="Observed loss (%)",
           title="H1. Configured vs observed packet loss", xlim=(-0.5, 11), ylim=(-0.5, 12))
    ax.grid(alpha=0.25)
    ax.legend(fontsize=7)
    finish(fig, "H1_loss.png")


def h2():
    fig, ax = plt.subplots(figsize=(7.0, 4.6))
    for case, color, offset, r in (("K2", "#1768ac", -0.18, 0.25),
                                   ("K3", "#e87524", 0.18, 1.0)):
        lengths = []
        for path in (BASE / case).glob("*/*_gateway_ingress_bursts.csv"):
            lengths.extend(int(row["gap_packets"]) for row in rows(path))
        counts = Counter(lengths)
        x = list(range(1, 16))
        ax.bar([n + offset for n in x], [counts[n] for n in x], width=0.36,
               color=color, alpha=0.75, label=f"{case} observed")
        ax.plot(x, [len(lengths) * r * (1 - r) ** (n - 1) for n in x],
                color=color, linestyle="--", label=f"{case} geometric theory")
    ax.set(xlabel="Loss burst length (packets)", ylabel="Number of bursts",
           title="H2. Burst length distribution (lengths 1-15)")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(fontsize=8)
    finish(fig, "H2_bursts.png")


def h3():
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for case in ("K2", "K3"):
        data = [row for row in rows(first_file(case, "_gateway_ingress_loss_seconds.csv"))
                if row["sysid"] == "1" and row["compid"] == "1" and int(row["second"]) < 60]
        ax.step([int(row["second"]) for row in data],
                [int(row["gap_packets"]) for row in data], where="mid", label=case)
    ax.set(xlabel="Time in first 60 s", ylabel="Sequence gaps / s",
           title="H3. Losses per second: bursty vs isolated")
    ax.grid(alpha=0.25)
    ax.legend()
    finish(fig, "H3_loss_time.png")


def h4():
    fig, ax = plt.subplots(figsize=(5.5, 4.2))
    x = []
    means = []
    stds = []
    for case in ("K1", "K5"):
        data = runs(case)
        if data:
            mean, std = mean_std(data, "attitude_jitter_std_ms")
            x.append(case)
            means.append(mean)
            stds.append(std)
    ax.bar(x, means, color=["#1768ac", "#e87524"][:len(x)])
    ax.errorbar(x, means, yerr=stds, fmt="none", color="black", capsize=5)
    ax.set(ylabel="Std. dev. of ATTITUDE intervals (ms)",
           title="H4. ATTITUDE reception regularity")
    ax.grid(axis="y", alpha=0.25)
    finish(fig, "H4_jitter.png")


def h5():
    levels = []
    success = []
    success_std = []
    retries = []
    retries_std = []
    for level in (0, 5, 10):
        data = [rows(path)[0] for path in (BASE / "K6" / f"L{level}").glob("*/result.csv")]
        if not data:
            continue
        levels.append(level)
        value, deviation = mean_std(data, "success_pct")
        success.append(value)
        success_std.append(deviation)
        value, deviation = mean_std(data, "retry_mean_per_command")
        retries.append(value)
        retries_std.append(deviation)
    if not levels:
        return
    fig, ax = plt.subplots(figsize=(6.2, 4.4))
    ax.bar(levels, success, width=2.5, color="#1768ac", label="ACK success")
    ax.errorbar(levels, success, yerr=success_std, fmt="none", color="black", capsize=4)
    ax.set(xlabel="Configured loss (%)", ylabel="Commands with ACK (%)", ylim=(0, 105),
           title="H5. Command success and retry")
    ax2 = ax.twinx()
    ax2.errorbar(levels, retries, yerr=retries_std, marker="o", color="#e87524",
                 capsize=4, label="Mean retries / command")
    ax2.set_ylabel("Mean retries / command")
    ax.grid(axis="y", alpha=0.25)
    finish(fig, "H5_commands.png")


def h6():
    data = [row for row in rows(first_file("K1", "_gateway_ingress.csv"))
            if row["sysid"] == "1" and row["compid"] == "1"]
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.plot([float(row["t_s"]) for row in data],
            [float(row["frames_per_s"]) for row in data], marker=".")
    ax.set(xlabel="Time (s)", ylabel="Received frames / s",
           title="H6. Baseline received frame rate")
    ax.grid(alpha=0.25)
    finish(fig, "H6_pps.png")


if __name__ == "__main__":
    h1()
    if runs("K2") and runs("K3"):
        h2()
        h3()
    if runs("K5"):
        h4()
    h5()
    if runs("K1"):
        h6()
