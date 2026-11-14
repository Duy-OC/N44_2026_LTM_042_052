"""Check that the live runner writes a complete result with synthetic MAVLink."""

import subprocess
import tempfile
import threading
import time
import socket
import unittest
from pathlib import Path
from pymavlink import mavutil


ROOT = Path(__file__).resolve().parents[1]


class LiveRunnerTest(unittest.TestCase):
    def test_three_second_k2_run(self):
        with tempfile.TemporaryDirectory(prefix="runner_smoke_", dir=ROOT / "docs/ketqua") as temporary:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            stop = threading.Event()
            sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sender.bind(("127.0.0.1", 0))
            mav = mavutil.mavlink.MAVLink(None)
            mav.srcSystem = 1
            mav.srcComponent = 1

            def feed():
                index = 0
                while not stop.wait(0.05):
                    if index % 20 == 0:
                        heartbeat = mav.heartbeat_encode(
                            mavutil.mavlink.MAV_TYPE_QUADROTOR,
                            mavutil.mavlink.MAV_AUTOPILOT_PX4, 0, 0,
                            mavutil.mavlink.MAV_STATE_ACTIVE)
                        sender.sendto(heartbeat.pack(mav), ("127.0.0.1", 14550))
                    attitude = mav.attitude_encode(index * 50, 0, 0, 0, 0, 0, 0)
                    sender.sendto(attitude.pack(mav), ("127.0.0.1", 14550))
                    index += 1

            feeder = threading.Thread(target=feed, daemon=True)
            feeder.start()
            try:
                result = subprocess.run([
                    "python", "-B", "scripts/run_k_live.py", "K2",
                    "--repeats", "1", "--seconds", "3",
                    "--online-wait", "10", "--output-root", temporary,
                ], cwd=ROOT, text=True, capture_output=True, timeout=20,
                    creationflags=flags)
                logs = "".join(path.read_text(encoding="utf-8", errors="replace")
                               for path in Path(temporary).glob("K2/*/*.log"))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr + logs)
                self.assertTrue((Path(temporary) / "K2/summary.csv").exists())
                self.assertEqual(len(list((Path(temporary) / "K2").glob("*/result.csv"))), 1)
            finally:
                stop.set()
                feeder.join(timeout=1)
                sender.close()


if __name__ == "__main__":
    unittest.main()
