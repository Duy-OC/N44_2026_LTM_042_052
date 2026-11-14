#!/bin/bash
# ==============================================================================
# Script ho tro cau hinh PX4 SITL tren WSL2 truyen UDP sang Windows Host
# ==============================================================================

# 1. Tu dong tim IP Windows Host tu WSL2
HOST_IP=$(ip route | grep default | awk '{print $3}')
PORT=14550

echo "=========================================================="
echo "  PX4 SITL -> Windows Gateway UDP Setup"
echo "  Windows Host IP phat hien: $HOST_IP"
echo "  Target Port: $PORT"
echo "=========================================================="

echo ""
echo "Cach 1: Neu chay PX4 SITL bang lenh make:"
echo "export PX4_SIM_HOST_ADDR=$HOST_IP"
echo "make px4_sitl default none_iris"
echo ""
echo "Cach 2: Neu dung WSL2 Mirrored Networking (.wslconfig):"
echo "Windows Host va WSL2 dung chung localhost (127.0.0.1)."
echo "Chay SITL binh thuong se tu dong den 127.0.0.1:14550."
echo ""
echo "Cach 3: Dung mavproxy forward:"
echo "mavproxy.py --master=udp:127.0.0.1:14540 --out=udp:$HOST_IP:$PORT"
echo "=========================================================="
