"""Measure DISARM ACK/retry against real PX4 SITL; never emits UAV telemetry."""

import argparse
import json
import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path

from run_k_live import ROOT, rows, write_csv, wait_for_measurement


def line(client, timeout=5):
    client.settimeout(timeout)
    data = bytearray()
    while not data.endswith(b"\n"):
        chunk = client.recv(1)
        if not chunk:
            raise ConnectionError("Gateway closed TCP")
        data.extend(chunk)
    return data.decode().strip()


def run_once(loss, repeat, output_root):
    seconds, commands = 120, 50
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_r{repeat}"
    folder = output_root / f"L{loss}" / run_id
    folder.mkdir(parents=True, exist_ok=False)
    relative = folder.relative_to(ROOT).as_posix()
    common = ["--scenario", "K6", "--run-id", run_id,
              "--output-dir", relative, "--measure-seconds", str(seconds)]
    gateway_cmd = [str(ROOT / "bin/gateway.exe"), *common, "--udp-port", "14551"]
    proxy_cmd = [str(ROOT / "bin/upstream_markov_proxy.exe"), *common,
                 "--listen-port", "14550", "--gateway-port", "14551",
                 "--gateway-source-port", "14610", "--seed", str(6000 + repeat),
                 "--urb", str(loss / 100), "--burst-packets", "4",
                 "--lossgood", "0", "--lossbad", "1"]
    journal = folder / "run.log"
    journal.write_text(f"start={datetime.now().isoformat()}\nsource=PX4_SITL\n"
                       f"fake_uav=false\nseconds={seconds}\ncommand=DISARM\n"
                       f"gateway={gateway_cmd!r}\nproxy={proxy_cmd!r}\n", encoding="utf-8")
    gateway = proxy = client = None
    records = []
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with (folder / "gateway.log").open("w", encoding="utf-8") as glog, \
            (folder / "proxy.log").open("w", encoding="utf-8") as plog:
        try:
            gateway = subprocess.Popen(gateway_cmd, cwd=ROOT, stdout=glog,
                                       stderr=subprocess.STDOUT, creationflags=flags)
            time.sleep(0.3)
            proxy = subprocess.Popen(proxy_cmd, cwd=ROOT, stdout=plog,
                                     stderr=subprocess.STDOUT, creationflags=flags)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                try:
                    client = socket.create_connection(("127.0.0.1", 5760), timeout=1)
                    break
                except OSError:
                    time.sleep(0.2)
            if client is None:
                raise RuntimeError("Gateway TCP unavailable")
            while time.monotonic() < deadline:
                client.sendall(b"GET_DETAIL 1\n")
                reply = line(client)
                if reply.startswith("DETAIL {"):
                    detail = json.loads(reply[len("DETAIL "):])
                    (folder / "initial_detail.json").write_text(
                        json.dumps(detail, indent=2), encoding="utf-8")
                    if detail.get("armed") is not False:
                        raise RuntimeError("K6 requires disarmed SITL; no commands sent")
                    break
                time.sleep(0.2)
            else:
                raise RuntimeError("PX4 not online")
            client.sendall(b"ACQUIRE\n")
            if line(client) != "OK ACQUIRE":
                raise RuntimeError("Control lock unavailable")
            # Wait for both real ingress measurement windows, after their warmups.
            ingress = folder / f"K6_{run_id}_gateway_ingress.csv"
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if ingress.exists() and any(float(r["t_s"]) >= 5 for r in rows(ingress)):
                    break
                time.sleep(0.2)
            else:
                raise RuntimeError("Measurement window did not start")
            started_commands = time.monotonic()
            for index in range(1, commands + 1):
                if time.monotonic() - started_commands > 102:
                    raise RuntimeError("Cannot fit all 50 commands inside 120-second window")
                started = time.monotonic()
                client.sendall(b"COMMAND 1 DISARM\n")
                first = line(client)
                result = line(client) if first.startswith("OK COMMAND_PENDING") else ""
                fields = result.split()
                acked = len(fields) == 4 and fields[:3] == ["RESULT", "1", "400"] and fields[3].isdigit()
                records.append({"command_index": index, "command": "DISARM",
                                "response": first, "result": result,
                                "acked": int(acked), "accepted": int(result == "RESULT 1 400 0"),
                                "elapsed_s": round(time.monotonic() - started, 4)})
                write_csv(folder / "commands.csv", records)
                if index < commands:
                    time.sleep(max(0, 1.8 - (time.monotonic() - started)))
            wait_for_measurement(folder, run_id, "K6", seconds, gateway, proxy, 30)
            trace = rows(folder / f"K6_{run_id}_reverse_trace.csv")
            attempts = sum(r["msgid"] == "76" and r["command"] == "400" for r in trace)
            pending = sum(r["response"].startswith("OK COMMAND_PENDING") for r in records)
            acked = sum(r["acked"] for r in records)
            accepted = sum(r["accepted"] for r in records)
            proxy_values = rows(folder / f"K6_{run_id}_summary.csv")[0]
            reverse_pre = int(proxy_values["reverse_frames_pre"])
            reverse_dropped = int(proxy_values["reverse_frames_dropped_markov"])
            result = {"case": "K6", "run_id": run_id, "seconds": seconds,
                      "source": "PX4_SITL", "command": "DISARM", "loss_set_pct": loss,
                      "commands": commands, "pending": pending, "acked": acked,
                      "accepted": accepted, "ack_pct": round(100 * acked / commands, 3),
                      "accepted_pct": round(100 * accepted / commands, 3),
                      "reverse_pre": reverse_pre, "reverse_dropped": reverse_dropped,
                      "reverse_loss_pct": round(100 * reverse_dropped / reverse_pre, 3) if reverse_pre else "",
                      "attempts": attempts, "retries": max(0, attempts - pending),
                      "retry_mean_per_command": round(max(0, attempts - pending) / commands, 3)}
            write_csv(folder / "result.csv", [result])
            with journal.open("a", encoding="utf-8") as stream:
                stream.write(f"end={datetime.now().isoformat()}\nstatus=PASS\n")
            return folder, result
        except Exception as error:
            with journal.open("a", encoding="utf-8") as stream:
                stream.write(f"end={datetime.now().isoformat()}\nstatus=FAIL\nerror={error}\n")
            raise
        finally:
            if client:
                client.close()
            for process in (proxy, gateway):
                if process and process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loss", type=int, choices=(0, 5, 10), required=True)
    parser.add_argument("--output-root", type=Path, default=ROOT / "docs/ketqua_lan2/K6")
    args = parser.parse_args()
    for repeat in range(1, 4):
        print(run_once(args.loss, repeat, args.output_root.resolve()), flush=True)
