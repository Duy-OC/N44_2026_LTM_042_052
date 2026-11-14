# Danh sách đầy đủ cho báo cáo: cần đo gì, thử nghiệm gì, trình bày thế nào

**Đề tài:** MAVLink Gateway cho 1 UAV PX4 (SITL, Gazebo, WSL2), server Winsock trên Windows.

**Phạm vi:** chỉ đo những thứ đưa được vào bảng hoặc biểu đồ của báo cáo. `pymavlink` dùng làm công cụ đối chiếu.

---

## 1. Môi trường thí nghiệm (ghi một lần)

| Nhóm | Cần ghi |
|---|---|
| Phần cứng | CPU, RAM, ổ đĩa |
| Hệ điều hành | Phiên bản Windows, phiên bản WSL2, chế độ mạng (NAT/mirrored), IP host `172.26.160.1` |
| Mô phỏng | Phiên bản PX4, Gazebo, model bay, headless hay có GUI |
| Cấu hình PX4 | `mavlink start -u 14600 -o 14550 -t 172.26.160.1 -r 100000`, chế độ stream |
| Công cụ | MinGW g++ (phiên bản, cờ `-O2 -std=c++17`), `pymavlink` (phiên bản), Wireshark nếu dùng |
| Tham số hệ thống | Cổng proxy (14550), cổng gateway (14551), timeout UAV (3 s), tần số đẩy cho client, kích thước hàng đợi mỗi client |
| Lưu ý | Gateway, PX4, Gazebo và proxy chạy chung một máy, nên có jitter nền |

> Tham số `-r` và chế độ stream của PX4 phải **giữ nguyên cho mọi kịch bản**, nếu không số pps và jitter giữa các kịch bản không so sánh được.

---

## 2. Các đại lượng cần đo

| # | Đại lượng | Đơn vị | Cách đo | Đối chiếu với |
|---|---|---|---|---|
| 1 | Tỉ lệ mất gói | % | Từ `seq`: `lost / (rx + lost)` | Log thả gói của proxy |
| 2 | Số cụm mất, độ dài cụm trung bình và lớn nhất | gói | Mỗi lần `seq` nhảy cóc là một cụm | `1/r` và log cụm của proxy |
| 3 | Jitter (độ lệch chuẩn, max) | ms | Khoảng cách giữa các gói ATTITUDE liên tiếp (bỏ khoảng có mất gói), đo bằng `QueryPerformanceCounter` | Tham số delay đặt ở proxy |
| 4 | pps trung bình | gói/s | Đếm gói hợp lệ mỗi giây | Tần số PX4 phát, `pymavlink` |
| 5 | Số gói sai CRC | gói | Bộ đếm `crc_err` | Số gói lật bit ở proxy |
| 6 | Tỉ lệ lệnh thành công | % | Số lệnh nhận ACK / tổng lệnh | Mức loss đặt |
| 7 | Số retry trung bình mỗi lệnh | lần | Tổng lần gửi lại / tổng lệnh | Mức loss đặt |
| 8 | Thời gian phát hiện mất liên lạc | s | Từ lúc tắt PX4 đến lúc gateway báo timeout | Ngưỡng 3 s |
| 9 | Kết quả đạt/không đạt của các chức năng | đạt/không | Test tay và test script | Yêu cầu của đề |

**Đại lượng của proxy (để kiểm định):** tỉ lệ thả thực tế, độ dài cụm thực tế, tái lập theo seed.

**Công thức đối chiếu:**

```
Sai số tương đối = |giá trị đo − giá trị đúng| / giá trị đúng
Tỉ lệ mất        = lost / (rx + lost)
Cụm trung bình   = tổng gói mất / số cụm
```

**Lưu ý khi có lật bit:** gói bị lật bit không qua được CRC nên gateway vừa đếm vào `sai CRC`, vừa thấy "mất" ở `seq`. Khi đó `loss gateway ≈ gói thả + gói sai CRC`, phải trừ ra khi đối chiếu.

---

## 3. Kịch bản thử nghiệm

Mỗi kịch bản chạy khoảng 5 phút (đủ vài chục nghìn gói), lặp 3 lần, báo cáo trung bình và độ lệch chuẩn giữa các lần.

Công thức chọn tham số khi `h_G = 0`, `h_B = 1`: `r = 1 / cụm_TB`, `p = r · L / (1 − L)`, với `L` là tỉ lệ mất mong muốn.

| Mã | Kịch bản | Tham số | Đo | Mục đích |
|---|---|---|---|---|
| K0 | Kiểm định proxy (không cần PX4) | 100.000 gói tổng hợp, vài bộ `p, r` | Thả thực tế, cụm thực tế | Chứng minh nguồn tạo lỗi đúng |
| K1 | Baseline | Không can thiệp | Loss, CRC, pps, jitter nền | Mốc so sánh |
| K2 | Loss 5%, cụm 4 | `r = 0,25`, `p ≈ 0,0132` | #1, #2 vs proxy | Kiểm tra độ đo loss |
| K3 | Loss 5%, cụm 1 | `r = 1`, `p ≈ 0,0526` | #1, #2 vs proxy | Cùng loss, khác cụm: giá trị của Markov |
| K4 | Loss 10%, cụm 4 | `r = 0,25`, `p ≈ 0,0278` | #1, #2 vs proxy | Độ chính xác khi loss cao hơn |
| K5 | Delay + jitter | Trạng thái xấu thêm 20-80 ms | #3 vs tham số đặt | Kiểm tra độ đo jitter |
| K6 | Lệnh qua đường xấu | Loss 0 / 5 / 10%, 50 lệnh mỗi mức | #6, #7 | Độ tin cậy ACK/retry |
| K7 | Lật bit | 2% gói bị lật 1 bit | #5 vs log proxy | Kiểm tra CRC |

Có thể thêm loss 1% và 20% ở K2 để biểu đồ loss đặt/đo có nhiều điểm hơn (tùy chọn).

### Thử nghiệm chức năng (đạt/không đạt, không cần số liệu)

| Nhóm | Phép thử |
|---|---|
| Parse + CRC | Frame mẫu v1/v2, lật bit, frame cụt, hai frame liền, dữ liệu rác |
| Logic thống kê | Chuỗi `seq` giả: liên tục, mất 1, mất cụm 5, quay vòng 255→0, PX4 restart, trùng/đảo; jitter với timestamp giả biết trước |
| TCP đa client | Nhiều client cùng nhận; kill client; gửi TCP từng byte; lệnh dính nhau; lệnh sai định dạng; một client không đọc |
| Điều khiển | arm → takeoff → land → disarm; heartbeat GCS không gây failsafe |
| Khóa quyền | B bị từ chối khi A giữ; A ngắt thì B lấy được; hai client xin đồng thời chỉ một thắng (lặp 100 lần); client chỉ xem bị từ chối |
| Ngoại lệ | Lệnh khi UAV timeout báo lỗi; ACK đến muộn/trùng |
| Ổn định | Chạy vài phút không crash; chạy lại toàn bộ bằng script |

---

## 4. Các bảng nên có trong báo cáo

| Bảng | Nội dung | Cột chính |
|---|---|---|
| B1 | Môi trường thí nghiệm | Nhóm, thông số |
| B2 | Tham số cấu hình hệ thống | Tham số, giá trị, ý nghĩa |
| B3 | Message MAVLink được hỗ trợ | Tên, ID, `CRC_EXTRA`, dữ liệu lấy ra |
| B4 | Đặc tả giao thức client ↔ gateway | Lệnh, tham số, phản hồi, mã lỗi |
| B5 | Kiểm thử đơn vị parse/CRC | Mã, phép thử, mong đợi, thực tế, đạt/không |
| B6 | Đối chiếu gateway với `pymavlink` | Chỉ số, gateway, pymavlink, lệch % |
| B7 | Kiểm thử logic loss/jitter bằng dữ liệu giả | Kịch bản `seq`, số mất đúng, số mất tính ra |
| B8 | Kiểm định proxy Markov (K0) | `p`, `r`, thả lý thuyết/thực tế, cụm lý thuyết/thực tế |
| B9 | Baseline K1 | Lần chạy 1-3 và trung bình: pps, tần số ATTITUDE, CRC, mất, jitter std, jitter max |
| B10 | Gateway vs proxy (K1-K5) | Kịch bản, loss proxy, loss gateway, sai số %, cụm proxy, cụm gateway, jitter, CRC |
| B11 | Kiểm chứng CRC (K7) | Số gói lật, `crc_err` gateway, chênh lệch |
| B12 | Chức năng TCP và điều khiển | Phép thử, kết quả, ghi chú |
| B13 | Khóa quyền điều khiển | Tình huống, kết quả mong đợi, thực tế |
| B14 | Độ tin cậy lệnh (K6) | Mức loss, số lệnh, tỉ lệ thành công, retry TB |
| B15 | Hạn chế và nguồn sai số | Nguồn, ảnh hưởng, cách xử lý |

Mọi bảng số liệu nên có dạng **trung bình ± độ lệch chuẩn của 3 lần chạy**.

### Mẫu bảng quan trọng nhất (B10)

| Kịch bản | Loss proxy (%) | Loss gateway (%) | Sai số (%) | Cụm proxy | Cụm gateway | Jitter std (ms) | CRC lỗi |
|---|---|---|---|---|---|---|---|
| K1 | 0 | | | | | | |
| K2 | 5 | | | 4 | | | |
| K3 | 5 | | | 1 | | | |
| K4 | 10 | | | 4 | | | |
| K5 | | | | | | | |

### Mẫu bảng B14 (độ tin cậy lệnh)

| Mức loss | Số lệnh | Tỉ lệ thành công (%) | Số retry TB |
|---|---|---|---|
| 0% | 50 | | |
| 5% | 50 | | |
| 10% | 50 | | |

---

## 5. Biểu đồ và sơ đồ

### Biểu đồ số liệu

| Hình | Loại | Trục / nội dung | Dữ liệu | Thể hiện |
|---|---|---|---|---|
| H1 | Đường/điểm | X: loss đặt (proxy), Y: loss đo (gateway), kèm đường chuẩn y = x | K1-K4 (thêm 1%, 20% nếu có) | Gateway đo bám sát giá trị thật |
| H2 | Histogram cột | X: độ dài cụm mất, Y: tần suất; so K2 (cụm 4) với K3 (cụm 1), thêm đường hình học lý thuyết | Log gateway + lý thuyết | **Điểm nhấn của Markov**: cùng loss, cụm khác |
| H3 | Chuỗi thời gian | X: thời gian (s), Y: gói mất mỗi giây; K2 và K3 cạnh nhau | CSV gateway | Mất thành đợt so với rải rác |
| H4 | Cột/hộp | Jitter std của K1, K5 so với giá trị đặt | CSV | Đo jitter đúng; có jitter nền |
| H5 | Cột kết hợp | X: mức loss; cột: tỉ lệ thành công lệnh; đường: số retry | K6 | ACK/retry giữ độ tin cậy khi loss tăng |
| H6 | Đường (tùy chọn) | pps theo thời gian ở K1 | CSV | Luồng ổn định ở baseline |

### Sơ đồ minh họa (không phải số liệu)

| Hình | Nội dung |
|---|---|
| S1 | Kiến trúc: PX4 → Proxy → Gateway ↔ Client |
| S2 | Cấu trúc frame MAVLink v2 và phạm vi tính CRC |
| S3 | Sơ đồ trạng thái Gilbert-Elliott (G ↔ B với `p`, `r`) |
| S4 | Luồng dữ liệu và phân luồng trong gateway (luồng nhận UDP, luồng thống kê, hàng đợi từng client) |
| S5 | Sơ đồ tuần tự gửi lệnh có ACK, timeout, retry |
| S6 | Sơ đồ trạng thái khóa quyền điều khiển (rảnh / bị giữ / thu hồi khi ngắt) |

Vẽ biểu đồ từ file CSV bằng Excel hoặc `matplotlib`; dùng cùng một kiểu trình bày (tên trục, đơn vị, chú thích) cho cả báo cáo.

---

## 6. Cấu trúc báo cáo và nội dung mỗi chương

| Chương | Nội dung | Số liệu / hình lấy từ |
|---|---|---|
| 1. Mở đầu | Bối cảnh, mục tiêu, phạm vi (1 UAV), đóng góp | S1 |
| 2. Cơ sở lý thuyết | UDP/TCP và framing; MAVLink (frame, `seq`, message); CRC và `CRC_EXTRA`; QoS (loss, jitter, pps); mô hình Gilbert-Elliott; ACK/retry | S2, S3 |
| 3. Phân tích và thiết kế | Kiến trúc, mô hình I/O và phân luồng, đặc tả giao thức client, thiết kế khóa quyền | S1, S4, S5, S6, B3, B4 |
| 4. Cài đặt | Cấu trúc mã, các module (parse, thống kê, proxy, TCP server, engine lệnh), khó khăn gặp phải | B2 |
| 5. Thực nghiệm và đánh giá | Môi trường, phương pháp đo, kết quả K0-K7, kiểm thử chức năng, phân tích sai số | B1, B5-B15, H1-H6 |
| 6. Kết luận | Kết quả đạt được, hạn chế, hướng phát triển | |
| Phụ lục | Mã nguồn chính, script chạy kịch bản, bảng dữ liệu thô, hướng dẫn chạy lại | CSV |

### Hạn chế nên nêu trong báo cáo

- `seq` 8 bit không phát hiện được mất từ 256 gói liên tiếp trở lên.
- Gateway, PX4, Gazebo và proxy chạy chung một máy nên có jitter nền (K1 dùng để tách phần này).
- `COMMAND_ACK` với `ACCEPTED` nghĩa là lệnh được chấp nhận chứ chưa hoàn thành; cần xác nhận bằng telemetry.
- Chỉ thử với mô phỏng SITL, chưa thử trên đường truyền không dây thật.
- Mất theo cụm có phương sai lớn, nên số đo dao động quanh lý thuyết; vì vậy cần chạy đủ dài và lặp nhiều lần.

### Cách giải thích sai số

- **Hữu hạn mẫu:** chạy đủ dài và lặp 3 lần để giảm sai số.
- **Giới hạn `seq` 8 bit:** cụm quá dài bị đếm thiếu.
- **Định nghĩa cụm:** hai cụm cách nhau rất ít gói có thể bị tính khác nhau giữa gateway và proxy; dùng cùng một định nghĩa ở cả hai phía.
- **Jitter nền:** bộ lập lịch hệ điều hành và việc chạy nhiều chương trình nặng cùng lúc.
- **Tái lập:** dùng seed cố định để chạy lại cho ra kết quả giống hệt.

---

## 7. Dữ liệu cần lưu để làm báo cáo

| File | Nội dung |
|---|---|
| `logs/k{n}_run{m}.csv` | Số liệu từng giây của gateway (pps, ok, crc_err, lost, tần số ATTITUDE) |
| `logs/proxy_k{n}_run{m}.csv` | Ground truth của proxy (gói vào, gói thả, độ dài từng cụm, số gói lật) |
| `logs/cmd_k6.csv` | Từng lệnh: thời điểm, số lần gửi, kết quả, thời gian đến ACK |
| `logs/summary_k{n}.txt` | Bảng tóm tắt in ra cuối mỗi lần chạy |
| Ảnh chụp | Output gateway có "Frame dau" và `crc_err = 0`; Wireshark nếu dùng; telemetry trong chuỗi bay |
| Git | Commit sau mỗi giai đoạn, tag bản dùng để đo |

---

## 8. Thứ tự đo (để không phải làm lại)

1. Môi trường + Bước 1 (parse, CRC, đối chiếu `pymavlink`) → B1, B3, B5, B6.
2. Test logic bằng dữ liệu giả → B7.
3. K1 baseline → B9.
4. Proxy + K0 → B8.
5. K2-K5, K7 → B10, B11, H1-H4.
6. Server TCP và điều khiển, rồi test chức năng → B12, B13.
7. K6 → B14, H5.
8. Viết chương 5 từ các bảng đã có, vẽ lại biểu đồ từ CSV.

---

## 9. Danh mục kiểm tra trước khi nộp

- [ ] Có đủ B1-B15 (bảng nào chưa làm thì ghi rõ lý do).
- [ ] Mọi bảng số liệu có trung bình ± độ lệch chuẩn của 3 lần chạy.
- [ ] H1-H5 có tên trục, đơn vị, chú thích.
- [ ] Phần hạn chế và giải thích sai số đầy đủ.
- [ ] Tham số PX4 (`-r`, stream) giống nhau ở mọi kịch bản.
- [ ] Seed và tham số của từng kịch bản được ghi lại để tái lập.
- [ ] Có hướng dẫn chạy lại và script trong phụ lục.
- [ ] Mã nguồn và log đã commit, có tag bản đo.
