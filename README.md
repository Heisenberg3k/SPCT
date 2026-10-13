# Hướng dẫn chạy Screen Solver trên Windows

Ứng dụng Python chạy nền, dùng GitHub Copilot CLI để giải đề trong ảnh.
Không cần mở VS Code. Python và Node.js đã có trên máy này; Copilot CLI được
cài riêng tại `.tools`, không cần lệnh `copilot` trong PATH.

## 1. Cài đặt lần đầu

Mở PowerShell thường (không cần Run as administrator) rồi chạy lần lượt:

```powershell
cd D:\Dev\SPCT_Example
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
```

Script tạo môi trường `.venv`, cài Pillow và Copilot CLI nếu thiếu, rồi kiểm tra
bộ chạy. Cần mạng để tải các gói. Máy mới cần Python 3.10+ và Node.js 22+ trong PATH.
Khi thành công sẽ có dòng `Setup complete`.
`ExecutionPolicy Bypass` ở lệnh trên chỉ áp dụng cho tiến trình PowerShell đó.

## 2. Đăng nhập Copilot lần đầu

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\login.ps1
```

Làm theo hướng dẫn đăng nhập GitHub hiện trong terminal/trình duyệt. Tài khoản
cần có quyền sử dụng Copilot CLI và model hỗ trợ ảnh. Nếu tài khoản do tổ chức
quản lý, chính sách tổ chức cũng phải cho phép tính năng này.

Bước cài đặt/đăng nhập có giao diện; ứng dụng chạy nền sau đó không hiện popup
hay thông báo. Việc đăng nhập extension trong VS Code chưa xác nhận CLI đã đăng nhập.

## 3. Khởi động

Nhấp đúp `start.vbs` trong thư mục dự án, hoặc chạy:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

Không có cửa sổ xuất hiện là hành vi bình thường. Có thể đóng PowerShell sau khi
khởi động. Chương trình chạy trong phiên Windows hiện tại, chưa tự khởi động cùng Windows.

Để kiểm tra trạng thái:

```powershell
Get-Content D:\Dev\SPCT_Example\runtime\status.json -Encoding UTF8
```

Lúc mới chạy, `stage` là `waiting`. File trạng thái ghi nhận lần cập nhật gần nhất,
không phải phép kiểm tra tiến trình còn sống. Nếu cần, dùng `pid` trong file để
kiểm tra bằng `Get-Process -Id <pid>`.

## 4. Sử dụng

| Phím tắt | Chức năng |
|---|---|
| Ctrl + Shift + Q | Chụp toàn bộ màn hình, bao gồm các màn hình phụ |
| Ctrl + Shift + E | Gửi ảnh vừa chụp tới Copilot kèm yêu cầu giải bằng Python |
| Ctrl + Shift + O | Nhấp tại vị trí chuột và dán lời giải |
| Ctrl + Shift + X | Thoát ứng dụng và hủy yêu cầu đang chạy |

1. Mở đề bài sao cho chữ rõ và đủ dữ kiện trên màn hình.
2. Bấm Q theo tổ hợp phía trên, rồi thả các phím. Ảnh lưu tại `runtime/latest.png`.
3. Bấm tổ hợp E. Chỉ thao tác này mới gửi ảnh tới Copilot.
4. Đợi xử lý. Thời hạn mặc định là 180 giây; không có thông báo hoàn tất.
5. Khi `stage` là `solution_ready`, mã đã được lưu vào
   `D:\Dev\SPCT_Example\a.txt` và chép vào clipboard.
6. Đặt chuột trong ô nhập/vùng soạn thảo cần dán, bấm tổ hợp O rồi thả toàn bộ
   phím. Chương trình nhấp chuột trái và gửi Ctrl+V. Vùng đó phải hỗ trợ nhập văn bản.

Bạn cũng có thể nhấp vào ô nhập rồi dùng Ctrl+V bình thường sau khi lời giải sẵn sàng.
Code do AI trả về được kiểm tra cú pháp, không được tự thực thi hay bảo đảm đúng thuật toán.
Nếu gửi lỗi, file `a.txt` cũ được giữ lại; vì vậy đừng chỉ dựa vào việc file đã tồn tại
để kết luận lời giải mới hoàn tất. Nếu chụp lại trong lúc đang giải, yêu cầu cũ bị hủy;
đợi một chút rồi bấm E cho ảnh mới.

## 5. Xem tiến độ và lỗi

```powershell
Get-Content D:\Dev\SPCT_Example\runtime\status.json -Encoding UTF8
Get-Content D:\Dev\SPCT_Example\runtime\app.log -Encoding UTF8 -Tail 30
```

| stage | Ý nghĩa |
|---|---|
| waiting | Chờ chụp ảnh |
| captured | Đã có ảnh, chờ gửi |
| solving | Đang chờ Copilot |
| solution_ready | Lời giải đã lưu và sẵn sàng dán |
| error | Xem trường message và app.log |
| stopped | Ứng dụng đã thoát |

Nếu không có `status.json`, xem `runtime/startup_error.log` hoặc
`runtime/launcher_error.log` nếu các file đó xuất hiện. Để kiểm tra phụ thuộc:

```powershell
cd D:\Dev\SPCT_Example
.\.venv\Scripts\python.exe -m screen_solver.app --check
```

Lệnh `--check` không gửi ảnh và không xác nhận đăng nhập hay hạn mức tài khoản.

- Lỗi đăng nhập: chạy lại `login.ps1`.
- Lỗi model không hỗ trợ ảnh: mở CLI bằng
  `.\.tools\node_modules\.bin\copilot.cmd`, dùng `/model` để xem model tài khoản
  có thể dùng, rồi chọn model hỗ trợ ảnh. Có thể đặt mã model vào `model` trong `config.json`.
- Phím tắt không đăng ký được: xem `startup_error.log`, đóng ứng dụng đang chiếm
  tổ hợp đó rồi khởi động lại.
- Không dán được: đảm bảo chuột nằm trên vùng nhập và thả Ctrl/Shift/O trong vòng
  3 giây. Ứng dụng chạy thường có thể không dán được vào chương trình đang chạy với quyền Administrator.
- Script PowerShell bị chặn: dùng đúng lệnh `powershell -NoProfile -ExecutionPolicy Bypass -File ...`
  ở trên, không cần thay đổi chính sách toàn máy.

## 6. Tùy chỉnh

Sửa `config.json`, bấm Ctrl+Shift+X rồi khởi động lại để áp dụng:

- `timeout_seconds`: thời gian chờ Copilot, từ 10 đến 1800 giây.
- `click_at_pointer: true`: tự nhấp tại chuột trước khi dán.
- `click_at_pointer: false`: dán vào ô đang có con trỏ nhập văn bản, không nhấp chuột.
- `model: ""`: dùng model theo thiết lập/default của CLI.
- `output_file`: đường dẫn lưu mã; mặc định `D:\Dev\SPCT_Example\a.txt`.

Những lần dùng sau chỉ cần chạy `start.vbs`; không cần cài lại hay đăng nhập lại
trừ khi xác thực hết hạn.

Tài liệu GitHub: [Copilot CLI](https://docs.github.com/en/copilot/get-started/cli-quickstart),
[tham số chạy tự động và đính kèm ảnh](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-programmatic-reference).
