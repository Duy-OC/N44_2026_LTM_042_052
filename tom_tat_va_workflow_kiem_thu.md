# Tóm tắt dự án và workflow có kiểm thử từng giai đoạn

## Phần A. Tóm tắt dự án

**Tên đề tài:** MAVLink Gateway cho UAV PX4 (môn Lập trình mạng, Winsock/Windows)

**Mục tiêu:** Xây dựng server trung gian giữa **1 UAV PX4 (SITL, Gazebo, WSL2)** và nhiều client:

1. Nhận telemetry MAVLink qua **UDP**, kiểm tra **CRC**.
2. Chuyển tiếp/đẩy dữ liệu qua **TCP** cho **nhiều client** cùng lúc.
3. **Đo chất lượng đường truyền:** số gói/giây, gói mất, jitter, CRC lỗi.
4. **Mô phỏng mất gói bằng Markov (Gilbert-Elliott)** qua một proxy đặt trước gateway, để có ground truth kiểm chứng phần đo.
5. Cho client **xem thông tin chi tiết** UAV (trạng thái bay, pin, vị trí, GPS, góc nghiêng...).
6. Cho client **điều khiển UAV** (arm, takeoff, land, RTL, đổi chế độ), có ACK + retry, và **khóa quyền** để chỉ một client điều khiển tại một thời điểm.

**Kiến trúc:**

```
PX4 SITL ─UDP→ [Proxy Markov] ─UDP→ [Gateway] ←TCP→ Client A (điều khiển)
        ←──────── lệnh (UDP) ←──────┘                Client B, C (chỉ xem)
```

**Giá trị chính của đề tài:**

- Đo QoS có đối chứng với ground truth.
- Độ tin cậy lệnh trên đường truyền không tin cậy (ACK + retry).
- Đồng bộ và phân quyền giữa nhiều client.

**Mô hình Markov (Gilbert-Elliott) tóm tắt:**

| Đại lượng | Công thức |
|---|---|
| Xác suất ở trạng thái xấu (B) | `π_B = p / (p + r)` |
| Tỉ lệ mất gói kỳ vọng | `π_G·h_G + π_B·h_B` |
| Độ dài cụm mất trung bình | `1 / r` (khi `h_B = 1`) |
| Độ dài cụm tốt trung bình | `1 / p` |

`p = P(G→B)`, `r = P(B→G)`. Ví dụ mất 5%, cụm trung bình 4 gói: `r = 0.25`, `p ≈ 0.0132`.

---

## Phần B. Workflow: yêu cầu và kiểm thử từng giai đoạn

**Quy tắc chung:** giai đoạn nào chưa đạt toàn bộ tiêu chí kiểm thử thì chưa sang giai đoạn sau. Sau mỗi giai đoạn, hệ thống vẫn phải chạy và demo được.

### Giai đoạn 0: Môi trường và khung dự án (1-2 ngày)

**Yêu cầu**

- Cấu trúc thư mục `src/ (common, gateway, proxy, client)`, `tests/`, `logs/`, `scripts/`.
- Git, commit theo giai đoạn.
- Build bằng một lệnh (MinGW).
- PX4 headless gửi UDP sang IP Windows host (hoặc WSL2 mirrored networking).

**Kiểm thử**

| Mã | Phép thử | Đạt khi |
|---|---|---|
| T0.1 | Build từ thư mục sạch | Một lệnh, không lỗi |
| T0.2 | Chương trình nghe UDP in số byte nhận | Thấy dữ liệu từ PX4 liên tục |

---

### Giai đoạn 1: Parse frame và CRC (2-3 ngày)

**Yêu cầu**

- CRC-16/MCRF4XX + `CRC_EXTRA` theo message ID.
- Parse MAVLink v1 (`0xFE`) và v2 (`0xFD`), xử lý payload bị cắt byte 0 và cờ signing.
- Bộ đếm riêng: hợp lệ, sai CRC, sai độ dài, message ID lạ.
- Không giả định một datagram = một frame.

**Kiểm thử**

| Mã | Phép thử | Đạt khi |
|---|---|---|
| T1.1 | Frame mẫu (từ `pymavlink`/Wireshark) v1 và v2 | CRC đúng 100% |
| T1.2 | Lật 1 bit trong frame | Bị đếm là sai CRC |
| T1.3 | Frame cụt, sai độ dài, hai frame trong một datagram | Parse đúng, không crash |
| T1.4 | 1 triệu byte rác ngẫu nhiên | Không crash, không treo |
| T1.5 | Chạy với PX4 thật vài phút | Sai CRC = 0; số gói hợp lệ khớp `pymavlink` chạy song song (sai lệch dưới 1%) |

---

### Giai đoạn 2: Trạng thái UAV và thống kê (2-3 ngày)

**Yêu cầu**

- Cấu trúc trạng thái UAV, giải mã `HEARTBEAT`, `SYS_STATUS`, `GLOBAL_POSITION_INT`, `ATTITUDE`, `GPS_RAW_INT`, `VFR_HUD`.
- Thống kê: pps, gói mất (`(seq − expected) mod 256`), jitter (inter-arrival; tùy chọn RFC 3550), tuổi dữ liệu.
- Timeout liên lạc 3 giây; ghi CSV mỗi giây.
- Đo thời gian bằng `QueryPerformanceCounter`.

**Kiểm thử**

| Mã | Phép thử | Đạt khi |
|---|---|---|
| T2.1 | Chuỗi `seq` giả: liên tục / mất 1 / mất cụm 5 / quay vòng 255→0 | Số mất đúng 100% |
| T2.2 | `seq` nhảy về 0 (PX4 khởi động lại), gói trùng, đảo thứ tự | Không tính mất hàng loạt sai |
| T2.3 | Timestamp giả với jitter biết trước | Sai số so với tính tay dưới 1% |
| T2.4 | Tắt rồi bật PX4 | Chuyển timeout sau ~3 s, phục hồi khi có lại |
| T2.5 | Đối chiếu giá trị giải mã (độ cao, pin, chế độ) với QGroundControl | Khớp |

---

### Giai đoạn 3: Proxy Markov và ground truth (2-3 ngày)

**Yêu cầu**

- Proxy nhận UDP từ PX4, thả/chuyển tiếp theo Gilbert-Elliott (`p`, `r`, `h_G`, `h_B`, seed cấu hình được).
- Log ground truth: gói vào, gói thả, số cụm, độ dài từng cụm.
- (Tùy chọn) trạng thái B thêm trễ 20-80 ms, giữ nguyên thứ tự gói.

**Kiểm thử** (kiểm định riêng proxy trước khi đo gateway)

| Mã | Phép thử | Đạt khi |
|---|---|---|
| T3.1 | 100.000 gói tổng hợp, các bộ tham số khác nhau | Tỉ lệ thả ≈ `p/(p+r)`, sai số dưới 10% |
| T3.2 | Như trên | Cụm mất trung bình ≈ `1/r`, sai số dưới 10% |
| T3.3 | Hai lần chạy cùng seed | Chuỗi thả giống hệt |
| T3.4 | `p = 0` | Không thả gói nào |

---

### Giai đoạn 4: Đối chiếu gateway với ground truth (3-4 ngày)

**Yêu cầu**

- Chạy ma trận kịch bản, mỗi kịch bản vài phút, lặp 3 lần, xuất CSV.
- Tính sai số tương đối giữa số đo gateway và log proxy.

**Kiểm thử**

| Mã | Kịch bản | Đạt khi |
|---|---|---|
| T4.1 | Không thả | Loss = 0, CRC lỗi = 0 |
| T4.2 | Loss 1%, 5%, 10%, 20% (cụm trung bình 4) | Loss gateway khớp proxy, sai số dưới 5% (tương đối) |
| T4.3 | Cùng 5% nhưng cụm 1 và cụm 10 | Loss giống nhau, độ dài cụm gateway khác nhau và khớp proxy |
| T4.4 | Delay + jitter theo trạng thái | Jitter đo bám theo tham số đặt |
| T4.5 | Lật bit 2% | Bộ đếm CRC khớp số gói bị lật |
| T4.6 | Đo độ trễ xử lý UDP→TCP của gateway | Nhỏ hơn jitter đáng kể (nêu số liệu) |

> Sai lệch ở kịch bản cụm mất từ 256 gói trở lên là hạn chế của `seq` 8 bit, nêu trong báo cáo.

---

### Giai đoạn 5: Giao thức client và fan-out TCP (3-4 ngày)

**Yêu cầu**

- Giao thức có đóng khung: `GET_DETAIL`, `SUBSCRIBE` (đẩy 1-5 Hz), `ACQUIRE/RELEASE`, `COMMAND`, phản hồi `ACK/FAIL/TIMEOUT`.
- `WSAPoll` hoặc thread-per-client; mỗi client một hàng đợi gửi có giới hạn (đầy thì bỏ gói cũ nhất hoặc ngắt client).
- Tách luồng nhận UDP và luồng gửi TCP.
- Client CLI hiển thị thông tin chi tiết.

**Kiểm thử**

| Mã | Phép thử | Đạt khi |
|---|---|---|
| T5.1 | 3 client cùng `SUBSCRIBE` | Cả 3 nhận đủ dữ liệu đúng tần số |
| T5.2 | `GET_DETAIL` | Trả đủ trạng thái + thống kê mạng, khớp log gateway |
| T5.3 | Kill client đột ngột | Gateway và client khác không ảnh hưởng |
| T5.4 | Kết nối/ngắt 1.000 lần | Số handle/socket không tăng |
| T5.5 | Gửi TCP từng byte một; hai lệnh dính nhau | Đóng khung đúng |
| T5.6 | Lệnh sai định dạng, message quá dài | Trả lỗi, không crash |
| T5.7 | Một client không đọc dữ liệu | Client khác vẫn nhận bình thường; bộ nhớ gateway bị chặn trên |
| T5.8 | 10 và 50 client | Ghi CPU, bộ nhớ, độ trễ UDP→TCP; không mất dữ liệu ở client đọc bình thường |

---

### Giai đoạn 6: Điều khiển, ACK, khóa quyền (4-5 ngày)

**Yêu cầu**

- Gateway gửi `HEARTBEAT` GCS (sysid 255) khoảng 1 Hz.
- Lệnh: arm/disarm, takeoff, land, RTL, đổi chế độ qua `COMMAND_LONG`; chờ `COMMAND_ACK`, timeout, retry (tăng `confirmation`), trả kết quả đúng client.
- Khóa quyền: một controller tại một thời điểm; tự thu hồi khi client ngắt.
- Từ chối lệnh khi UAV đang timeout.

**Kiểm thử**

| Mã | Phép thử | Đạt khi |
|---|---|---|
| T6.1 | Arm → takeoff → land → disarm trên SITL | Telemetry xác nhận từng bước (độ cao tăng/giảm, trạng thái armed) |
| T6.2 | PX4 không failsafe khi gateway chạy lâu | Không báo mất liên kết GCS |
| T6.3 | B ra lệnh khi A giữ quyền | Bị từ chối |
| T6.4 | A ngắt kết nối | B xin được quyền |
| T6.5 | Hai client `ACQUIRE` đồng thời, lặp 100 lần | Mỗi lần đúng một client thắng |
| T6.6 | Client chỉ xem gửi lệnh | Bị từ chối |
| T6.7 | Lệnh qua proxy Markov ở loss 0/5/10/20% (mỗi mức 50 lệnh) | Có bảng: tỉ lệ thành công, số retry trung bình, thời gian đến ACK |
| T6.8 | ACK đến muộn, ACK trùng | Không xử lý sai, không gửi lặp ngoài ý muốn |
| T6.9 | Lệnh khi UAV timeout | Báo lỗi rõ ràng, không treo |

---

### Giai đoạn 7: Kiểm thử hệ thống và tài liệu (3-4 ngày + báo cáo)

**Yêu cầu**

- Chạy dài, phục hồi, fuzz.
- Tài liệu: kiến trúc, đặc tả giao thức, bảng kết quả, hướng dẫn chạy lại, script chạy toàn bộ kịch bản.

**Kiểm thử**

| Mã | Phép thử | Đạt khi |
|---|---|---|
| T7.1 | Soak test 30-60 phút (loss 5%, vài client) | Bộ nhớ, handle, CPU phẳng, không tăng dần |
| T7.2 | Khởi động lại PX4 giữa chừng | Gateway nhận lại, không tính mất hàng loạt |
| T7.3 | Fuzz UDP ngẫu nhiên vào gateway 10 phút | Không crash, không treo |
| T7.4 | Chạy lại toàn bộ bằng script trên máy sạch | Tái lập được kết quả chính |

---

## Phần C. Nghiệm thu và ưu tiên

### Tiêu chí nghiệm thu cuối

- [ ] 100% test T1-T3 qua; T4 có bảng sai số được giải thích.
- [ ] Chuỗi bay cơ bản qua giao thức client chạy ổn (T6.1).
- [ ] Khóa quyền đúng dưới tranh chấp (T6.3-T6.6).
- [ ] Có số liệu độ tin cậy lệnh theo mức loss (T6.7).
- [ ] Soak test không rò rỉ (T7.1).

### Thứ tự ưu tiên nếu thiếu thời gian

1. **Không cắt:** giai đoạn 0-4 (lõi và đối chiếu Markov).
2. **Có thể thu hẹp:** giai đoạn 6 còn arm/takeoff/land + ACK/retry + khóa quyền.
3. **Bỏ trước:** bay tới tọa độ, client có giao diện, jitter kiểu RFC 3550.

### Lịch tham khảo

| Giai đoạn | Thời lượng |
|---|---|
| 0 | 1-2 ngày |
| 1 | 2-3 ngày |
| 2 | 2-3 ngày |
| 3 | 2-3 ngày |
| 4 | 3-4 ngày |
| 5 | 3-4 ngày |
| 6 | 4-5 ngày |
| 7 | 3-4 ngày + báo cáo |
| **Tổng** | **khoảng 3-4 tuần** |

### Nguyên tắc thực hiện

1. Luôn có bản chạy được sau mỗi giai đoạn.
2. Tự động hóa kịch bản bằng script ngay từ giai đoạn 3.
3. Ghi log có cấu trúc (CSV) để vẽ biểu đồ cho báo cáo.
4. Giữ khóa quyền điều khiển và một client chỉ xem để chứng minh phân quyền.
