# Credit (isd_credit_app)

Tính tiền khách theo credit trong một Odoo 18 do ISD host. ISD cấp credit theo kỳ theo hợp đồng và đặt giá cho từng thao tác. Khách dùng hết thì nạp thêm (tiền mặt, VND hoặc USD), ISD duyệt.

Phụ thuộc: `base`, `web`, `mail`.

## Vai trò

| Nhóm | Gán cho | Được làm |
|---|---|---|
| **Credit Vendor (ISD)** | Admin của ISD (`admin` và `__system__` có sẵn) | Cấu hình gói theo kỳ, bảng giá, gói nạp, thiết lập; duyệt hoặc từ chối nạp; điều chỉnh credit. **Không bị tính credit.** |
| **Credit Manager** | Quản lý phía khách | Xem số dư, lịch sử, báo cáo; giới hạn nhân viên; gửi yêu cầu nạp |
| **Credit User** | Tự động cho mọi user nội bộ | Xem bảng giá, credit mình đã dùng và hạn mức của mình |

Credit Manager không sửa được bảng giá, gói nạp, sổ credit, số dư, và không tự duyệt được yêu cầu nạp. Các nút quản trị trên ví và luồng duyệt đều kiểm tra quyền ở server, không chỉ ẩn trên giao diện.

**Lưu ý:** khách **không được** có quyền Administrator (Settings). Có quyền đó thì tự thêm mình vào nhóm Vendor được.

## Cài đặt và cấu hình (ISD)

1. Cài **Credit (by ISD)**. VND và USD được bật sẵn.
2. **Credit → Configuration → Settings**:
   - **Credit Wallets**: một ví cho cả database (mặc định), hoặc mỗi công ty một ví. Nên chọn trước khi bắt đầu dùng.
   - **Time Zone**: kỳ, giới hạn và "Không hiện lại hôm nay" tính theo ngày ở múi giờ này. Mặc định `Asia/Ho_Chi_Minh`.
   - **Warn Below**: ngưỡng cảnh báo, tính bằng credit (ví dụ `200`).
   - **Price per Credit (VND / USD)**: đơn giá khi khách nạp số credit tuỳ ý, ngoài các gói.
3. **Credit → Configuration → Wallets** (hoặc **Overview**): nhập gói theo hợp đồng:
   - **Credit per Period**, ví dụ 1000
   - **Period**: Ngày / Tuần / Tháng / Quý / Năm / Một lần
   - **Reset Mode**: **Reset** về đúng mức mỗi kỳ, **Cộng dồn** có **Cap** (trần), hoặc **Không reset**
   - **Contract Ends** (tuỳ chọn): sau ngày này kỳ mới cấp 0 credit

   Bấm **Start Plan** để cấp kỳ đầu. Đổi gói giữa chừng thì có hiệu lực từ kỳ sau, hoặc bấm **Apply Plan Now**. Cron **Credit: start new periods** chạy mỗi giờ và sang kỳ đúng nửa đêm theo múi giờ đã chọn.
4. **Credit → Configuration → Prices**: bảng giá (xem bên dưới).
5. **Credit → Configuration → Packages**: gói nạp, ví dụ "1.000 credit = 500.000 VND", "1.000 credit = 20 USD".

## Bảng giá

Mỗi dòng gồm module, loại thao tác, đối tượng và số credit.

- **Module**: các module **đang cài**. Cài thêm module là nó tự xuất hiện. Tick **ISD Modules Only** để chỉ hiện module có tác giả IntelliSyncData. Chính module Credit không có trong danh sách.
- Chọn module xong thì ô **Model**, **Server Action**, **Report** chỉ còn những thứ của module đó (theo dữ liệu đăng ký `ir.model.data`).

| Loại | Tính khi | Ghi chú |
|---|---|---|
| **Create** | Tạo bản ghi | Tạo/import nhiều bản ghi: tính theo số bản ghi, không đủ cho cả lô thì chặn cả lô |
| **Edit** | Lưu thay đổi | **Only When Editing**: chỉ tính khi sửa các trường được chọn |
| **Delete** | Xoá bản ghi | Tính trước khi xoá |
| **Button** | Bấm nút trên form/list | Nhập tên hàm của nút; form hiện sẵn danh sách nút của model để chép |
| **Server Action** | Chạy server action / automation | Tính theo số bản ghi được chạy |
| **Print Report** | In PDF hoặc text | Tính theo số bản ghi được in. Xem trước dạng HTML không tính |
| **Named Action** | Module tự gọi trong code | Xem phần dành cho lập trình viên |

- **Only When**: chỉ tính bản ghi thoả điều kiện (ví dụ loại = vCard).
- **Credits … per … times**: tính gộp, ví dụ **1 credit mỗi 50 lần** (gửi 50 tin nhắn mới trừ 1 credit). Module đếm số lần cho từng ví; đủ 50 thì trừ và ghi một dòng sổ "× 50". Ví không còn đủ cho một lần trừ thì chặn luôn, kể cả lần chưa đủ 50.
- Giá **0**: chỉ để biết, không tính. Tắt **Active** để tạm dừng.
- Đổi giá không ảnh hưởng những gì đã tính. Xoá bản ghi không hoàn credit; cần thì dùng **Adjust Credit**.

## Cách tính

- **Thứ tự trừ:** credit hệ thống trước, hết mới trừ credit đã nạp. Credit đã nạp không hết hạn.
- **Hết credit thì chặn**, báo cần bao nhiêu và còn bao nhiêu.
- Trừ credit trong **cùng giao dịch** với thao tác: thao tác lỗi thì credit tự hoàn. Dòng ví bị khoá (`SELECT … FOR UPDATE`) khi trừ, hai người cùng lúc không bao giờ trừ quá số dư.
- **Không tính:** lúc cài/nâng cấp module, tác vụ của superuser (cron hệ thống chạy bằng `__system__`), user nhóm **Credit Vendor**. Cron chạy bằng user khác và API vẫn bị tính.
- **Mỗi công ty một ví:** trừ vào ví công ty của bản ghi (nếu model có `company_id`), không thì công ty user đang chọn.

## Thông báo

- Credit **≤ ngưỡng**: mọi user nội bộ, kể cả ISD, thấy hộp thông báo mỗi lần mở hoặc tải lại Odoo. Hết thì báo đang bị chặn.
- Tick **Không hiện lại hôm nay** thì hộp không hiện nữa trong ngày (riêng từng user). Sang ngày sau credit vẫn thấp thì hiện lại.
- Credit Manager có nút **Gửi yêu cầu nạp** ngay trong hộp.
- Email cho Credit Manager và ISD **một lần** lúc chạm ngưỡng, **một lần** lúc hết. Nạp lên trên ngưỡng thì lần chạm sau lại gửi.
- Thanh trên cùng có biểu tượng credit: số dư, phần hệ thống/đã nạp, credit mình đã dùng tháng này, hạn mức của mình.
- Form của model có giá **Create/Edit** hiện dòng "Tạo bản ghi này tốn X credit".

## Giới hạn nhân viên (Credit Manager)

**Credit → User Limits**. Mặc định không ai bị giới hạn.

- Đặt cho **một nhân viên** hoặc **một nhóm quyền**: tối đa N credit mỗi ngày/tuần/tháng, hoặc cấm thao tác tính credit.
- Nhân viên có giới hạn riêng thì chỉ áp giới hạn riêng; không có thì áp mọi giới hạn của các nhóm họ thuộc.
- Giới hạn chỉ chia bớt ví chung, không tạo thêm credit.

## Nạp credit

1. Credit Manager: **Credit → Top-ups → New** (hoặc nút trong hộp thông báo). Chọn gói hoặc nhập số credit, loại tiền, đính kèm biên nhận nếu có, **Send Request**. Mỗi yêu cầu có mã `TOP/2026/0001`.
2. ISD nhận activity và tin nhắn. Mở yêu cầu, nhập **Received Amount**, bấm **Approve**: credit cộng vào phần đã nạp, ghi sổ, báo lại người yêu cầu. Hoặc ghi **Reject Reason** rồi **Reject**.
3. Yêu cầu đã duyệt không sửa, không xoá được.

## Báo cáo

- **Credit → Usage**: sổ credit (list / graph / pivot). Nhóm theo thao tác, user, module, tháng.
- **Credit → My Usage**: credit mình đã dùng.
- **Credit → Configuration → Monthly Statement** (ISD): pivot theo tháng; tiền nạp theo VND/USD ở pivot của **Top-ups**. Xuất Excel từ nút tải của pivot/list.
- Sổ credit không ai sửa hay xoá được, kể cả admin. Chỉnh bằng **Adjust Credit** (ghi lý do).

## Dành cho lập trình viên

Tính credit cho một bước quan trọng trong code (AI trả lời, xuất ảnh 4K, gửi Zalo...):

```python
self.env['isd.credit.wallet'].consume('ai_chatbot.ai_reply', qty=1, record=lead)
```

- Không có dòng giá **Named Action** nào cho mã đó thì không làm gì, nên gọi an toàn cả khi chưa cấu hình giá.
- Không đủ credit thì raise `UserError`, giao dịch rollback.
- Module gọi `consume` cần `isd_credit_app` trong `depends`, hoặc kiểm tra `'isd.credit.wallet' in self.env` trước.
- Bỏ qua việc tính trong một đoạn code: `with_context(isd_credit_skip=True)`.

## Kiểm thử

```bash
odoo-bin -c odoo.conf -d <db> --db-filter='^<db>$' -i isd_credit_app \
  --test-enable --test-tags=/isd_credit_app --stop-after-init
```

33 test: thứ tự trừ, giá theo N lần, reset / cộng dồn / không reset / hết hợp đồng, cron, chặn khi hết kể cả theo lô, hoàn credit khi lỗi, đủ 7 loại thao tác, thông báo và "không hiện lại hôm nay", email một lần, giới hạn nhân viên và nhóm, ví theo công ty, nạp VND/USD, khách không tự cộng credit hay tự duyệt, sổ không sửa được, khoá dòng ví, và 2 test trình duyệt (hộp thông báo, systray, dòng giá trên form).

## Chưa làm

- Thanh toán online khi nạp (nối `isd_payment`).
- Báo trước N ngày khi hợp đồng sắp hết hạn.
- Hoá đơn VAT tự động.
