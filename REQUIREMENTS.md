# isd_credit_app: Yêu cầu chức năng (bản 2, đã cập nhật theo góp ý)

> Trạng thái: **đã duyệt**, đã làm xong bản đầu (xem README.md).
> Nền tảng: Odoo 18, LGPL-3.

---

## 1. Mục tiêu

Tính tiền khách hàng theo mức sử dụng các module của ISD trong một Odoo do **ISD host**:

- **Ví credit chung**: một ví cho cả database, hoặc mỗi công ty một ví (công tắc, F1). Không chia theo từng user.
- **ISD (bên bán)** cấu hình:
  - credit cấp theo kỳ, theo thoả thuận trên hợp đồng
  - chế độ reset khi qua kỳ
  - bảng giá thao tác
  - gói nạp
  - duyệt yêu cầu nạp
- **Quản lý phía khách** xem số dư và lịch sử, tự giới hạn (hoặc không) mức dùng của từng nhân viên, và gửi yêu cầu nạp. Trước mắt nạp bằng **tiền mặt**.
- **Nhân viên** biết mỗi thao tác tốn bao nhiêu credit và đã dùng bao nhiêu.
- **Gần hết hoặc hết credit** thì **mọi người** đều được nhắc, kể cả ISD.

**Về chống gian lận:** ISD host server và giữ quyền Administrator của Odoo. Khách không có quyền Administrator (Settings) hay quyền vào server/database. Trường hợp khách mua đứt hệ thống và tự host thì không còn tính credit, nên module chỉ cần phân quyền trong Odoo là đủ.

---

## 2. Vai trò

| Vai trò | Ai | Được làm gì |
|---|---|---|
| **Credit Vendor** | ISD (admin hệ thống) | Cấu hình gói theo kỳ, bảng giá, gói nạp và giá, ngưỡng cảnh báo; duyệt/từ chối nạp; điều chỉnh credit bằng tay (ghi lý do); xem mọi thứ |
| **Credit Manager** | Quản lý công ty khách | Xem số dư, lịch sử, báo cáo; giới hạn credit cho nhân viên/nhóm; gửi yêu cầu nạp |
| **Credit User** | Mọi nhân viên của khách | Xem bảng giá, số credit mình đã dùng, hạn mức còn lại của mình (nếu bị giới hạn) |

Credit Manager **không** sửa được bảng giá, gói, sổ credit, và **không tự duyệt** yêu cầu nạp của mình.

---

## 3. Chức năng chi tiết

### F1. Ví credit

**Công tắc phạm vi ví** (ISD chọn trong cấu hình):

| Chế độ | Hoạt động |
|---|---|
| **Một ví cho cả database** (mặc định) | Mọi công ty trong hệ thống dùng chung một ví |
| **Mỗi công ty một ví** | Mỗi công ty có ví, gói theo kỳ, giới hạn và yêu cầu nạp riêng. Thao tác trừ vào ví của **công ty đang làm việc**, tức công ty của bản ghi nếu có, không thì công ty user đang chọn |

Mỗi ví gồm **hai phần riêng biệt**:

| Phần | Nguồn | Hạn dùng |
|---|---|---|
| **Credit hệ thống** (theo kỳ) | ISD cấp theo hợp đồng | Xử lý theo chế độ reset khi qua kỳ (F2) |
| **Credit đã nạp** | Khách mua thêm, được ISD duyệt | **Không bao giờ hết hạn** |

- **Thứ tự trừ:** **credit hệ thống trước**, hết mới trừ **credit đã nạp**.
- **Hiển thị:** số dư tổng = credit hệ thống còn lại + credit đã nạp còn lại. Kèm ngày reset kế tiếp.

### F2. Gói credit hệ thống theo kỳ (ISD cấu hình theo hợp đồng)

| Thiết lập | Lựa chọn |
|---|---|
| Số credit mỗi kỳ | ví dụ 1000 |
| Chu kỳ | Ngày / Tuần / Tháng / Quý / Năm / Một lần (không có kỳ) |
| Chế độ khi sang kỳ mới | **Reset**: về lại đúng 1000, phần chưa dùng mất<br>**Cộng dồn có trần**: cộng thêm 1000 vào phần còn lại, không vượt trần (ví dụ 3000)<br>**Không reset**: không cấp thêm |
| Ngày bắt đầu, múi giờ | Kỳ tính theo múi giờ của khách |
| Ngày hết hạn hợp đồng (tuỳ chọn) | Sau ngày này không cấp kỳ mới; báo trước N ngày |

- Reset do **cron chạy mỗi ngày**; mỗi lần reset ghi một dòng sổ (F7).
- Đổi gói giữa chừng có hiệu lực **từ kỳ kế tiếp**, hoặc **ngay lập tức** nếu ISD chọn vậy.

### F3. Bảng giá thao tác (ISD cấu hình)

**Chọn module:** danh sách module **đang cài** trong hệ thống. Cài thêm module mới là nó **tự xuất hiện**, không phải cập nhật tay.
- Có lựa chọn **"Chỉ module của ISD"** (lọc theo tác giả IntelliSyncData) để danh sách gọn.
- Chọn module rồi thì ô **Model** chỉ còn các model của module đó; ô **Nút** / **Server action** / **Báo cáo** cũng chỉ hiện những thứ của module đó.

**Mỗi quy tắc gồm:**

| Trường | Ví dụ |
|---|---|
| Tên hiển thị | "Tạo mã QR" |
| Module | `isd_qr_code` |
| Loại thao tác | xem bảng dưới |
| Đối tượng | model, tên nút, server action, báo cáo, hoặc mã hành động |
| Số credit | 2 (để **0** nếu chỉ muốn theo dõi mà không tính) |
| Điều kiện (tuỳ chọn) | Chỉ tính khi bản ghi thoả điều kiện, ví dụ "loại = vCard" |
| Trạng thái | Đang áp dụng / Tạm tắt |

**Các loại thao tác bắt được** (6 loại đầu không cần viết code):

| Loại | Khi nào tính | Ví dụ |
|---|---|---|
| **Tạo** | Tạo bản ghi của model | Tạo 1 đơn Profile Management |
| **Sửa** | Lưu thay đổi bản ghi (tuỳ chọn: chỉ khi sửa các trường được chọn) | Sửa giá đơn |
| **Xoá** | Xoá bản ghi | |
| **Bấm nút** | Bấm một nút trên form/danh sách (theo tên nút của model) | "Book Meeting", "Save to CRM" |
| **Server action** | Chạy một server action / hành động tự động | "Gửi email hàng loạt" |
| **In báo cáo** | In/tải một báo cáo PDF | "In nhãn" |
| **Hành động có tên** | Module ISD tự gọi trong code ở chỗ quan trọng | "AI trả lời", "Xuất PNG 4K", "Gửi tin Zalo" |

**Thao tác hàng loạt** (tạo hoặc xoá nhiều bản ghi một lúc, import file) được tính **theo số bản ghi**. Nếu không đủ credit cho cả lô thì **chặn cả lô** và báo cần bao nhiêu credit.

**Khi hết credit: chặn.** Thao tác bị từ chối với thông báo rõ ràng: "Hệ thống đã hết credit. Liên hệ quản lý để nạp thêm.".

**Quy tắc chung:**
- Thao tác bị lỗi giữa chừng thì credit **tự hoàn lại**, vì trừ chung giao dịch với thao tác.
- Đổi giá **không ảnh hưởng** những gì đã tính trước đó.
- **Không tự hoàn** credit khi xoá bản ghi đã tạo. ISD điều chỉnh tay nếu cần.
- **Không tính** cho việc cài/nâng cấp module, nạp dữ liệu mẫu, tác vụ nội bộ của hệ thống, và user của ISD (Credit Vendor). Cron và API vẫn bị tính.

### F4. Thông báo gần hết / hết credit

- **Ngưỡng cảnh báo** do ISD nhập bằng **số credit**, ví dụ `200`. Khi số dư **≤ 200** thì bắt đầu nhắc.
- **Ai thấy:** **mọi user** đang đăng nhập backend, kể cả user của ISD (để nhắc khách nạp).
- **Hiện thế nào:** một **hộp thông báo** mỗi khi vào hệ thống (mở hoặc tải lại Odoo):

  | Tình trạng | Nội dung |
  |---|---|
  | Sắp hết (≤ ngưỡng) | "Hệ thống còn 150 credit. Hãy liên hệ quản lý để nạp thêm." |
  | Hết (= 0) | "Hệ thống đã hết credit. Các thao tác có tính credit đang bị chặn." |

  Credit Manager có thêm nút **"Gửi yêu cầu nạp"** ngay trong hộp.
- **Ô "Không hiện lại hôm nay":** tick thì hộp không hiện nữa trong ngày (tính riêng cho từng user, theo múi giờ của khách). **Sang ngày hôm sau vẫn hiện lại** nếu credit vẫn thấp hoặc hết.
- **Kèm email** cho Credit Manager và ISD lúc **lần đầu chạm ngưỡng** và lúc **hết**. Chỉ gửi một lần cho mỗi lần chạm, không gửi liên tục.
- Ở chế độ mỗi công ty một ví, thông báo dựa trên ví của **công ty đang chọn**.

### F5. Giới hạn theo nhân viên (Credit Manager cấu hình)

- **Mặc định không giới hạn:** nhân viên dùng chung ví.
- Quản lý đặt giới hạn cho **nhân viên** hoặc **nhóm quyền**:
  - tối đa N credit mỗi kỳ (ngày/tuần/tháng), hoặc
  - **cấm** các thao tác có tính credit.
- **Vượt giới hạn thì bị chặn**, ví dụ: "Bạn đã dùng hết 100/100 credit hôm nay. Liên hệ quản lý.". Người khác vẫn dùng bình thường.
- Giới hạn chỉ **chia bớt ví chung**, không tạo thêm credit. Ví hết thì mọi người đều dừng.

### F6. Yêu cầu nạp credit

**Gói nạp** do ISD cấu hình, mỗi gói có giá theo **VND hoặc USD**. Ví dụ: "1.000 credit = 500.000đ", "1.000 credit = 20 USD". Ngoài gói, có thể nạp số credit tuỳ ý theo đơn giá của từng loại tiền.

**Luồng nạp:**

```
Credit Manager tạo yêu cầu  →  Đã gửi  →  ISD duyệt  →  Credit cộng vào phần "đã nạp"
                                         ↘  ISD từ chối (ghi lý do)
```

| Bước | Chi tiết |
|---|---|
| Tạo yêu cầu | Chọn gói hoặc số credit, **loại tiền (VND/USD)**, phương thức **Tiền mặt** (sau này thêm chuyển khoản, cổng thanh toán qua `isd_payment`), ghi chú, ảnh biên nhận nếu có |
| Gửi | ISD nhận thông báo (email + activity) |
| ISD duyệt | Nhập số tiền thực nhận. Credit được cộng ngay, ghi vào sổ, báo lại cho khách |
| ISD từ chối | Ghi lý do, báo lại cho khách |

- Mỗi yêu cầu có **mã**, ví dụ `TOP/2026/0012`, để đối chiếu tiền mặt.
- Credit nạp **không bao giờ hết hạn**.

### F7. Sổ credit (lịch sử, không sửa được)

Mỗi biến động tạo **một dòng sổ**:
- trừ khi dùng
- cấp theo kỳ / reset
- nạp
- điều chỉnh tay

Mỗi dòng ghi: thời gian, người thực hiện, công ty/ví, quy tắc, bản ghi liên quan, số credit (+/−), phần ví bị trừ (hệ thống/đã nạp), số dư sau đó.

- **Không ai sửa hay xoá** được dòng sổ. Muốn chỉnh thì tạo dòng **điều chỉnh** có lý do.
- **Trừ credit có khoá chống tranh chấp:** hai người dùng cùng lúc thì không bao giờ trừ quá số dư.

### F8. Bảng điều khiển và báo cáo

**Credit Manager thấy:**
- số dư (hệ thống / đã nạp), ngày reset kế tiếp
- biểu đồ dùng theo ngày
- top thao tác, top nhân viên, top module
- lịch sử nạp

**Credit User thấy:**
- **bảng giá thao tác**
- credit mình đã dùng trong kỳ
- hạn mức còn lại (nếu bị giới hạn)

**ISD thấy:**
- tất cả những gì Credit Manager thấy
- **bản kê theo tháng** (tổng dùng, tổng nạp, tổng tiền theo VND/USD), xuất Excel/PDF để tính tiền

### F9. Hiện giá ngay lúc thao tác

Trên form có tính credit, hiện một dòng nhỏ, ví dụ "Lưu bản ghi này tốn 2 credit", để người dùng biết trước khi bấm.

---

## 4. Kỹ thuật (tóm tắt)

- **Tạo/Sửa/Xoá:** kế thừa model gốc `base` của Odoo. Bảng giá được đọc vào cache, nên model không có quy tắc nào không bị chậm đi.
- **Bấm nút:** bắt tại điểm Odoo xử lý mọi nút bấm (`/web/dataset/call_button`), theo model + tên nút.
- **Server action:** bắt khi `ir.actions.server` chạy.
- **In báo cáo:** bắt khi `ir.actions.report` dựng báo cáo.
- **Hành động có tên:** hàm `self.env['isd.credit.wallet'].consume('<mã>', qty=1, record=...)` cho các module ISD gọi.
- **Danh sách module:** lấy từ module đang cài, nên tự cập nhật. Model, nút, server action và báo cáo được lọc theo module qua dữ liệu đăng ký của Odoo.
- **Ví:** khoá dòng ví (`SELECT … FOR UPDATE`) khi trừ. Cron reset hằng ngày. Một ví cho database hoặc mỗi công ty một ví theo công tắc cấu hình.
- **Thông báo:** hộp thông báo hiện khi tải giao diện backend. Lưu ngày bấm "Không hiện lại hôm nay" theo từng user.
- **Model dự kiến:**
  - `isd.credit.wallet`: ví
  - `isd.credit.plan`: gói theo kỳ
  - `isd.credit.rule`: bảng giá
  - `isd.credit.ledger`: sổ
  - `isd.credit.limit`: giới hạn nhân viên
  - `isd.credit.package`: gói nạp
  - `isd.credit.topup`: yêu cầu nạp
- **Nhóm quyền:** Credit Vendor (gán cho admin ISD), Credit Manager, Credit User, kèm record rule.
- **Kiểm thử:**
  - thứ tự trừ: hệ thống trước, đã nạp sau
  - reset / cộng dồn / không reset
  - chặn khi hết, kể cả với thao tác hàng loạt
  - ngưỡng cảnh báo và "không hiện lại hôm nay"
  - giới hạn nhân viên
  - một ví và mỗi công ty một ví
  - đủ 7 loại thao tác
  - hai người trừ cùng lúc không vượt số dư
  - lỗi giữa chừng thì credit tự hoàn
  - khách không tự cộng credit, không tự duyệt nạp
  - nạp bằng VND và USD

---

## 5. Đã chốt

| # | Câu hỏi | Quyết định |
|---|---|---|
| 1 | Ai host | ISD host và giữ quyền admin. Khách mua đứt và tự host thì không tính credit |
| 2 | Thao tác bị tính | Tất cả: tạo, sửa, xoá, bấm nút, server action, in báo cáo, hành động có tên. Không muốn tính thì để 0 |
| 3 | Hết credit | **Chặn**. Ngưỡng cảnh báo cấu hình được (ví dụ 200); hộp thông báo mỗi lần vào hệ thống cho mọi người kể cả ISD; có "Không hiện lại hôm nay" |
| 4 | Hạn credit nạp | Không bao giờ hết hạn. Trừ credit hệ thống trước |
| 5 | Credit hệ thống | Cấp theo hợp đồng, ISD tự nhập |
| 6 | Ví | Công tắc: một ví cho database, hoặc mỗi công ty một ví |
| 7 | Tiền tệ | VND và USD |
| 8 | Module áp dụng | Mọi module. ISD tự chọn module trong danh sách module đang cài, module mới tự xuất hiện |
| 9 | Hoàn credit khi xoá | Không tự hoàn; ISD điều chỉnh tay |

## 6. Ngoài phạm vi bản đầu

- Thanh toán online khi nạp: làm sau, nối với `isd_payment`.
- Hoá đơn VAT tự động.
