"""K8: 3 x 120s real PX4 ingress, with a six-second C++ proxy outage."""

import json
import subprocess
import time
from datetime import datetime

from run_k_live import ROOT, rows, write_csv, wait_for_measurement


BASE = ROOT / "docs/ketqua_lan2/K8"


def run_once(repeat):
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_r{repeat}"
    folder = BASE / run_id
    folder.mkdir(parents=True, exist_ok=False)
    relative = folder.relative_to(ROOT).as_posix()
    gateway_cmd = [str(ROOT / "bin/gateway.exe"), "--scenario", "K8",
                   "--run-id", run_id, "--output-dir", relative,
                   "--udp-port", "14551", "--measure-seconds", "120"]
    proxy_cmd = [str(ROOT / "bin/upstream_markov_proxy.exe"),
                 "--listen-port", "14550", "--gateway-port", "14551",
                 "--gateway-source-port", "14610", "--urb", "0",
                 "--lossgood", "0", "--lossbad", "0", "--seed", str(8000 + repeat)]
    (folder / "config.json").write_text(json.dumps({
        "gateway": gateway_cmd, "proxy": proxy_cmd,
        "seconds": 120, "outage_seconds": 6,
        "action": "stop_and_restart_cpp_proxy", "source": "PX4_SITL",
        "poll_interval_s": 0.05,
        "timing_note": "Detection/recovery times observe flushed gateway log; include logging and polling delay."
    }, indent=2), encoding="utf-8")
    journal = folder / "run.log"
    journal.write_text(f"start={datetime.now().isoformat()}\nsource=PX4_SITL\n"
                       "fake_uav=false\nseconds=120\naction=stop_and_restart_cpp_proxy\n", encoding="utf-8")
    events = []
    gateway = proxy = None
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    log_path = folder / "gateway.log"
    ingress = folder / f"K8_{run_id}_gateway_ingress.csv"
    trace = folder / f"K8_{run_id}_gateway_ingress_trace.csv"

    def event(name):
        stamp = time.time()
        events.append({"event": name, "epoch_s": round(stamp, 6),
                       "local_time": datetime.now().isoformat()})
        write_csv(folder / "events.csv", events)
        return stamp

    def healthy():
        if gateway.poll() is not None:
            raise RuntimeError("Gateway exited early")

    with log_path.open("w", encoding="utf-8") as glog, \
            (folder / "proxy.log").open("w", encoding="utf-8") as plog:
        try:
            gateway = subprocess.Popen(gateway_cmd, cwd=ROOT, stdout=glog,
                                       stderr=subprocess.STDOUT, creationflags=flags)
            time.sleep(0.3)
            proxy = subprocess.Popen(proxy_cmd, cwd=ROOT, stdout=plog,
                                     stderr=subprocess.STDOUT, creationflags=flags)
            deadline = time.monotonic() + 55
            while time.monotonic() < deadline:
                healthy()
                if proxy.poll() is not None:
                    raise RuntimeError("Proxy exited before outage")
                if ingress.exists() and any(float(r["t_s"]) >= 30 and int(r["frames"]) > 0
                                            for r in rows(ingress)):
                    break
                time.sleep(0.05)
            else:
                raise RuntimeError("Real ingress did not reach 30s")
            text = log_path.read_text(encoding="utf-8", errors="replace")
            initial_online = text.count("UAV 1 ONLINE")
            initial_offline = text.count("UAV 1 OFFLINE (Timeout)")
            if initial_online < 1 or initial_offline:
                raise RuntimeError("Unstable PX4 link before controlled outage")
            event("proxy_stop_requested")
            proxy.terminate()
            proxy.wait(timeout=5)
            stopped_at = event("proxy_stopped")
            restart_at = time.monotonic() + 6
            detected_at = None
            while time.monotonic() < restart_at:
                healthy()
                text = log_path.read_text(encoding="utf-8", errors="replace")
                if detected_at is None and text.count("UAV 1 OFFLINE (Timeout)") > initial_offline:
                    detected_at = event("gateway_offline_observed")
                time.sleep(0.05)
            if detected_at is None:
                raise RuntimeError("Gateway did not report timeout during six-second outage")
            trace_rows = rows(trace)
            last_ingress_epoch = float(trace_rows[-1]["epoch_ms"]) / 1000
            restart_requested = event("proxy_restart_requested")
            proxy = subprocess.Popen(proxy_cmd, cwd=ROOT, stdout=plog,
                                     stderr=subprocess.STDOUT, creationflags=flags)
            deadline = time.monotonic() + 15
            recovered_at = None
            while time.monotonic() < deadline:
                healthy()
                if proxy.poll() is not None:
                    raise RuntimeError("Proxy failed to restart")
                text = log_path.read_text(encoding="utf-8", errors="replace")
                if text.count("UAV 1 ONLINE") > initial_online:
                    recovered_at = event("gateway_online_observed")
                    break
                time.sleep(0.05)
            if recovered_at is None:
                raise RuntimeError("Gateway did not recover after proxy restart")
            print(f"K8 {repeat}/3: OFFLINE after {detected_at - last_ingress_epoch:.3f}s "
                  f"from last frame; ONLINE restored", flush=True)
            wait_for_measurement(folder, run_id, "K8", 120, gateway, None, 30)
            final = [r for r in rows(ingress) if float(r["t_s"]) >= 120 and r["sysid"] == "1"][-1]
            result = {"case": "K8", "run_id": run_id, "seconds": 120,
                      "source": "PX4_SITL", "action": "stop_and_restart_cpp_proxy",
                      "threshold_s": 3, "outage_set_s": 6,
                      "detected": 1, "recovered": 1,
                      "detected_after_last_frame_s": round(detected_at - last_ingress_epoch, 4),
                      "detected_after_proxy_stopped_s": round(detected_at - stopped_at, 4),
                      "recovery_after_restart_request_s": round(recovered_at - restart_requested, 4),
                      "frames": int(final["frames"]), "crc_errors": int(final["crc_errors"]),
                      "qos_offline_events": int(final["offline_events"])}
            write_csv(folder / "result.csv", [result])
            with journal.open("a", encoding="utf-8") as stream:
                stream.write(f"end={datetime.now().isoformat()}\nstatus=PASS\n")
            return result
        except Exception as error:
            with journal.open("a", encoding="utf-8") as stream:
                stream.write(f"end={datetime.now().isoformat()}\nstatus=FAIL\nerror={error}\n")
            raise
        finally:
            for process in (proxy, gateway):
                if process and process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)


if __name__ == "__main__":
    from run_round2_live import completed
    from run_k_live import aggregate
    for repeat in range(len(completed(BASE)) + 1, 4):
        print(f"K8 {repeat}/3: start, 120 seconds", flush=True)
        print(run_once(repeat), flush=True)
        aggregate(BASE)
        time.sleep(1)
