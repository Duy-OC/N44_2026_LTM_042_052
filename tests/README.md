# Huong dan kiem thu Giai doan 0

## T0.1: Build tu thu muc sach
1. Chay lenh build:
   ```cmd
   build.bat
   ```
2. **Dat khi:** Tat ca module (`gateway.exe`, `tcpclient.exe`, `upstream_markov_proxy.exe`, `t0_2_udp_listener.exe`) duoc bien dich thanh cong khong co loi.

---

## T0.2: Chuong trinh nghe UDP in so byte nhan tu PX4
1. Chay chuong trinh lang nghe UDP:
   ```cmd
   t0_2_udp_listener.exe 14550
   ```
2. Chay PX4 SITL (hoac script gia lap PX4 de kiem tra nhanh):
   ```cmd
   python scripts/simulate_px4.py 127.0.0.1 14550 50
   ```
3. **Dat khi:**
   - Chuong trinh `t0_2_udp_listener.exe` in lien tuc so byte va so datagram nhan duoc moi giay.
   - Phat hien header MAVLink v1/v2 hop le.
