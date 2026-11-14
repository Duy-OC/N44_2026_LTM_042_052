# Các chỉ số cần đo trong dự án MAVLink Gateway (1 UAV)

Tài liệu này liệt kê **chỉ những thứ chính cần đo** để đưa vào báo cáo, kèm giải thích: đo cái gì, vì sao đo, đo bằng cách nào, so với cái gì, kết quả mong đợi và các bẫy cần tránh.

**Nguyên tắc chọn:** chỉ đo thứ nào giúp trả lời câu hỏi *"gateway có đo đúng và hoạt động tin cậy không?"*. Thứ nào không vào bảng hoặc biểu đồ của báo cáo thì không đo.

---

## 1. Tổng quan: 7 chỉ số chính

| # | Chỉ số | Câu hỏi nó trả lời | So với |
|---|---|---|---|
| 1 | Tỉ lệ mất gói | Gateway phát hiện mất gói có đúng không? | Log thả gói của proxy |
| 2 | Độ dài cụm mất trung bình | Gateway có thấy được mất theo cụm không? | `1/r` và log proxy |
| 3 | Jitter | Gateway đo dao động thời gian có đúng không? | Tham số delay đặt ở proxy |
| 4 | pps (gói/giây) | Luồng dữ liệu đều đến mức nào? | Tần số PX4 phát |
| 5 | Số gói sai CRC | Gateway phát hiện gói hỏng có đúng không? | Số gói bị lật bit ở proxy |
| 6 | Độ tin cậy lệnh theo mức loss | Lệnh có đến được UAV khi đường truyền xấu không? | Mức loss đặt ở proxy |
| 7 | Chạy đúng chức năng | Hệ thống có làm đúng việc không? | Đạt / không đạt |

---

## 2. Giải thích chi tiết từng chỉ số

### Chỉ số 1: Tỉ lệ mất gói

**Là gì.** Phần trăm gói MAVLink do UAV gửi nhưng không đến gateway.

**Vì sao đo.** Đây là chức năng đo cốt lõi của đề tài. Chạy cục bộ thì mạng gần như hoàn hảo nên phải dùng proxy Markov để tạo mất gói, rồi kiểm tra gateway có phát hiện đúng không.

**Cách đo trong gateway.** Dùng trường `SEQ` (8 bit, mỗi gói tăng 1, quay vòng 255 → 0):

```c
uint8_t expected = last_seq + 1;            // tự quay vòng nhờ uint8_t
uint8_t lost     = (uint8_t)(seq - expected);
total_lost      += lost;
last_seq         = seq;
```

```
Tỉ lệ mất = total_lost / (total_received + total_lost)
```

**Đối chiếu.** Proxy ghi log số gói vào và số gói thả (ground truth). So sánh:

```
Sai số tương đối = |loss_gateway − loss_proxy| / loss_proxy
```

**Kết quả mong đợi.** Hai số khớp nhau, sai số dưới khoảng 5%.

**Bẫy cần tránh.**
- Gói đến muộn hoặc trùng làm hiệu `seq` ra số rất lớn (~250), dễ tính nhầm là mất hàng trăm gói. Cần quy tắc: nếu chênh lệch quá lớn (ví dụ trên 128) thì coi là đảo thứ tự hoặc UAV khởi động lại, không cộng vào số mất.
- Mất liên tiếp từ 256 gói trở lên thì `seq` trở về đúng giá trị cũ, gateway không phát hiện được. Đây là hạn chế của `seq` 8 bit, nêu trong báo cáo.
- `seq` tính riêng theo từng cặp `sysid/compid`. Với 1 UAV, chỉ cần theo dõi một nguồn.
- Gói sai CRC phải đếm riêng, không tính vào gói mất.

---

### Chỉ số 2: Độ dài cụm mất trung bình (burst length)

**Là gì.** Số gói mất liên tiếp trung bình trong mỗi lần mất.

**Vì sao đo.** Tỉ lệ mất một mình chưa đủ mô tả chất lượng đường truyền. Mất 5% lẻ tẻ khác hẳn mất 5% thành từng cụm 10 gói liền. Với UAV, mất liền nhiều gói mới là vấn đề thật. Chỉ số này cho thấy **giá trị của mô hình Markov** so với thả ngẫu nhiên.

**Cách đo trong gateway.** Mỗi lần phát hiện `lost > 0` là một cụm mới có độ dài `lost`:

```
cụm_trung_bình = tổng_gói_mất / số_cụm_mất
```

**Đối chiếu.**
- Với mô hình Gilbert-Elliott (`h_B = 1`): lý thuyết `1/r`.
- Log proxy: độ dài từng cụm thực tế.

Ví dụ `r = 0,25` thì cụm trung bình lý thuyết là 4 gói.

**Kết quả mong đợi.** Gateway đo ra ~4 gói ở cấu hình cụm 4. Khi đổi sang cấu hình cụm 1 (cùng 5% mất), tỉ lệ mất giữ nguyên nhưng cụm giảm xuống ~1.

**Bẫy cần tránh.** Hai cụm cách nhau đúng 1 gói tốt sẽ bị gateway thấy là hai cụm riêng, còn proxy cũng ghi hai cụm; hãy dùng cùng định nghĩa "cụm" ở cả hai phía. Gói đến lộn xộn cũng làm sai số này.

---

### Chỉ số 3: Jitter

**Là gì.** Độ dao động của khoảng thời gian giữa hai gói liên tiếp. Telemetry phát đều 50 Hz nghĩa là 20 ms một gói. Nếu các khoảng cách là 20, 21, 35, 20, 24 ms thì đường truyền có jitter, dù không mất gói nào.

**Vì sao đo.** Là chức năng đo cốt lõi thứ hai, phản ánh độ ổn định đường truyền (không chỉ có mất hay không mất).

**Cách đo (đơn giản, đủ dùng).** Ghi thời điểm nhận mỗi gói, tính khoảng cách giữa hai gói liên tiếp rồi lấy độ lệch của khoảng cách đó so với khoảng cách trung bình:

```
dt_i   = t_i − t_(i−1)
jitter = độ lệch chuẩn của dt   (hoặc trung bình |dt − dt_trung_bình|)
```

Báo cáo thêm giá trị lớn nhất (max) nếu cần.

**Đo thời gian.** Dùng `QueryPerformanceCounter` (độ phân giải dưới micro giây). `GetTickCount` chỉ có độ phân giải khoảng 10-16 ms nên không đủ.

**Đối chiếu.** Cho proxy thêm độ trễ ngẫu nhiên có tham số biết trước ở trạng thái xấu (ví dụ 20-80 ms), rồi kiểm tra jitter gateway đo ra có bám theo tham số đặt hay không. Khi không có delay (kịch bản baseline), jitter đo được chính là **jitter nền** của hệ thống.

**Kết quả mong đợi.** Baseline có jitter rất nhỏ; khi bật delay, jitter tăng tương ứng với tham số đặt.

**Bẫy cần tránh.**
- Khi mất gói, khoảng cách giữa hai gói nhận được dài gấp đôi, gấp ba bình thường. Nếu không loại các khoảng cách đó ra thì jitter bị phình lên vì mất gói chứ không phải vì dao động thời gian. Chỉ tính `dt` giữa hai gói có `seq` liên tiếp.
- Bộ lập lịch Windows cũng gây jitter nhỏ; vì vậy cần có số liệu baseline để so.

---

### Chỉ số 4: pps (gói trên giây)

**Là gì.** Số gói hợp lệ nhận được mỗi giây.

**Vì sao đo.** Là chỉ số đề bài yêu cầu và rất rẻ để lấy. Cho biết luồng dữ liệu có đều hay không.

**Cách đo.** Đếm gói hợp lệ trong cửa sổ 1 giây rồi đặt lại bộ đếm.

**Đối chiếu.** So với tần số PX4 phát (tổng các message cấu hình).

**Kết quả mong đợi.** Baseline ổn định quanh một giá trị. Khi có loss, pps giảm xuống tương ứng với tỉ lệ mất.

**Cách trình bày.** Chỉ cần báo cáo giá trị trung bình trong mỗi kịch bản, không cần vẽ biểu đồ theo thời gian.

---

### Chỉ số 5: Số gói sai CRC

**Là gì.** Số gói đến nơi nhưng nội dung bị hỏng (CRC tính lại không khớp).

**Vì sao đo.** Chức năng kiểm tra CRC là một yêu cầu của đề bài. Phép đo này chứng minh bộ kiểm tra hoạt động.

**Cách đo.** Mỗi frame: tính CRC-16/MCRF4XX trên các byte từ `LEN` đến hết payload, cộng thêm byte `CRC_EXTRA` của message, rồi so với 2 byte CRC trong frame. Không khớp thì tăng bộ đếm `crc_error`.

**Đối chiếu.** Cho proxy lật 1 bit ngẫu nhiên ở một tỉ lệ biết trước (ví dụ 2% số gói) và ghi log số gói đã lật. Bộ đếm của gateway phải khớp số đó.

**Kết quả mong đợi.**
- Baseline (không can thiệp): `crc_error = 0`. Nếu khác 0 nghĩa là bảng `CRC_EXTRA` hoặc cách parse có lỗi.
- Có lật bit: `crc_error` ≈ số gói đã lật (một số trường hợp lật bit rơi vào chỗ làm frame sai độ dài hoặc mất đồng bộ nên có thể lệch nhẹ, hãy giải thích trong báo cáo).

**Bẫy cần tránh.** Phân biệt sai CRC, sai độ dài và message ID lạ; đừng gộp chung. Gói sai CRC không được tính vào "gói mất".

---

### Chỉ số 6: Độ tin cậy lệnh theo mức loss

**Là gì.** Khi đường gateway → UAV bị mất gói, lệnh điều khiển (arm, takeoff, land...) có thể không đến nơi. Gateway tự bảo đảm độ tin cậy bằng cơ chế chờ `COMMAND_ACK`, hết thời gian thì gửi lại (retry). Chỉ số này đo cơ chế đó hiệu quả đến đâu.

**Vì sao đo.** Đây là kết quả hay nhất của phần điều khiển: cho thấy dù đường truyền UDP không tin cậy, tầng ứng dụng vẫn bảo đảm được lệnh.

**Cách đo.** Với mỗi mức loss (0%, 5%, 10%), gửi nhiều lệnh (ví dụ 50 lệnh mỗi mức) qua proxy Markov và ghi:

| Đại lượng | Công thức |
|---|---|
| Tỉ lệ thành công | số lệnh nhận ACK / tổng số lệnh |
| Số retry trung bình | tổng số lần gửi lại / tổng số lệnh |

**Kết quả mong đợi.** Loss tăng thì số retry tăng, nhưng tỉ lệ thành công vẫn cao (gần 100%) ở loss thấp đến trung bình. Ở loss rất cao hoặc cụm dài thì bắt đầu có lệnh thất bại (`TIMEOUT`).

**Bẫy cần tránh.**
- `COMMAND_ACK` với kết quả `ACCEPTED` chỉ có nghĩa **lệnh đã được chấp nhận**, không phải hành động đã xong. Muốn biết đã xong thì nhìn telemetry (ví dụ độ cao tăng sau takeoff).
- Mất cụm dài có thể làm mất cả lệnh lẫn các lần retry liên tiếp, nên thời gian chờ và số lần retry phải chọn hợp lý. Đây là điểm đáng đưa vào phân tích.
- ACK đến muộn sau khi gateway đã báo thất bại cũng cần được xử lý đúng.

---

### Chỉ số 7: Chạy đúng chức năng (đạt / không đạt)

Không phải số liệu mà là bằng chứng hệ thống làm việc. Chỉ cần ghi nhận kết quả đạt hay không đạt:

| Chức năng | Cách kiểm chứng |
|---|---|
| Chuỗi bay | arm → takeoff → độ cao tăng trong telemetry → land → disarm |
| Nhiều client nhận đúng dữ liệu | 2-3 client cùng đăng ký, cùng nhận đúng |
| Khóa quyền điều khiển | client thứ hai bị từ chối khi client thứ nhất đang giữ quyền; client thứ nhất ngắt thì client thứ hai xin được; hai client xin đồng thời thì chỉ một thắng |
| Client chỉ xem | gửi lệnh bị từ chối |
| UAV mất liên lạc | lệnh bị từ chối với lỗi rõ ràng, không treo |
| Client chậm | một client không đọc thì các client khác vẫn nhận bình thường |

---

## 3. Bộ kịch bản đo (6 kịch bản)

Mỗi kịch bản chạy vài phút (đủ vài chục nghìn gói để số liệu hội tụ), lặp 3 lần, báo cáo trung bình.

| Mã | Kịch bản | Tham số gợi ý | Chỉ số được đo |
|---|---|---|---|
| K1 | Baseline, không can thiệp | `p = 0` | Loss = 0, CRC = 0, pps, jitter nền |
| K2 | Loss 5%, cụm trung bình 4 | `r = 0,25`, `p ≈ 0,0132` | Loss, cụm: gateway vs proxy |
| K3 | Loss 5%, cụm trung bình 1 | `r = 1`, `p ≈ 0,0526` | Cùng loss với K2 nhưng cụm khác |
| K4 | Loss 10%, cụm trung bình 4 | `r = 0,25`, `p ≈ 0,0278` | Độ chính xác khi loss cao hơn |
| K5 | Delay + jitter ở trạng thái xấu | thêm 20-80 ms | Jitter đo vs tham số đặt |
| K6 | Lệnh qua proxy | loss 0 / 5 / 10% | Tỉ lệ thành công và số retry |

Công thức chọn tham số (khi `h_G = 0`, `h_B = 1`): `r = 1 / cụm_trung_bình` và `p = r · L / (1 − L)` với `L` là tỉ lệ mất mong muốn.

Có thể thêm một kịch bản lật bit (2% gói bị lật) để kiểm chứng chỉ số 5 nếu chưa gộp vào K1-K5.

---

## 4. Kiểm định proxy Markov (làm trước khi đo gateway)

Nếu proxy sai thì mọi số đối chiếu đều vô nghĩa, vì vậy phải kiểm định proxy trước, độc lập với gateway:

| Đại lượng | Lý thuyết | Đạt khi |
|---|---|---|
| Tỉ lệ thả | `p / (p + r)` | Sai số dưới 10% với ~100.000 gói |
| Cụm mất trung bình | `1 / r` | Sai số dưới 10% |
| Tái lập | Cùng seed cho cùng chuỗi thả | Giống hệt |

---

## 5. Các bảng và biểu đồ đưa vào báo cáo

Chỉ cần **3 bảng và 1 biểu đồ**:

1. **Bảng 1: Kiểm định proxy Markov.** Tỉ lệ thả và cụm trung bình, lý thuyết vs thực tế.
2. **Bảng 2: Gateway vs proxy (K1-K5).** Các cột: kịch bản, loss proxy, loss gateway, sai số %, cụm proxy, cụm gateway, jitter, CRC.
3. **Bảng 3: Độ tin cậy lệnh (K6).** Các cột: mức loss, số lệnh, tỉ lệ thành công, số retry trung bình.
4. **Biểu đồ:** loss đo được (gateway) theo loss đặt (proxy) cho các mức, hoặc so sánh K2 và K3 để minh họa tác động của cụm.

---

## 6. Những thứ KHÔNG đo (không đưa vào báo cáo)

- Jitter kiểu RFC 3550 (dùng cách đơn giản ở trên là đủ).
- Độ trễ xử lý chi tiết, CPU, bộ nhớ theo số client, tải 10-50 client.
- Phân phối thời gian từ lệnh đến ACK (chỉ giữ tỉ lệ thành công và số retry).
- Soak test 30-60 phút, fuzz dài, kết nối/ngắt 1.000 lần.
- Ma trận kịch bản dày (nhiều mức loss × nhiều độ dài cụm).

Các thứ này vẫn nên **tự chạy qua một lần cho yên tâm** rằng hệ thống không crash, nhưng không cần ghi số liệu.

---

## 7. Cách giải thích sai số trong báo cáo

Báo cáo thuyết phục hơn khi nêu lý do của sai số thay vì chỉ khẳng định "khớp":

- **Hữu hạn mẫu:** mất theo cụm có phương sai lớn hơn mất độc lập, nên số đo dao động quanh lý thuyết; chạy đủ dài và lặp nhiều lần để giảm sai số.
- **Giới hạn `seq` 8 bit:** cụm mất từ 256 gói trở lên bị đếm thiếu.
- **Cụm kề nhau:** hai cụm cách nhau rất ít gói có thể bị định nghĩa khác nhau giữa gateway và proxy.
- **Jitter nền:** bộ lập lịch của hệ điều hành và việc chạy PX4, Gazebo, WSL2 trên cùng máy tạo ra jitter không do proxy gây ra; baseline K1 giúp tách phần này.
- **Tái lập:** dùng seed cố định để có thể chạy lại và ra kết quả giống hệt.
