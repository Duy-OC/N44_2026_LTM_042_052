# Kết quả đo lần 2

## Trạng thái

Kết thúc K8 lúc 13:19 ngày 18/11/2026: K1–K5, K7, K8 đã đủ 3 lượt × 120 giây;
K6 đã đủ 3 lượt × 120 giây cho mỗi mức loss 0%, 5%, 10%.
Bộ đo K1–K7 hoàn tất lúc 13:05:37; K8 đã hoàn tất sau đó.
Hiện không còn tiến trình đo chạy.
K8 ngắt đường truyền thật bằng dừng proxy C++ 6 giây rồi khởi động lại.
Cả 3 lượt đều phát hiện OFFLINE và phục hồi ONLINE; timeout quan sát từ
frame cuối trung bình 3,2815 giây, phục hồi sau yêu cầu khởi động proxy
trung bình 1,0831 giây, CRC 0. PX4/Gazebo vẫn chạy;
xem [phương pháp và kết quả K8](K8/README.md).
Các ghi chú tạm dừng bên dưới mô tả mốc trước khi tiếp tục, không phải trạng thái hiện tại.

Đã xác minh nguồn PX4 SITL/Gazebo ngày 18/11/2026, xem
[bằng chứng nguồn](nguon_mo_phong.md). Probe sau cấu hình nhận 561 frame
trong 10 giây từ `172.26.162.42:14600`, gồm 9 HEARTBEAT và 139 ATTITUDE.
K1 baseline đã hoàn tất 3 lượt × 120 giây: trung bình 55,936 frame/s,
loss 0%, CRC 0, jitter ATTITUDE trung bình 2,1713 ms.
Đã dừng theo yêu cầu người vận hành sau khi K3 hoàn tất lúc 11:32 ngày
18/11/2026. K1, K2, K3 đều đủ 3 lượt × 120 giây.
K4 vừa tự khởi động khi dừng bộ chạy; lượt `20261118_113223_r1` đã bị
ngắt, đánh dấu INTERRUPTED và không tính vào kết quả. Chưa đo xong K4–K8.
Tiếp tục bằng `python scripts/run_round2_live.py` sẽ bỏ qua K1–K3,
đo lại K4 từ lượt 1 rồi tiếp tục K5, K7, K6. K8 cần phiên thao tác riêng.
Chỉ các lượt hoàn tất có
`result.csv` và `status=PASS` trong `run.log` mới được dùng để tổng hợp.

Probe trước cấu hình nhận 0 frame. Đây là kiểm tra kết nối, không phải
kết quả baseline và không được đưa vào bảng QoS.

## Yêu cầu dữ liệu

- Tất cả kịch bản: **3 lượt hợp lệ × 120 giây đo/lượt**, không tính warmup. K6 áp dụng riêng cho từng mức loss 0%, 5%, 10%. Lượt bị ngắt không tính vào ba lượt.
- Nguồn telemetry và COMMAND_ACK phải từ PX4 SITL chạy cùng Gazebo thật.
- Không dùng `simulate_px4.py`, FakeUAV trong `run_k6.py`, hay dữ liệu tổng hợp thay cho PX4.
- Không sao chép kết quả lần 1 sang đây. Không điền số dự kiến thành số đo.
- Script thu thập/phân tích được phép đọc dữ liệu thật; proxy C++ chỉ gây lỗi trên luồng PX4 thật.
- Lưu log gốc, lệnh chạy, thời gian, seed, cấu hình PX4/Gazebo và địa chỉ nguồn cho từng lượt.
- HEARTBEAT đơn lẻ chưa chứng minh nguồn là PX4 thật; cần đối chiếu tiến trình mô phỏng, `ver all` và `mavlink status`.

## Chuẩn bị PX4

Trong WSL:

```bash
cd ~/PX4-Autopilot
make px4_sitl gz_x500
```

Trong terminal WSL khác, lấy IP Windows với mạng WSL2 NAT:

```bash
ip route show default
```

Lấy IP sau `via`. Trong shell `pxh>`:

```text
ver all
mavlink status
```

Nếu chưa có instance local UDP 14600, thay `<IP_WINDOWS>` bằng IP vừa lấy:

```text
mavlink start -u 14600 -o 14550 -t <IP_WINDOWS> -r 100000
mavlink status
```

Nếu instance 14600 đã tồn tại, kiểm tra đích trước khi chỉnh; không khởi động trùng.
Lưu đầu ra `ver all`, `mavlink status` và phiên bản Gazebo vào thư mục này.

## Đo khi đã xác nhận nguồn thật

Từ PowerShell tại gốc dự án, kiểm tra nguồn trước (không chạy cùng gateway đang giữ cổng 14550):

```powershell
python scripts/probe_px4.py 14550 10 docs/ketqua_lan2/probe_px4.csv
```

Sau khi xác minh PX4/Gazebo và luồng nhận hợp lệ, chạy lần lượt:

```powershell
python scripts/run_k_live.py K1 --repeats 3 --seconds 120 --output-root docs/ketqua_lan2
python scripts/run_k_live.py K2 --repeats 3 --seconds 120 --output-root docs/ketqua_lan2
python scripts/run_k_live.py K3 --repeats 3 --seconds 120 --output-root docs/ketqua_lan2
python scripts/run_k_live.py K4 --repeats 3 --seconds 120 --output-root docs/ketqua_lan2
python scripts/run_k_live.py K5 --repeats 3 --seconds 120 --output-root docs/ketqua_lan2
python scripts/run_k_live.py K7 --repeats 3 --seconds 120 --output-root docs/ketqua_lan2
```

Hoặc tiếp tục toàn bộ các kịch bản tự động, tự bỏ qua các lượt 120 giây đã PASS:

```powershell
python scripts/run_round2_live.py
```

Không chạy đồng thời các lệnh đo vì dùng chung cổng UDP/TCP.

`run_k_live.py` khởi động gateway/proxy và đọc log, không tạo UAV giả.
K1 dùng tuyến trực tiếp; K2–K5/K7 dùng proxy, giữ nguyên đích PX4 UDP 14550.
K6 dùng `scripts/run_k6_live.py`, 3 lượt × 120 giây cho mỗi mức loss,
50 lệnh DISARM/lượt đến PX4 thật đang disarm. Lưu `commands.csv`, trace proxy
và tỷ lệ ACK riêng với tỷ lệ ACCEPTED. Đây là đo độ tin cậy giao thức;
không chứng minh hoàn tất chuỗi bay. Không chạy `run_k6.py` (UAV giả).
K0 dùng gói tổng hợp nên không đưa vào bộ kết quả PX4 thật này.
K8 dùng `python scripts/run_k8_live.py`, 3 lượt × 120 giây,
tự dừng/khởi động lại proxy C++ để ngắt/khôi phục đường truyền PX4 thật.
Không dùng script K8 cũ cửa sổ 10 giây.
Kiểm chứng chuỗi bay cần phiên thao tác riêng với log từ mô phỏng.
