# Giao thức, Cấu hình PX4 & Tham số CLI

Tài liệu chi tiết về cấu hình mạng PX4 SITL, giao thức `client ↔ gateway`, các script hỗ trợ và tham số dòng lệnh.

## 1. Cấu hình PX4 SITL và mạng WSL2

Trong WSL2, khởi động mô phỏng:

```bash
cd ~/PX4-Autopilot
make px4_sitl gz_x500
```

Với cấu hình WSL2 NAT, chạy `ip route show default` trong một terminal WSL khác và lấy địa chỉ sau `via` làm IP Windows.

Trong shell `pxh>`, chạy `mavlink status` để xem các instance đang phát. Nếu chưa có instance dùng cổng local `14600`, khởi động nó sau khi thay `172.26.160.1` bằng IP Windows:

```text
mavlink start -u 14600 -o 14550 -t 172.26.160.1 -r 100000
mavlink status
```

| Tham số | Ý nghĩa |
|---|---|
| `-u 14600` | Cổng UDP nguồn của phiên MAVLink PX4. |
| `-o 14550` | Cổng đích của gateway hoặc proxy trên Windows. |
| `-t <IP Windows>` | Địa chỉ Windows mà WSL2 sử dụng để gửi UDP. |
| `-r 100000` | Giới hạn cấu hình, tính bằng byte/giây. |

Nếu phiên MAVLink đã chạy, kiểm tra đích và cổng bằng `mavlink status` trước khi thay đổi. Giữ chế độ stream và giới hạn tốc độ nhất quán giữa các lượt cần so sánh.

## 2. Giao thức client ↔ gateway

Gateway phục vụ MAVLink nhị phân và giao thức văn bản trên cùng cổng TCP `5760`. Khung hợp lệ từ UAV được phân phối đến các client nhị phân. Client văn bản nhận dữ liệu `DETAIL` dạng JSON và phản hồi theo từng dòng kết thúc bằng `\n`. `DETAIL` tổng hợp từ `HEARTBEAT`, `SYS_STATUS`, `GPS_RAW_INT`, `ATTITUDE`, `GLOBAL_POSITION_INT` và `VFR_HUD`.

| Lệnh văn bản | Hành vi |
|---|---|
| `GET_DETAIL [sysid]` | Trả trạng thái UAV đang online. Khi không có đối tượng phù hợp, trả `DETAIL NONE`. |
| `SUBSCRIBE <hz>` / `UNSUBSCRIBE` | Bật hoặc tắt nhận `DETAIL` định kỳ. Tần số hợp lệ từ 1 đến 5 Hz. |
| `ACQUIRE` / `RELEASE` | Xin hoặc trả khóa điều khiển dùng chung. Khóa được giải phóng khi phiên giữ quyền ngắt kết nối. |
| `COMMAND <sysid> <ARM\|DISARM\|TAKEOFF\|LAND> [altitude_m]` | Gửi lệnh tới UAV đích khi phiên có quyền và UAV online. `TAKEOFF` nhận độ cao từ 1 đến 100 m, mặc định 10 m. |

`OK COMMAND_PENDING <sysid> <command>` báo yêu cầu đang chờ xử lý. Gateway trả `RESULT <sysid> <command> <result>` khi nhận ACK kết thúc, hoặc `RESULT <sysid> TIMEOUT` / `RESULT <sysid> OFFLINE` trong các trường hợp tương ứng. Đường lệnh văn bản chờ khoảng 1 giây trước khi xét gửi lại và giới hạn 3 lần gửi tổng cộng. ACK chấp nhận xác nhận phản hồi ở mức giao thức; trạng thái thực hiện thao tác bay cần kiểm tra qua telemetry hoặc Gazebo.

QGroundControl dùng đường MAVLink nhị phân. Một số lệnh điều khiển hợp lệ có thể tự lấy khóa khi khóa đang rảnh. Gateway áp dụng danh sách bản tin được phép, kiểm tra UAV đích và dùng chung khóa với client văn bản.

Lỗi thường gặp: `ERR LOCKED` (khóa thuộc phiên khác), `ERR NOT_OWNER` (chưa giữ khóa), `ERR UAV_OFFLINE` (UAV mất liên lạc), `ERR COMMAND_BUSY` (UAV đang có lệnh chờ).

## 3. Tham số cấu hình & CLI

| Tham số | Giá trị hoặc cách dùng |
|---|---|
| Cổng UDP gateway | Mặc định `14550`, đổi bằng `--udp-port`. |
| Cổng TCP gateway | `5760`. |
| Timeout UAV | `3 s` kể từ khung hợp lệ gần nhất của nguồn đã học. |
| Giới hạn TCP | Tối đa 10 client, hàng đợi 256 KiB mỗi client. Gateway ngắt phiên nếu việc thêm khung/phản hồi vượt giới hạn. |
| Hàng đợi UDP | Tối đa 512 khung. |
| Đo tại gateway | `--measure-seconds <1..3600>` bật chế độ đo (mặc định `60` khi dùng). Dùng `--scenario` (mặc định `DEFAULT`), `--run-id` và `--output-dir` (mặc định `docs/ketqua`) để đặt nhãn và nơi ghi kết quả. |
| `tcpclient.exe` | `[host]` `[port]` tùy chọn, mặc định `127.0.0.1` `5760`. |
| `control_client.py` | `[host]` `[port]` mặc định `127.0.0.1` `5760`, hỗ trợ `--log-file <PATH>`. |
| Cổng & định danh proxy | `--listen-port` (mặc định `14551`), `--gateway-port` (mặc định `14550`) và `--gateway-source-port` (mặc định `14610`); ba cổng phải khác nhau và nên ghi rõ khi chạy tuyến đo chuẩn (`14550`/`14551`/`14610`). `--sysid` chọn UAV đích (`1..255`, mặc định `1`). |
| Markov tại proxy | Chiều thuận: `--urb` (tỷ phần trạng thái xấu), `--burst-packets` (bật chế độ đếm theo gói), `--dur-s`, `--slot-ms`, `--lossgood`, `--lossbad`, `--seed`. Chiều ngược kế thừa chiều thuận (với `seed ^ 0x9e3779b9`) và có thể ghi đè bằng `--reverse-urb`, `--reverse-burst-packets`, `--reverse-dur-s`, `--reverse-slot-ms`, `--reverse-lossgood`, `--reverse-lossbad`, `--reverse-seed`. |
| Lỗi & đo tại proxy | `--delay-bad-min-ms` và `--delay-bad-max-ms` (`0..10000` ms), `--flip-probability` (`0..1`). `--measure-seconds <1..3600>` bật ghi CSV theo `--scenario` (mặc định `UPSTREAM`), `--run-id` và `--output-dir`. |
| Tái lập lượt đo | Lưu seed cùng cấu hình và cửa sổ đo. Seed giúp tái lập quyết định với cùng đầu vào và thứ tự xử lý. |

## 4. Tổng quan `scripts/`

| Nhóm | Tệp | Mục đích |
|---|---|---|
| Điều khiển & giả lập | `control_client.py`, `simulate_px4.py`, `probe_px4.py`, `setup_px4_env.sh` | Client văn bản (`--log-file`), phát telemetry giả (`pymavlink`), probe luồng PX4, gợi ý IP WSL2. |
| Chạy đo & kiểm chứng | `run_k_live.py`, `run_k6.py`, `run_case.py`, `measure_timeout_px4.py`, `check_gateway_functions.py` | Chạy các kịch bản đo K1–K8, đo ACK/retry K6, kiểm tra khóa/multi-client. |
| Tổng hợp & biểu đồ | `analyze_markov_run.py`, `compare_markov_common.py`, `summarize_k0.py`, `summarize_manual.py`, `plot_k_results.py`, `plot_project_results.py` | Phân tích trace proxy/gateway, tổng hợp CSV và vẽ biểu đồ (`matplotlib`). |
| Kiểm thử C++ | `run_test_stage1.bat`, `run_test_stage2.bat` | Biên dịch và chạy kiểm thử framing/CRC (Stage 1) và giải mã telemetry (Stage 2). |
