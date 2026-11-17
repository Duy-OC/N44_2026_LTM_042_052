# Hướng dẫn kiểm thử (`tests/`)

## 1. Điều kiện trước khi chạy

- **Windows & MinGW `g++` (C++17):** chạy `.\build.bat` tại thư mục gốc để biên dịch `bin\gateway.exe`, `bin\tcpclient.exe` và `bin\upstream_markov_proxy.exe`.
- **Python 3 & `pymavlink`:** tất cả các bài kiểm thử `tests\test_*.py` đều dùng `pymavlink` và gọi các tệp `.exe` trong `bin\`.
- **Cổng mạng trống:** các bài kiểm thử tích hợp dùng cổng cục bộ (gồm `14550`, `5760` hoặc cổng test riêng); dừng `gateway.exe` / `upstream_markov_proxy.exe` đang chạy tay trước khi chạy test.

---

## 2. Kiểm thử C++

### Stage 1 & Stage 2 (có script chạy sẵn)

```powershell
.\scripts\run_test_stage1.bat
.\scripts\run_test_stage2.bat
```

- `test_stage1_framing.cpp`: kiểm thử T1.1–T1.5 (parse MAVLink v1/v2, kiểm tra CRC, đồng bộ lại khi nhiễu), xuất CSV/log vào `docs\ketqua\`.
- `test_stage2_telemetry.cpp`: kiểm thử T2.1–T2.6 (giải mã telemetry trong `uav_manager.h`), xuất `docs\ketqua\stage2_telemetry_results.csv`.

### Kiểm thử theo dõi `seq` và bộ sinh lỗi Markov K0

Biên dịch và chạy thủ công với chuẩn C++17:

```powershell
g++ -std=c++17 -O2 -Isrc/common -Ithird_party -o bin\test_sequence_cases.exe tests\test_sequence_cases.cpp
.\bin\test_sequence_cases.exe docs\ketqua\sequence_cases.csv

g++ -std=c++17 -O2 -Isrc/common -Ithird_party -o bin\markov_k0.exe tests\markov_k0.cpp
.\bin\markov_k0.exe docs\ketqua\k0_runs.csv
```

- `test_sequence_cases.cpp`: kiểm thử `SequenceTracker` (liên tiếp, mất 1/nhiều gói, quay vòng `255 -> 0`, đảo thứ tự đến muộn, trùng lặp, nhảy quá cửa sổ).
- `markov_k0.cpp`: chạy 100.000 gói tổng hợp cho mỗi cấu hình K0 trên `Markov::Channel` (`src\common\emulator.h`) để kiểm định tỉ lệ mất và độ dài cụm.

### Stage 0 — Nghe UDP thô (`T0.2`)

`build.bat` không tự động biên dịch `t0_2_udp_listener.cpp`. Nếu cần kiểm tra nhanh UDP từ PX4 hoặc `scripts/simulate_px4.py`:

```powershell
g++ -std=c++17 -O2 -Isrc/common -Ithird_party -o bin\t0_2_udp_listener.exe tests\t0_2_udp_listener.cpp -lws2_32
.\bin\t0_2_udp_listener.exe 14550
python scripts\simulate_px4.py 127.0.0.1 14550 50
```

Đạt khi `t0_2_udp_listener.exe` in liên tục số byte, số datagram mỗi giây và nhận diện header MAVLink v1/v2 hợp lệ.

---

## 3. Kiểm thử tích hợp Python (`unittest`)

Chạy toàn bộ từ thư mục gốc sau khi đã chạy `build.bat`:

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

| Tệp | Nội dung kiểm thử |
|---|---|
| `test_control_protocol.py` | Giao thức văn bản TCP (`GET_DETAIL`, `SUBSCRIBE`, `ACQUIRE`/`RELEASE`, `COMMAND`, timeout/offline). |
| `test_qgc_control.py` | Luồng lệnh nhị phân kiểu QGroundControl, whitelist bản tin và khóa dùng chung với client văn bản. |
| `test_measurement_modes.py` | Chế độ đo `K2`, `K5`, `K7` giữa `gateway.exe` và `upstream_markov_proxy.exe`. |
| `test_reverse_markov.py` | Kênh Markov chiều ngược (`--reverse-*`) khi gửi lệnh qua proxy. |
| `test_live_runner.py` | Smoke test `scripts/run_k_live.py` với luồng MAVLink giả lập. |

---

## 4. Công cụ phụ trợ khác

- `udp_joystick_bridge.py`: cầu nối UDP (`0.0.0.0:14560`) sang TCP (`127.0.0.1:5760`) để thử chuyển tiếp gói điều khiển thủ công.
