"""Short UDP integration checks for the K2, K5 and K7 measurement paths."""

import csv
import socket
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from pymavlink import mavutil


ROOT = Path(__file__).resolve().parents[1]


def last_row(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))[-1]


class MeasurementModesTest(unittest.TestCase):
    def exercise(self, name, proxy_options):
        with tempfile.TemporaryDirectory(prefix="measure_smoke_", dir=ROOT / "docs" / "ketqua") as temporary:
            folder = Path(temporary)
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            gateway_log = (folder / "gateway.log").open("w", encoding="utf-8")
            proxy_log = (folder / "proxy.log").open("w", encoding="utf-8")
            gateway = proxy = None
            try:
                gateway = subprocess.Popen([
                    str(ROOT / "bin/gateway.exe"), "--scenario", name,
                    "--run-id", "smoke", "--output-dir", temporary,
                    "--udp-port", "14551", "--measure-seconds", "3",
                ], cwd=ROOT, stdout=gateway_log, stderr=subprocess.STDOUT,
                    creationflags=flags)
                proxy = subprocess.Popen([
                    str(ROOT / "bin/upstream_markov_proxy.exe"),
                    "--scenario", name, "--run-id", "smoke",
                    "--output-dir", temporary, "--listen-port", "14550",
                    "--gateway-port", "14551", "--gateway-source-port", "14610",
                    "--measure-seconds", "3", "--seed", "12",
                    *proxy_options,
                ], cwd=ROOT, stdout=proxy_log, stderr=subprocess.STDOUT,
                    creationflags=flags)
                time.sleep(0.4)
                self.assertIsNone(gateway.poll())
                self.assertIsNone(proxy.poll())
                sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                mav = mavutil.mavlink.MAVLink(None)
                mav.srcSystem = 1
                mav.srcComponent = 1
                target = ("127.0.0.1", 14550)
                try:
                    for index in range(1000):
                        if index % 50 == 0:
                            heartbeat = mav.heartbeat_encode(
                                mavutil.mavlink.MAV_TYPE_QUADROTOR,
                                mavutil.mavlink.MAV_AUTOPILOT_PX4, 0, 0,
                                mavutil.mavlink.MAV_STATE_ACTIVE)
                            sender.sendto(heartbeat.pack(mav), target)
                        attitude = mav.attitude_encode(index * 10, 0, 0, 0, 0, 0, 0)
                        sender.sendto(attitude.pack(mav), target)
                        time.sleep(0.01)
                finally:
                    sender.close()
                summary_path = folder / f"{name}_smoke_summary.csv"
                deadline = time.monotonic() + 3
                while not summary_path.exists() and time.monotonic() < deadline:
                    time.sleep(0.1)
                self.assertTrue(summary_path.exists())
                summary = last_row(summary_path)
                gateway_csv = folder / f"{name}_smoke_gateway_ingress.csv"
                gateway_row = last_row(gateway_csv)
                self.assertGreater(int(gateway_row["attitude_count"]), 0)
                self.assertGreater(int(summary["frames_pre"]), 0)
                return summary, gateway_row, folder
            finally:
                for process in (proxy, gateway):
                    if process and process.poll() is None:
                        process.terminate()
                        process.wait(timeout=3)
                gateway_log.close()
                proxy_log.close()

    def test_packet_burst(self):
        summary, _, _ = self.exercise("K2", [
            "--urb", "0.05", "--burst-packets", "4",
            "--lossgood", "0", "--lossbad", "1",
        ])
        self.assertEqual(int(summary["frames_pre"]),
                         int(summary["frames_dropped_markov"]) + int(summary["frames_kept"]))

    def test_delay(self):
        summary, _, _ = self.exercise("K5", [
            "--urb", "0.5", "--dur-s", "0.4",
            "--lossgood", "0", "--lossbad", "0",
            "--delay-bad-min-ms", "20", "--delay-bad-max-ms", "80",
        ])
        self.assertGreater(int(summary["delayed_frames"]), 0)

    def test_flip(self):
        summary, gateway, _ = self.exercise("K7", [
            "--urb", "0", "--flip-probability", "0.3",
        ])
        self.assertGreater(int(summary["flipped_sent"]), 0)
        self.assertGreater(int(gateway["crc_errors"]), 0)


if __name__ == "__main__":
    unittest.main()
