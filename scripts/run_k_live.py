"""Run one PX4 QoS scenario three times, 120 seconds per measurement."""

import argparse
import csv
import math
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs" / "ketqua"
CASES = {
    "K1": [],
    "K2": ["--urb", "0.05", "--burst-packets", "4", "--lossgood", "0", "--lossbad", "1"],
    "K3": ["--urb", "0.05", "--burst-packets", "1", "--lossgood", "0", "--lossbad", "1"],
    "K4": ["--urb", "0.10", "--burst-packets", "4", "--lossgood", "0", "--lossbad", "1"],
    "K5": ["--urb", "0.10", "--dur-s", "0.4", "--lossgood", "0", "--lossbad", "0",
           "--delay-bad-min-ms", "20", "--delay-bad-max-ms", "80"],
    "K7": ["--urb", "0", "--flip-probability", "0.02"],
}


def rows(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def number(value, default=0.0):
    return float(value) if value not in (None, "") else default


def burst_metrics(path):
    lengths = [int(row["gap_packets"]) for row in rows(path)]
    return len(lengths), statistics.mean(lengths) if lengths else 0, max(lengths, default=0)


def proxy_bursts(path):
    lengths = []
    current = 0
    for row in rows(path):
        if row["in_window"] != "1":
            continue
        if row["decision"] == "DROP":
            current += 1
        elif current:
            lengths.append(current)
            current = 0
    if current:
        lengths.append(current)
    return len(lengths), statistics.mean(lengths) if lengths else 0, max(lengths, default=0)


def wait_for_measurement(folder, run_id, case, seconds, gateway, proxy, online_wait):
    gateway_csv = folder / f"{case}_{run_id}_gateway_ingress.csv"
    proxy_csv = folder / f"{case}_{run_id}_summary.csv"
    first_frame_deadline = time.monotonic() + online_wait
    complete_deadline = time.monotonic() + online_wait + seconds + 12
    frame_seen = False
    while time.monotonic() < complete_deadline:
        for process, label in ((gateway, "gateway"), (proxy, "proxy")):
            if process is not None and process.poll() is not None:
                raise RuntimeError(f"{label} exited early with code {process.returncode}")
        if gateway_csv.exists():
            gateway_rows = rows(gateway_csv)
            frame_seen = frame_seen or any(number(row.get("frames")) > 0 for row in gateway_rows)
            complete = any(number(row.get("t_s")) >= seconds and
                           number(row.get("frames")) > 0 for row in gateway_rows)
            if complete and (proxy is None or proxy_csv.exists()):
                return
        if not frame_seen and time.monotonic() >= first_frame_deadline:
            raise RuntimeError("No PX4 frames reached gateway; inspect gateway.log and proxy.log")
        time.sleep(0.5)
    raise RuntimeError("Measurement did not reach the configured duration")


def collect(folder, case, run_id, seconds):
    gateway_csv = folder / f"{case}_{run_id}_gateway_ingress.csv"
    candidates = [row for row in rows(gateway_csv)
                  if number(row.get("t_s")) >= seconds and row.get("sysid") == "1"]
    if not candidates:
        raise RuntimeError("No complete gateway QoS row for UAV 1")
    gateway = max(candidates, key=lambda row: int(row["frames"]))
    frames = int(gateway["frames"])
    lost = int(gateway["seq_gap_estimate"])
    burst_path = folder / f"{case}_{run_id}_gateway_ingress_bursts.csv"
    bursts, burst_mean, burst_max = burst_metrics(burst_path)
    result = {
        "case": case, "run_id": run_id, "seconds": seconds,
        "frames": frames, "pps": round(frames / seconds, 3),
        "attitude_hz": round(int(gateway["attitude_count"]) / seconds, 3),
        "loss_gateway_pct": round(100 * lost / (frames + lost), 3) if frames + lost else 0,
        "gateway_lost_estimate": lost,
        "gateway_bursts": bursts,
        "gateway_burst_mean_packets": round(burst_mean, 3),
        "gateway_burst_max_packets": burst_max,
        "attitude_jitter_std_ms": gateway["attitude_jitter_std_ms"],
        "attitude_jitter_max_ms": gateway["attitude_jitter_max_ms"],
        "attitude_skipped_loss": gateway["attitude_skipped_loss"],
        "crc_errors": gateway["crc_errors"],
        "offline_events": gateway["offline_events"],
        "proxy_pre": "", "proxy_dropped": "", "proxy_loss_pct": "",
        "proxy_reverse_pre": "", "proxy_reverse_dropped": "", "proxy_reverse_loss_pct": "",
        "proxy_bursts": "", "proxy_burst_mean_packets": "", "proxy_burst_max_packets": "",
        "delayed_frames": "", "delay_set_mean_ms": "", "delay_observed_mean_ms": "",
        "flipped_sent": "", "counts_ok": "PASS",
    }
    if case != "K1":
        proxy = rows(folder / f"{case}_{run_id}_summary.csv")[0]
        pre, dropped = int(proxy["frames_pre"]), int(proxy["frames_dropped_markov"])
        reverse_pre = int(proxy["reverse_frames_pre"])
        reverse_dropped = int(proxy["reverse_frames_dropped_markov"])
        proxy_burst_path = folder / f"{case}_{run_id}_decision_trace.csv"
        proxy_count, proxy_mean, proxy_max = proxy_bursts(proxy_burst_path)
        result.update({
            "proxy_pre": pre, "proxy_dropped": dropped,
            "proxy_loss_pct": round(100 * dropped / pre, 3) if pre else "",
            "proxy_reverse_pre": reverse_pre, "proxy_reverse_dropped": reverse_dropped,
            "proxy_reverse_loss_pct": round(100 * reverse_dropped / reverse_pre, 3) if reverse_pre else "",
            "proxy_bursts": proxy_count,
            "proxy_burst_mean_packets": round(proxy_mean, 3),
            "proxy_burst_max_packets": proxy_max,
            "delayed_frames": proxy.get("delayed_frames", ""),
            "flipped_sent": proxy.get("flipped_sent", ""),
            "counts_ok": "PASS" if pre == dropped + int(proxy["frames_post_sent"]) +
                         int(proxy["send_errors"]) and reverse_pre == reverse_dropped +
                         int(proxy["reverse_frames_post_sent"]) +
                         int(proxy["reverse_send_errors"]) else "FAIL",
        })
        delay_path = folder / f"{case}_{run_id}_delay.csv"
        delays = rows(delay_path)
        if delays:
            result["delay_set_mean_ms"] = round(statistics.mean(number(row["delay_set_ms"]) for row in delays), 3)
            result["delay_observed_mean_ms"] = round(statistics.mean(number(row["delay_observed_ms"]) for row in delays), 3)
    return result


def write_csv(path, data):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(data[0]))
        writer.writeheader()
        writer.writerows(data)


def aggregate(case_dir):
    results = []
    for path in sorted(case_dir.glob("*/result.csv")):
        results.extend(rows(path))
    if not results:
        return
    summary = []
    for key in results[0]:
        if key in ("case", "run_id", "counts_ok"):
            continue
        try:
            values = [float(row[key]) for row in results if row[key] not in ("", None)]
        except ValueError:
            continue
        if not values:
            continue
        summary.append({"metric": key, "runs": len(values),
                        "mean": round(statistics.mean(values), 4),
                        "std": round(statistics.stdev(values), 4) if len(values) > 1 else ""})
    write_csv(case_dir / "summary.csv", summary)


def run_once(case, repeat, seconds, online_wait, results_root):
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_r{repeat}"
    folder = results_root / case / run_id
    folder.mkdir(parents=True, exist_ok=False)
    relative = folder.relative_to(ROOT).as_posix()
    gateway_cmd = [str(ROOT / "bin/gateway.exe"), "--scenario", case,
                   "--run-id", run_id, "--output-dir", relative,
                   "--udp-port", "14550" if case == "K1" else "14551",
                   "--measure-seconds", str(seconds)]
    proxy_cmd = None if case == "K1" else [
        str(ROOT / "bin/upstream_markov_proxy.exe"), "--scenario", case,
        "--run-id", run_id, "--output-dir", relative,
        "--listen-port", "14550", "--gateway-port", "14551",
        "--gateway-source-port", "14610", "--measure-seconds", str(seconds),
        "--seed", str(1000 + repeat), *CASES[case],
    ]
    (folder / "run.log").write_text(
        f"start={datetime.now().isoformat()}\n"
        f"gateway={' '.join(gateway_cmd)}\n"
        f"proxy={' '.join(proxy_cmd) if proxy_cmd else 'none'}\n",
        encoding="utf-8")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    gateway_log = (folder / "gateway.log").open("w", encoding="utf-8")
    proxy_log = (folder / "proxy.log").open("w", encoding="utf-8") if proxy_cmd else None
    gateway = proxy = None
    try:
        gateway = subprocess.Popen(gateway_cmd, cwd=ROOT, stdout=gateway_log,
                                   stderr=subprocess.STDOUT, creationflags=flags)
        time.sleep(0.3)
        if proxy_cmd:
            proxy = subprocess.Popen(proxy_cmd, cwd=ROOT, stdout=proxy_log,
                                     stderr=subprocess.STDOUT, creationflags=flags)
        wait_for_measurement(folder, run_id, case, seconds, gateway, proxy, online_wait)
        result = collect(folder, case, run_id, seconds)
        write_csv(folder / "result.csv", [result])
        with (folder / "run.log").open("a", encoding="utf-8") as stream:
            stream.write(f"end={datetime.now().isoformat()}\nstatus=PASS\n")
        return folder, result
    except Exception as error:
        with (folder / "run.log").open("a", encoding="utf-8") as stream:
            stream.write(f"end={datetime.now().isoformat()}\nstatus=FAIL\nerror={error}\n")
        raise
    finally:
        for process in (proxy, gateway):
            if process and process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
        gateway_log.close()
        if proxy_log:
            proxy_log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--seconds", type=int, default=120)
    parser.add_argument("--online-wait", type=int, default=30)
    parser.add_argument("--output-root", type=Path, default=RESULTS)
    args = parser.parse_args()
    if args.repeats < 1 or args.seconds < 1:
        parser.error("repeats and seconds must be positive")
    for repeat in range(1, args.repeats + 1):
        print(f"{args.case} run {repeat}/{args.repeats}: start", flush=True)
        folder, result = run_once(args.case, repeat, args.seconds, args.online_wait,
                                  args.output_root.resolve())
        print(f"{folder}: pps={result['pps']} gateway_loss={result['loss_gateway_pct']}% "
              f"proxy_loss={result['proxy_loss_pct']}%", flush=True)
        aggregate(args.output_root.resolve() / args.case)
        time.sleep(1)
    print(f"Summary: {args.output_root.resolve() / args.case / 'summary.csv'}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Measurement failed: {error}", file=sys.stderr)
        raise SystemExit(1)
