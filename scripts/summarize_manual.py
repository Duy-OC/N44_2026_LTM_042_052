"""Summarize gateway QoS and gateway functions after a manual run."""

import argparse
import csv
import datetime as dt
import re
from pathlib import Path


def read_last(path, sysid=None):
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8-sig") as source:
        rows = list(csv.DictReader(source))
    if sysid is not None:
        rows = [row for row in rows if row.get("sysid") == sysid]
    return max(rows, key=lambda row: float(row.get("t_s") or 0)) if rows else {}


def number(row, key):
    try:
        return float(row.get(key) or 0)
    except (ValueError, TypeError):
        return 0.0


def pct(numerator, denominator):
    return round(100 * numerator / denominator, 3) if denominator else "NA"


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def read_log(path):
    if not path.exists():
        return ""
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace")
    return raw.decode("utf-8-sig", errors="replace")


def find_file(folder, suffix, short_name):
    short = folder / short_name
    if short.exists():
        return short
    matches = list(folder.glob(f"*{suffix}"))
    if len(matches) != 1:
        raise FileNotFoundError(f"Expected one *{suffix} in {folder}; found {len(matches)}")
    matches[0].rename(short)
    return short


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("case", choices=("A1", "B5", "B10", "C1", "E1"))
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    folder = args.folder.resolve()
    if not folder.is_dir():
        parser.error(f"Folder not found: {folder}")

    if args.case == "E1":
        observed = {}
        for name in "AB":
            path = folder / f"client_{name}.log"
            content = read_log(path)
            observed[name] = re.findall(r"\bRX (OK ACQUIRE|ERR LOCKED|ERR NOT_OWNER|OK RELEASE)\b", content)
        checks = [
            ("A_first_acquire", "OK ACQUIRE", observed["A"][:1], observed["A"][:1] == ["OK ACQUIRE"]),
            ("B_locked", "ERR LOCKED", observed["B"][:1], observed["B"][:1] == ["ERR LOCKED"]),
            ("B_command_denied", "ERR NOT_OWNER", observed["B"][1:2], observed["B"][1:2] == ["ERR NOT_OWNER"]),
            ("A_release", "OK RELEASE", observed["A"][1:2], observed["A"][1:2] == ["OK RELEASE"]),
            ("B_acquire", "OK ACQUIRE", observed["B"][2:3], observed["B"][2:3] == ["OK ACQUIRE"]),
            ("A_after_B_exit", "OK ACQUIRE", observed["A"][2:3], observed["A"][2:3] == ["OK ACQUIRE"]),
        ]
        result = {"case": "E1", "passed": sum(check[3] for check in checks),
                  "total": len(checks), "pass": "PASS" if all(check[3] for check in checks) else "FAIL"}
        write_csv(folder / "result.csv", [result])
        write_csv(folder / "checks.csv", [
            {"test": name, "expected": expected, "actual": " ".join(actual),
             "pass": "PASS" if passed else "FAIL"}
            for name, expected, actual, passed in checks
        ])
        (folder / "run.log").write_text(
            f"case=E1\nsummary_at={dt.datetime.now().isoformat(timespec='seconds')}\n"
            f"status={result['pass']}\nfolder={folder}\n", encoding="utf-8")
        print(f"{result['pass']}: {folder / 'result.csv'}")
        return

    if args.case == "C1":
        gateway_online = "UAV 1 ONLINE" in read_log(folder / "gateway.log")
        clients = {}
        for name in "ABC":
            subscribed_at = None
            details = []
            for line in read_log(folder / f"client_{name}.log").splitlines():
                match = re.match(r"^(\S+) (TX|RX) (.*)$", line)
                if not match:
                    continue
                if match.group(2) == "RX" and match.group(3) == "OK SUBSCRIBE 5":
                    try:
                        subscribed_at = dt.datetime.fromisoformat(match.group(1))
                    except ValueError:
                        pass
                if match.group(2) == "RX" and match.group(3).startswith("DETAIL {"):
                    try:
                        details.append(dt.datetime.fromisoformat(match.group(1)))
                    except ValueError:
                        pass
            clients[name] = (subscribed_at, details)
        common_start = max((at for at, _ in clients.values() if at), default=None)
        checks = [("gateway_online", "UAV 1 ONLINE", str(gateway_online), gateway_online)]
        for name, (subscribed_at, details) in clients.items():
            passed = bool(subscribed_at and common_start and any(at >= common_start for at in details))
            checks.append((f"gateway_to_{name}", "SUBSCRIBE accepted and DETAIL delivered concurrently",
                           str(passed), passed))
        result = {"case": "C1", "pass": "PASS" if all(item[3] for item in checks) else "FAIL"}
        write_csv(folder / "result.csv", [result])
        write_csv(folder / "checks.csv", [
            {"test": name, "expected": expected, "actual": actual,
             "pass": "PASS" if passed else "FAIL"}
            for name, expected, actual, passed in checks
        ])
        (folder / "run.log").write_text(
            f"case=C1\nsummary_at={dt.datetime.now().isoformat(timespec='seconds')}\n"
            f"status={result['pass']}\nfolder={folder}\n", encoding="utf-8")
        print(f"{result['pass']}: {folder / 'result.csv'}")
        return

    if not (folder / "gateway.csv").exists() and not list(folder.glob("*_gateway_ingress.csv")):
        result = {"case": args.case, "pass": "INCOMPLETE",
                  "reason": "Missing gateway CSV in this run folder; check gateway process and output path"}
        write_csv(folder / "result.csv", [result])
        write_csv(folder / "checks.csv", [
            {"test": "gateway_csv", "expected": "present in run folder",
             "actual": "missing", "pass": "INCOMPLETE"}
        ])
        (folder / "run.log").write_text(
            f"case={args.case}\nsummary_at={dt.datetime.now().isoformat(timespec='seconds')}\n"
            f"status=INCOMPLETE\nreason={result['reason']}\nfolder={folder}\n",
            encoding="utf-8")
        print(f"INCOMPLETE: no gateway CSV in {folder}; start the matching gateway and measure again")
        return

    gateway_path = find_file(folder, "_gateway_ingress.csv", "gateway.csv")
    gateway = read_last(gateway_path, "1")
    if not gateway:
        raise RuntimeError("gateway.csv has no sysid=1 row; check PX4 stream and gateway.log")
    try:
        find_file(folder, "_gateway_ingress_msgid.csv", "msg.csv")
    except FileNotFoundError:
        pass

    frames = number(gateway, "frames")
    gaps = number(gateway, "seq_gap_estimate")
    gateway_log = read_log(folder / "gateway.log")
    crc_values = re.findall(r"CRC errors=(\d+)", gateway_log)
    result = {
        "case": args.case,
        "seconds": number(gateway, "t_s"),
        "frames": int(frames),
        "fps": round(frames / 60, 3),
        "loss_gw": pct(gaps, frames + gaps),
        "hb_jitter_ms": gateway.get("hb_jitter_ms", ""),
        "offline": gateway.get("offline_events", ""),
        "crc": int(crc_values[-1]) if crc_values else "NA",
        "loss_set": {"B5": 5, "B10": 10}.get(args.case, 0),
        "loss_up": "NA",
        "loss_down": "NA",
    }
    checks = [
        ("qos_60s", ">=60", result["seconds"], result["seconds"] >= 60),
        ("telemetry", ">0", result["frames"], result["frames"] > 0),
    ]

    if args.case in ("B5", "B10"):
        proxy_path = find_file(folder, "_summary.csv", "proxy.csv")
        proxy = read_last(proxy_path)
        up = number(proxy, "frames_pre")
        down = number(proxy, "reverse_frames_pre")
        result["loss_up"] = pct(number(proxy, "frames_dropped_markov"), up)
        result["loss_down"] = pct(number(proxy, "reverse_frames_dropped_markov"), down)
        checks.append(("proxy_input", "up/down >0", f"{int(up)}/{int(down)}", up > 0 and down > 0))
        for suffix, short in (("_proxy_pre.csv", "pre.csv"),
                              ("_proxy_post.csv", "post.csv"),
                              ("_reverse_trace.csv", "reverse.csv")):
            try:
                find_file(folder, suffix, short)
            except FileNotFoundError:
                pass
    elif args.case == "A1":
        checks.append(("crc_baseline", "0", result["crc"],
                       None if result["crc"] == "NA" else result["crc"] == 0))
        checks.append(("uav_online", "0 offline", result["offline"],
                       number(gateway, "offline_events") == 0))

    result["pass"] = ("FAIL" if any(check[3] is False for check in checks)
                      else "INCOMPLETE" if any(check[3] is None for check in checks)
                      else "PASS")
    write_csv(folder / "result.csv", [result])
    write_csv(folder / "checks.csv", [
        {"test": name, "expected": expected, "actual": actual,
         "pass": "INCOMPLETE" if passed is None else "PASS" if passed else "FAIL"}
        for name, expected, actual, passed in checks
    ])
    (folder / "run.log").write_text(
        f"case={args.case}\nsummary_at={dt.datetime.now().isoformat(timespec='seconds')}\n"
        f"status={result['pass']}\nfolder={folder}\n", encoding="utf-8")
    print(f"{result['pass']}: {folder / 'result.csv'}")


if __name__ == "__main__":
    main()
