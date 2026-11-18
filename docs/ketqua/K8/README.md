# K8 — Timeout và phục hồi khi gián đoạn đường truyền thật

Đã hoàn tất 3 lượt × 120 giây, cả 3 lượt PASS, có OFFLINE và ONLINE phục hồi.

| Lượt | Timeout từ frame cuối (s) | Phục hồi từ yêu cầu restart (s) | Frame | CRC |
|---|---:|---:|---:|---:|
| 1 | 3,1293 | 1,0547 | 6248 | 0 |
| 2 | 3,3801 | 1,0439 | 6247 | 0 |
| 3 | 3,3351 | 1,1507 | 6242 | 0 |
| Trung bình | 3,2815 | 1,0831 | 6245,6667 | 0 |

Độ lệch chuẩn mẫu: timeout 0,1337 giây, phục hồi 0,0588 giây.
Số tổng hợp lưu tại [summary.csv](summary.csv); dữ liệu gốc ở từng thư mục lượt.

Nguồn: PX4 SITL/Gazebo thật, UDP 14600 → Windows 14550.
Trước khi đo: probe 10 giây nhận 546 frame, 9 HEARTBEAT, 136 ATTITUDE
từ 172.26.162.42:14600, lưu tại `../probe_k8_px4.csv`.

Chạy `python scripts/run_k8_live.py` từ gốc dự án.
Mỗi lượt có 120 giây đo, sau warmup 5 giây; lặp 3 lượt hoàn tất.

Tuyến đo: PX4 → proxy C++ UDP 14550 → gateway UDP 14551 (nguồn 14610).
Proxy chạy không loss/delay/flip. Khi log đo đạt ít nhất 30 giây,
bộ điều phối dừng tiến trình proxy trong 6 giây, sau đó khởi động lại.
PX4/Gazebo tiếp tục chạy suốt phép đo. Không tạo telemetry/ACK giả.

Đây là phép đo gián đoạn đường truyền bằng dừng/khởi động proxy.
Phương pháp khác K8 lần 1 dùng SIGSTOP/SIGCONT PX4; không so sánh
trực tiếp hai độ trễ từ lúc phát lệnh ngắt nếu chưa xét khác biệt này.

Đo timeout từ frame thật cuối cùng tại gateway đến khi quan sát dòng
`UAV 1 OFFLINE (Timeout)` trong log. Đo phục hồi từ lúc yêu cầu khởi động
proxy đến dòng `UAV 1 ONLINE` mới. Các mốc quan sát bao gồm độ trễ ghi log
và vòng kiểm tra 50 ms, không phải thời điểm nội bộ chính xác của gateway.

Mỗi lượt lưu `config.json`, `events.csv`, `gateway.log`, `proxy.log`,
CSV QoS/trace gốc, `run.log` và `result.csv` khi đủ 120 giây.
PASS xác nhận thu đủ cửa sổ đo, phát hiện OFFLINE và nhận lại ONLINE;
không xác nhận hoàn tất hành động bay hoặc mọi chức năng điều khiển.
