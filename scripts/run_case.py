"""Run one or all gateway measurements and file results under docs/ketqua."""

import argparse
import csv
import datetime as dt
import json
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

from pymavlink import mavutil


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs" / "ketqua"
FOLDERS = {
    "A1": "A/A1", "B5": "B/B5", "B10": "B/B10",
    "D1": "D/D1", "D2": "D/D2", "E1": "E/E1", "E2": "E/E2",
}
FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)
BUILD_TARGETS = {
    "gateway.exe": "src/gateway/gateway.cpp",
    "upstream_markov_proxy.exe": "src/proxy/upstream_markov_proxy.cpp",
    "test_stage1_framing.exe": "tests/test_stage1_framing.cpp",
    "test_stage2_telemetry.exe": "tests/test_stage2_telemetry.cpp",
}


def stamp():
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def ensure_build(cases, log_path):
    required = {"gateway.exe"}
    if "B5" in cases or "B10" in cases:
        required.add("upstream_markov_proxy.exe")
    if "D1" in cases:
        required.update(("test_stage1_framing.exe", "test_stage2_telemetry.exe"))
    compiler = shutil.which("g++")
    if not compiler:
        raise RuntimeError("MinGW g++ is not in PATH")
    (ROOT / "bin").mkdir(exist_ok=True)
    headers = list((ROOT / "src").rglob("*.h")) + list((ROOT / "third_party").rglob("*.h"))
    with log_path.open("w", encoding="utf-8") as log:
        for binary, source in BUILD_TARGETS.items():
            if binary not in required:
                continue
            target = ROOT / "bin" / binary
            origin = ROOT / source
            newest = max(path.stat().st_mtime for path in (origin, *headers))
            if target.exists() and target.stat().st_mtime >= newest:
                log.write(f"{binary}: up to date\n")
                continue
            command = [compiler, "-std=c++17", "-O2", "-Isrc/common", "-Isrc/gateway",
                       "-Isrc/proxy", "-Isrc/client", "-Ithird_party", "-o",
                       str(target), source, "-lws2_32"]
            log.write(f"{binary}: building\n")
            log.flush()
            completed = subprocess.run(command, cwd=ROOT, stdout=log,
                                       stderr=subprocess.STDOUT, creationflags=FLAGS)
            if completed.returncode != 0:
                raise RuntimeError(f"Build failed for {binary}; see {log_path}")
            log.write(f"{binary}: OK\n")
            log.flush()


def last_csv(path):
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    return next((row for row in reversed(rows) if row.get("sysid") == "1"), rows[-1] if rows else {})


def value(row, key):
    try:
        return float(row.get(key) or 0)
    except ValueError:
        return 0.0


def percent(part, total):
    return round(100 * part / total, 3) if total else "NA"


def start_process(command, directory, label, cwd=ROOT):
    stdout = (directory / f"{label}.log").open("wb")
    stderr = (directory / f"{label}.err.log").open("wb")
    try:
        process = subprocess.Popen(command, cwd=cwd, stdout=stdout, stderr=stderr,
                                   creationflags=FLAGS)
    except Exception:
        stdout.close()
        stderr.close()
        raise
    return process, stdout, stderr


def stop_processes(entries):
    for process, _, _ in entries:
        if process.poll() is None:
            process.terminate()
    for process, stdout, stderr in entries:
        try:
            process.wait(timeout=5)
        finally:
            stdout.close()
            stderr.close()


def short_names(directory):
    suffixes = {
        "_gateway_ingress_msgid.csv": "msg.csv",
        "_gateway_ingress.csv": "gateway.csv",
        "_proxy_pre_msgid.csv": "pre_msg.csv",
        "_proxy_post_msgid.csv": "post_msg.csv",
        "_proxy_pre.csv": "pre.csv",
        "_proxy_post.csv": "post.csv",
        "_reverse_trace.csv": "reverse.csv",
        "_reverse_states.csv": "reverse_state.csv",
        "_post_trace.csv": "trace.csv",
        "_states.csv": "state.csv",
        "_summary.csv": "proxy.csv",
        "_config.txt": "config.txt",
    }
    for file in list(directory.iterdir()):
        if not file.is_file():
            continue
        for suffix, name in suffixes.items():
            if file.name.endswith(suffix):
                file.rename(directory / name)
                break


def log_checks(directory, checks):
    write_csv(directory / "checks.csv", [
        {"test": name, "expected": expected, "actual": actual,
         "pass": "PASS" if passed else "FAIL"}
        for name, expected, actual, passed in checks
    ])


def run_qos(case, directory, run_id):
    has_proxy = case in ("B5", "B10")
    loss = {"B5": 0.05, "B10": 0.10}.get(case, 0.0)
    seed = {"B5": 202, "B10": 303}.get(case, 0)
    entries = []
    qos_file = directory / f"{case}_{run_id}_gateway_ingress.csv"
    proxy_file = directory / f"{case}_{run_id}_summary.csv"
    try:
        command = [str(ROOT / "bin" / "gateway.exe"), "--scenario", case,
                   "--run-id", run_id, "--output-dir", str(directory),
                   "--udp-port", "14551" if has_proxy else "14550",
                   "--measure-seconds", "60"]
        entries.append(start_process(command, directory, "gateway"))
        if has_proxy:
            time.sleep(0.3)
            command = [str(ROOT / "bin" / "upstream_markov_proxy.exe"),
                       "--scenario", case, "--run-id", run_id,
                       "--output-dir", str(directory), "--listen-port", "14550",
                       "--gateway-port", "14551", "--gateway-source-port", "14610",
                       "--urb", str(loss), "--reverse-urb", str(loss),
                       "--dur-s", "0.4", "--reverse-dur-s", "0.4",
                       "--slot-ms", "100", "--reverse-slot-ms", "100",
                       "--lossgood", "0", "--lossbad", "1",
                       "--reverse-lossgood", "0", "--reverse-lossbad", "1",
                       "--seed", str(seed), "--measure-seconds", "60"]
            entries.append(start_process(command, directory, "proxy"))
        start = time.monotonic()
        deadline = start + 90
        last_report = start
        while time.monotonic() < deadline:
            if any(process.poll() is not None for process, _, _ in entries):
                raise RuntimeError("Gateway or proxy exited before QoS finished")
            if time.monotonic() - start > 20:
                source_log = directory / ("proxy.log" if has_proxy else "gateway.log")
                marker = "PX4 SOURCE:" if has_proxy else "UAV 1 ONLINE"
                if marker not in source_log.read_text(encoding="utf-8", errors="replace"):
                    raise RuntimeError("No PX4 telemetry received; check UDP 14550")
            row = last_csv(qos_file)
            if value(row, "t_s") >= 60 and (not has_proxy or proxy_file.exists()):
                break
            time.sleep(0.2)
            if time.monotonic() - last_report >= 15:
                print(f"{case}: waiting for 60-second QoS window", flush=True)
                last_report = time.monotonic()
        else:
            raise RuntimeError("QoS did not finish within 90 seconds")
    finally:
        stop_processes(entries)

    gateway = last_csv(qos_file)
    proxy = last_csv(proxy_file) if has_proxy else {}
    rx = value(gateway, "frames")
    gap = value(gateway, "seq_gap_estimate")
    pre = value(proxy, "frames_pre")
    reverse_pre = value(proxy, "reverse_frames_pre")
    gateway_log = (directory / "gateway.log").read_text(encoding="utf-8", errors="replace")
    crc_matches = re.findall(r"CRC errors=(\d+)", gateway_log)
    crc = int(crc_matches[-1]) if crc_matches else "NA"
    result = {
        "case": case, "loss_set": int(loss * 100),
        "loss_up": percent(value(proxy, "frames_dropped_markov"), pre) if has_proxy else "NA",
        "loss_down": percent(value(proxy, "reverse_frames_dropped_markov"), reverse_pre) if has_proxy else "NA",
        "loss_gw": percent(gap, rx + gap), "fps": round(rx / 60, 3),
        "hb_jitter_ms": gateway.get("hb_jitter_ms", ""),
        "offline": gateway.get("offline_events", ""), "crc": crc,
        "seq_resyncs": gateway.get("seq_resyncs", ""),
    }
    checks = [("telemetry", ">0 frame", str(int(rx)), rx > 0)]
    if has_proxy:
        checks.append(("markov_input", "up/down >0", f"{int(pre)}/{int(reverse_pre)}",
                       pre > 0 and reverse_pre > 0))
    if case == "A1":
        checks.append(("baseline_crc", "0", str(crc), crc == 0))
        checks.append(("uav_online", "0 offline events", str(result["offline"]),
                       value(gateway, "offline_events") == 0))
    result["pass"] = "PASS" if all(item[3] for item in checks) else "FAIL"
    write_csv(directory / "result.csv", [result])
    log_checks(directory, checks)
    short_names(directory)
    return result


def run_d1(directory):
    scratch = directory / "docs" / "ketqua"
    scratch.mkdir(parents=True)
    tests = (("parser", "test_stage1_framing.exe"),
             ("telemetry", "test_stage2_telemetry.exe"))
    checks = []
    for label, binary in tests:
        with (directory / f"{label}.log").open("wb") as out:
            completed = subprocess.run([str(ROOT / "bin" / binary)], cwd=directory,
                                       stdout=out, stderr=subprocess.STDOUT,
                                       timeout=30, creationflags=FLAGS)
        checks.append((label, "exit 0", str(completed.returncode), completed.returncode == 0))
    for source, target in (("stage1_framing_results.csv", "parser.csv"),
                           ("stage1_framing_log.txt", "parser_detail.log"),
                           ("stage2_telemetry_results.csv", "telemetry.csv")):
        if (scratch / source).exists():
            (scratch / source).rename(directory / target)
    scratch.rmdir()
    (directory / "docs").rmdir()
    log_checks(directory, checks)
    result = {"case": "D1", "passed": sum(item[3] for item in checks),
              "total": len(checks), "pass": "PASS" if all(item[3] for item in checks) else "FAIL"}
    write_csv(directory / "result.csv", [result])
    return result


def make_heartbeat(mav):
    msg = mav.heartbeat_encode(mavutil.mavlink.MAV_TYPE_QUADROTOR,
                               mavutil.mavlink.MAV_AUTOPILOT_PX4, 0, 0,
                               mavutil.mavlink.MAV_STATE_ACTIVE)
    return msg.pack(mav)


def run_d2(directory, run_id):
    command = [str(ROOT / "bin" / "gateway.exe"), "--scenario", "D2",
               "--run-id", run_id, "--udp-port", "14553",
               "--output-dir", str(directory)]
    entry = start_process(command, directory, "gateway")
    try:
        time.sleep(0.4)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        mav = mavutil.mavlink.MAVLink(None)
        mav.srcSystem = 1
        mav.srcComponent = 1
        valid = make_heartbeat(mav)
        damaged = bytearray(make_heartbeat(mav))
        damaged[10] ^= 0x01
        sock.sendto(valid, ("127.0.0.1", 14553))
        sock.sendto(damaged, ("127.0.0.1", 14553))
        sock.close()
        time.sleep(5.5)
    finally:
        stop_processes([entry])
    log = (directory / "gateway.log").read_text(encoding="utf-8", errors="replace")
    crc_matches = re.findall(r"CRC errors=(\d+)", log)
    crc = int(crc_matches[-1]) if crc_matches else 0
    accepted = "UAV 1 ONLINE" in log
    checks = [("valid_frame", "UAV online", str(accepted), accepted),
              ("bad_crc", ">=1", str(crc), crc >= 1)]
    log_checks(directory, checks)
    result = {"case": "D2", "valid_accepted": int(accepted), "crc_errors": crc,
              "pass": "PASS" if all(item[3] for item in checks) else "FAIL"}
    write_csv(directory / "result.csv", [result])
    short_names(directory)
    return result


def line(sock, timeout=4):
    sock.settimeout(timeout)
    data = b""
    while not data.endswith(b"\n"):
        part = sock.recv(1)
        if not part:
            raise RuntimeError("TCP client disconnected")
        data += part
    return data.decode().strip()


def connect_client():
    for _ in range(30):
        try:
            return socket.create_connection(("127.0.0.1", 5760), timeout=0.3)
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("Gateway TCP 5760 unavailable")


def run_control(case, directory, run_id):
    command = [str(ROOT / "bin" / "gateway.exe"), "--scenario", case,
               "--run-id", run_id, "--udp-port", "14553",
               "--output-dir", str(directory)]
    entry = start_process(command, directory, "gateway")
    a = b = None
    uav = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    uav.bind(("127.0.0.1", 0))
    uav.settimeout(0.3)
    mav = mavutil.mavlink.MAVLink(None)
    mav.srcSystem = 1
    mav.srcComponent = 1
    steps = []
    checks = []
    try:
        a = connect_client()
        b = connect_client()
        a.sendall(b"ACQUIRE\n")
        response = line(a)
        steps.append(f"A ACQUIRE -> {response}")
        checks.append(("A_acquire", "OK ACQUIRE", response, response == "OK ACQUIRE"))
        b.sendall(b"ACQUIRE\nCOMMAND 1 ARM\n")
        locked = line(b)
        denied = line(b)
        steps.extend((f"B ACQUIRE -> {locked}", f"B COMMAND -> {denied}"))
        checks.extend((("B_locked", "ERR LOCKED", locked, locked == "ERR LOCKED"),
                       ("B_denied", "ERR NOT_OWNER", denied, denied == "ERR NOT_OWNER")))
        if case == "E1":
            a.close()
            a = None
            time.sleep(0.2)
            b.sendall(b"ACQUIRE\n")
            reacquired = line(b)
            steps.append(f"B after A disconnect -> {reacquired}")
            checks.append(("release_on_disconnect", "OK ACQUIRE", reacquired,
                           reacquired == "OK ACQUIRE"))
        else:
            uav.sendto(make_heartbeat(mav), ("127.0.0.1", 14553))
            time.sleep(0.2)
            a.sendall(b"COMMAND 1 ARM\n")
            pending = line(a)
            steps.append(f"A COMMAND -> {pending}")
            checks.append(("pending", "OK COMMAND_PENDING 1 400", pending,
                           pending == "OK COMMAND_PENDING 1 400"))
            parser = mavutil.mavlink.MAVLink(None)
            commands = []
            gcs_heartbeats = 0
            next_heartbeat = time.monotonic() + 0.8
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and len(commands) < 2:
                if time.monotonic() >= next_heartbeat:
                    uav.sendto(make_heartbeat(mav), ("127.0.0.1", 14553))
                    next_heartbeat += 0.8
                try:
                    packet = uav.recv(4096)
                except socket.timeout:
                    continue
                for byte in packet:
                    message = parser.parse_char(bytes([byte]))
                    if message and message.get_type() == "COMMAND_LONG":
                        commands.append(message)
                    elif message and message.get_type() == "HEARTBEAT" and message.get_srcSystem() == 255:
                        gcs_heartbeats += 1
            confirmations = [int(message.confirmation) for message in commands]
            steps.append(f"COMMAND_LONG confirmations -> {confirmations}")
            checks.append(("retry", "[0, 1]", str(confirmations),
                           confirmations[:2] == [0, 1]))
            steps.append(f"GCS HEARTBEAT count -> {gcs_heartbeats}")
            checks.append(("gcs_heartbeat", ">=1", str(gcs_heartbeats), gcs_heartbeats >= 1))
            ack = mav.command_ack_encode(400, mavutil.mavlink.MAV_RESULT_ACCEPTED)
            uav.sendto(ack.pack(mav), ("127.0.0.1", 14553))
            response = line(a)
            steps.append(f"A RESULT -> {response}")
            checks.append(("ack_owner", "RESULT 1 400 0", response,
                           response == "RESULT 1 400 0"))
    finally:
        if a: a.close()
        if b: b.close()
        uav.close()
        stop_processes([entry])
    (directory / "test.log").write_text("\n".join(steps) + "\n", encoding="utf-8")
    log_checks(directory, checks)
    result = {"case": case, "passed": sum(item[3] for item in checks),
              "total": len(checks), "pass": "PASS" if all(item[3] for item in checks) else "FAIL"}
    write_csv(directory / "result.csv", [result])
    short_names(directory)
    return result


def run_one(case, command_label, built=False):
    directory = BASE / FOLDERS[case] / stamp()
    directory.mkdir(parents=True, exist_ok=False)
    started = dt.datetime.now().isoformat(timespec="seconds")
    error = ""
    result = None
    print(f"[{case}] output={directory}", flush=True)
    try:
        if not built:
            ensure_build((case,), directory / "build.log")
        if case in ("A1", "B5", "B10"):
            result = run_qos(case, directory, directory.name)
        elif case == "D1":
            result = run_d1(directory)
        elif case == "D2":
            result = run_d2(directory, directory.name)
        else:
            result = run_control(case, directory, directory.name)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    except Exception as exc:
        error = str(exc)
        result = {"case": case, "pass": "FAIL", "error": error}
        write_csv(directory / "result.csv", [result])
        print(f"[{case}] FAIL: {error}", flush=True)
    finally:
        (directory / "run.log").write_text(
            f"case={case}\nstart={started}\n"
            f"end={dt.datetime.now().isoformat(timespec='seconds')}\n"
            f"command=python -B scripts/run_case.py {command_label}\n"
            f"status={'FAIL' if error else result.get('pass', 'PASS')}\nerror={error}\n",
            encoding="utf-8")
    return {"case": case, "status": result.get("pass", "FAIL"),
            "folder": str(directory.relative_to(BASE)), "error": error}


def main():
    parser = argparse.ArgumentParser(description="Run one case or ALL cases in sequence")
    parser.add_argument("case", choices=("ALL", *FOLDERS))
    args = parser.parse_args()
    if args.case == "ALL":
        directory = BASE / "ALL" / stamp()
        directory.mkdir(parents=True, exist_ok=False)
        started = dt.datetime.now().isoformat(timespec="seconds")
        results = []
        try:
            ensure_build(FOLDERS, directory / "build.log")
            for case in FOLDERS:
                results.append(run_one(case, "ALL", built=True))
                write_csv(directory / "result.csv", results)
        except Exception as exc:
            results.append({"case": "BUILD", "status": "FAIL", "folder": "",
                            "error": str(exc)})
            write_csv(directory / "result.csv", results)
            print(f"[ALL] FAIL: {exc}", flush=True)
        finally:
            (directory / "run.log").write_text(
                f"command=python -B scripts/run_case.py ALL\nstart={started}\n"
                f"end={dt.datetime.now().isoformat(timespec='seconds')}\n"
                f"completed={len(results)}/{len(FOLDERS)}\n",
                encoding="utf-8")
        print(f"[ALL] summary={directory / 'result.csv'}", flush=True)
        if any(row["status"] != "PASS" for row in results):
            sys.exit(1)
    else:
        if run_one(args.case, args.case)["status"] != "PASS":
            sys.exit(1)


if __name__ == "__main__":
    main()
