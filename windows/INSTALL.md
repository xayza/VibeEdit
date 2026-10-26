# Cài đặt và chạy VibeEdit trên Windows

## Yêu cầu

- Python 3.10 trở lên (khi cài đặt nhớ tick **Add python.exe to PATH**).
- FFmpeg trong PATH (tải bản full tại https://www.gyan.dev/ffmpeg/builds/ rồi thêm thư mục `bin` vào PATH).
- Không cần cài thêm thư viện Python nào: VibeEdit Windows chỉ dùng thư viện chuẩn của Python + FFmpeg.

## Cách chạy nhanh nhất (khuyên dùng)

1. Tải repo này về máy (clone hoặc tải ZIP rồi giải nén).
2. Double-click file `windows\run_vibeedit.bat` (hoặc bấm phải `windows\run_vibeedit.ps1` → Run with PowerShell).
3. Launcher sẽ kiểm tra Python và FFmpeg, mở server rồi tự mở trình duyệt tại http://127.0.0.1:8000/.
4. Trong lúc dùng, **đừng đóng cửa sổ "VibeEdit Server"**. Muốn dừng app thì đóng cửa sổ đó hoặc bấm Ctrl+C trong đó.

## Cách chạy bằng lệnh

```bat
python windows\vibeedit.py serve --port 8000
```

Rồi mở http://127.0.0.1:8000/ trên trình duyệt.

## Lệnh CLI

```bat
python windows\vibeedit.py new TenDuAn --dir windows\projects
python windows\vibeedit.py add <project> media\clip.mp4 v1 0
python windows\vibeedit.py transition <project> <clip_truoc> <clip_sau> dissolve 0.5
python windows\vibeedit.py keyframe <project> <clip> 1.0 opacity 0.5
python windows\vibeedit.py srt-import <project> captions.srt
python windows\vibeedit.py srt-export <project> captions_out.srt
python windows\vibeedit.py export <project> --preset draft
python windows\vibeedit.py mcp <project>
```

## Lưu ý

- Bản xem trước trong giao diện web là video đã xuất gần nhất, chưa phải
  xem trực tiếp timeline (giới hạn của Phase 2, xem `windows/README.md`).
- File LUT `.cube` phải nằm trên máy bạn và đường dẫn phải đúng thì app mới
  áp dụng; đường dẫn sai sẽ báo lỗi rõ ràng chứ không tự bỏ qua.
- Các model AI nặng (nhận diện, dịch, giọng nói) của bản macOS gốc chưa có
  trong bản Windows Phase 2; danh sách còn thiếu xem `VibeEdit/docs/windows-port.md`.
