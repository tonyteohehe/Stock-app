# Trợ lý phân tích cổ phiếu cá nhân

## Chạy trên máy
```
py -m pip install -r requirements.txt
py -m streamlit run app.py
```
Trên máy không đặt mật khẩu thì app không hỏi đăng nhập.

## Đưa lên mạng (Streamlit Community Cloud, miễn phí)
1. Tạo tài khoản GitHub tại github.com.
2. Tạo repository mới (New repository), chọn **Private**, rồi bấm "uploading an existing file"
   và kéo toàn bộ file trong thư mục này vào (kể cả thư mục `.streamlit`). Không cần đưa `__pycache__`.
3. Vào share.streamlit.io, đăng nhập bằng GitHub, bấm **Create app** và chọn repository vừa tạo.
   Main file: `app.py`. Trong Advanced settings, chọn Python 3.12.
4. Trong **Advanced settings → Secrets**, dán:
   ```
   APP_PASSWORD = "mat-khau-cua-ban"
   ```
5. Bấm **Deploy**. Sau vài phút bạn có link dạng `ten-app.streamlit.app` để gửi bạn bè, kèm mật khẩu.

## Lưu ý khi chạy trên mạng
- Dữ liệu cơ bản (`co_ban.csv`) dùng chung cho mọi người. File có thể bị đặt lại khi app khởi động lại,
  nên hãy thường xuyên bấm **⬇️ Tải về bản sao** ở thanh bên để lưu, và dùng **⬆️ Khôi phục** khi cần.
- Nếu bật AI (`ANTHROPIC_API_KEY` trong Secrets), mọi người dùng chung key của bạn. Mỗi người tối đa
  10 lượt mỗi lần mở app (sửa `AI_LIMIT_PER_SESSION` trong app.py).
- Chỉ chia sẻ trong nhóm nhỏ để tham khảo. Không công khai hay thu phí khuyến nghị đầu tư.

## Cấu trúc
- `data.py`: lấy giá (VNDirect, dự phòng DNSE); chỉ số cơ bản tự nhập, lưu ở `co_ban.csv`.
- `indicators.py`: tính chỉ báo và chấm điểm. Trọng số: 40% Cơ bản, 35% Kỹ thuật, 25% Dòng tiền.
- `app.py`: giao diện, mật khẩu, giới hạn lượt AI.
