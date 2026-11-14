"""Pause PX4 to measure OFFLINE; original terminal may need `fg` afterward."""

import argparse
import csv
import subprocess
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def wsl(*args):
    return subprocess.run(["wsl", "--exec", *args], text=True,
                          capture_output=True, check=True).stdout.strip()


def wait_log(path, needle, deadline):
    while time.monotonic() < deadline:
        if path.exists() and needle in path.read_text(encoding="utf-8", errors="replace"):
            return time.perf_counter()
        time.sleep(0.05)
    raise TimeoutError(f"Gateway did not log {needle}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-terminal-stop", action="store_true",
                        help="Acknowledge PX4/Gazebo may require `fg` in the original WSL terminal")
    args = parser.parse_args()
    if not args.allow_terminal_stop:
        parser.error("This may stop the PX4 terminal job; add --allow-terminal-stop only when ready to restore it with `fg`")
    pids = wsl("pgrep", "-x", "px4").splitlines()
    if len(pids) != 1 or not pids[0].isdigit():
        raise RuntimeError(f"Expected one PX4 SITL process, found {pids}")
    pid = pids[0]
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = ROOT / "docs/ketqua/K8" / run_id
    folder.mkdir(parents=True, exist_ok=False)
    log_path = folder / "gateway.log"
    relative = folder.relative_to(ROOT).as_posix()
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    paused = False
    with log_path.open("w", encoding="utf-8") as output:
        gateway = subprocess.Popen([
            str(ROOT / "bin/gateway.exe"), "--scenario", "K8",
            "--run-id", run_id, "--output-dir", relative,
            "--udp-port", "14550", "--measure-seconds", "10",
        ], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
            creationflags=flags)
        try:
            wait_log(log_path, "UAV 1 ONLINE", time.monotonic() + 15)
            time.sleep(1.0)
            stop_epoch = time.time()
            stop_clock = time.perf_counter()
            wsl("kill", "-STOP", pid)
            paused = True
            detected_clock = wait_log(log_path, "UAV 1 OFFLINE (Timeout)",
                                      time.monotonic() + 6)
            elapsed = detected_clock - stop_clock
            result = {"run_id": run_id, "px4_pid": pid,
                      "action": "SIGSTOP_then_SIGCONT", "stop_epoch_s": round(stop_epoch, 3),
                      "threshold_s": 3, "detected_after_stop_s": round(elapsed, 3),
                      "detected": 1}
            with (folder / "result.csv").open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=result)
                writer.writeheader()
                writer.writerow(result)
            print(folder / "result.csv", result)
        finally:
            if paused:
                wsl("kill", "-CONT", pid)
                time.sleep(0.5)
                state = wsl("ps", "-o", "stat=", "-p", pid).strip()
                restored = not state.startswith("T")
                (folder / "restore.log").write_text(
                    f"px4_state_after_SIGCONT={state}\nrestored={restored}\n"
                    + ("Original PX4 terminal may need `fg`.\n" if not restored else ""),
                    encoding="utf-8")
                if not restored:
                    print("PX4 is still stopped; run `fg` in its original terminal")
            if gateway.poll() is None:
                gateway.terminate()
                gateway.wait(timeout=5)


if __name__ == "__main__":
    main()
