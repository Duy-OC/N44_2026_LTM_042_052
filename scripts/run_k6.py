"""Measure gateway command ACK/retry through a Markov proxy and fake UAV."""

import argparse
import csv
import socket
import statistics
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from pymavlink import mavutil


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/ketqua/K6"


def read_line(sock, timeout=5):
    sock.settimeout(timeout)
    data = bytearray()
    while not data.endswith(b"\n"):
        chunk = sock.recv(1)
        if not chunk:
            raise ConnectionError("Gateway closed TCP connection")
        data.extend(chunk)
    return data.decode(errors="replace").strip()


def rows(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def write_csv(path, data):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(data[0]))
        writer.writeheader()
        writer.writerows(data)


class FakeUav:
    def __init__(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(("127.0.0.1", 0))
        self.socket.settimeout(0.1)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.acks_sent = 0
        self.commands_received = 0

    def start(self):
        self.thread.start()

    def run(self):
        sender = mavutil.mavlink.MAVLink(None)
        sender.srcSystem = 1
        sender.srcComponent = 1
        decoder = mavutil.mavlink.MAVLink(None)
        next_heartbeat = 0.0
        target = ("127.0.0.1", 14650)
        while not self.stop.is_set():
            now = time.monotonic()
            if now >= next_heartbeat:
                heartbeat = sender.heartbeat_encode(
                    mavutil.mavlink.MAV_TYPE_QUADROTOR,
                    mavutil.mavlink.MAV_AUTOPILOT_PX4, 0, 0,
                    mavutil.mavlink.MAV_STATE_ACTIVE)
                self.socket.sendto(heartbeat.pack(sender), target)
                next_heartbeat = now + 0.5
            try:
                packet, _ = self.socket.recvfrom(4096)
            except (socket.timeout, ConnectionResetError):
                continue
            for byte in packet:
                message = decoder.parse_char(bytes([byte]))
                if message and message.get_type() == "COMMAND_LONG" and message.command == 400:
                    self.commands_received += 1
                    ack = sender.command_ack_encode(400, mavutil.mavlink.MAV_RESULT_ACCEPTED)
                    self.socket.sendto(ack.pack(sender), target)
                    self.acks_sent += 1

    def close(self):
        self.stop.set()
        self.thread.join(timeout=1)
        self.socket.close()


def run_once(loss, repeat, commands, seconds, spacing, output_root):
    case = f"L{int(loss * 100)}"
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_r{repeat}"
    folder = output_root / case / run_id
    folder.mkdir(parents=True, exist_ok=False)
    relative = folder.relative_to(ROOT).as_posix()
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    gateway_cmd = [str(ROOT / "bin/gateway.exe"), "--scenario", "K6",
                   "--run-id", run_id, "--output-dir", relative,
                   "--udp-port", "14651", "--measure-seconds", str(seconds)]
    proxy_cmd = [str(ROOT / "bin/upstream_markov_proxy.exe"), "--scenario", "K6",
                 "--run-id", run_id, "--output-dir", relative,
                 "--listen-port", "14650", "--gateway-port", "14651",
                 "--gateway-source-port", "14660", "--measure-seconds", str(seconds),
                 "--seed", str(6000 + repeat), "--urb", str(loss),
                 "--burst-packets", "4", "--lossgood", "0", "--lossbad", "1"]
    (folder / "run.log").write_text(
        f"start={datetime.now().isoformat()}\n"
        f"fake_uav=true\ncommands={commands}\n"
        f"gateway={' '.join(gateway_cmd)}\nproxy={' '.join(proxy_cmd)}\n",
        encoding="utf-8")
    gateway_log = (folder / "gateway.log").open("w", encoding="utf-8")
    proxy_log = (folder / "proxy.log").open("w", encoding="utf-8")
    gateway = proxy = client = uav = None
    records = []
    try:
        gateway = subprocess.Popen(gateway_cmd, cwd=ROOT, stdout=gateway_log,
                                   stderr=subprocess.STDOUT, creationflags=flags)
        time.sleep(0.3)
        proxy = subprocess.Popen(proxy_cmd, cwd=ROOT, stdout=proxy_log,
                                 stderr=subprocess.STDOUT, creationflags=flags)
        time.sleep(0.3)
        uav = FakeUav()
        uav.start()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                client = socket.create_connection(("127.0.0.1", 5760), timeout=0.5)
                break
            except OSError:
                time.sleep(0.1)
        if client is None:
            raise RuntimeError("Cannot connect to gateway TCP 5760")
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            client.sendall(b"GET_DETAIL 1\n")
            if read_line(client).startswith("DETAIL {"):
                break
            time.sleep(0.2)
        else:
            raise RuntimeError("Fake UAV did not come online")
        client.sendall(b"ACQUIRE\n")
        if read_line(client) != "OK ACQUIRE":
            raise RuntimeError("Cannot acquire control lock")

        # Let the proxy complete its 5-second warmup before issuing commands.
        time.sleep(5.5)
        for index in range(1, commands + 1):
            started = time.monotonic()
            client.sendall(b"COMMAND 1 ARM\n")
            first = read_line(client)
            second = read_line(client, 5) if first.startswith("OK COMMAND_PENDING") else ""
            records.append({"command_index": index, "response": first,
                            "result": second, "success": int(second == "RESULT 1 400 0"),
                            "elapsed_s": round(time.monotonic() - started, 3)})
            if index < commands:
                time.sleep(max(0, spacing - (time.monotonic() - started)))

        proxy_summary = folder / f"K6_{run_id}_summary.csv"
        gateway_csv = folder / f"K6_{run_id}_gateway_ingress.csv"
        deadline = time.monotonic() + seconds + 15
        while time.monotonic() < deadline:
            if gateway.poll() is not None or proxy.poll() is not None:
                raise RuntimeError("Gateway or proxy exited early")
            if proxy_summary.exists() and gateway_csv.exists() and any(
                float(row["t_s"]) >= seconds for row in rows(gateway_csv)):
                break
            time.sleep(0.3)
        else:
            raise RuntimeError("K6 did not reach full measurement window")
        write_csv(folder / "commands.csv", records)
        trace = rows(folder / f"K6_{run_id}_reverse_trace.csv")
        attempts = sum(row["msgid"] == "76" and row["command"] == "400" for row in trace)
        pending = sum(row["response"].startswith("OK COMMAND_PENDING") for row in records)
        success = sum(row["success"] for row in records)
        proxy_values = rows(proxy_summary)[0]
        reverse_pre = int(proxy_values["reverse_frames_pre"])
        reverse_dropped = int(proxy_values["reverse_frames_dropped_markov"])
        result = {"loss_set_pct": loss * 100, "run_id": run_id,
                  "commands": commands, "pending": pending, "acked": success,
                  "success_pct": round(100 * success / commands, 3),
                  "attempts": attempts, "retries": max(0, attempts - pending),
                  "retry_mean_per_command": round(max(0, attempts - pending) / commands, 3),
                  "reverse_pre": reverse_pre, "reverse_dropped": reverse_dropped,
                  "reverse_loss_pct": round(100 * reverse_dropped / reverse_pre, 3) if reverse_pre else "",
                  "fake_uav_commands_received": uav.commands_received,
                  "fake_uav_acks_sent": uav.acks_sent}
        write_csv(folder / "result.csv", [result])
        with (folder / "run.log").open("a", encoding="utf-8") as stream:
            stream.write(f"end={datetime.now().isoformat()}\nstatus=PASS\n")
        return folder, result
    except Exception as error:
        with (folder / "run.log").open("a", encoding="utf-8") as stream:
            stream.write(f"end={datetime.now().isoformat()}\nstatus=FAIL\nerror={error}\n")
        raise
    finally:
        if client:
            client.close()
        if uav:
            uav.close()
        for process in (proxy, gateway):
            if process and process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
        gateway_log.close()
        proxy_log.close()


def aggregate(case_dir):
    results = [row for path in sorted(case_dir.glob("*/result.csv")) for row in rows(path)]
    if not results:
        return
    output = []
    for metric in ("success_pct", "retry_mean_per_command", "reverse_loss_pct"):
        values = [float(row[metric]) for row in results if row[metric]]
        output.append({"metric": metric, "runs": len(values),
                       "mean": round(statistics.mean(values), 4),
                       "std": round(statistics.stdev(values), 4) if len(values) > 1 else ""})
    write_csv(case_dir / "summary.csv", output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loss", type=int, choices=(0, 5, 10), required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--commands", type=int, default=50)
    parser.add_argument("--seconds", type=int, default=120)
    parser.add_argument("--spacing", type=float, default=1.8)
    parser.add_argument("--output-root", type=Path, default=BASE)
    args = parser.parse_args()
    if min(args.repeats, args.commands, args.seconds) <= 0 or args.spacing < 0:
        parser.error("invalid positive measurement parameters")
    for repeat in range(1, args.repeats + 1):
        print(f"K6 loss={args.loss}% run {repeat}/{args.repeats}: start", flush=True)
        folder, result = run_once(args.loss / 100, repeat, args.commands,
                                  args.seconds, args.spacing, args.output_root.resolve())
        print(f"{folder}: success={result['success_pct']}% "
              f"retry_mean={result['retry_mean_per_command']}", flush=True)
        aggregate(args.output_root.resolve() / f"L{args.loss}")
        time.sleep(1)


if __name__ == "__main__":
    main()
