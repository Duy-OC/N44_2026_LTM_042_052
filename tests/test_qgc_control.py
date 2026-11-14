"""QGC over TCP: telemetry, ARM/TAKEOFF, mode and joystick control."""

import socket
import subprocess
import threading
import time
import unittest
from collections import deque
from pathlib import Path

from pymavlink.dialects.v20 import common as mavlink


ROOT = Path(__file__).resolve().parents[1]
UDP_PORT = 14564
UAV_PORT = 14600
TCP_PORT = 5760


class MavStream:
    def __init__(self, sock):
        self.sock = sock
        self.parser = mavlink.MAVLink(None)
        self.messages = deque()

    def read(self, predicate, timeout=3.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            while self.messages:
                message = self.messages.popleft()
                if predicate(message):
                    return message
            self.sock.settimeout(max(0.05, deadline - time.monotonic()))
            try:
                data = self.sock.recv(4096)
            except socket.timeout:
                return None
            if not data:
                return None
            for byte in data:
                message = self.parser.parse_char(bytes([byte]))
                if message:
                    self.messages.append(message)
        return None


class QgcControlTest(unittest.TestCase):
    def setUp(self):
        self.gateway = subprocess.Popen(
            [str(ROOT / "bin" / "gateway.exe"), "--udp-port", str(UDP_PORT)],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.uav = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.uav.bind(("127.0.0.1", UAV_PORT))
        self.uav.settimeout(0.1)
        self.uav_parser = mavlink.MAVLink(None)
        self.uav_link = mavlink.MAVLink(None, srcSystem=1, srcComponent=1)
        self.stop = threading.Event()
        self.feeder = threading.Thread(target=self.feed_uav, daemon=True)
        self.feeder.start()
        self.clients = []
        self.text = None
        self.wait_for_tcp()

    def tearDown(self):
        for client in self.clients:
            client.close()
        if self.text:
            self.text.close()
        self.stop.set()
        self.feeder.join(timeout=1)
        self.uav.close()
        self.gateway.terminate()
        self.gateway.wait(timeout=3)

    def feed_uav(self):
        while not self.stop.wait(0.3):
            heartbeat = self.uav_link.heartbeat_encode(
                mavlink.MAV_TYPE_QUADROTOR,
                mavlink.MAV_AUTOPILOT_PX4,
                0,
                0,
                mavlink.MAV_STATE_ACTIVE,
            )
            self.uav.sendto(heartbeat.pack(self.uav_link), ("127.0.0.1", UDP_PORT))

    def wait_for_tcp(self):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                probe = socket.create_connection(("127.0.0.1", TCP_PORT), timeout=0.2)
                probe.close()
                return
            except OSError:
                time.sleep(0.1)
        raise RuntimeError("Gateway TCP unavailable")

    def connect_qgc(self):
        sock = socket.create_connection(("127.0.0.1", TCP_PORT), timeout=2)
        link = mavlink.MAVLink(None, srcSystem=255, srcComponent=190)
        heartbeat = link.heartbeat_encode(
            mavlink.MAV_TYPE_GCS,
            mavlink.MAV_AUTOPILOT_INVALID,
            0,
            0,
            mavlink.MAV_STATE_ACTIVE,
        )
        sock.sendall(heartbeat.pack(link))
        self.clients.append(sock)
        return sock, link

    def read_uav(self, predicate, timeout=2.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data, _ = self.uav.recvfrom(65535)
            except socket.timeout:
                continue
            for message in self.uav_parser.parse_buffer(data):
                if predicate(message):
                    return message
        return None

    def assert_forwarded(self, sock, link, message, predicate, timeout=2.0):
        self.uav_parser = mavlink.MAVLink(None)
        sock.sendall(message.pack(link))
        received = self.read_uav(predicate, timeout)
        self.assertIsNotNone(received)
        self.assertEqual(received.get_srcSystem(), 255)
        return received

    def test_qgc_telemetry_and_control(self):
        qgc, link = self.connect_qgc()
        stream = MavStream(qgc)

        # Wait until the gateway has learned the UAV and forwards its
        # heartbeat to QGC before checking telemetry.
        heartbeat = self.uav_link.heartbeat_encode(
            mavlink.MAV_TYPE_QUADROTOR,
            mavlink.MAV_AUTOPILOT_PX4,
            0,
            0,
            mavlink.MAV_STATE_ACTIVE,
        )
        self.uav.sendto(heartbeat.pack(self.uav_link), ("127.0.0.1", UDP_PORT))
        self.assertIsNotNone(stream.read(
            lambda m: m.get_msgId() == mavlink.MAVLINK_MSG_ID_HEARTBEAT
            and m.get_srcSystem() == 1))

        # Telemetry is broadcast to the QGC connection.
        attitude = self.uav_link.attitude_encode(500, 0.1, 0.2, 0.3, 0, 0, 0)
        self.uav.sendto(attitude.pack(self.uav_link), ("127.0.0.1", UDP_PORT))
        self.assertIsNotNone(stream.read(lambda m: m.get_msgId() == mavlink.MAVLINK_MSG_ID_ATTITUDE))

        # ARM and TAKEOFF are forwarded without the text ACQUIRE command.
        arm = link.command_long_encode(
            1, 1, mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0,
            1, 0, 0, 0, 0, 0, 0)
        self.assert_forwarded(
            qgc, link, arm,
            lambda m: m.get_msgId() == mavlink.MAVLINK_MSG_ID_COMMAND_LONG
            and m.command == mavlink.MAV_CMD_COMPONENT_ARM_DISARM
            and m.param1 == 1)

        takeoff = link.command_long_encode(
            1, 1, mavlink.MAV_CMD_NAV_TAKEOFF, 0,
            0, 0, 0, 0, 0, 0, 10)
        self.assert_forwarded(
            qgc, link, takeoff,
            lambda m: m.get_msgId() == mavlink.MAVLINK_MSG_ID_COMMAND_LONG
            and m.command == mavlink.MAV_CMD_NAV_TAKEOFF
            and abs(m.param7 - 10) < 0.01)

        # QGC flight-mode and joystick messages are forwarded too.
        set_mode = link.set_mode_encode(1, 1, 4)
        self.assert_forwarded(
            qgc, link, set_mode,
            lambda m: m.get_msgId() == mavlink.MAVLINK_MSG_ID_SET_MODE
            and m.target_system == 1)

        do_set_mode = link.command_long_encode(
            1, 1, mavlink.MAV_CMD_DO_SET_MODE, 0,
            1, 4, 0, 0, 0, 0, 0)
        self.assert_forwarded(
            qgc, link, do_set_mode,
            lambda m: m.get_msgId() == mavlink.MAVLINK_MSG_ID_COMMAND_LONG
            and m.command == mavlink.MAV_CMD_DO_SET_MODE)

        land = link.command_long_encode(
            1, 1, mavlink.MAV_CMD_NAV_LAND, 0,
            0, 0, 0, 0, 0, 0, 0)
        self.assert_forwarded(
            qgc, link, land,
            lambda m: m.get_msgId() == mavlink.MAVLINK_MSG_ID_COMMAND_LONG
            and m.command == mavlink.MAV_CMD_NAV_LAND)

        manual = link.manual_control_encode(1, 100, 0, 0, 0, 0)
        self.assert_forwarded(
            qgc, link, manual,
            lambda m: m.get_msgId() == mavlink.MAVLINK_MSG_ID_MANUAL_CONTROL
            and m.target == 1 and m.x == 100)

        # A second QGC connection cannot control while the first owns the lock.
        qgc2, link2 = self.connect_qgc()
        self.uav_parser = mavlink.MAVLink(None)
        arm2 = link2.command_long_encode(
            1, 1, mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0,
            1, 0, 0, 0, 0, 0, 0)
        qgc2.sendall(arm2.pack(link2))
        self.assertIsNone(self.read_uav(
            lambda m: m.get_msgId() == mavlink.MAVLINK_MSG_ID_COMMAND_LONG
            and m.command == mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            timeout=0.8))

        # The text client also sees the lock as held by QGC.
        self.text = socket.create_connection(("127.0.0.1", TCP_PORT), timeout=2)
        self.text.sendall(b"ACQUIRE\n")
        self.assertEqual(self.text.recv(64).decode().strip(), "ERR LOCKED")
        self.text.close()
        self.text = None

        # Closing QGC releases the lock; the second connection can take over.
        qgc.close()
        self.clients.remove(qgc)
        time.sleep(0.5)
        self.assert_forwarded(
            qgc2, link2, arm2,
            lambda m: m.get_msgId() == mavlink.MAVLINK_MSG_ID_COMMAND_LONG
            and m.command == mavlink.MAV_CMD_COMPONENT_ARM_DISARM
            and m.param1 == 1)

    def test_telemetry_keeps_route_alive_without_heartbeat(self):
        qgc, link = self.connect_qgc()
        stream = MavStream(qgc)

        heartbeat = self.uav_link.heartbeat_encode(
            mavlink.MAV_TYPE_QUADROTOR,
            mavlink.MAV_AUTOPILOT_PX4,
            0,
            0,
            mavlink.MAV_STATE_ACTIVE,
        )
        self.uav.sendto(heartbeat.pack(self.uav_link), ("127.0.0.1", UDP_PORT))
        self.assertIsNotNone(stream.read(
            lambda m: m.get_msgId() == mavlink.MAVLINK_MSG_ID_HEARTBEAT
            and m.get_srcSystem() == 1))

        # Stop heartbeat and keep only attitude telemetry for longer than the
        # 3 s heartbeat timeout. A live telemetry stream must keep the route
        # valid so QGC joystick control is not dropped.
        self.stop.set()
        self.feeder.join(timeout=1)

        for i in range(9):
            attitude = self.uav_link.attitude_encode(
                1000 + i, 0.1, 0.2, 0.3, 0, 0, 0)
            self.uav.sendto(
                attitude.pack(self.uav_link), ("127.0.0.1", UDP_PORT))
            time.sleep(0.5)

        manual = link.manual_control_encode(1, 123, 0, 0, 0, 0)
        self.assert_forwarded(
            qgc, link, manual,
            lambda m: m.get_msgId() == mavlink.MAVLINK_MSG_ID_MANUAL_CONTROL
            and m.target == 1 and m.x == 123)


if __name__ == "__main__":
    unittest.main()
