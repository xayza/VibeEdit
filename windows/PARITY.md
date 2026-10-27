# VibeEdit — Bảng parity: bản gốc macOS (BashCut) so với bản Windows

Mục tiêu sản phẩm là **chuyển TOÀN BỘ BashCut gốc macOS thành ứng dụng
Windows mang tên VibeEdit** — không giới hạn ở MVP hay Giai đoạn 1, và
không chủ động bỏ tính năng nào của bản gốc. Vì vậy mọi tính năng gốc
còn thiếu trong bảng này đều ghi trạng thái
**`missing — planned to port`** kèm hướng port khả thi trên Windows nếu
đã biết. Không có tính năng gốc nào bị ghi là "out of scope" hay
"not planned" ở đây.

Trạng thái hiện tại (đợt Phase 0, sau code-gap batch 2):
**MCP 144/249 công cụ gốc** (số live đọc từ `/api/mcp-tools` trong app;
số trong tài liệu này là số tại thời điểm viết và sẽ cũ đi khi thêm
công cụ mới — app luôn là nguồn đúng nhất).

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
| Magnetic di chuyển cả khối (block-move) + âm thanh gắn liền (linked audio) | missing — planned to port | Đọc source gốc | Hướng port: khi di chuyển một clip trên Main, các clip sau trên cùng track dời theo, và audio Dialogue gắn với clip video dời cùng; cần giữ nguyên hành vi undo và kiểm tra overlap |
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

### 6. Effects và màu

| Tính năng | Status | Verification | Ghi chú |
|---|---|---|---|
| LUT (.cube), preset màu, adjustment layer | works | Linux VM | LUT strength 0–1; preset strength riêng |
| Thanh trượt màu từng thông số | works | Linux VM | Brightness −1–1, contrast 0–2, saturation 0–3, gamma 0.1–10 qua `eq=`; hẹp hơn model gốc (Exposure −10–10, Contrast 0–4, Saturation 0–4) — cần mở rộng sau nếu render vẫn ổn |
| Keyframes (opacity, scale, tilt, zoompan, vị trí) | works | Linux VM | Render thật; keyframes main-track và overlay still-image đều render |
| Đường cong tốc độ (speed curves) | works | Linux VM | Đủ 6 preset gốc (montage/hero/bullet/jump-cut/flash-in/flash-out) theo đúng điểm trong `SpeedCurve.swift`, tách clip + tốc độ từng đoạn; chưa có đường cong tự vẽ tay |
| Đảo ngược clip (reverse), đóng băng khung hình (freeze) | works | Linux VM | Render thật bằng `reverse`/`areverse` và frame-hold |
| Transition xfade thông dụng + 8 loại mới | partial | Linux VM | Thêm shutter, double-exposure, seamless/infinite/crash-zoom, blur, flash/blink, roll; `dissolve` nay map đúng `dissolve` |
| Transition dạng motion-only (spin, swing/arc, diamond, kaleidoscope, crash-out, infinite-out) | missing — planned to port | Đọc source gốc | FFmpeg xfade không có các loại này; hướng port: filter tùy chỉnh hoặc render chuyển động trước rồi ghép, và cho tới lúc đó phải báo lỗi rõ chứ không thay thế lặng bằng loại khác |
| Reframe / crop theo preset | missing — planned to port | Đọc source gốc | Hướng port: crop/scale theo tỉ lệ đích trong render, giữ nguyên clip gốc |

### 7. Export

| Tính năng | Status | Verification | Ghi chú |
|---|---|---|---|
| Export H.264 + phụ đề đốt vào, draft 720p | works | Linux VM | Lỗi filter dấu `:` trên Windows đã sửa ở Phase 7 nhưng người dùng chưa xác nhận lại trên Windows thật |
| Export preset đủ 10 mục gốc | partial | Linux VM | TikTok/Reels/Shorts 8 Mbps, Feed 4:5 5 Mbps, Square, Portrait 3:4, YouTube 1080p 12 Mbps, YouTube 4K 45 Mbps, Quick Draft 720p 4 Mbps, ProRes 422 HQ (prores_ks, .mov); preset lạ báo lỗi, không rơi về H.264 lặng; render 4K và ProRes đầy đủ CHƯA chạy (chỉ assert mapping + render youtube1080/quickdraft) — cần kiểm tra trên Windows thật |
| OTIO export/import, batch export | works | Linux VM | Import OTIO merge có backup trước khi ghi (Phase 0); file media thiếu được liệt kê, không bịa |
| Review workflow (run/accept/verify) | partial | Linux VM | run/accept/verify thật, không bịa verdict; các công cụ review còn lại của bản gốc thuộc nhóm ~105 tên MCP còn thiếu bên dưới |

### 8. CLI và MCP

| Tính năng | Status | Verification | Ghi chú |
|---|---|---|---|
| CLI `vibeedit` (serve, mcp, export…) | works | Linux VM | Cần kiểm tra lại trên Windows thật (đường dẫn, quyền) |
| MCP 144/249 công cụ gốc | partial | Linux VM | Số live từ registry; UI/help nay đọc live từ `/api/mcp-tools`, không còn số ghi cứng trong `static/` (Phase 0 sửa cả chỗ "106 tools" còn sót trong đoạn capabilities) |
| ~105 tên công cụ MCP còn lại của bản gốc | missing — planned to port | Đọc source gốc | Bao gồm kho kiến thức/skill (21+8 công cụ), phần còn lại của review workflow, library/brand panels, plugin browse/install/updates; port theo từng nhóm, mỗi công cụ phải gọi thao tác Project/export thật, không tạo công cụ giả |
| Kho kiến thức / skill cho agent (knowledge/skills store) | missing — planned to port | Đọc source gốc | Hướng port: skill của agent-kit gốc dưới dạng markdown local + endpoint kho skill; chưa có model/nhị phân nào trong repo |
| Terminal cho agent trong app (in-app LLM terminal) | works (parity by design) | Đọc source gốc | Bản gốc cũng KHÔNG có chat LLM trong app (panel model-API đã bị gỡ trong `AgentDockModel.swift`; agent chạy trong terminal nhúng Claude/Codex/Shell) — tương đương trên Windows là terminal/VS Code ngoài nối qua MCP; không phải tính năng thiếu |

### 9. Plugins

| Tính năng | Status | Verification | Ghi chú |
|---|---|---|---|
| 2 plugin mẫu, áp plugin, liệt kê, bật/tắt, quét lại | works | Linux VM | Tắt plugin nay được `apply_plugin` thực thi (sửa ở code-gap batch 2); trạng thái lưu ở `windows/plugins.json` |
| Cài plugin từ URL/bundle, cập nhật plugin | missing — planned to port | Đọc source gốc | Hướng port: copy an toàn vào `windows/plugins/` kèm cảnh báo, kiểm tra manifest trước khi bật; chưa làm vì cần cơ chế copy an toàn, không bịa cài đặt |
| Vision / OCR / cutout (plugin vision gốc) | missing — planned to port | Đọc source gốc | Hướng port: OpenCV/Tesseract/ONNX — cần cài model/thư viện ngoài repo, không commit nhị phân/model vào repo; cho tới lúc đó panel Vision ghi rõ chưa có |

### 10. Tích hợp native và phát hành Windows

| Tính năng | Status | Verification | Ghi chú |
|---|---|---|---|
| Cửa sổ desktop (pywebview/WebView2, 1600×900) | partial | Linux VM (chưa chạy được pywebview) | Cần kiểm tra trên Windows thật: mở cửa sổ, HiDPI, các kích thước cửa sổ thông dụng |
| Tắt app sạch (server dừng cùng cửa sổ) | partial | Linux VM | Chưa có `server.shutdown()` tường minh khi đóng cửa sổ — cần kiểm tra và sửa trên Windows thật |
| Launcher `.bat`/`.ps1` (chạy, cập nhật bằng git pull, desktop) | partial | Linux VM (chưa chạy trên Windows) | Launcher đã chấp nhận FFmpeg ở 3 vị trí (VIBEEDIT_FFMPEG_DIR, PATH, cạnh app); người dùng cần chạy thử trên Windows thật |
| Phím tắt chuẩn Windows (Ctrl thay Command) | partial | Linux VM | Phím S tách tại playhead đã có; chuẩn hóa Ctrl toàn app chưa làm — thuộc giai đoạn Windows-isation |
| Bộ cài / .exe cho máy Windows sạch (bundle runtime + FFmpeg/FFprobe) | missing — planned to port | Đọc source gốc | Workflow `build-windows.yml` đã có sẵn ở máy phát triển (Phase 6) nhưng CHƯA có trong repo (đẩy workflow qua GitHub App bị chặn 403) và CHƯA từng chạy; người dùng cần đẩy file này bằng git thật hoặc giao diện web GitHub, rồi tải .exe từ lần chạy Actions xanh; chưa kiểm tra điều khoản phân phối của FFmpeg bundle |
| Windows CI (build + test trên runner Windows) | missing — planned to port | — | Cùng file workflow trên; chưa có CI Windows nào trong repo; CI của cây Swift gốc không phải CI Windows |
| Test chạy được trên Windows (không giả định `python3`, đường dẫn POSIX) | partial | Linux VM | Một số test còn ghi `python3` và giả định POSIX; cần sửa sang `sys.executable` và tách test cần socket/FFmpeg khỏi test đơn vị thuần |

## Những gì KHÔNG phải là tính năng thiếu

- Chat LLM trong app: bản gốc cũng không có (xem mục 8).
- Catalogue giọng nói có sẵn trong app: bản gốc cũng không có — giọng đi
  qua plugin provider (xem mục 4).
- "Hoàn thành 100%" theo nghĩa không còn gì để làm: mục tiêu là port đầy
  đủ, và bảng này chính là danh sách việc còn lại; bất kỳ báo cáo nào nói
  "đã xong" mà không đối chiếu bảng này đều là phóng đại.
