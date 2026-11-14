"""Audit one 60-second Markov proxy run using its existing CSV files."""

import argparse
import csv
from pathlib import Path


WINDOW_START_MS = 5_000
WINDOW_END_MS = 65_000


def unique_file(folder, suffix):
    matches = list(folder.glob(f"*{suffix}"))
    if suffix == "_states.csv":
        matches = [path for path in matches if not path.name.endswith("_reverse_states.csv")]
    if len(matches) != 1:
        raise ValueError(f"Expected one *{suffix} in {folder}; found {len(matches)}")
    return matches[0]


def state_window(path):
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows or rows[0]["event"] != "INITIAL" or int(rows[0]["t_ms"]) != 0:
        raise ValueError(f"Invalid initial state: {path}")
    if rows[-1]["event"] != "END" or int(rows[-1]["t_ms"]) != WINDOW_END_MS:
        raise ValueError(f"Incomplete 60-second run: {path}")

    bad_ms = 0
    bursts = []
    for current, following in zip(rows, rows[1:]):
        start = int(current["t_ms"])
        end = int(following["t_ms"])
        if end < start or current["state"] not in ("G", "B"):
            raise ValueError(f"Invalid state sequence: {path}")
        if current["state"] == "B":
            overlap = max(0, min(end, WINDOW_END_MS) - max(start, WINDOW_START_MS))
            if overlap:
                bad_ms += overlap
                bursts.append(overlap)
    return {
        "bad_ms": bad_ms,
        "bad_pct": 100 * bad_ms / (WINDOW_END_MS - WINDOW_START_MS),
        "bursts": len(bursts),
        "mean_burst_ms": sum(bursts) / len(bursts) if bursts else 0,
        "max_burst_ms": max(bursts, default=0),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, help="One B5/B10 result folder")
    args = parser.parse_args()
    folder = args.folder
    summary_path = folder / "proxy.csv"
    if not summary_path.is_file():
        summary_path = unique_file(folder, "_summary.csv")
    with summary_path.open(newline="", encoding="utf-8") as stream:
        summary = next(csv.DictReader(stream))

    output = []
    for direction, state_suffix, pre_key, drop_key, sent_key, error_key in (
        ("PX4_to_gateway", "_states.csv", "frames_pre", "frames_dropped_markov", "frames_post_sent", "send_errors"),
        ("gateway_to_PX4", "_reverse_states.csv", "reverse_frames_pre", "reverse_frames_dropped_markov", "reverse_frames_post_sent", "reverse_send_errors"),
    ):
        pre = int(summary[pre_key])
        dropped = int(summary[drop_key])
        sent = int(summary[sent_key])
        errors = int(summary[error_key])
        state = state_window(unique_file(folder, state_suffix))
        output.append({
            "run_id": summary["run_id"],
            "direction": direction,
            "window_s": 60,
            "pre": pre,
            "dropped": dropped,
            "sent": sent,
            "send_errors": errors,
            "loss_pct": round(100 * dropped / pre, 3) if pre else "",
            "bad_ms": state["bad_ms"],
            "bad_pct": round(state["bad_pct"], 3),
            "bad_bursts": state["bursts"],
            "mean_burst_ms_observed": round(state["mean_burst_ms"], 1),
            "max_burst_ms_observed": state["max_burst_ms"],
            "counts_ok": pre == dropped + sent + errors,
        })

    destination = folder / "markov_eval.csv"
    with destination.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=output[0].keys())
        writer.writeheader()
        writer.writerows(output)
    for row in output:
        print(f"{row['direction']}: loss={row['loss_pct']}% "
              f"bad_time={row['bad_pct']}% bursts={row['bad_bursts']} "
              f"counts_ok={row['counts_ok']}")
    print(destination)


if __name__ == "__main__":
    main()
