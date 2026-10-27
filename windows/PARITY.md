# VibeEdit — Bảng parity: bản gốc macOS (BashCut) so với bản Windows

Mục tiêu sản phẩm là **chuyển TOÀN BỘ BashCut gốc macOS thành ứng dụng
Windows mang tên VibeEdit** — không giới hạn ở MVP hay Giai đoạn 1, và
không chủ động bỏ tính năng nào của bản gốc. Vì vậy mọi tính năng gốc
còn thiếu trong bảng này đều ghi trạng thái
**`missing — planned to port`** kèm hướng port khả thi trên Windows nếu
đã biết. Không có tính năng gốc nào bị ghi là "out of scope" hay
"not planned" ở đây.

Trạng thái hiện tại (đợt full-parity vòng 5, sau vòng 4):
**MCP 479 công cụ** (số live đọc từ `/api/mcp-tools` trong app; số
trong tài liệu này là số tại thời điểm viết và sẽ cũ đi khi thêm công
cụ mới — app luôn là nguồn đúng nhất). Trong 479 công cụ có **359
công cụ thao tác thật** và **120 công cụ kiểm tra-và-báo-lỗi trung
thực** (trả lỗi `NOT_AVAILABLE` kèm lý do và hướng port, không bao giờ
trả thành công giả). Vòng 5 chuyển thêm 12 công cụ từ báo-lỗi thành
thao tác thật so với vòng 4 (xem mục 8) mà không thêm công cụ mới nào
nên tổng giữ 479. Về tên gốc: **cả 249 spec gốc đều có tên tương
ứng trong registry** theo cách đếm đã kiểm chứng bằng test
(`tests/test_round3_parity.py`: trích spec từ
`CommandCatalog*.swift` bằng regex đa dòng — grep một dòng chỉ tìm
được 7 vì spec viết nhiều dòng — rồi chuẩn hóa dấu `.` và `-` thành
`_`, thêm tiền tố `vibeedit_`; vòng 5 chạy lại test này và vẫn đủ
249 tên). 4 tên khác với tên Windows chính
(`beats.detect`, `clip.speed-curve`, `transcript.words`,
`library.save-selection`) được bao phủ bằng alias thật trỏ về handler
thật, theo đúng tiền lệ handler dùng chung của bản gốc
(`voice.speak`/`voice.lines` cùng handler `voice.synthesize`);
vòng 5 thêm 2 alias thật nữa (`media.ocr` → `vision.text`,
`media.subjects` → `vision.faces`).
Đây là bao phủ **tên**, không phải tuyên bố 249 hành vi gốc khác biệt
— các alias dùng chung handler, và các giới hạn thật còn lại vẫn liệt
kê ở mục 8 bên dưới. Test: **454 tests OK** trên Linux VM (404 trước
vòng năm + 50 test vòng năm mới: 14 công cụ MCP, 20 desktop, 14 nút
chết giao diện, 2 đường dẫn skills khi đóng băng).

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
trong đợt này.** Kế hoạch từng bước để người dùng thực hiện bằng git
thật trên Windows nằm ở [`MERGE_PLAN.md`](MERGE_PLAN.md) (viết ở vòng
bốn, chỉ chuẩn bị chứ không thực hiện). Khi tới bước đó, phải làm đủ
các kiểm tra sau, theo đúng thứ tự, trước khi dọn cấu trúc cũ:

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
| Snap, marker, đóng khoảng trống (close gaps) | works | Linux VM | Close gaps đưa clip đầu về frame 0; marker dời theo cả khi close_gaps (marker trong clip dời cùng clip, marker trong gap co về đầu clip kế tiếp, marker sau clip cuối giữ nguyên) |
| Magnetic di chuyển cả khối (block-move) trên Main | works | Linux VM | Xóa/chèn/di chuyển/trim cuối trên Main dời các clip sau theo, không để gap, không overlap, có undo; tắt được bằng `magnetic_set` (mặc định bật). Reorder (đổi thứ tự khối) đã có từ vòng hai: `reorder_main` dời clip tới trước một clip khác hoặc xuống cuối, các clip ở giữa dời theo cùng linked audio, không đổi duration. Marker nay dời theo khi chèn/xóa/trim cuối magnetic trên Main (marker trong đoạn bị xóa/trim co về đầu đoạn) và từ vòng ba: khi move clip (marker trong span của clip dời theo clip, marker ngoài span giữ nguyên; move magnetic trên Main dời cả clip lẫn follower) và khi reorder (map một lần từ vị trí gốc, tránh lỗi dời kép). Giới hạn còn lại: ripple chỉ từ thao tác trực tiếp, kéo audio gắn liền không ripple toàn timeline |
| Âm thanh gắn liền (linked audio) | works | Linux VM | `link_audio`/`unlink_audio` lưu `linked_audio` + `linked_video` hai chiều; di chuyển/trim/tách video kéo audio theo cùng delta, tách video tách audio cùng điểm; xóa video xóa luôn audio gắn liền, xóa audio thì video còn lại và bị unlink (đúng tính không đối xứng của bản gốc); thao tác làm audio va chạm bị từ chối toàn bộ, dữ liệu không đổi. Giới hạn: ghi đè lên chính clip audio gắn liền bị từ chối (phải unlink trước); audio của clip bị ghi đè mà không căn khớp chính xác cũng bị từ chối thay vì bịa thời gian |
| Track đổi tên / xóa track | works | Linux VM | Xóa từ chối track Main và track còn clip |

### 3. Preview

| Tính năng | Status | Verification | Ghi chú |
|---|---|---|---|
| Xem file gốc, xem bản xuất gần nhất, Fit, Safe-area | works | Linux VM | Xem nguồn qua `GET /api/media/<id>` (Range 206, chỉ file trong project) |
| Compare nguồn / bản xuất | works (với giới hạn đồng bộ) | Linux VM (chưa nhìn thấy trên trình duyệt Windows thật) | Vòng bốn: wipe có mặt nạ thật — một khung hình duy nhất, Before ở trái vạch chia, After ở phải vạch chia, kéo vạch hoặc thanh trượt để so sánh; hai `<video>` đồng bộ thời gian qua sự kiện play/pause/seek/timeupdate (lệch >0,3s thì đồng bộ lại), KHÔNG khóa khung hình tuyệt đối ở mức mẫu (trình duyệt không khóa được hai decoder riêng) — ghi rõ trong giao diện, không tuyên bố khác. Bản gốc cũng chỉ có overlay xem Compare, chưa có công cụ Compare độc lập |
| Xem trước transition (ảnh tĩnh giữa transition) | works | Linux VM | Render thật bằng renderer, không phải ảnh giả |

### 4. Audio

| Tính năng | Status | Verification | Ghi chú |
|---|---|---|---|
| Âm lượng, fade từng clip (0–5s), ducking nhạc dưới giọng nói, loudnorm | works | Linux VM | Ducking mặc định bản gốc: level −14, attack 3, release 8 |
| Sóng âm (waveform) thật, beat grid, snap theo beat | works | Linux VM | Waveform giải mã thật bằng FFmpeg; file không giải mã được báo 400, không vẽ hình giả |
| Import và đặt voiceover take lên track Voiceover | works | Linux VM | Tạo track Voiceover nếu chưa có |
| Thu voiceover trong app | works (cần kiểm chứng micro trên Windows thật) | Linux VM (endpoint + giao diện) | Vòng bốn: panel Voice ghi âm bằng MediaRecorder/getUserMedia của trình duyệt (quyền micro do trình duyệt hỏi; bị từ chối thì báo rõ, không tạo file giả), bản ghi tải lên `POST /api/voiceover/record` — chỉ nhận audio, tên duy nhất không ghi đè, đăng ký thành media audio thật và đặt lên track Voiceover bằng đúng form voiceover sẵn có. Chưa có micro trên máy ảo Linux nên bước ghi âm thật bằng micro chỉ mới kiểm chứng ở mức endpoint (blob audio thật) và nối giao diện — cần người dùng thử micro trên Windows thật |
| Nhân bản giọng (voice clone) | missing — planned to port | Đọc source gốc | Clone cần model của provider clone; bản gốc dùng provider on-device và không có model nào như vậy trong cả hai cây. Các nút clone vẫn ghi rõ là chưa có, không tạo giọng giả |
| Tạo giọng nói (voice generation: Edge TTS / Piper) | partial | Linux VM | Vòng ba: `voice.py` mới — Edge TTS qua module `edge-tts` hoặc Piper qua binary + model `.onnx` (model do người dùng chỉ đường, không bundle, không bịa model mặc định); thiếu cả hai backend thì báo rõ cách cài cả hai; `voice_synthesize`/`lines`/`place`/`use`/`fit` và alias `voice_speak` đều là công cụ thật, panel Voice đã nối tới op thật (`voice_generate`...). Chưa kiểm chứng tổng hợp giọng thật ở đâu (cả hai backend đều vắng trên máy ảo Linux này) — chỉ mới kiểm chứng đường báo lỗi thiếu backend và giao diện; thu trong app và clone vẫn chưa có (clone cần model của provider clone, bản gốc dùng provider on-device) |

### 5. Captions và chữ

| Tính năng | Status | Verification | Ghi chú |
|---|---|---|---|
| SRT import/export, karaoke highlight từng chữ (.ass `\k`), preset chữ | works | Linux VM | Preset: bold-outline, cinematic-serif, keyword-sticker, place-card, hook-title, chapter-card |
| Phụ đề tự động (transcription) | partial | Linux VM | Chỉ chạy khi máy đã cài faster-whisper (mặc định tiny); chưa cài thì báo rõ, không tạo phụ đề giả |
| Caption transcribe/generate/align thành công cụ MCP | partial | Linux VM | Vòng hai: `captions_transcribe`/`media_transcribe` chạy transcribe thật vào text track; `captions_generate` transcribe rồi trả SRT thật; `captions_align` snap timing của caption về segment giọng nói đã detect (mapping thuần đã có test riêng). Tất cả đều báo lỗi rõ khi máy chưa cài faster-whisper, không đổi timing, không bịa phụ đề |
| Font import | works | Linux VM | Vòng hai: import .ttf/.otf vào thư mục fonts của app (tên duy nhất, không ghi đè, từ chối đuôi khác); font đã import trở thành candidate cho renderer và xuất hiện trong `fonts_list` |
| Voice check / app update check | partial | Linux VM | Vòng hai: `voice_check` kiểm tra thật (piper binary, edge-tts module, số voiceover take trong project đang mở); `app_update_check` trả trạng thái thật (version hiện tại, chưa có kênh updater). Vòng ba: tạo giọng đã nối thật (xem mục 4); updater nay có khung check/download/verify (`updater.py`, kênh lấy từ biến môi trường `VIBEEDIT_RELEASES_URL` hoặc file `updater.json` cạnh module — mặc định chưa cấu hình nên chỉ trả trạng thái, không bịa URL; download verify SHA-256 và không bao giờ tự chạy file tải về; `app_update_download` là công cụ thật). Vòng bốn: thêm `prepare_update` + công cụ `app_update_prepare` — download + verify SHA-256 + ghi script handoff `vibeedit-update-run.bat` (chờ PID của app thoát qua vòng lặp tasklist rồi mới chạy installer; script chỉ được ghi ra, không bao giờ tự chạy; nội dung script được test bằng cách đọc file, không chạy trên Linux). Còn thiếu: bản thân việc thay app đang chạy (app không tự thay chính nó — người dùng vẫn phải thoát app rồi double-click script handoff), và vị trí releases thật của VibeEdit (chưa có — người dùng phải chọn); `app_update_later`/`skip` vẫn là công cụ báo lỗi (defer là tùy chọn giao diện, chưa có kênh) |

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
| Transition halftone | works | Linux VM (render thật, clip tổng hợp 320×180) | Vòng bốn: render thật hai đường. (1) Timeline: mask chấm động bằng filter geq (chấm trong mỗi ô 24px lớn dần theo tiến trình, tới khung cuối thì phủ kín ô) + `alphamerge`/`overlay` để chọn cứng (không pha): khung giữa transition chứa cả pixel đỏ thuần và xanh thuần chưa pha — tiêu chí này loại trừ dissolve/cut/pixelize giả mạo. Lưu ý thật: `maskedmerge` đã thử trước và bị loại vì ngay cả trong RGB với mask nhị phân nó vẫn cho khung pha tím trên FFmpeg 8.1.2, không chọn cứng. (2) Segment độc lập: `render_halftone_segment()` dựng khung bằng Pillow rồi encode bằng FFmpeg (đường pre-rendered segment mà vòng ba đã vạch ra). `add_transition` nay chấp nhận halftone; pixelize không bao giờ bị thay thế lặng. Còn cần kiểm chứng: chất lượng halftone trên footage thật và khung hình lớn trên Windows thật (render VM mới ở 320×180) |
| Reframe / crop theo preset | partial | Linux VM | Render-side đã hoạt động: `reframe` trên clip (cửa sổ phân số khung hình nguồn) crop trước khi scale, không stretch, cửa sổ sai báo lỗi; dùng qua `add_clip`/`clip_reframe` (API/MCP). Chưa có: form chọn reframe trong giao diện web và preset reframe theo tỉ lệ đích có sẵn |

### 7. Export

| Tính năng | Status | Verification | Ghi chú |
|---|---|---|---|
| Export H.264 + phụ đề đốt vào, draft 720p | works | Linux VM | Lỗi filter dấu `:` trên Windows đã sửa ở Phase 7 nhưng người dùng chưa xác nhận lại trên Windows thật |
| Export preset đủ 10 mục gốc | partial | Linux VM | TikTok/Reels/Shorts 8 Mbps, Feed 4:5 5 Mbps, Square, Portrait 3:4, YouTube 1080p 12 Mbps, YouTube 4K 45 Mbps, Quick Draft 720p 4 Mbps, ProRes 422 HQ (prores_ks, .mov); preset lạ báo lỗi, không rơi về H.264 lặng; vòng ba đã chạy render thật trên máy ảo Linux với clip tổng hợp 1s: youtube4k ra 3840×2160 H.264 High (target 45 Mbps, thực tế ~25,8 Mbps cho clip test ngắn) và proRes422HQ ra .mov ProRes profile HQ ở đúng kích thước project (preset ProRes giữ kích thước project theo thiết kế). Giới hạn thật: clip nguồn chỉ 320×180 nên bản 4K là upscale, chưa phải footage 4K gốc; vẫn cần kiểm tra trên Windows thật với footage thật |
| OTIO export/import, batch export | works | Linux VM | Import OTIO merge có backup trước khi ghi (Phase 0); file media thiếu được liệt kê, không bịa |
| Review workflow (run/accept/verify + các công cụ con) | works | Linux VM | run/accept/verify thật, không bịa verdict; các công cụ review con (compare/coverage/layout/measure/packet/picture/shots/sync/window) trả dữ liệu từ lần review run thật, hoặc báo lỗi rõ nếu chưa chạy review |

### 8. CLI và MCP

| Tính năng | Status | Verification | Ghi chú |
|---|---|---|---|
| CLI `vibeedit` (serve, mcp, export…) | works | Linux VM | Cần kiểm tra lại trên Windows thật (đường dẫn, quyền) |
| MCP 479 công cụ (359 thao tác thật, 120 kiểm tra-và-báo-lỗi) | partial | Linux VM | Số live từ registry; UI/help đọc live từ `/api/mcp-tools`, không còn số ghi cứng trong `static/`; vòng ba chuyển thêm 6 công cụ giọng từ báo-lỗi thành thao tác thật (synthesize/speak/lines/use/fit/place) và thêm 6 công cụ mới (4 alias tên gốc, `app_update_download`, `vision_cutout_model`); vòng bốn thêm 1 công cụ thật (`app_update_prepare`); vòng năm chuyển thêm 12 công cụ từ báo-lỗi thành thật mà không thêm công cụ mới: `app_update_later`/`app_update_skip` (ghi lựa chọn hoãn/bỏ qua version vào `updater.json`, hoạt động cả khi chưa cấu hình kênh), `library_search` (tìm trong library của project), `plugins_search`/`plugins_run`/`plugins_invoke` (tìm plugin local; chạy đúng hook đã khai báo của plugin đang bật qua `apply_plugin`), `media_ocr`/`media_subjects` (alias của `vision_text`/`vision_faces` đã thật), `vision_cutout` (chỉ sửa mô tả — handler đã thật từ trước nhưng mô tả vẫn ghi "Not available"), `media_analysis`/`media_analyze` (metadata + ffprobe trực tiếp), `media_proxy` (transcode proxy H.264 theo chiều rộng cho trước, là file dẫn xuất chứ không đăng ký thành media timeline). 120 công cụ còn lại chia 3 nhóm: (a) kiểm tra theo thiết kế — headless MCP không có viewer/session trực tiếp nên các công cụ chat trong app, dialog `show_*`, điều khiển UI trực tiếp `ui_*`, playback, terminal agent đều báo lỗi có kiểm soát trong khi bản web hoặc agent ngoài đã có tương đương (bản gốc cũng đã gỡ panel model-API); (b) cần provider/model không tồn tại — clone giọng (3), image generate/style/disclose (4), library generate/brand_pose/pack, media describe/digest/cuts/sync/speech_map/strip, VLM cho mô tả media; (c) cần state/workflow chưa có — clip motion/backdrop/framing (cần state clip + render), outcomes store, workflow runner `run_*`, plugin view/overlay/proposal/replace, narration, music_replace, agent_kit. `app_update` (tự thay app đang chạy) vẫn báo lỗi đúng bản chất. Test quét toàn bộ registry bắt mọi công cụ mồ côi (có mô tả mà không có handler); test vòng ba bắt mọi handler mới phải báo lỗi có kiểm soát (ValueError) thay vì KeyError khi thiếu tham số; test mẫu honest trong `test_mcp_parity2.py` đã bỏ 12 tên vòng năm khỏi mẫu |
| Các tên gốc còn thiếu sau đợt full-parity vòng năm | works (bao phủ tên) — xem giới hạn | Linux VM | Rà soát lại bằng regex đa dòng (test vòng ba chạy lại ở vòng năm, vẫn đủ): cả 249 spec gốc đều có tên tương ứng trong registry (6 tên qua alias thật). Những gì thực sự còn chưa port xong, không còn là "tên thiếu": clone giọng (cần model provider clone), bản thân updater thay app đang chạy (vòng bốn chỉ thêm handoff: người dùng vẫn phải chọn vị trí releases thật rồi thoát app và chạy script handoff bằng tay; vòng năm chỉ thêm hoãn/bỏ qua version — `later`/`skip` thật, không phải tự thay app), thực thi model segmentation học sâu cho cutout (vòng ba chỉ thêm khe cắm backend: nhận đường dẫn model do người dùng cung cấp, thiếu model thì báo rõ tên model thiếu, có model nhưng thiếu ONNX Runtime thì báo rõ runtime thiếu, không bao giờ trả kết quả grabCut giả làm "learned"), fetch cập nhật plugin từ registry (không có registry nào được bịa ra), bộ cài/.exe + CI Windows. Đã xong ở vòng bốn, không còn trong danh sách thiếu: thu voiceover trong app, thực thi code plugin dạng manifest, transition halftone. Đã xong thêm ở vòng năm, không còn trong danh sách thiếu: hoãn/bỏ qua cập nhật (`app_update_later`/`skip`), tìm library, tìm/chạy plugin, OCR/subject qua alias vision, phân tích media bằng ffprobe, proxy media, mô tả `vision_cutout`. Riêng `chat.stop`, `view.compare`, `view.safe-area` giữ nguyên là công cụ báo lỗi theo thiết kế: không có chat session nào để dừng (bản gốc cũng đã gỡ panel model-API), còn Compare và Safe-area đã có sẵn dưới dạng điều khiển trong giao diện web — MCP headless không có viewer để bật/tắt |
| Panel giao diện cho tính năng vòng một/vòng hai | works | Linux VM | Vòng ba đã nối panel thật, không còn nút chết: Knowledge & Skills (list/get/enable/disable/remove có confirm/save/propose draft/add lesson), Vision (OCR/faces/cutout/learned-model — thiếu backend thì báo rõ, không trả kết quả giả), cài plugin (folder/.zip + download URL chỉ-download có confirm), toggle Magnetic trên thanh timeline. Vòng năm quét lại toàn bộ ~130 nút trong `index.html` + `app.js` và sửa 4 điểm chết còn sót: nút Plugins trên topbar trước đây chỉ báo "chưa có panel" sai sự thật nay cuộn tới panel Plugins thật ở cột Details; tab Source của player trước đây ẩn cả khung preview (kể cả ghi chú Source) nay giữ preview và hiện file nguồn đã chọn; panel Captions (SRT/karaoke/phiên âm) trước đây không có nút mở nào nay có nút trong panel Text; nút Write VO trong dock AGENT đổi nhãn trung thực thành "Write VO — chưa có (cần AI viết kịch bản)" thay vì bấm chỉ để báo không có. Mọi control còn lại đều gọi op server thật và được test quét (0 nút bấm-không-làm-gì, trừ nút đã ghi rõ là chưa có kèm lý do). Mọi `/api/*` và op project mà `app.js` dùng đều tồn tại trong core — không phát hiện endpoint giả nào |
| Kho kiến thức / skill cho agent (knowledge/skills store) | works | Linux VM | Knowledge store đã hoạt động (vòng hai): lessons/facts/prefs/claims/proposals/memo/history/verdicts/revert/migrate, lưu trong chính project data (đi cùng save/backup/undo), nội dung đều do người gọi cung cấp, không bịa lesson/fact nào; 21 công cụ MCP thật + server op `knowledge` theo action. Skills đã đủ cả đọc và ghi: list/get/search + save (header provenance User-written, từ chối ghi đè nếu không có overwrite), enable/disable (state `skills.json`), export nguyên văn, remove (cần confirm=true), propose (bản nháp dưới `proposals/`, không liệt kê thành skill hoạt động). `windows/skills/` có 4 skill (1 skill gốc chép nguyên văn `loudness-check` từ cây gốc, 3 skill ghi rõ là suy ra từ tài liệu gốc). Giới hạn: proposal không tự duyệt — cần approve tường minh |
| Terminal cho agent trong app (in-app LLM terminal) | works (parity by design) | Đọc source gốc | Bản gốc cũng KHÔNG có chat LLM trong app (panel model-API đã bị gỡ trong `AgentDockModel.swift`; agent chạy trong terminal nhúng Claude/Codex/Shell) — tương đương trên Windows là terminal/VS Code ngoài nối qua MCP; không phải tính năng thiếu |

### 9. Plugins

| Tính năng | Status | Verification | Ghi chú |
|---|---|---|---|
| 2 plugin mẫu, áp plugin, liệt kê, bật/tắt, quét lại | works | Linux VM | Tắt plugin nay được `apply_plugin` thực thi (sửa ở code-gap batch 2); trạng thái lưu ở `windows/plugins.json` |
| Cài plugin từ URL/bundle, cập nhật plugin | partial | Linux VM | Cài đặt đã hoạt động: folder hoặc .zip, manifest kiểm tra trước khi copy (từ chối id không an toàn, traversal, symlink, bundle nhiều thư mục, >50 MiB, trùng id), cài xong ở trạng thái tắt, có cảnh báo nguồn không tin cậy, không thực thi code khi cài; download URL là bước riêng cần xác nhận; remove (từ chối khi đang bật) và update-check (chỉ metadata, không fetch) đã có; plugin manifest nay được `list_plugins` phát hiện và bật/tắt được. Vòng ba đã nối form cài/download trong panel Templates vào op thật. Vòng bốn: thực thi code plugin dạng manifest đã hoạt động — manifest khai báo `"entry"` (tên file `.py` thuần trong thư mục plugin, không traversal) thì `load_plugins` nạp `register()` của entry và `apply_plugin` chạy đúng hook đã khai báo; plugin tắt vẫn bị từ chối trước mọi thứ, manifest hỏng hoặc entry thiếu file đều báo lỗi rõ (bundle khai báo entry mà thiếu file bị từ chối ngay khi cài, trước khi copy). Mô hình tin cậy đã ghi rõ trong code: code plugin chạy cùng quyền với app (đúng mô hình plugin của bản gốc) nên chỉ chấp nhận được vì plugin cài xong ở trạng thái tắt, người dùng phải xem file rồi bật tường minh, và chỉ hook đã khai báo trong manifest mới được chạy. Còn thiếu: fetch cập nhật từ registry (không có registry nào được bịa ra) |
| Vision / OCR / cutout (plugin vision gốc) | partial | Linux VM | Pipeline đã có thật qua `vision.py` + server op + công cụ MCP (OCR bằng Tesseract, detect faces bằng OpenCV Haar, cutout bằng OpenCV grabCut), nhưng chạy được chỉ khi máy đã cài backend đó; trên máy ảo Linux này cả Tesseract và OpenCV đều vắng nên các công cụ trả lỗi rõ tên backend thiếu và cách cài, không bao giờ trả kết quả giả. Vòng ba đã thêm panel Vision trong giao diện web (nối tới op thật) và khe cắm learned cutout: `cutout_segmented(path, model_path)` — thiếu model thì báo rõ tên model thiếu, có model nhưng thiếu ONNX Runtime thì báo rõ runtime thiếu; khi đủ cả hai mới chạy với giả định đã ghi rõ (input NCHW float, output đầu tiên là mask, ngưỡng 0,5, resize NEAREST, lưu RGBA PNG). Còn thiếu: model segmentation thật và ONNX Runtime trên máy người dùng (không bundle, không tham chiếu model nào không tồn tại) |

### 10. Tích hợp native và phát hành Windows

| Tính năng | Status | Verification | Ghi chú |
|---|---|---|---|
| Cửa sổ desktop (pywebview/WebView2, 1600×900) | partial | Linux VM (chưa chạy được pywebview) | Cần kiểm tra trên Windows thật: mở cửa sổ, HiDPI, các kích thước cửa sổ thông dụng. Vòng năm hoàn thiện thêm phía launcher (chưa có cửa sổ thật để kiểm chứng): chạy lần 2 trên cùng cổng sẽ tự mở trình duyệt tới instance đang chạy và thoát thay vì chiếm cổng mới (probe HTTP `/` bằng stdlib, không tạo lock file; cổng khác được coi là instance khác; `--project` ở lần chạy 2 bị bỏ qua kèm cảnh báo vì server đang chạy giữ project của nó); thiếu pywebview hoặc WebView2 lỗi nay rơi về trình duyệt kèm thông điệp tiếng Việt không dấu thay vì traceback; cổng ngoài 1–65535 bị từ chối trước khi bind; launcher desktop nay ưu tiên `.venv\Scripts\python.exe` khi có |
| Tắt app sạch (server dừng cùng cửa sổ) | works | Linux VM | Phase 2: `shutdown_server` (shutdown + server_close + join thread) trên mọi đường thoát (đóng cửa sổ, Ctrl+C, lỗi); cổng được ràng buộc lại ngay sau khi tắt — đã kiểm chứng bằng test và smoke. Cần kiểm tra lại trên Windows thật (cửa sổ pywebview thật) |
| Launcher `.bat`/`.ps1` (chạy, cập nhật bằng git pull, desktop) | partial | Linux VM (chưa chạy trên Windows) | Launcher đã chấp nhận FFmpeg ở 3 vị trí (VIBEEDIT_FFMPEG_DIR, PATH, cạnh app); người dùng cần chạy thử trên Windows thật |
| Phím tắt chuẩn Windows (Ctrl thay Command) | works | Linux VM | Phase 2: Ctrl+Z hoàn tác, Ctrl+Shift+Z/Ctrl+Y làm lại, Ctrl+S lưu qua endpoint `/api/save`; phím một chữ cái bỏ qua khi giữ Ctrl nên Ctrl+S không còn tách clip vô tình. Cần kiểm tra lại trong trình duyệt Windows thật |
| Bộ cài / .exe cho máy Windows sạch (bundle runtime + FFmpeg/FFprobe) | missing — planned to port | Đọc source gốc | Workflow `build-windows.yml` đã có sẵn ở máy phát triển (Phase 6) nhưng CHƯA có trong repo (đẩy workflow qua GitHub App bị chặn 403) và CHƯA từng chạy; người dùng cần đẩy file này bằng git thật hoặc giao diện web GitHub, rồi tải .exe từ lần chạy Actions xanh. Vòng ba đã sửa một defect thật trong `build_windows.bat`: trước đây chỉ cài PyInstaller trong khi bản đóng gói cần cả Pillow cho đường vision cutout (import lazy trong `vision.py`) — nay cài `pillow pyinstaller`; core editor/export không cần Pillow. Vòng năm rà lại `build_windows.bat` + `vibeedit.spec` và sửa thêm: spec trước đây quên đóng gói data `skills/` (app đóng băng sẽ liệt kê 0 skill) nay đã thêm; liệt kê rõ 16 hidden import `vibeedit_core.*` (không thêm `edge_tts`/`faster_whisper`/`onnxruntime`/`cv2` vì là backend tùy chọn vắng trong môi trường build, app sẽ báo thiếu trung thực; `webview` không thêm vì exe không phải cửa sổ desktop); sửa 1 dòng echo chứa dấu ngoặc trong block ngoặc của `build_windows.bat` (đúng họ lỗi từng làm hỏng `update_and_run.bat` v1), thêm kiểm tra file exe sau build, thông điệp FFmpeg nay nêu cả `ffmpeg.exe` + `ffprobe.exe`, xử lý lỗi `pip --upgrade` và venv hỏng; `skills.py` nay có nhánh `_MEIPASS` như `plugins.py` để app đóng băng tìm đúng thư mục skills. Chưa có .exe nào được build và chưa có CI nào chạy — không tuyên bố khác. **Giấy phép bundle FFmpeg (kiểm chứng vòng năm, từ ffmpeg.org/legal.html + LICENSE + trang gyan.dev, không phải tư vấn pháp lý):** workflow CI tải build tĩnh `ffmpeg-release-essentials` của gyan.dev và chỉ copy `ffmpeg.exe` + `ffprobe.exe` — theo gyan.dev các build này là tĩnh và **GPLv3**, không phải LGPL; vì vậy artifact không được gọi là "FFmpeg LGPL". Khi phân phối các binary đó phải kèm text GPLv3 + nguồn tương ứng cho đúng build đó (hoặc đề nghị cung cấp nguồn hợp lệ) + ghi nhận; checklist LGPL trên ffmpeg.org (không `--enable-gpl`/`--enable-nonfree`, link động DLL…) là lộ trình LGPL và KHÔNG áp dụng cho build tĩnh GPLv3 này. VibeEdit chỉ gọi ffmpeg/ffprobe qua subprocess nên nghĩa vụ gắn với binary được phân phối, không phải code Python của app. Hiện artifact còn thiếu các file licence/source offer này (workflow chưa copy, `CHECK_WINDOWS.md` mới chỉ ghi chung chung) — phải bổ sung thành bước packaging trước khi phân phối công khai; cơ chế source của gyan.dev và vấn đề patent codec (H.264…) chưa kiểm chứng được, không ghi bừa |
| Màn hình chính vừa viewport, không lăn chuột (1280×720–1920×1080, scaling 125%/150%) | partial | Linux VM (chỉ kiểm chứng bằng CSS + tính toán, chưa nhìn thấy trên Windows thật) | Vòng ba sửa theo đúng số liệu gốc đã đọc kỹ (xem ghi chú cuối bảng): cột phải 300 (340 khi viewport ≥1680) thay cho 380 cố định; cột trái 356 → 300 dưới 1161 → 280 dưới 860; timeline theo đúng ruler 22 / hàng 29 / hàng Main 46 / cách 6 và pane cao tối đa clamp(300px, 46vh, 480px) ≈ ideal 330 của bản gốc, cuộn nội bộ khi vượt; preview flex vừa pane (kiểu Fit gốc, margin thay bằng padding) thay cho sizing theo vh; rail cuộn nội bộ + tile gọn dưới 900 chiều cao (bản gốc: rail bỏ label dưới 900 và cuộn trong ScrollView; bản web dùng tile chữ nên gọn tile + cuộn nội bộ thay cho icon-only). Đã xóa block media query 1100px cũ bị xung đột — chính nó biến workbench thành dải cuộn ngang ở đúng các chiều rộng hiệu dụng khi scaling (1024/1093/911) khiến cột Inspector bị cắt ở mép phải. Dưới 780px workbench cuộn ngang là phương án cuối (bản gốc từ chối hẳn cửa sổ cỡ đó). CẦN người dùng xác nhận bằng mắt trên Windows thật sau khi pull — chưa render trình duyệt thật ở đây |
| Windows CI (build + test trên runner Windows) | missing — planned to port | — | Cùng file workflow trên; chưa có CI Windows nào trong repo; CI của cây Swift gốc không phải CI Windows |
| Test chạy được trên Windows (không giả định `python3`, đường dẫn POSIX) | partial | Linux VM | Phase 2 đã sửa: subprocess `python3` duy nhất đổi sang `sys.executable`, đầu file test ghi rõ lệnh `py` trên Windows. Còn thiếu: chưa từng chạy toàn bộ suite bằng `py` trên Windows thật |

## Ghi chú: số liệu bố cục gốc dùng cho bản sửa viewport vòng ba

Đọc kỹ từ cây Swift gốc (chỉ đọc, không sửa):
`Views/EditorView+Layout.swift` (rail 54, library 300–520 mặc định 372
trên màn hình ≥1680 còn không thì 300, viewer tối thiểu 260, cột
editor tối thiểu 860, Inspector 300 / 340 từ cửa sổ ≥1680, timeline
tối thiểu 170 / lý tưởng 330, cửa sổ tối thiểu cao 600, rộng 860 hoặc
1161 khi có cột agent), `EditorView+Rail.swift` (dưới 900 chiều cao
rail bỏ label, label thành tooltip, rail vẫn cuộn), `EditorView+
Toolbar.swift` (cửa sổ hẹp gấp các mục cuối toolbar vào menu ☰ bằng
ViewThatFits thay vì đẩy hàng xuống hay đẩy nội dung ra ngoài),
`EditorView+Viewer.swift` (Fit giữ margin 24, vừa pane, không cuộn ở
chế độ Fit; Compare gốc là player thứ hai mask nửa trái + vạch chia
và nhãn Before/After — bản web đang dùng hai player cạnh nhau, đã ghi
rõ là không khóa khung hình và không phải masked wipe),
`SourceViewer.swift` (In/Out + Insert E / Overwrite Q),
`InspectorView.swift` + `+Speed` (cột Inspector cuộn nội bộ; control
số gồm label + ô 60–70 + slider bên dưới) + `+Crop`,
`WelcomeView.swift` (cột trái tối đa 440 + padding 40, cột recent tối
thiểu 240 / lý tưởng 480 / tối đa 480 + padding 32, welcome tối thiểu
rộng 560), `RecentProjectsView.swift` (danh sách cuộn nội bộ, tối đa
cao 420), `Core/Services/EditorUIState.swift` (mặc định hiện library
panel và agent dock), `Views/Timeline/TimelineLayout.swift` (ruler 22,
hàng 29, hàng Main 46, cách hàng 6, footer 22).
Quy đổi: 1pt = 1 CSS px ở scale 100% (điểm AppKit map 1:1 sang CSS px;
Windows scaling 125%/150% làm viewport CSS nhỏ lại nên các breakpoint
kích hoạt đúng khi cửa sổ hiệu dụng thu nhỏ — cùng điều kiện với
chiều rộng cột theo cửa sổ của bản gốc). Hành vi khi cửa sổ nhỏ của
bản gốc được giữ tương đương: cửa sổ không thu dưới minSize (bản web
không ép được kích thước cửa sổ nên dùng bậc cột 356→300→280 và
workbench cuộn ngang chỉ dưới 780px làm phương án cuối); panel có thể
ẩn (bản gốc) tương đương với cuộn nội bộ từng panel (bản web); rail
gọn + cuộn nội bộ; toolbar gấp mục (bản gốc) tương đương với topbar
và player-head wrap hàng (bản web, không cắt nội dung); timeline giữ
chiều cao lý tưởng và canvas cuộn nội bộ; viewer Fit vừa pane.

## Những gì KHÔNG phải là tính năng thiếu

- Chat LLM trong app: bản gốc cũng không có (xem mục 8).
- Catalogue giọng nói có sẵn trong app: bản gốc cũng không có — giọng đi
  qua plugin provider (xem mục 4).
- "Hoàn thành 100%" theo nghĩa không còn gì để làm: mục tiêu là port đầy
  đủ, và bảng này chính là danh sách việc còn lại; bất kỳ báo cáo nào nói
  "đã xong" mà không đối chiếu bảng này đều là phóng đại.
