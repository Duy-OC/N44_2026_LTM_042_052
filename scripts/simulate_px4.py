#!/usr/bin/env python3
"""
Simulate PX4 sending MAVLink UDP packets to Windows Gateway (port 14550 or specified).
Usage: python scripts/simulate_px4.py [target_ip] [target_port] [frequency_hz]
Default: 127.0.0.1 14550 50
"""
import socket
import time
import sys

target_ip = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
target_port = int(sys.argv[2]) if len(sys.argv) > 2 else 14550
freq_hz = float(sys.argv[3]) if len(sys.argv) > 3 else 50.0

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Simple MAVLink v2 dummy frame (STX=0xFD, len=9, incompat=0, compat=0, seq, sysid=1, compid=1, msgid=0 HEARTBEAT)
seq = 0
print(f"[Simulate PX4] Gui luong goi UDP den {target_ip}:{target_port} o tan so {freq_hz} Hz...")
print("Nhan Ctrl+C de dung.")

interval = 1.0 / freq_hz
sent = 0

try:
    while True:
        # Construct simple MAVLink v2 heartbeat frame
        # Header: FD 09 00 00 <seq> 01 01 00 00 00
        # Payload (9 bytes): custom_mode(4), type(1), autopilot(1), base_mode(1), sys_status(1), mavlink_version(1)
        # Checksum (2 bytes)
        payload = b'\x00\x00\x00\x00\x02\x0c\x59\x04\x03'
        header = bytes([0xFD, len(payload), 0, 0, seq & 0xFF, 1, 1, 0, 0, 0])
        # Simple dummy checksum for testing UDP throughput
        chk = b'\x12\x34'
        pkt = header + payload + chk

        sock.sendto(pkt, (target_ip, target_port))
        sent += 1
        seq = (seq + 1) % 256

        if sent % int(freq_hz) == 0:
            print(f"[PX4 SITL Dummy] Da gui {sent} goi tin...")

        time.sleep(interval)
except KeyboardInterrupt:
    print(f"\n[PX4 SITL Dummy] Da dung. Tong so goi da gui: {sent}")
