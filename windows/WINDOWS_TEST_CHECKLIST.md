# Checklist test Windows cho VibeEdit — DÙNG SAU KHI BIMO BÁO HOÀN THIỆN

> Chưa làm ngay. Checklist này chỉ dùng cho lần test Windows sau khi
> bimo báo ứng dụng thật sự hoàn thiện. Người dùng không cần test
> giữa chừng theo từng vòng nữa.
>
> Nguyên tắc: test bằng project và media test tạm của chính bạn, đừng
> dùng project/media gốc quan trọng chưa có bản lưu. Gặp lỗi thì dừng
> ở bước đó, ghi lại đúng như mục 13 rồi báo, đừng cố sửa code song
> song với bên VS Code AI khi chưa `git pull` (tránh conflict).

## 0. Cập nhật code đúng cách (bắt buộc trước mọi bước khác)

1. Mở terminal tại `D:\VibeEdit` (thư mục git, không phải thư mục
   Downloads hay bản ZIP cũ).
2. `git status` phải sạch. Nếu bên VS Code AI đã sửa file chưa commit
   thì commit hoặc stash trước, rồi mới pull.
3. `git pull --ff-only`. Nếu pull báo lỗi thì dừng, gửi nguyên văn
   lỗi cho bimo, đừng tải ZIP về đè lên bản git.
4. Chạy từ trong thư mục `windows\`: `.\update_and_run.bat` (hoặc từ
   `D:\VibeEdit`: `.\windows\update_and_run.bat`). Đừng chạy
   `.\windows\update_and_run.bat` khi đã đứng trong `windows\`.

## 1. Khởi động

- [ ] Chạy `run_vibeedit.bat`: server lên tại `http://127.0.0.1:8000/`,
      trình duyệt tự mở, console không báo lỗi đỏ.
- [ ] Chạy `run_vibeedit_desktop.bat`: cửa sổ desktop mở (pywebview /
      WebView2), giao diện hiện đủ, đóng cửa sổ thì app tắt hẳn
      (không còn process python treo, terminal trả lại prompt).

## 2. Giao diện vừa màn hình (không cuộn chuột)

Thử lần lượt ở 1280×720, 1366×768, 1600×900, 1920×1080, mỗi kích
thước thử ở scaling 100%, 125% và 150% (nếu máy có):

- [ ] Màn hình chính hiện đủ, không phải cuộn dọc hay cuộn ngang để
      thấy hết Inspector, timeline và thanh công cụ.
- [ ] Cột Inspector không bị cắt ở mép phải (ô Speed/Fade hiện đủ).
- [ ] Timeline hiện đủ các track, không bị cuộn dọc khuất track.

## 3. Import (kể cả trùng tên)

- [ ] Import video, audio, ảnh vào Media Library; thumbnail hiện.
- [ ] Import hai file trùng tên: file thứ hai phải lưu thành
      `tên-2.ext`, clip cũ vẫn trỏ file cũ, không file nào bị ghi đè.
- [ ] Mở project cũ, lưu lại, mở lại: dữ liệu còn nguyên, không mất
      clip/media; file backup chỉ tạo theo đúng quy tắc (không tạo
      một bản mới mỗi lần autosave).

## 4. Sửa trên timeline

- [ ] Thêm clip, di chuyển, trim đầu/cuối, split tại playhead (nút
      Split và phím `S`), copy/paste clip, undo (Ctrl+Z) / redo
      (Ctrl+Shift+Z hoặc Ctrl+Y), lưu (Ctrl+S).
- [ ] Bật/tắt magnetic: chèn clip ở boundary dời các clip sau theo,
      chèn giữa clip bị từ chối rõ ràng.
- [ ] Marker: thêm, dời theo khi chèn/xóa/trim, reorder, close gaps.
- [ ] Text: thêm text, đổi preset, đổi vị trí/cỡ; import/export SRT.

## 5. Transition, backdrop, freeze

- [ ] Transition dissolve giữa hai clip main: export ra, đoạn nối
      phải mượt, tổng thời lượng đúng report (không thừa/thiếu khung).
- [ ] Transition motion (ví dụ spin) và halftone: export ra, hiệu
      ứng nhìn thấy được, không bị thay lặng bằng hiệu ứng khác.
- [ ] Backdrop: clip hẹp (fit để lại viền) đặt backdrop blur và màu:
      viền phải được lấp bằng blur/màu, không để đen (trừ khi chọn
      màu đen).
- [ ] Freeze: đoạn freeze giữ đúng khung cuối của clip, không đen,
      không nhảy khung.

## 6. Nhạc và voiceover

- [ ] Thêm nhạc: chỉnh volume, fade in/out; nhạc ducking khi có lời
      thoại (nếu bật).
- [ ] Thu voiceover trong app: bấm ghi, trình duyệt hỏi quyền micro
      thì cho phép, ghi xong take phải nằm trên track Voiceover và
      phát được. Từ chối quyền micro thì app phải báo rõ, không tạo
      file giả.

## 7. Export

- [ ] Export mặc định: file ra đúng kích thước project, đúng thời
      lượng và số khung như report mà app ghi, có cả video và audio.
- [ ] Export preset `youtube4k`: file ra 3840×2160, codec H.264.
- [ ] Export preset `proRes422HQ`: file ra `.mov`, codec ProRes HQ.
- [ ] Export draft (540×960 hoặc nửa kích thước project) nhanh hơn
      bản full và vẫn xem được.

## 8. Desktop, HiDPI, phím tắt

- [ ] Cửa sổ desktop mặc định 1600×900, đổi kích thước được, kéo
      sang màn hình khác vẫn hiển thị đúng, HiDPI không bị mờ/nhòe.
- [ ] Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y / Ctrl+S hoạt động trong cửa sổ
      desktop và trong trình duyệt; Ctrl+S không tách clip (phím chữ
      đơn chỉ tác dụng khi không giữ Ctrl).
- [ ] Tắt app bằng nút đóng cửa sổ hoặc Ctrl+C ở terminal: không còn
      process, cổng 8000 được giải phóng (chạy lại được ngay).

## 9. Chạy full test suite bằng `py`

Từ trong `windows\`:

```
py -m unittest discover -s tests
```

- [ ] Toàn bộ test pass (số test mới nhất ghi trong
      `windows/PARITY.md` — vòng 13 là 567 test). Gửi nguyên văn đoạn
      cuối (`Ran ... OK` hoặc danh sách FAIL) cho bimo nếu có lỗi.

## 10. Những thứ KHÔNG test như thể đã có (giới hạn đã biết)

- Clone giọng nói (cần model provider clone — không có trong cây).
- Chạy segmentation học sâu thật cho cutout (cần model ONNX +
  ONNX Runtime do người dùng cung cấp; khe cắm đã có, grabCut
  không phải "learned").
- Lấy cập nhật plugin từ registry (không có registry nào tồn tại).
- Bộ cài `.exe` một lần bấm và Windows CI (workflow
  `build-windows.yml` vẫn phải đẩy bằng git thật/web UI vì GitHub
  App bị chặn 403; chưa có .exe nào được build, chưa có CI nào chạy).
- Updater tự thay app đang chạy (chỉ có handoff: chọn vị trí
  releases thật, thoát app, chạy script handoff bằng tay).
- Hợp nhất mã Windows vào `VibeEdit/` (chưa làm; làm bằng git thật
  theo `windows/MERGE_PLAN.md` sau khi kiểm thử xong).
- Footage 4K gốc (mới render 4K/ProRes từ clip giả lập trên Linux VM).
- OCR/cutout khi máy chưa cài Tesseract/OpenCV: app phải báo thiếu
  backend rõ ràng, đó là hành vi đúng, không phải lỗi.

## 11. Báo lại cho bimo cái gì

Mỗi lỗi gửi kèm đủ 5 thứ, thiếu một thứ bimo sẽ phải hỏi lại:

1. Ảnh chụp màn hình (toàn màn hình, thấy cả thanh công cụ).
2. Kích thước cửa sổ và mức scaling Windows (100%/125%/150%).
3. Nội dung lỗi nguyên văn (copy text, đừng gõ lại).
4. Các bước làm trước khi lỗi xảy ra (bấm gì, import file gì).
5. Launcher đã dùng (`run_vibeedit.bat` hay
   `run_vibeedit_desktop.bat`) và phiên bản Python/FFmpeg
   (`py --version`, `ffmpeg -version` dòng đầu).

Không gửi media riêng tư hay project gốc quan trọng kèm báo lỗi;
mô tả bằng chữ là đủ, trừ khi bimo hỏi rõ file test nào.
