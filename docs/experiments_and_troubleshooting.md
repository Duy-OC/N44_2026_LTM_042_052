# Kết quả đo, Định dạng Log & Xử lý sự cố

## 1. Kết quả đo

Giá trị có dấu **±** biểu diễn trung bình và độ lệch chuẩn mẫu giữa các lượt. Đợt đo telemetry dùng một UAV PX4 SITL với `sysid=1`. Đo lệnh ARM dùng UAV giả trả ACK. Xem bảng tổng hợp đầy đủ tại [tong_hop_qos_gateway.csv](tong_hop_qos_gateway.csv).

| Phép thử | Kết quả ghi nhận | Dữ liệu |
|---|---|---|
| Kiểm định bộ sinh lỗi với mục tiêu mất 5%, cụm trung bình 4 gói | Mất **4,850 ± 0,279%**, cụm trung bình **3,947 ± 0,090 gói**. | `K0` |
| Truyền trực tiếp qua gateway | **51,367 ± 0,055 khung/s**, không ghi nhận khoảng thiếu `seq` hoặc lỗi CRC. | `K1` |
| Cùng mức mất mục tiêu 5%, khác độ dài cụm | Cụm thiếu trung bình tại gateway lần lượt **4,555** và **1,000 khung**. | `K2` (cụm dài), `K3` (cụm đơn) |
| Tuyến qua proxy có chèn trễ | Jitter `ATTITUDE` **13,242 ± 1,319 ms**, so với **1,801 ± 0,154 ms** trên tuyến trực tiếp. | `K5` |
| Gửi lệnh ARM với UAV giả | Tỷ lệ yêu cầu nhận ACK chấp nhận **100%, 96%, 100%** tại các mức mất mục tiêu **0%, 5%, 10%**. Số lần gửi lại trung bình tương ứng **0**, **0,080** và **0,160 lần/yêu cầu**. | `K6` (`L0`, `L5`, `L10`) |
| Lật bit payload | Proxy gửi **65** và **51** khung đã sửa. Gateway ghi **64** và **51** lỗi CRC. | `K7` |
| Tạm dừng PX4 | Gateway báo `OFFLINE` sau **3,163 s**, tính từ lúc tạm dừng. | `K8` |

**Cách đọc số liệu.** Gateway ước lượng khung thiếu từ `seq`; proxy đếm các khung thực sự bị thả. K2 có hai cửa sổ ghi riêng, còn K3 và K4 có dữ liệu đối chiếu trên phần cửa sổ giao nhau trong `common.csv`. Jitter là độ lệch chuẩn mẫu của các khoảng đến `ATTITUDE` được giữ lại. So sánh jitter giữa tuyến trực tiếp và tuyến có proxy phản ánh cả hiệu ứng của proxy lẫn thao tác chèn trễ. Phép thử ARM đánh giá ACK và retry ở gateway. Phép probe sau khi tiếp tục PX4 kiểm tra telemetry đến máy Windows.

## 2. Định dạng log

| Tệp hoặc nhóm tệp | Nội dung |
|---|---|
| `*_gateway_ingress.csv` | Thống kê luồng tại gateway. Các trường gồm `t_s`, `frames_per_s`, `seq_gap_estimate`, `crc_errors` và các chỉ số `attitude_*`. |
| `*_gateway_ingress_bursts.csv` | Độ dài khoảng nhảy `seq` tại thời điểm phát hiện, ghi trong `gap_packets`. |
| `*_gateway_ingress_loss_seconds.csv` | Khoảng nhảy cộng gộp theo giây, dùng để xem diễn biến trong lượt. |
| `*_decision_trace.csv` của proxy | Quyết định giữ hoặc thả theo khung. Có thể đối chiếu theo `sysid`, `compid`, `seq` và `msgid`. |
| `result.csv` và `summary.csv` | Chỉ số từng lượt và bản tổng hợp của kịch bản. |
| `commands.csv` trong thử nghiệm ARM | Kết quả từng yêu cầu lệnh với UAV giả. |

`attitude_jitter_std_ms` là độ lệch chuẩn mẫu của khoảng đến. `attitude_jitter_max_ms` là độ lệch tuyệt đối lớn nhất so với khoảng đến trung bình. `attitude_skipped_loss` đếm các khoảng bị bỏ qua do phát hiện khoảng nhảy `seq`.

## 3. Hạn chế đã biết

- Đợt đo telemetry dùng một UAV PX4 SITL trên cùng một máy Windows/WSL2. Mã quản lý route theo nhiều `sysid`. Kết quả phản ánh cấu hình một UAV đã đo.
- Trường `seq` 8 bit và dữ liệu đến sai thứ tự giới hạn phép ước lượng thiếu khung. Khung đến muộn có thể bù một khoảng thiếu đã ghi nếu còn trong cửa sổ theo dõi.
- Mốc jitter trực tiếp và bài chèn trễ dùng hai tuyến khác nhau. Chênh lệch quan sát bao gồm việc thêm proxy và thao tác chèn trễ.
- Phép thử ARM dùng UAV giả để đánh giá ACK/retry. Việc xác nhận thao tác bay cần telemetry hoặc trạng thái mô phỏng của bài thử tương ứng.

## 4. Xử lý sự cố

| Hiện tượng | Kiểm tra |
|---|---|
| Bind lỗi `10048` | Kiểm tra tiến trình đang giữ UDP `14550`, `14551` hoặc TCP `5760` bằng `Get-NetUDPEndpoint` hoặc `Get-NetTCPConnection`. Dừng tiến trình trùng cổng hoặc dùng cấu hình cổng phù hợp. |
| Gateway không thấy UAV `ONLINE` | Kiểm tra IP Windows, endpoint đích trong `mavlink status`, tuyến đang chọn và Windows Firewall. Nếu dùng proxy, đối chiếu cả ba cổng và `--sysid`. |
| QGroundControl không có telemetry | Kiểm tra kết nối TCP `127.0.0.1:5760` và xác nhận gateway đã học được route của UAV. |
| `ERR LOCKED` hoặc `ERR NOT_OWNER` | Kiểm tra phiên đang giữ quyền. Trả quyền hoặc đóng phiên cũ rồi xin lại bằng `ACQUIRE`. |
| CRC tăng trong bài lật bit | Đối chiếu số khung đã sửa và gửi tại proxy với bộ đếm CRC của gateway trong cửa sổ tương ứng. |
| Script đo báo xung đột cổng | Dừng gateway và proxy chạy tay. Chạy từng kịch bản tuần tự. |
