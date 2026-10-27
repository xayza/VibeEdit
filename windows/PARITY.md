# VibeEdit — Bảng parity: bản gốc macOS (BashCut) so với bản Windows

Mục tiêu sản phẩm là **chuyển TOÀN BỘ BashCut gốc macOS thành ứng dụng
Windows mang tên VibeEdit** — không giới hạn ở MVP hay Giai đoạn 1, và
không chủ động bỏ tính năng nào của bản gốc. Vì vậy mọi tính năng gốc
còn thiếu trong bảng này đều ghi trạng thái
**`missing — planned to port`** kèm hướng port khả thi trên Windows nếu
đã biết. Không có tính năng gốc nào bị ghi là "out of scope" hay
"not planned" ở đây.

Trạng thái hiện tại (đợt full-parity vòng 2, sau Phase 2):
**MCP 472 công cụ** (số live đọc từ `/api/mcp-tools` trong app; số
trong tài liệu này là số tại thời điểm viết và sẽ cũ đi khi thêm công
cụ mới — app luôn là nguồn đúng nhất). Trong 472 công cụ có **334
công cụ thao tác thật** và **138 công cụ kiểm tra-và-báo-lỗi trung
thực** (trả lỗi `NOT_AVAILABLE` kèm lý do và hướng port, không bao giờ
trả thành công giả). Con số này KHÔNG có nghĩa là đã đạt 249/249 tên
gốc: tên gốc và tên Windows khác nhau do đổi tên, và bản Windows còn
có thêm công cụ riêng; các tên gốc còn thiếu được liệt kê thật ở mục
8 bên dưới. Test: **369 tests OK** trên Linux VM (359 trước vòng hai
+ 10 test vòng hai mới). Vòng hai đã rà soát lại toàn bộ và sửa các
dòng cũ còn sót trong README (một số mục vẫn ghi MCP 144/249 và liệt
kê vision/knowledge/magnetic/motion là chưa làm dù đã port xong).

## Cách đọc cột Verification

- **Windows thật** — người dùng đã chạy và thấy trên máy Windows của họ
  (Python 3.12.10, FFmpeg 9.0.2, server tại `http://127.0.0.1:8000/`).
- **Linux VM** — chỉ mới chạy/kiểm chứng trên máy ảo Linux của nhóm phát
  triển (FFmpeg 8.1.2, không có Windows, không có Xcode, không có
  pywebview). Chạy được trên Linux KHÔNG có nghĩa là đã chạy được trên
  Windows thật.
- **Đọc source gốc** — chỉ mới đọc code/tài liệu Swift gốc, chưa biên
  dịch bằng Xcode, chưa chạy bản macOS.

## Cấu trúc đích (chưa thực hiện hợp nhất)

Sản phẩm cuối cùng chỉ có hai ứng dụng:

| Thành phần | Hiện trạng | Đích |
|---|---|---|
| `BashCut-main/` (trên máy người dùng) | App macOS gốc, giữ nguyên | **Giữ nguyên cho macOS, không sửa, không làm mất** trong bất kỳ bước nào |
| `VibeEdit/` (trong repo) | Mã Swift/macOS đã đổi tên từ BashCut | Sau khi port hoàn thiện và kiểm thử xong, trở thành nhà của bản Windows đầy đủ (xem bước hợp nhất có cổng kiểm soát bên dưới) |
| `windows/` (trong repo) | Bản port Windows đang phát triển (Python + FFmpeg + giao diện web/desktop) | Nơi phát triển duy nhất cho tới khi port hoàn thiện |

**Bước hợp nhất cuối là một bước có cổng kiểm soát riêng và CHƯA làm
trong đợt này.** Khi tới bước đó, phải làm đủ các kiểm tra sau, theo
đúng thứ tự, trước khi dọn cấu trúc cũ:

1. Kiểm tra `BashCut-main` còn nguyên vẹn (không sửa, không mất file).
2. Đối chiếu xem cây `VibeEdit/` Swift có thay đổi riêng nào không nằm
   trong `BashCut-main` không (ví dụ phần đổi tên, tài liệu port), và
   bảo toàn các thay đổi đó.
3. Tạo tag/bản lưu (snapshot) của repo trước khi hợp nhất.
4. Chỉ sau đó mới hợp nhất mã Windows vào `VibeEdit/` và dọn cấu trúc cũ.
5. Kiểm thử lại toàn bộ app Windows sau hợp nhất (mở project, import,
   sửa, xuất) trước khi coi bước hợp nhất là xong.

Trong đợt này: **không di chuyển, đổi tên hay xóa gì trong `VibeEdit/`
hay `BashCut-main`** — mọi việc chỉ trong `windows/`. README không được
viết như thể `VibeEdit/` đã là mã Windows ngay bây giờ: `windows/` là
bản port đang phát triển, `VibeEdit/` hiện vẫn là mã Swift/macOS.

## Bảng parity theo nhóm tính năng

### 1. Project và media

| Tính năng | Status | Verification | Ghi chú |
|---|---|---|---|
| Tạo / mở / đổi tên project, nhiều project, project gần đây | works | Windows thật (mở, tạo) + Linux VM | Panel Chào mừng liệt kê recents thật từ `windows/projects/.recent.json`; chưa phải màn hình chào mừng dạng màn hình riêng |
| Import media (video/ảnh/audio), xem file gốc | works | Windows thật (media list, timeline) + Linux VM | Thumbnail khung hình đầu bằng FFmpeg thật |
| Upload 2 file trùng tên không ghi đè | works | Linux VM | Phase 0: file thứ hai lưu thành `tên-2.ext`, clip cũ vẫn trỏ file cũ; cần kiểm tra lại trên Windows thật |
| Lưu project JSON, giữ trường chưa hỗ trợ (unknown fields) | works | Linux VM | Lưu atomic (file tạm + `os.replace`) |
| Backup có dọn dẹp | works | Linux VM | Phase 0: autosave KHÔNG tạo backup; backup chỉ khi lưu lần đầu sau khi mở và trước thao tác ảnh hưởng dữ liệu (xóa, ghi đè, đổi format, import OTIO, xóa track qua MCP); giữ 1 `project.json.bak` + `backups/` tối đa 5 bản mới nhất + 1 bản/ngày trong 7 ngày, chỉ chứa JSON, không chứa media; cần kiểm tra lại trên Windows thật |
| Reveal thư mục / Copy đường dẫn / xóa khỏi recents | partial | Linux VM (Reveal qua `xdg-open`); Windows thật chưa kiểm chứng | Reveal trên Windows dùng `os.startfile` — chưa chạy thử trên Windows thật; xóa khỏi recents chỉ xóa mục danh sách, không xóa file project |
| Tương thích project gốc BashCut (đọc, không làm mất dữ liệu) | partial | Đọc source gốc + Linux VM | Schema `vibeedit.project/1`, đọc được schema cũ; project mẫu thật của người dùng không được dùng làm dữ liệu test |

### 2. Timeline

| Tính năng | Status | Verification | Ghi chú |
|---|---|---|---|
| Thêm / di chuyển / trim / tách / copy-paste / xóa clip, undo/redo (50 bước) | works | Linux VM | Kéo-thả trong cùng track và sang track khác; tách tại playhead (nút + phím S) |
| Snap, marker, đóng khoảng trống (close gaps) | works | Linux VM | Close gaps đưa clip đầu về frame 0; chưa phải magnetic đầy đủ |
| Magnetic di chuyển cả khối (block-move) trên Main | works | Linux VM | Xóa/chèn/di chuyển/trim cuối trên Main dời các clip sau theo, không để gap, không overlap, có undo; tắt được bằng `magnetic_set` (mặc định bật). Reorder (đổi thứ tự khối) đã có từ vòng hai: `reorder_main` dời clip tới trước một clip khác hoặc xuống cuối, các clip ở giữa dời theo cùng linked audio, không đổi duration. Marker nay dời theo khi chèn/xóa/trim cuối magnetic trên Main (marker trong đoạn bị xóa/trim co về đầu đoạn). Giới hạn còn lại: marker chưa dời theo khi move clip và khi close_gaps; ripple chỉ từ thao tác trực tiếp, kéo audio gắn liền không ripple toàn timeline |
| Âm thanh gắn liền (linked audio) | works | Linux VM | `link_audio`/`unlink_audio` lưu `linked_audio` + `linked_video` hai chiều; di chuyển/trim/tách video kéo audio theo cùng delta, tách video tách audio cùng điểm; xóa video xóa luôn audio gắn liền, xóa audio thì video còn lại và bị unlink (đúng tính không đối xứng của bản gốc); thao tác làm audio va chạm bị từ chối toàn bộ, dữ liệu không đổi. Giới hạn: ghi đè lên chính clip audio gắn liền bị từ chối (phải unlink trước); audio của clip bị ghi đè mà không căn khớp chính xác cũng bị từ chối thay vì bịa thời gian |
| Track đổi tên / xóa track | works | Linux VM | Xóa từ chối track Main và track còn clip |

### 3. Preview

| Tính năng | Status | Verification | Ghi chú |
|---|---|---|---|
| Xem file gốc, xem bản xuất gần nhất, Fit, Safe-area | works | Linux VM | Xem nguồn qua `GET /api/media/<id>` (Range 206, chỉ file trong project) |
| Compare nguồn / bản xuất | partial | Linux VM | Dạng chia đôi 2 player, KHÔNG khóa khung hình, không phải wipe có mặt nạ; bản gốc cũng chỉ có overlay xem Compare, chưa có công cụ Compare độc lập |
| Xem trước transition (ảnh tĩnh giữa transition) | works | Linux VM | Render thật bằng renderer, không phải ảnh giả |

### 4. Audio

| Tính năng | Status | Verification | Ghi chú |
|---|---|---|---|
| Âm lượng, fade từng clip (0–5s), ducking nhạc dưới giọng nói, loudnorm | works | Linux VM | Ducking mặc định bản gốc: level −14, attack 3, release 8 |
| Sóng âm (waveform) thật, beat grid, snap theo beat | works | Linux VM | Waveform giải mã thật bằng FFmpeg; file không giải mã được báo 400, không vẽ hình giả |
| Import và đặt voiceover take lên track Voiceover | works | Linux VM | Tạo track Voiceover nếu chưa có |
| Thu voiceover trong app, tạo giọng nói, nhân bản giọng (voice clone) | missing — planned to port | Đọc source gốc | Bản gốc không có sẵn catalogue giọng trong app — giọng đi qua plugin provider; hướng port: làm provider plugin cho giọng nói sau khi có cài plugin từ URL, rồi mới nối tạo/clone/thu vào panel Voice; hiện tại các nút này ghi rõ là chưa có, không tạo giọng giả |

### 5. Captions và chữ

| Tính năng | Status | Verification | Ghi chú |
|---|---|---|---|
| SRT import/export, karaoke highlight từng chữ (.ass `\k`), preset chữ | works | Linux VM | Preset: bold-outline, cinematic-serif, keyword-sticker, place-card, hook-title, chapter-card |
| Phụ đề tự động (transcription) | partial | Linux VM | Chỉ chạy khi máy đã cài faster-whisper (mặc định tiny); chưa cài thì báo rõ, không tạo phụ đề giả |
| Caption transcribe/generate/align thành công cụ MCP | partial | Linux VM | Vòng hai: `captions_transcribe`/`media_transcribe` chạy transcribe thật vào text track; `captions_generate` transcribe rồi trả SRT thật; `captions_align` snap timing của caption về segment giọng nói đã detect (mapping thuần đã có test riêng). Tất cả đều báo lỗi rõ khi máy chưa cài faster-whisper, không đổi timing, không bịa phụ đề |
| Font import | works | Linux VM | Vòng hai: import .ttf/.otf vào thư mục fonts của app (tên duy nhất, không ghi đè, từ chối đuôi khác); font đã import trở thành candidate cho renderer và xuất hiện trong `fonts_list` |
| Voice check / app update check | partial | Linux VM | Vòng hai: `voice_check` kiểm tra thật (piper binary, edge-tts module, số voiceover take trong project đang mở); `app_update_check` trả trạng thái thật (version hiện tại, chưa có kênh updater). Tạo/clone giọng và bản thân updater vẫn chưa có |

### 6. Effects và màu

| Tính năng | Status | Verification | Ghi chú |
|---|---|---|---|
| LUT (.cube), preset màu, adjustment layer | works | Linux VM | LUT strength 0–1; preset strength riêng |
| Thanh trượt màu từng thông số | works | Linux VM | Brightness −1–1, contrast 0–2, saturation 0–3, gamma 0.1–10 qua `eq=`; hẹp hơn model gốc (Exposure −10–10, Contrast 0–4, Saturation 0–4) — cần mở rộng sau nếu render vẫn ổn |
| Keyframes (opacity, scale, tilt, zoompan, vị trí) | works | Linux VM | Render thật; keyframes main-track và overlay still-image đều render |
| Đường cong tốc độ (speed curves) | works | Linux VM | Đủ 6 preset gốc (montage/hero/bullet/jump-cut/flash-in/flash-out) theo đúng điểm trong `SpeedCurve.swift`, tách clip + tốc độ từng đoạn; chưa có đường cong tự vẽ tay |
| Đảo ngược clip (reverse), đóng băng khung hình (freeze) | works | Linux VM | Render thật bằng `reverse`/`areverse` và frame-hold |
| Transition xfade thông dụng + 8 loại mới | partial | Linux VM | Thêm shutter, double-exposure, seamless/infinite/crash-zoom, blur, flash/blink, roll; `dissolve` nay map đúng `dissolve` |
| Transition dạng motion-only (spin, swing/arc, diamond, kaleidoscope, crash-out, infinite-out) | works | Linux VM | 13 loại render thật bằng filter chain FFmpeg (spin/swing/arc/arc-right/diamond bằng mask geq + maskedmerge/crash-out/infinite-out/screen-in/screen-out/dip-black/color-shift/flicker/kaleidoscope), đã kiểm chứng bằng render thật: khung giữa transition khác cả hai clip gốc; `add_transition` nay chấp nhận các loại này. Giới hạn thật: swing là xấp xỉ pivot-giữa (FFmpeg rotate pivot ở tâm, không phải swing phối cảnh mép trái); kaleidoscope là xấp xỉ tile gương 2×2 + xoay, không phải kaleidoscope lục giác thật (không có filter FFmpeg nào làm được); diamond bằng mask geq nên render chậm hơn xfade ở khung hình lớn |
| Transition halftone | missing — planned to port | Đọc source gốc | Không có filter FFmpeg nào tái tạo được mẫu chấm halftone động; `add_transition` báo lỗi rõ kèm hướng pre-rendered segment, không thay thế lặng bằng pixelize |
| Reframe / crop theo preset | partial | Linux VM | Render-side đã hoạt động: `reframe` trên clip (cửa sổ phân số khung hình nguồn) crop trước khi scale, không stretch, cửa sổ sai báo lỗi; dùng qua `add_clip`/`clip_reframe` (API/MCP). Chưa có: form chọn reframe trong giao diện web và preset reframe theo tỉ lệ đích có sẵn |

### 7. Export

| Tính năng | Status | Verification | Ghi chú |
|---|---|---|---|
| Export H.264 + phụ đề đốt vào, draft 720p | works | Linux VM | Lỗi filter dấu `:` trên Windows đã sửa ở Phase 7 nhưng người dùng chưa xác nhận lại trên Windows thật |
| Export preset đủ 10 mục gốc | partial | Linux VM | TikTok/Reels/Shorts 8 Mbps, Feed 4:5 5 Mbps, Square, Portrait 3:4, YouTube 1080p 12 Mbps, YouTube 4K 45 Mbps, Quick Draft 720p 4 Mbps, ProRes 422 HQ (prores_ks, .mov); preset lạ báo lỗi, không rơi về H.264 lặng; render 4K và ProRes đầy đủ CHƯA chạy (chỉ assert mapping + render youtube1080/quickdraft) — cần kiểm tra trên Windows thật |
| OTIO export/import, batch export | works | Linux VM | Import OTIO merge có backup trước khi ghi (Phase 0); file media thiếu được liệt kê, không bịa |
| Review workflow (run/accept/verify + các công cụ con) | works | Linux VM | run/accept/verify thật, không bịa verdict; các công cụ review con (compare/coverage/layout/measure/packet/picture/shots/sync/window) trả dữ liệu từ lần review run thật, hoặc báo lỗi rõ nếu chưa chạy review |

### 8. CLI và MCP

| Tính năng | Status | Verification | Ghi chú |
|---|---|---|---|
| CLI `vibeedit` (serve, mcp, export…) | works | Linux VM | Cần kiểm tra lại trên Windows thật (đường dẫn, quyền) |
| MCP 472 công cụ (334 thao tác thật, 138 kiểm tra-và-báo-lỗi) | partial | Linux VM | Số live từ registry; UI/help đọc live từ `/api/mcp-tools`, không còn số ghi cứng trong `static/`; vòng hai chuyển thêm 29 công cụ từ báo-lỗi thành thao tác thật (knowledge 21, skills ghi 6, voice_check, app_update_check) và thêm 9 công cụ mới (caption transcribe/generate/align, media_transcribe, fonts_import, timeline_reorder thật; chat_stop/view_compare/view_safe_area báo lỗi theo thiết kế). Test quét toàn bộ registry bắt mọi công cụ mồ côi (có mô tả mà không có handler) |
| Các tên gốc còn thiếu sau đợt full-parity vòng hai | missing — planned to port | Đọc source gốc | Voice provider — tạo/clone giọng (10 công cụ; chỉ mới có `voice_check` kiểm tra thật backend đã cài và số voiceover take); app updater (update/later/skip — chưa có updater nào được cấu hình; chỉ mới có `app_update_check` trả trạng thái thật); model segmentation học sâu cho cutout tốt hơn; dời marker khi move clip và khi close_gaps; panel giao diện cho các tính năng mới (knowledge/skills/vision/plugin install/reframe/link/magnetic — hiện mới có API/MCP/server op). Các công cụ này hiện trả lỗi `NOT_AVAILABLE` kèm lý do và hướng port, không trả thành công giả. Riêng `chat.stop`, `view.compare`, `view.safe-area` giữ nguyên là công cụ báo lỗi theo thiết kế: không có chat session nào để dừng (bản gốc cũng đã gỡ panel model-API), còn Compare và Safe-area đã có sẵn dưới dạng điều khiển trong giao diện web — MCP headless không có viewer để bật/tắt |
| Kho kiến thức / skill cho agent (knowledge/skills store) | works | Linux VM | Knowledge store đã hoạt động (vòng hai): lessons/facts/prefs/claims/proposals/memo/history/verdicts/revert/migrate, lưu trong chính project data (đi cùng save/backup/undo), nội dung đều do người gọi cung cấp, không bịa lesson/fact nào; 21 công cụ MCP thật + server op `knowledge` theo action. Skills đã đủ cả đọc và ghi: list/get/search + save (header provenance User-written, từ chối ghi đè nếu không có overwrite), enable/disable (state `skills.json`), export nguyên văn, remove (cần confirm=true), propose (bản nháp dưới `proposals/`, không liệt kê thành skill hoạt động). `windows/skills/` có 4 skill (1 skill gốc chép nguyên văn `loudness-check` từ cây gốc, 3 skill ghi rõ là suy ra từ tài liệu gốc). Giới hạn: proposal không tự duyệt — cần approve tường minh |
| Terminal cho agent trong app (in-app LLM terminal) | works (parity by design) | Đọc source gốc | Bản gốc cũng KHÔNG có chat LLM trong app (panel model-API đã bị gỡ trong `AgentDockModel.swift`; agent chạy trong terminal nhúng Claude/Codex/Shell) — tương đương trên Windows là terminal/VS Code ngoài nối qua MCP; không phải tính năng thiếu |

### 9. Plugins

| Tính năng | Status | Verification | Ghi chú |
|---|---|---|---|
| 2 plugin mẫu, áp plugin, liệt kê, bật/tắt, quét lại | works | Linux VM | Tắt plugin nay được `apply_plugin` thực thi (sửa ở code-gap batch 2); trạng thái lưu ở `windows/plugins.json` |
| Cài plugin từ URL/bundle, cập nhật plugin | partial | Linux VM | Cài đặt đã hoạt động: folder hoặc .zip, manifest kiểm tra trước khi copy (từ chối id không an toàn, traversal, symlink, bundle nhiều thư mục, >50 MiB, trùng id), cài xong ở trạng thái tắt, có cảnh báo nguồn không tin cậy, không thực thi code khi cài; download URL là bước riêng cần xác nhận; remove (từ chối khi đang bật) và update-check (chỉ metadata, không fetch) đã có; plugin manifest nay được `list_plugins` phát hiện và bật/tắt được. Còn thiếu: thực thi code của plugin dạng manifest (apply báo lỗi rõ thay vì giả vờ chạy); fetch cập nhật từ registry (không có registry nào được bịa ra) |
| Vision / OCR / cutout (plugin vision gốc) | partial | Linux VM | Pipeline đã có thật qua `vision.py` + server op + công cụ MCP (OCR bằng Tesseract, detect faces bằng OpenCV Haar, cutout bằng OpenCV grabCut), nhưng chạy được chỉ khi máy đã cài backend đó; trên máy ảo Linux này cả Tesseract và OpenCV đều vắng nên các công cụ trả lỗi rõ tên backend thiếu và cách cài, không bao giờ trả kết quả giả. Còn thiếu: model segmentation học sâu tương đương mask của Apple Vision (không bundle, không tham chiếu model nào không tồn tại); panel Vision trong giao diện web |

### 10. Tích hợp native và phát hành Windows

| Tính năng | Status | Verification | Ghi chú |
|---|---|---|---|
| Cửa sổ desktop (pywebview/WebView2, 1600×900) | partial | Linux VM (chưa chạy được pywebview) | Cần kiểm tra trên Windows thật: mở cửa sổ, HiDPI, các kích thước cửa sổ thông dụng |
| Tắt app sạch (server dừng cùng cửa sổ) | works | Linux VM | Phase 2: `shutdown_server` (shutdown + server_close + join thread) trên mọi đường thoát (đóng cửa sổ, Ctrl+C, lỗi); cổng được ràng buộc lại ngay sau khi tắt — đã kiểm chứng bằng test và smoke. Cần kiểm tra lại trên Windows thật (cửa sổ pywebview thật) |
| Launcher `.bat`/`.ps1` (chạy, cập nhật bằng git pull, desktop) | partial | Linux VM (chưa chạy trên Windows) | Launcher đã chấp nhận FFmpeg ở 3 vị trí (VIBEEDIT_FFMPEG_DIR, PATH, cạnh app); người dùng cần chạy thử trên Windows thật |
| Phím tắt chuẩn Windows (Ctrl thay Command) | works | Linux VM | Phase 2: Ctrl+Z hoàn tác, Ctrl+Shift+Z/Ctrl+Y làm lại, Ctrl+S lưu qua endpoint `/api/save`; phím một chữ cái bỏ qua khi giữ Ctrl nên Ctrl+S không còn tách clip vô tình. Cần kiểm tra lại trong trình duyệt Windows thật |
| Bộ cài / .exe cho máy Windows sạch (bundle runtime + FFmpeg/FFprobe) | missing — planned to port | Đọc source gốc | Workflow `build-windows.yml` đã có sẵn ở máy phát triển (Phase 6) nhưng CHƯA có trong repo (đẩy workflow qua GitHub App bị chặn 403) và CHƯA từng chạy; người dùng cần đẩy file này bằng git thật hoặc giao diện web GitHub, rồi tải .exe từ lần chạy Actions xanh; chưa kiểm tra điều khoản phân phối của FFmpeg bundle |
| Windows CI (build + test trên runner Windows) | missing — planned to port | — | Cùng file workflow trên; chưa có CI Windows nào trong repo; CI của cây Swift gốc không phải CI Windows |
| Test chạy được trên Windows (không giả định `python3`, đường dẫn POSIX) | partial | Linux VM | Phase 2 đã sửa: subprocess `python3` duy nhất đổi sang `sys.executable`, đầu file test ghi rõ lệnh `py` trên Windows. Còn thiếu: chưa từng chạy toàn bộ suite bằng `py` trên Windows thật |

## Những gì KHÔNG phải là tính năng thiếu

- Chat LLM trong app: bản gốc cũng không có (xem mục 8).
- Catalogue giọng nói có sẵn trong app: bản gốc cũng không có — giọng đi
  qua plugin provider (xem mục 4).
- "Hoàn thành 100%" theo nghĩa không còn gì để làm: mục tiêu là port đầy
  đủ, và bảng này chính là danh sách việc còn lại; bất kỳ báo cáo nào nói
  "đã xong" mà không đối chiếu bảng này đều là phóng đại.
