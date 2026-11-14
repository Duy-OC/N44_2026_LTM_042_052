# Tóm tắt dự án và workflow có kiểm thử từng giai đoạn (bản 2: bỏ Markov)

**Thay đổi so với bản 1:** bỏ mô hình Markov (Gilbert-Elliott). Proxy vẫn giữ nhưng chỉ **thả gói ngẫu nhiên độc lập (Bernoulli)** với xác suất `L`, kèm tùy chọn **thêm trễ** và **lật bit**, và vẫn ghi **log ground truth** để đối chiếu với số đo của gateway (hướng B).

---

## Phần A. Tóm tắt dự án

**Tên đề tài:** MAVLink Gateway cho UAV PX4 (môn Lập trình mạng, Winsock/Windows)

**Mục tiêu:** Xây dựng server trung gian giữa **1 UAV PX4 (SITL, Gazebo, WSL2)** và nhiều client:

1. Nhận telemetry MAVLink qua **UDP**, kiểm tra **CRC**.
2. Chuyển tiếp/đẩy dữ liệu qua **TCP** cho **nhiều client** cùng lúc.
3. **Đo chất lượng đường truyền:** số gói/giây (pps), gói mất, jitter, CRC lỗi.
4. **Proxy tạo nhiễu có kiểm soát** đặt trước gateway: thả gói ngẫu nhiên với xác suất `L`, (tùy chọn) thêm trễ ngẫu nhiên và lật bit, để có ground truth kiểm chứng phần đo.
5. Cho client **xem thông tin chi tiết** UAV (trạng thái bay, pin, vị trí, GPS, góc nghiêng...).
6. Cho client **điều khiển UAV** (arm, takeoff, land, RTL, đổi chế độ), có ACK + retry, và **khóa quyền** để chỉ một client điều khiển tại một thời điểm.

**Kiến trúc:**

```
PX4 SITL ─UDP→ [Proxy nhiễu] ─UDP→ [Gateway] ←TCP→ Client A (điều khiển)
        ←──────── lệnh (UDP) ←──────┘                Client B, C (chỉ xem)
```

Proxy áp dụng cho **cả hai hướng** (telemetry và lệnh/ACK) khi đo độ tin cậy lệnh.

**Giá trị chính của đề tài:**

- Đo QoS (loss, jitter, CRC) có đối chiếu với ground truth độc lập.
- Độ tin cậy lệnh trên đường truyền không tin cậy: so sánh **không retry (`N = 1`)** với **có retry (`N = 3`)**.
- Đồng bộ và phân quyền giữa nhiều client.

### Mô hình nhiễu và công thức đối chiếu

| Đại lượng | Công thức | Ghi chú |
|---|---|---|
| Mất gói | Mỗi datagram mất độc lập với xác suất `L` | Tỉ lệ mất kỳ vọng bằng `L` |
| Sai số thống kê của tỉ lệ thả thực tế | `σ = √(L(1−L)/N)` | `N` là số gói đi qua proxy; dùng ngưỡng `3σ` khi kiểm định |
| Độ dài cụm mất trung bình | `1 / (1 − L)` | Suy ra từ `L`; chỉ dùng như phép kiểm tra phụ, không phải chỉ số riêng |
| Trễ thêm | `D ~ U[0, b]` | Độc lập từng gói, giữ nguyên thứ tự gói |
| Jitter thêm do trễ | `σ_dt = b / √6` | Xấp xỉ khi `b` nhỏ hơn nửa chu kỳ phát của ATTITUDE |
| Jitter đo được | `σ_đo² ≈ σ_nền² + b²/6` | `σ_nền` lấy từ K1 |
| Xác suất một lượt (lệnh + ACK) thành công | `q = (1 − L)²` | Giả thiết cả hai chiều bị thả độc lập với cùng `L` |
| Xác suất lệnh thành công sau `N` lần gửi | `P = 1 − (1 − q)^N` | Chính xác khi các lần thử độc lập |
| Số lần gửi trung bình | `E = (1 − (1 − q)^N) / q` | |

Ví dụ số (để so với thực nghiệm):

| `L` | `q` | `N = 1`: `P` | `N = 3`: `P` | `N = 3`: `E` |
|---|---|---|---|---|
| 0% | 1 | 1 | 1 | 1,00 |
| 5% | 0,9025 | 0,9025 | 0,9991 | 1,11 |
| 10% | 0,81 | 0,81 | 0,9931 | 1,23 |

**Lưu ý về đơn vị đếm:** PX4 có thể đặt nhiều frame MAVLink vào một datagram. Proxy thả theo datagram, còn gateway đếm mất theo `seq` (tức theo frame). Vì vậy proxy phải ghi cả **số datagram** và **số frame** bị thả (đếm frame bằng magic + `LEN`, không cần kiểm CRC) và đối chiếu với gateway theo **số frame**.

**Mã mẫu của bộ tạo nhiễu (thay cho Markov):**

```cpp
struct Impair {
    double L = 0.0;   // xác suất thả
    double f = 0.0;   // xác suất lật 1 bit (áp dụng cho gói không bị thả)
    double b = 0.0;   // trễ tối đa (ms), D ~ U[0, b]
    std::mt19937_64 rng{12345};                   // seed cố định để lặp lại được
    std::uniform_real_distribution<double> u{0.0, 1.0};

    bool drop()  { return u(rng) < L; }
    bool flip()  { return u(rng) < f; }
    double delay_ms() { return b * u(rng); }
};
```

---

## Phần B. Workflow: yêu cầu và kiểm thử từng giai đoạn

**Quy tắc chung:** giai đoạn nào chưa đạt toàn bộ tiêu chí kiểm thử bắt buộc thì chưa sang giai đoạn sau. Sau mỗi giai đoạn, hệ thống vẫn phải chạy và demo được.

Cột **Báo cáo** cho biết kết quả có đưa vào báo cáo hay không: **Có** (ghi số liệu, đưa vào bảng/hình) hoặc **Tự chạy** (chạy một lần cho yên tâm, không cần ghi số liệu).

### Giai đoạn 0: Môi trường và khung dự án (1-2 ngày)

**Yêu cầu**

- Cấu trúc thư mục `src/ (common, gateway, proxy, client)`, `tests/`, `logs/`, `scripts/`.
- Git, commit theo giai đoạn.
- Build bằng một lệnh (MinGW).
- PX4 headless gửi UDP sang IP Windows host (hoặc WSL2 mirrored networking), ví dụ `mavlink start -u 14600 -o 14550 -t 172.26.160.1 -r 100000`.
- Giữ nguyên tham số `-r` và chế độ stream cho mọi kịch bản để các số đo so sánh được.

**Kiểm thử**

| Mã | Phép thử | Đạt khi | Báo cáo |
|---|---|---|---|
| T0.1 | Build từ thư mục sạch | Một lệnh, không lỗi | Tự chạy |
| T0.2 | Chương trình nghe UDP in số byte nhận | Thấy dữ liệu từ PX4 liên tục | Có (môi trường thí nghiệm) |

---

### Giai đoạn 1: Parse frame và CRC (2-3 ngày)

**Yêu cầu**

- CRC-16/MCRF4XX + `CRC_EXTRA` theo message ID.
- Parse MAVLink v1 (`0xFE`) và v2 (`0xFD`), xử lý payload bị cắt byte 0 và cờ signing.
- Bộ đếm riêng: hợp lệ, sai CRC, sai độ dài, message ID lạ.
- Không giả định một datagram = một frame.

**Kiểm thử**

| Mã | Phép thử | Đạt khi | Báo cáo |
|---|---|---|---|
| T1.1 | Frame mẫu v1 và v2 (sinh bằng `pymavlink` hoặc bắt bằng Wireshark) | CRC đúng 100% | Có |
| T1.2 | Lật 1 bit trong frame | Bị đếm là sai CRC | Có |
| T1.3 | Frame cụt, hai frame trong một datagram | Parse đúng, không crash | Có |
| T1.4 | Buffer rác ngẫu nhiên | Không crash, không treo | Có |
| T1.5 | Chạy với PX4 thật vài phút, đối chiếu với `pymavlink` | Sai CRC = 0; số gói hợp lệ lệch dưới khoảng 5% (so `ok + unknown` của gateway với số gói hợp lệ của `pymavlink`) | Có |

---

### Giai đoạn 2: Trạng thái UAV và thống kê (2-3 ngày)

**Yêu cầu**

- Cấu trúc trạng thái UAV, giải mã `HEARTBEAT`, `SYS_STATUS`, `GLOBAL_POSITION_INT`, `ATTITUDE`, `GPS_RAW_INT`, `VFR_HUD`.
- Thống kê: pps, gói mất (`(seq − expected) mod 256`), tuổi dữ liệu.
- Jitter: độ lệch chuẩn của khoảng cách giữa các gói **ATTITUDE** liên tiếp, bỏ khoảng có mất gói xen giữa; đo bằng `QueryPerformanceCounter`.
- Quy tắc `seq`: chênh lệch lớn hơn 128 coi là trùng/đảo thứ tự/PX4 khởi động lại, không cộng vào số mất.
- Timeout liên lạc 3 giây; ghi CSV mỗi giây.

**Kiểm thử**

| Mã | Phép thử | Đạt khi | Báo cáo |
|---|---|---|---|
| T2.1 | Chuỗi `seq` giả: liên tục / mất 1 / mất cụm 5 / quay vòng 255→0 | Số mất đúng 100% | Có |
| T2.2 | `seq` nhảy về 0 (PX4 khởi động lại), gói trùng, đảo thứ tự | Không tính mất hàng loạt sai | Có |
| T2.3 | Timestamp giả với jitter biết trước | Sai số so với tính tay dưới 1% | Có |
| T2.4 | Tắt rồi bật PX4 | Chuyển timeout sau khoảng 3 s, phục hồi khi có lại | Có |
| T2.5 | Đối chiếu giá trị giải mã (độ cao, pin, chế độ) với QGroundControl | Khớp | Tự chạy |

---

### Giai đoạn 3: Proxy nhiễu và ground truth (1-2 ngày)

**Yêu cầu**

- Proxy nhận UDP từ PX4 (cổng 14550), tạo nhiễu rồi chuyển tiếp sang gateway (cổng 14551); chiều ngược lại chuyển lệnh về PX4 (cổng 14600).
- Tham số `L`, `f`, `b`, seed đọc từ dòng lệnh hoặc file cấu hình.
- Thứ tự quyết định cho mỗi datagram: thả với xác suất `L`; nếu không thả thì lật 1 bit ngẫu nhiên với xác suất `f`; rồi trễ `D ~ U[0, b]` (giữ nguyên thứ tự gói).
- Log ground truth: số datagram và số frame vào/thả/lật bit, tham số `L`, `f`, `b`, seed.
- Chọn `b` nhỏ hơn nửa chu kỳ phát ATTITUDE đo được ở K1 (ví dụ 5 và 10 ms), để công thức jitter `b/√6` còn xấp xỉ tốt.

**Kiểm thử** (kiểm định riêng proxy, trước khi đo gateway)

| Mã | Phép thử | Đạt khi | Báo cáo |
|---|---|---|---|
| T3.1 | 100.000 gói tổng hợp, `L` = 1%, 5%, 10%, 20% | Tỉ lệ thả thực tế nằm trong `L ± 3σ` với `σ = √(L(1−L)/N)` | Có |
| T3.2 | Như trên | Độ dài cụm mất trung bình ≈ `1/(1−L)` (phép kiểm tra phụ) | Tự chạy |
| T3.3 | Hai lần chạy cùng seed | Chuỗi thả giống hệt | Có |
| T3.4 | `L = 0`, `f = 0`, `b = 0` | Không thả, không lật, không trễ; gói đi qua nguyên vẹn | Có |
| T3.5 | `f` = 2% trên 100.000 gói | Tỉ lệ lật thực tế nằm trong `f ± 3σ` | Có |
| T3.6 | Trễ `b` = 10 ms | Mọi trễ nằm trong `[0, b]`; thứ tự gói không đổi | Có |

---

### Giai đoạn 4: Đối chiếu gateway với ground truth (3-4 ngày)

**Yêu cầu**

- Chạy các kịch bản bên dưới, mỗi kịch bản khoảng 5 phút (đủ vài chục nghìn gói), lặp 3 lần, xuất CSV.
- Hai loại đối chiếu cần phân biệt rõ trong báo cáo:
  - **(a) Gateway vs log proxy:** số frame mất do gateway đếm có khớp số frame proxy thực sự thả không (kiểm tra phép đo).
  - **(b) Proxy vs `L` đặt:** tỉ lệ thả thực tế có khớp tham số đặt không (kiểm tra bộ tạo nhiễu, mang tính thống kê).

**Bộ kịch bản**

| Mã | Kịch bản | Tham số | Đo |
|---|---|---|---|
| K1 | Baseline | `L = 0`, `f = 0`, `b = 0` | Loss, CRC, pps, tần số ATTITUDE, jitter nền |
| K2 | Loss 1% | `L = 0,01` | Loss gateway vs proxy |
| K3 | Loss 5% | `L = 0,05` | Như trên |
| K4 | Loss 10% | `L = 0,10` | Như trên |
| K5 | Loss 20% | `L = 0,20` | Như trên |
| K6 | Delay | `b` = 5 và 10 ms | Jitter đo vs `√(σ_nền² + b²/6)` |
| K7 | Lật bit | `f = 0,02` | `crc_err` gateway vs số gói lật; loss gateway vs thả + lật |
| K8 | Độ tin cậy lệnh | Xem giai đoạn 6 | Tỉ lệ thành công, số retry |

**Kiểm thử**

| Mã | Kịch bản | Đạt khi | Báo cáo |
|---|---|---|---|
| T4.1 | K1 | Loss = 0, CRC = 0, ghi jitter nền | Có |
| T4.2 | K2-K5, đối chiếu (a) | Số frame mất của gateway chênh log proxy tối đa 1% số gói mất hoặc 3 gói, lấy giá trị lớn hơn | Có |
| T4.3 | K2-K5, đối chiếu (b) | Tỉ lệ thả thực tế của proxy nằm trong `L ± 3σ` | Có |
| T4.4 | K6 | Jitter đo bám `√(σ_nền² + b²/6)` (nêu sai lệch; đây là xấp xỉ) và tăng khi `b` tăng | Có |
| T4.5 | K7 | `crc_err` của gateway khớp số gói proxy đã lật (chênh tối đa 1% hoặc 3 gói); loss `seq` của gateway ≈ gói thả + gói lật | Có |
| T4.6 | Đo độ trễ xử lý UDP→TCP của gateway | Nhỏ hơn jitter nền đáng kể | Tự chạy (tùy chọn) |

> Gói bị lật bit không qua được CRC nên gateway vừa đếm vào `sai CRC`, vừa thấy "mất" ở `seq`. Vì vậy ở K7, loss của gateway bằng gói thả cộng gói lật; trừ ra khi đối chiếu.
>
> Gói mất ở đầu hoặc cuối đoạn đo không phát hiện được bằng `seq` (không có gói nào đến sau để so). Đó là nguyên nhân của dung sai 3 gói ở T4.2 và T4.5. Mất liên tiếp từ 256 gói trở lên là hạn chế của `seq` 8 bit; nêu trong báo cáo.

---

### Giai đoạn 5: Giao thức client và fan-out TCP (3-4 ngày)

**Yêu cầu**

- Giao thức có đóng khung: `GET_DETAIL`, `SUBSCRIBE` (đẩy 1-5 Hz), `ACQUIRE/RELEASE`, `COMMAND`, phản hồi `ACK/FAIL/TIMEOUT`.
- `WSAPoll` hoặc thread-per-client; mỗi client một hàng đợi gửi có giới hạn (đầy thì bỏ gói cũ nhất hoặc ngắt client).
- Tách luồng nhận UDP và luồng gửi TCP.
- Client CLI hiển thị thông tin chi tiết.

**Kiểm thử**

| Mã | Phép thử | Đạt khi | Báo cáo |
|---|---|---|---|
| T5.1 | 3 client cùng `SUBSCRIBE` | Cả 3 nhận đủ dữ liệu đúng tần số | Có |
| T5.2 | `GET_DETAIL` | Trả đủ trạng thái + thống kê mạng, khớp log gateway | Có |
| T5.3 | Kill client đột ngột | Gateway và client khác không ảnh hưởng | Có |
| T5.4 | Kết nối/ngắt 1.000 lần | Số handle/socket không tăng | Tự chạy |
| T5.5 | Gửi TCP từng byte một; hai lệnh dính nhau | Đóng khung đúng | Có |
| T5.6 | Lệnh sai định dạng, message quá dài | Trả lỗi, không crash | Có |
| T5.7 | Một client không đọc dữ liệu | Client khác vẫn nhận bình thường; bộ nhớ gateway bị chặn trên | Có |
| T5.8 | 10 và 50 client | Không crash; ghi CPU/bộ nhớ nếu có thời gian | Tự chạy |

---

### Giai đoạn 6: Điều khiển, ACK, khóa quyền (4-5 ngày)

**Yêu cầu**

- Gateway gửi `HEARTBEAT` GCS (sysid 255) khoảng 1 Hz.
- Lệnh: arm/disarm, takeoff, land, RTL, đổi chế độ qua `COMMAND_LONG`; chờ `COMMAND_ACK`, timeout `T_r`, retry tối đa `N` lần (tăng `confirmation`), trả kết quả đúng client. `N` và `T_r` cấu hình được; ghi lại giá trị dùng khi đo.
- Khóa quyền: một controller tại một thời điểm; tự thu hồi khi client ngắt.
- Từ chối lệnh khi UAV đang timeout.

**Kiểm thử**

| Mã | Phép thử | Đạt khi | Báo cáo |
|---|---|---|---|
| T6.1 | Arm → takeoff → land → disarm trên SITL, không nhiễu | Telemetry xác nhận từng bước (độ cao tăng/giảm, trạng thái armed) | Có |
| T6.2 | PX4 không failsafe khi gateway chạy lâu | Không báo mất liên kết GCS | Tự chạy |
| T6.3 | B ra lệnh khi A giữ quyền | Bị từ chối | Có |
| T6.4 | A ngắt kết nối | B xin được quyền | Có |
| T6.5 | Hai client `ACQUIRE` đồng thời, lặp 100 lần | Mỗi lần đúng một client thắng | Có |
| T6.6 | Client chỉ xem gửi lệnh | Bị từ chối | Có |
| T6.7 | **K8:** lệnh qua proxy ở `L` = 0%, 5%, 10%, mỗi mức đo với `N = 1` và `N = 3`, 100 lệnh mỗi cấu hình | Có bảng: tỉ lệ thành công, số lần gửi trung bình; so với `P = 1 − (1 − q)^N` và `E` ở Phần A | Có |
| T6.8 | ACK đến muộn, ACK trùng | Không xử lý sai, không gửi lặp ngoài ý muốn | Tự chạy |
| T6.9 | Lệnh khi UAV timeout | Báo lỗi rõ ràng, không treo | Có |

> Với K8, dùng một lệnh **an toàn, lặp lại được, không đổi trạng thái bay** (ví dụ `MAV_CMD_SET_MESSAGE_INTERVAL`; hãy kiểm tra PX4 trả `COMMAND_ACK` cho lệnh bạn chọn) thay vì arm/takeoff lặp 600 lần. Hai chiều của proxy dùng cùng `L`, và ghi `N`, `T_r` vào báo cáo.
>
> Với 100 lệnh, sai số chuẩn của tỉ lệ thành công khoảng 4 điểm phần trăm ở `P ≈ 0,81`, nên chênh lệch nhỏ hơn mức đó giữa thực nghiệm và công thức là chấp nhận được.

---

### Giai đoạn 7: Kiểm thử hệ thống và tài liệu (3-4 ngày + báo cáo)

**Yêu cầu**

- Chạy ổn định, phục hồi, tái lập.
- Tài liệu: kiến trúc, đặc tả giao thức, bảng kết quả, hướng dẫn chạy lại, script chạy toàn bộ kịch bản.

**Kiểm thử**

| Mã | Phép thử | Đạt khi | Báo cáo |
|---|---|---|---|
| T7.1 | Chạy vài phút với 2-3 client và `L = 5%` | Không crash, bộ nhớ không tăng bất thường (chạy 30-60 phút nếu có thời gian) | Tự chạy |
| T7.2 | Khởi động lại PX4 giữa chừng | Gateway nhận lại, không tính mất hàng loạt | Có |
| T7.3 | Gửi UDP ngẫu nhiên vào gateway vài phút | Không crash, không treo | Tự chạy |
| T7.4 | Chạy lại toàn bộ kịch bản bằng script (cùng seed) | Tái lập được kết quả chính | Có |

---

## Phần C. Nghiệm thu và ưu tiên

### Tiêu chí nghiệm thu cuối

- [ ] 100% test T1-T3 qua (trừ các mục "Tự chạy" nếu hết thời gian).
- [ ] T4 có bảng so sánh gateway vs proxy cho K1-K7, kèm giải thích sai số.
- [ ] Chuỗi bay cơ bản qua giao thức client chạy ổn (T6.1).
- [ ] Khóa quyền đúng dưới tranh chấp (T6.3-T6.6).
- [ ] Có số liệu độ tin cậy lệnh theo mức loss, `N = 1` vs `N = 3`, so với công thức (T6.7).
- [ ] Chạy lại được bằng script (T7.4).

### Thứ tự ưu tiên nếu thiếu thời gian

1. **Không cắt:** giai đoạn 0-4 (lõi, proxy và đối chiếu).
2. **Có thể thu hẹp:** giai đoạn 6 còn arm/takeoff/land + ACK/retry + khóa quyền; K8 giữ vì là baseline duy nhất của phần điều khiển.
3. **Bỏ trước:** các mục "Tự chạy", delay ở K6 (nếu không kịp), client có giao diện, bay tới tọa độ.

### Bảng thay đổi so với bản 1

| Mục | Bản 1 | Bản 2 |
|---|---|---|
| Mô hình lỗi | Gilbert-Elliott (`p`, `r`) | Bernoulli (`L`) + trễ `U[0, b]` + lật bit `f` |
| Giai đoạn 3 | Proxy Markov, 2-3 ngày | Proxy nhiễu, 1-2 ngày |
| Kiểm định proxy | Tỉ lệ thả ≈ `p/(p+r)`, cụm ≈ `1/r`, sai số dưới 10% | Tỉ lệ thả trong `L ± 3σ` |
| Kịch bản | K0-K7 (có cụm 1 vs cụm 10, cụm 4) | K1-K8, không còn kịch bản theo độ dài cụm |
| Chỉ số độ dài cụm | Chỉ số chính | Chỉ là phép kiểm tra phụ (`1/(1−L)`) |
| Baseline | Bernoulli vs Markov; không retry vs có retry | Chỉ còn không retry vs có retry (K8) |
| Độ tin cậy lệnh | Loss 0/5/10/20%, 50 lệnh | Loss 0/5/10%, `N = 1` và `N = 3`, 100 lệnh |
| Tiêu chí sai số | "dưới 5%" chung chung | Hai loại: (a) gateway vs log proxy, (b) proxy vs `L` đặt |

### Lịch tham khảo

| Giai đoạn | Thời lượng |
|---|---|
| 0 | 1-2 ngày |
| 1 | 2-3 ngày |
| 2 | 2-3 ngày |
| 3 | 1-2 ngày |
| 4 | 3-4 ngày |
| 5 | 3-4 ngày |
| 6 | 4-5 ngày |
| 7 | 3-4 ngày + báo cáo |
| **Tổng** | **khoảng 3 tuần** |

### Nguyên tắc thực hiện

1. Luôn có bản chạy được sau mỗi giai đoạn.
2. Tự động hóa kịch bản bằng script ngay từ giai đoạn 3, dùng seed cố định.
3. Ghi log có cấu trúc (CSV) để vẽ biểu đồ cho báo cáo.
4. Giữ khóa quyền điều khiển và một client chỉ xem để chứng minh phân quyền.
5. Giữ nguyên tham số PX4 (`-r`, stream) ở mọi kịch bản.
