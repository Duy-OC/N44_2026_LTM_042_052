"""Smoke check for the gateway-to-PX4 Markov channel."""

import socket
import subprocess
import time
import threading
import tempfile
import uuid
import unittest
from pathlib import Path

from pymavlink import mavutil


ROOT = Path(__file__).resolve().parents[1]


def read_line(conn):
    conn.settimeout(4)
    data = b""
    while not data.endswith(b"\n"):
        data += conn.recv(1)
    return data.decode().strip()


class ReverseMarkovTest(unittest.TestCase):
    def test_reverse_drop_reaches_command(self):
        run_id = "reverse_" + uuid.uuid4().hex[:12]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        temporary = tempfile.TemporaryDirectory(prefix="reverse_markov_")
        output_dir = temporary.name
        proxy = subprocess.Popen([
            str(ROOT / "bin" / "upstream_markov_proxy.exe"),
            "--run-id", run_id, "--scenario", "SMOKE", "--urb", "0",
            "--output-dir", output_dir, "--measure-seconds", "10",
            "--reverse-urb", "0.5", "--reverse-lossgood", "1",
            "--reverse-lossbad", "1",
        ], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=flags)
        gateway = subprocess.Popen([
            str(ROOT / "bin" / "gateway.exe"),
            "--scenario", "reverse_smoke", "--run-id", run_id,
            "--output-dir", output_dir, "--measure-seconds", "10",
        ], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=flags)
        uav = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        uav.bind(("127.0.0.1", 0))
        client = None
        heartbeat_stop = threading.Event()
        heartbeat_thread = None
        try:
            for _ in range(30):
                try:
                    client = socket.create_connection(("127.0.0.1", 5760), timeout=0.2)
                    break
                except OSError:
                    time.sleep(0.1)
            self.assertIsNotNone(client)
            self.assertIsNone(proxy.poll())
            mav = mavutil.mavlink.MAVLink(None)
            mav.srcSystem = 1
            mav.srcComponent = 1
            heartbeat = mav.heartbeat_encode(
                mavutil.mavlink.MAV_TYPE_QUADROTOR,
                mavutil.mavlink.MAV_AUTOPILOT_PX4, 0, 0,
                mavutil.mavlink.MAV_STATE_ACTIVE)
            target = ("127.0.0.1", 14551)
            for _ in range(10):
                uav.sendto(heartbeat.pack(mav), target)
                client.sendall(b"GET_DETAIL 1\n")
                if read_line(client).startswith("DETAIL {"):
                    break
                time.sleep(0.1)
            else:
                self.fail("UAV route was not learned through proxy")

            def keep_online():
                while not heartbeat_stop.wait(0.5):
                    uav.sendto(heartbeat.pack(mav), target)

            heartbeat_thread = threading.Thread(target=keep_online, daemon=True)
            heartbeat_thread.start()

            client.sendall(b"ACQUIRE\nCOMMAND 1 ARM\n")
            self.assertEqual(read_line(client), "OK ACQUIRE")
            self.assertEqual(read_line(client), "OK COMMAND_PENDING 1 400")
            self.assertEqual(read_line(client), "RESULT 1 TIMEOUT")
            late_mav = mavutil.mavlink.MAVLink(None)
            late_mav.srcSystem = 1
            late_mav.srcComponent = 1
            late_ack = late_mav.command_ack_encode(400, mavutil.mavlink.MAV_RESULT_ACCEPTED)
            uav.sendto(late_ack.pack(late_mav), target)
            client.settimeout(0.5)
            with self.assertRaises(socket.timeout):
                client.recv(1)

            trace = Path(output_dir) / f"SMOKE_{run_id}_reverse_trace.csv"
            rows = trace.read_text().splitlines()[1:]
            self.assertTrue(any(",76,400," in row and row.endswith(",DROP") for row in rows))
        finally:
            heartbeat_stop.set()
            if heartbeat_thread:
                heartbeat_thread.join(timeout=1)
            if client: client.close()
            uav.close()
            gateway.terminate()
            proxy.terminate()
            gateway.wait(timeout=3)
            proxy.wait(timeout=3)
            temporary.cleanup()


if __name__ == "__main__":
    unittest.main()
