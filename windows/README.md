# VibeEdit — Windows (Phase 8, final planned phase)

## Chạy nhanh trong VS Code và cập nhật không cần tải ZIP

- **Clone một lần duy nhất:** `git clone https://github.com/xayza/VibeEdit.git`
- **Chạy trong VS Code:** mở thư mục `windows/` (không phải thư mục gốc của repo)
  trong VS Code, rồi bấm **F5** (cấu hình `VibeEdit` trong `windows/.vscode/launch.json`),
  hoặc vào Terminal → Run Task → **Run VibeEdit**. Giữ nguyên cửa sổ terminal
  trong lúc dùng app; nếu trình duyệt không tự mở, tự gõ `http://127.0.0.1:8000/`;
  muốn dừng app thì bấm **Ctrl+C** trong terminal đó.
- **Cập nhật về sau, không cần tải ZIP nữa:** mở terminal trong thư mục `windows/`
  (git tự tìm `.git` ở thư mục cha) rồi gõ `git pull`, hoặc bấm nút Pull trong
  VS Code → Source Control, hoặc chạy `update_and_run.bat` / `update_and_run.ps1`
  (tự `git pull --ff-only` rồi chạy server; nếu không có git hoặc pull lỗi thì
  script chỉ cảnh báo và vẫn chạy code hiện có, không dừng lại).
- **Lưu ý về bản ZIP:** thư mục tải ZIP về không có `.git` nên không pull được.
  Muốn cập nhật kiểu trên thì clone một lần như trên, rồi copy thư mục
  `windows/projects/` cũ của bạn sang bản clone để giữ nguyên các project.

## Vòng rà soát thứ hai — knowledge, skills ghi, reorder, marker, font, caption MCP (mới nhất)

Vòng hai đối chiếu lại toàn bộ source gốc với code Windows sau đợt
full-parity đầu, sửa các dòng cũ còn sót trong README này (một số mục
vẫn ghi MCP 144/249 và liệt kê vision/knowledge/magnetic/motion là
chưa làm dù đã port xong), rồi bổ sung tiếp những gì bổ sung được:

- **Knowledge store (21 công cụ):** lessons/facts/prefs/claims/
  proposals/memo/history/verdicts/revert/migrate, lưu trong chính
  project data (đi cùng save/backup/undo của project); nội dung đều
  do người gọi cung cấp, không bịa lesson/fact nào.
- **Skills ghi:** save (header provenance "User-written", từ chối ghi
  đè nếu không có overwrite), enable/disable (state `skills.json`),
  export (nguyên văn hoặc copy ra dest), remove (cần confirm=true),
  propose (bản nháp dưới `proposals/`, không liệt kê thành skill
  đang hoạt động).
- **Magnetic reorder + marker:** `reorder_main` dời clip Main tới
  trước một clip khác hoặc xuống cuối, các clip ở giữa dời theo cùng
  linked audio, không đổi duration; marker nay dời theo khi chèn/xóa/
  trim cuối magnetic trên Main (marker trong đoạn bị xóa/trim co về
  đầu đoạn). Chưa dời marker khi move clip và khi close_gaps.
- **Caption MCP:** transcribe/generate/align thành công cụ MCP thật
  (dùng faster-whisper khi máy có cài; không có thì báo lỗi rõ, không
  đổi timing, không bịa phụ đề); `media_transcribe` là alias thật.
- **Font import + voice/update check:** import .ttf/.otf vào thư mục
  fonts của app (tên duy nhất, không ghi đè) và font đó trở thành
  candidate cho renderer; `voice_check` kiểm tra thật (piper binary,
  edge-tts module, số voiceover take); `app_update_check` trả trạng
  thái thật (version hiện tại, chưa có kênh updater).
- **Vẫn giữ trung thực:** `chat.stop`, `view.compare`, `view.safe-area`
  là công cụ MCP báo lỗi (không có chat session để dừng; Compare và
  Safe-area đã có sẵn dưới dạng điều khiển trong giao diện web, MCP
  headless không có viewer để bật/tắt).
- **Kiểm chứng:** 384 tests OK trên Linux VM (369 trước vòng ba + 15
  test vòng ba mới).

## Phase 0 — bảng parity và an toàn dữ liệu

Mục tiêu sản phẩm là **chuyển TOÀN BỘ BashCut gốc macOS thành ứng dụng
Windows mang tên VibeEdit** — không giới hạn ở MVP hay Giai đoạn 1, và
không chủ động bỏ tính năng nào của bản gốc. Bảng parity đầy đủ ở
[`PARITY.md`](PARITY.md): mỗi tính năng ghi works / partial /
missing — planned to port kèm mức độ xác minh (Windows thật / Linux VM /
chỉ đọc source gốc). Không có tính năng gốc nào bị ghi là "out of scope".

Trạng thái hiện tại (sau đợt full-parity vòng 3): **MCP 478 công cụ
(346 thao tác thật, 132 kiểm tra-và-báo-lỗi)** — số live đọc từ
`/api/mcp-tools` trong app; số trong tài liệu sẽ cũ đi khi thêm công cụ
mới. Đã hoạt động thêm từ các đợt full-parity: magnetic đầy đủ +
linked audio + reorder, cài plugin, skills (đọc + ghi), knowledge
store, vision (khi máy có backend), motion transitions, reframe,
caption transcribe/generate/align (khi máy có faster-whisper), font
import. Hoạt động một phần: Compare chưa khóa khung hình, export
preset ProRes/4K mới assert mapping chưa render đầy đủ; desktop tắt
sạch, HiDPI, phím tắt Ctrl và test chạy trên Windows đã làm xong về
code ở Phase 2, chỉ còn chưa kiểm tra bằng mắt / bằng `py` trên
Windows thật. Còn thiếu và sẽ port tiếp (không bỏ): bộ cài/.exe cho
máy Windows sạch, Windows CI, voice provider (tạo/clone giọng nói),
app updater (chỉ mới có update-check dạng trạng thái), model
segmentation học sâu cho cutout, panel giao diện cho các tính năng
mới (knowledge/skills/vision/plugin install/reframe/link/magnetic),
và một số tên gốc lẻ — xem `PARITY.md` để có danh sách thật.

An toàn dữ liệu (Phase 0):
- Upload trùng tên không còn ghi đè: file thứ hai lưu thành `tên-2.ext`,
  clip cũ vẫn trỏ file cũ.
- Backup có dọn dẹp: autosave KHÔNG tạo backup mới. Backup chỉ tạo khi
  lưu lần đầu sau khi mở project và trước thao tác ảnh hưởng dữ liệu
  (xóa clip/track, ghi đè từ nguồn, đổi format, import OTIO merge, xóa
  qua MCP). Giữ 1 file `project.json.bak` (bản lưu ngay trước đó) +
  thư mục `backups/` tối đa 5 bản mới nhất + 1 bản/ngày trong 7 ngày,
  chỉ chứa JSON project, không chứa media, và không bị liệt kê làm media
  hay bị copy theo khi nhân bản project.
- Số công cụ MCP trong giao diện/help nay đọc live từ `/api/mcp-tools`,
  không còn số ghi cứng trong `static/` (đợt này sửa cả chỗ "106 tools"
  còn sót trong đoạn mô tả capabilities).

Cấu trúc đích (chưa làm bước hợp nhất trong đợt này): sản phẩm cuối
cùng chỉ có hai ứng dụng — `BashCut-main` giữ nguyên cho macOS, và
VibeEdit hoàn thiện thành ứng dụng Windows đầy đủ. Hiện mã Windows đang
ở `windows/` và `VibeEdit/` vẫn là mã Swift/macOS. Việc hợp nhất mã
Windows vào `VibeEdit/` chỉ làm SAU KHI port đã hoàn thiện và kiểm thử
xong, và chỉ dọn cấu trúc cũ khi đã bảo toàn mã và dữ liệu. Bước hợp
nhất đó có cổng kiểm soát riêng (xem `PARITY.md`: kiểm tra BashCut-main
còn nguyên, đối chiếu thay đổi riêng của cây Swift, tạo tag/bản lưu
trước khi hợp nhất, kiểm thử lại app Windows sau hợp nhất) — chưa làm
trong đợt này, và đợt này không di chuyển/đổi tên/xóa gì trong
`VibeEdit/` hay `BashCut-main`.

## Full-parity batch — MCP, magnetic, plugin install, skills, vision, motion (mới nhất)

- **MCP 144 → 478 công cụ** (346 thao tác thật, 132 kiểm tra-và-báo-lỗi
  trung thực, 0 trùng tên): wrapper cho hầu hết tên gốc còn thiếu
  (timeline/clip/source/playhead/layer/captions/project/export/plugin/
  jobs/review/media/audio/doctor/EDL/selects/variants/plan/workflow/
  checkpoint/batch/library) và công cụ báo lỗi có cấu trúc cho các
  tên chưa port được (agent/chat/show/ui/voice/image-provider/
  knowledge/skills-write-side/updater...), không bao giờ trả thành
  công giả. Đợt này còn sửa 3 công cụ mồ côi của đợt trước (có mô tả
  kiểu thật nhưng không có handler) và thêm test quét toàn bộ
  registry để lần sau còn sót là test fail ngay.
- **Magnetic Main + linked audio đầy đủ:** xóa/chèn/di chuyển/trim
  trên Main dời các clip sau theo; `link_audio`/`unlink_audio` hai
  chiều, di chuyển/trim/tách video kéo audio theo, xóa video xóa
  luôn audio gắn liền. Tắt được bằng magnetic toggle (mặc định bật).
  Giới hạn: chưa có reorder khối, marker không dời theo ripple.
- **Cài plugin:** folder hoặc .zip, kiểm tra manifest trước khi copy
  (từ chối id xấu, traversal, symlink, bundle nhiều thư mục, >50
  MiB, trùng id), cài xong ở trạng thái tắt, download URL là bước
  riêng cần xác nhận; plugin manifest nay được liệt kê và bật/tắt
  được. Còn thiếu: thực thi code của plugin dạng manifest.
- **Skills + vision:** `windows/skills/` có 4 skill (1 chép nguyên văn
  từ cây gốc, 3 ghi rõ suy ra từ tài liệu gốc) với endpoint và công
  cụ MCP list/get/search thật; vision (OCR Tesseract, faces OpenCV
  Haar, cutout OpenCV grabCut) chạy thật khi máy có backend, nếu
  không thì báo lỗi rõ tên backend thiếu — không bundle model nào.
- **Motion transitions + reframe:** 13 loại motion render thật
  (spin/swing/arc/diamond/crash-out/infinite-out/screen-in/screen-out/
  dip-black/color-shift/flicker/kaleidoscope-xấp-xỉ); halftone vẫn
  báo lỗi kèm hướng pre-rendered segment; reframe crop-trước-scale
  qua API/MCP (chưa có form trong giao diện).
- **Kiểm chứng:** 359 tests OK trên Linux VM (347 trước đợt này + 12
  test tích hợp mới); smoke server trên project tạm (magnetic,
  skills, renderability, cổng download có xác nhận). Chưa kiểm tra
  trên Windows thật: toàn bộ tính năng mới của đợt này, cửa sổ
  desktop, phím Ctrl trong trình duyệt thật, suite chạy bằng `py`.

## Phase 2 — desktop hoàn thiện, phím tắt Windows, test chạy trên Windows

- **Desktop tắt sạch (`desktop_app.py`):** đóng cửa sổ pywebview
  (hoặc Ctrl+C) sẽ gọi `shutdown()` + `server_close()` rồi join
  thread server, nên không còn tiến trình nằm lại và cổng được giải
  phóng ngay để chạy lại. `run_server` cũng đóng socket sau Ctrl+C.
  Cửa sổ mặc định vẫn 1600x900, resizable; giao diện dùng panel co
  giãn + cuộn nội bộ và media query nên vẫn dùng được ở 1280x720
  và 1920x1080 (chưa kiểm tra bằng mắt trên Windows thật).
- **Lỗi dễ hiểu, không traceback trần:** thiếu pywebview thì in
  hướng dẫn `pip install pywebview` rồi mở trình duyệt thay thế;
  thiếu ffmpeg/ffprobe thì in cảnh báo nêu đúng 3 cách khắc phục
  (PATH, `VIBEEDIT_FFMPEG_DIR`, copy exe cạnh app) và vẫn mở app
  để soạn thảo; cổng bị chiếm thì in cổng đang chiếm và gợi ý cổng
  kế tiếp (ví dụ `--port 8001`), kèm mã thoát 2.
- **HiDPI:** chỉ trên Windows, `ctypes` bật per-monitor DPI
  awareness trước khi mở cửa sổ; ngoài Windows hàm này trả về
  False và không làm gì cả, nên Linux không bị ảnh hưởng.
- **Phím tắt Windows:** Ctrl+Z Undo, Ctrl+Shift+Z / Ctrl+Y Redo,
  Ctrl+S lưu (endpoint mới `POST /api/save`; mọi thao tác thành
  công vốn đã autosave, Ctrl+S chỉ ghi lại trạng thái hiện tại).
  Phím chữ đơn (S tách tại playhead, I/O/E/Q nguồn) vẫn hoạt động
  và tự bỏ qua khi kèm Ctrl, nên Ctrl+S không bị tách clip nhầm.
  Gợi ý phím tắt trong giao diện ghi Ctrl, không ghi Command/Cmd.
- **Test chạy trên Windows:** lời gọi subprocess dùng `python3`
  duy nhất còn lại (trong `test_phase7.py`) đã đổi sang
  `sys.executable`; tiêu đề các file test ghi cả hai lệnh chạy.
  Chạy test:
  - Windows: `py -m unittest discover -s tests -v`
    (hoặc `python -m unittest discover -s tests -v`)
  - Linux: `python3 -m unittest discover -s tests -v`
  Test mới `tests/test_phase2_desktop.py` khẳng định: server tắt
  sạch và cổng rebind được ngay, thông điệp lỗi FFmpeg/cổng,
  endpoint `/api/save`, phím tắt Ctrl trong `app.js`/`index.html`,
  và không còn lời gọi subprocess dùng `python3` trần trong test.
  Chưa kiểm tra trên Windows thật: giao diện cửa sổ desktop ở
  720p/900p/1080p, render HiDPI, phím Ctrl trong trình duyệt
  Windows thật, và toàn bộ test chạy bằng `py` trên Windows.

## Code-gap batch 2
Soát tiếp từ code gốc và cập nhật: timeline redo (MCP), export preset theo đúng ExportPreset của bản gốc (TikTok/Reels/Shorts 1080x1920 8 Mbps, Feed 4:5 5 Mbps, Square, Portrait 3:4, YouTube 1080p 12 Mbps, YouTube 4K 45 Mbps, Quick Draft 720p 4 Mbps, ProRes 422 HQ qua prores_ks .mov), đường cong tốc độ (montage/hero/bullet/jump-cut/flash-in/flash-out theo đúng điểm trong SpeedCurve.swift), đảo ngược clip (reverse/areverse), đóng băng khung hình, quy trình review chạy/chấp nhận/kiểm tra lại, màn hình chào mừng với project gần đây + Reveal (Windows) + Copy đường dẫn + xóa khỏi gần đây (không xóa file project), thư viện clip + brand kit, panel plugin có bật/tắt/quét lại, thêm loại transition của bản gốc mà FFmpeg xfade có thật (shutter, double-exposure, seamless/infinite/crash zoom, blur, flash/blink, roll). MCP lúc đó: 144 công cụ (đã tăng lên 478 ở các đợt full-parity sau). Chưa làm trong đợt này: vision/OCR/cutout (cần model ML), kho kiến thức/skill (21+8 công cụ), di chuyển magnetic cả khối + âm thanh gắn liền, và các loại transition chỉ có bằng motion của bản gốc (spin, swing/arc, diamond, kaleidoscope). Tất cả các mục này đã được bổ sung ở các đợt full-parity sau đó, trừ model segmentation học sâu cho cutout — xem `PARITY.md` để biết trạng thái thật hiện tại.

## Cửa sổ desktop thật (không phải tab trình duyệt)

- **Cài một lần:** `pip install pywebview` trong `.venv` của bạn.
- **Chạy:** bấm đúp `run_vibeedit_desktop.bat` trong thư mục `windows/`,
  hoặc gõ `python desktop_app.py` trong terminal của thư mục đó.
- Cửa sổ này dùng Edge WebView2 có sẵn trên Windows 10/11 để hiện đúng
  giao diện web đã có (không viết lại UI, không Electron, không Qt),
  nên trông như một app desktop thật: có thanh tiêu đề VibeEdit, không
  có tab trình duyệt hay thanh địa chỉ. Nếu chưa cài pywebview, app sẽ
  in hướng dẫn cài đặt rồi tự mở bằng trình duyệt như trước, không
  đứng im và không báo lỗi khó hiểu.

## Original-app layout (after the CapCut shell)

- **Layout, in the structure of the original BashCut macOS app
  (inspiration only — no artwork, logos, or code copied):** top bar
  with project name, "Edited rev N" from real project data, and
  Export report (opens Review) beside Export video; left rail
  Media / Audio / Text / Stickers / Effects / Transitions / Filters
  / Voice; centre Timeline / Source tabs, preview with Fit, Compare
  (honestly not available yet) and Safe-area (display-only guide)
  controls, playback controls and current / total time; right
  column with INSPECTOR tabs Video / Audio / Text / Color / Speed
  (mapped to the real inspector) stacked above an always-visible
  AGENT dock; bottom timeline toolbar with Add, Split, Delete, Add
  Layer, Sections, Ask agent, zoom, time ruler and a red playhead.
- **Voice panel (new):** provider/voice selectors, Clone voice from
  a reference file, Generate takes, Record voiceover, and Import a
  voiceover take. Only import + place on a Voiceover track is real;
  generation, cloning and recording are labelled not available in
  the Windows port yet. The Voiceover form creates a Voiceover
  audio track if none exists (`add_track` op) and adds the clip.
- **AGENT dock (answers "where is the AI chat"):** always visible
  on the right, with provider selector, chat history, message input
  and Workspace / Project context / Survey / Write VO / Review
  buttons. The input runs real safe commands (list clips, export
  draft, review, stats, workspace, undo/redo); anything else gets an
  honest reply that no LLM is connected in-app, with the real MCP
  command `python windows\vibeedit.py mcp <project-folder>` (478
  tools). No fake AI replies, no fake timeline edits, no fake
  voices. There is no terminal emulator in the web UI — use your
  own terminal for the MCP agent.
- **Timeline presentation:** tracks in Captions / Overlay / Main /
  Adjustment / Background / Dialogue / Voiceover / Music / Sfx
  order (project tracks plus labelled empty rows, never fake
  tracks); Main clips show filename + duration; Captions show
  word-level karaoke chips; Dialogue / Voiceover / Music tracks
  show waveform strips decoded from the real file via
  `/api/waveform` (FFmpeg RMS peaks, normalised — silence is all
  zeros, an undecodable file draws no strip instead of a fake
  shape); a collapsible "What this timeline can do" panel lists
  what works and what does not yet (in-app LLM generation, voice
  cloning/recording, VieNeu TTS, silence cutting).

## CapCut-style shell redesign (after Phase 8)

- **Layout, in the spirit of the user's CapCut desktop reference
  screenshot (inspiration only — no CapCut assets, icons, or code
  copied):** brand top bar (logo, project name, Undo/Redo, Export
  draft / Export video) + a slim tool toolbar (Media, Audio, Text,
  Stickers, Effects, Transitions, Captions, Filters, Adjustment,
  Templates, AI, teal accent on the active item) + a workbench of
  three columns + a full-width timeline at the bottom.
- **Left column:** a narrow rail (Import, Media, Timeline,
  Subprojects, Yours, Generate, Spaces, Library) beside tab panels.
  The Media tab has a centred "+ Import" drop zone ("Drag and drop
  videos, photos, and audio files here" — dropping files fills the
  existing upload input and submits the existing upload form) and a
  "No media? Create with these tools" row (Generate / AI avatars
  switch to the AI tab; Record is disabled and labelled as not
  available in VibeEdit yet).
- **Centre:** a "Player" stage with the preview video centred and
  aspect-correct, plus its playhead/duration pills.
- **Right column:** a "Details" panel holding the real Inspector
  (selected-clip properties, LUT/colour, keyframes) — only real
  project data, no invented CapCut fields.
- **Bottom:** a timeline toolbar (+ Add, Undo, Redo, Split, Delete
  — mirrors of the real actions, not duplicates) + the "Drag
  material here and start to create" hint + ruler with time and
  beat ticks + labelled track rows with type-coloured clips.
- **No feature was lost or faked:** every old panel moved verbatim
  (same ids, labels, and submit handlers) into its tab — see the
  mapping in `tests/test_capcut_ui.py`. Stickers and Filters tabs
  say honestly what VibeEdit lacks (no stickers yet; colour
  presets/LUT live in the Details inspector) instead of inventing
  tools. Teal (#00c8d4) replaces the Phase 7 gradient accent.
- 131 tests OK (122 Phase 1–8 + 9 new shell tests), plus a
  web-server smoke test (HTTP 200 for `/`, `/api/project`,
  `/static/style.css`, served HTML containing the new shell
  markers and the logo data URI).


## What Phase 8 adds (on top of Phase 7) — final planned phase

- **Overlay still images now render:** overlay-track still-image
  items were skipped entirely before. Now the single frame is
  looped for the item duration, scaled to the project frame,
  with scale keyframes via zoompan, tilt, colour and stepwise
  opacity, and position keyframes driving the overlay x/y.
  Verified: a red still over a 3 s main clip renders 3.0 s with
  `overlay_clips: 1`, `skipped: []`, and the centre pixel at 2 s
  is red (249, 0, 0).
- **Transition preview stills:** the Transition panel has a
  "Preview selected transition (still)" button. It renders a
  short draft window around the cut with the real renderer and
  grabs one frame at the transition midpoint
  (`POST /api/transition-preview`, served at
  `GET /api/transition-preview?transition=<id>`), so you can
  see what a transition looks like before a full export.
- **Review panel:** a new panel with a "Refresh review" button
  (`GET /api/review`) listing project validation issues,
  project stats, the last export path and report, and the
  skipped/warnings lists from that real export — never
  invented data. No export is run by the review endpoint.
- **UI beautified further (user priority):** the Phase 7 dark
  theme is kept, but the preview stage is now centred with
  proper aspect framing (the old full-width video stretched
  vertical 1080x1920 projects), the top bar has a gradient
  hairline and larger logo, panels have gradient section bars
  and reflow with the window, the timeline has labelled
  track cards, type-coloured gradient clips, a highlighted
  selection, a playhead with a handle, ruler ticks and beat
  ticks, and controls have hover/focus states. CSS only: no
  `app.js` id was renamed or removed (test-enforced), and the
  logo data URI in `index.html` is untouched.
- **MCP expanded from 90 to 106 real tools:** transition
  preview, review get, overlay items, clip position/scale/
  opacity keyframe setters, clip fades/speed getters, marker
  move, beat grid get, ducking toggle, clip keyframes clear,
  media kind list, timeline gaps, project duration in
  frames, clip at time. Every tool calls real Project/export
  code.
- 122 tests OK (113 Phase 1–7 + 9 Phase 8), plus a web-server
  smoke test (HTTP 200 for `/`, `/api/project`, `/api/review`
  and the transition-preview PNG, valid PNG magic) and an
  MCP stdio smoke test (`tools/list` count 106).

## What Phase 7 adds (on top of Phase 6)

- **Windows export bugfix — drawtext fontfile colon (critical,
  from a real user failure):** FFmpeg's filter parser splits
  options on every unescaped colon, even inside single quotes,
  so `fontfile='C:/Windows/Fonts/arial.ttf'` failed on Windows
  with `No option name near '/Windows/Fonts/arial.ttf:...'`.
  Phase 5's slash conversion alone was not enough. The fix in
  `vibeedit_core/render.py` (`_filter_path`) now escapes every
  colon as `\:` in all filter-embedded paths (drawtext
  fontfile, lut3d file, subtitles filename), so Windows drive
  paths and paths with spaces work. Proven on FFmpeg 8.1.2: a
  colon-containing font path fails unescaped with exactly the
  user's error and renders fine escaped.
- **Vietnamese text mojibake fix:** the user's text "xin chào"
  showed up as "xin chÃ o" in the export error. The project
  file, server JSON and browser layers are all UTF-8 throughout;
  the mojibake came from `subprocess.run(..., text=True)` in
  `render.py`, which on Windows decodes FFmpeg's UTF-8 stderr
  with the locale codepage (typically windows-1252). Both
  FFmpeg subprocess calls (and the beats decoder) now decode
  explicitly as UTF-8 with `errors="replace"`, and a full
  Vietnamese-text render is test-covered.
- **Still-image keyframes now render:** main-track still-image
  clips with x/y/scale keyframes animate via zoompan on the
  looped still, tilt via rotate, colour via the normal colour
  filters, and opacity/fades via the alpha steps — the old
  "stored, not rendered" skipped entry is gone. (Overlay
  still-image items are still skipped entirely, as before —
  that is a separate limitation, not a keyframe one.)
- **Eq preset strength in the Inspector:** the preset-strength
  control existed in code since Phase 5 but had no UI field;
  the Inspector now has a "Preset strength (0–1)" input wired
  to `set_color`'s `preset_strength`, alongside the existing
  LUT-strength input.
- **UI beautified (CapCut-style dark editor):** `static/
  style.css` was redesigned — near-black chrome, logo-gradient
  accents (pink -> violet -> blue), sticky top bar with the
  logo, gradient primary buttons, clearer panels, track lanes
  with kind-coloured left accents, white playhead, and
  focus-visible rings. CSS only: no element id or class used
  by `app.js` was renamed or removed (a test asserts every
  `app.js` id still exists in `index.html`).
- **MCP expanded from 78 to 90 real tools:** clip get,
  clip duplicate, clip keyframe remove, media remove (blocked
  while any item references it), project format set, track
  add, karaoke remove, adjustment get, beat count, text style
  get, export preview (draft), project rev. Every tool calls
  real Project/export code.
- 113 tests OK (91 Phase 1–6 + 22 Phase 7), plus a web-server
  smoke test (HTTP 200 for `/`, `/api/project` and the new
  stylesheet) and a full draft export smoke on the VM
  (540x960, 3.003 s, H.264/AAC, 1 Vietnamese text overlay,
  no skips).

## What Phase 6 adds (on top of Phase 5)

- **Ready-made Windows exe via GitHub Actions** (the main Phase 6
  deliverable): new `.github/workflows/build-windows.yml` runs
  on `windows-latest` on pushes to `main` touching `windows/**`
  (or the workflow file) and on manual dispatch. It checks out
  the repo, sets up Python 3.12, installs Pillow + PyInstaller,
  runs the existing `windows/build_windows.bat` (its `pause`
  prompts are now skipped when `GITHUB_ACTIONS` is set, so CI
  cannot hang on them), downloads the gyan.dev FFmpeg
  essentials build, copies `ffmpeg.exe` + `ffprobe.exe` into
  `dist/VibeEdit/` next to `VibeEdit.exe` (the app already
  looks for FFmpeg next to the frozen exe), smoke-tests the
  exe with `VibeEdit.exe --help`, and uploads `dist/VibeEdit/`
  as the **VibeEdit-Windows** artifact. Download it from the
  repo's Actions tab (see `windows/CHECK_WINDOWS.md` section 0
  for the exact steps); no Python or separate FFmpeg install is
  needed to run it. Honest limit: the workflow has NOT been run
  yet — it can only run on GitHub after it is pushed — so the
  exe appears only after its first green run, and it is never
  in the repo itself. The artifact bundles the gyan.dev FFmpeg
  build (GPL/LGPL); see CHECK_WINDOWS.md for the licence note.
- **Exe easy-run behaviour:** `serve --open-browser` opens the
  editor URL once the server starts (browser failure never
  crashes the server), and the frozen exe with no arguments now
  defaults to `serve --open-browser --port 8000`, so
  double-clicking `VibeEdit.exe` just works. The unfrozen CLI
  is unchanged: no arguments still means the "required
  subcommand" error, never a surprise server.
- **MCP expanded from 66 to 78 real tools:** clip copy (same
  project, preserving keyframes/colour/fades/volume/speed/text
  style/karaoke), clip paste into another project (media entry
  copied with it; missing media on the destination reported,
  never invented), text preset list/apply (`title`, `subtitle`,
  `lower_third`, `top_caption`), text set, clip volume, export
  preset list (full: project resolution, fast, CRF 20; draft:
  half resolution, veryfast, CRF 28), timeline duration, media
  duration (stored + ffprobe), project backup (`.bak` copy) and
  project rename. Every tool calls real Project/export code.
- 91 tests OK (79 Phase 1–5 + 12 Phase 6), plus a web-server
  smoke test (HTTP 200 for `/`, `/api/project` and
  `/api/mcp-tools`) and a YAML-parse validation of the new
  workflow.

## What Phase 5 adds (on top of Phase 4)

- Windows compatibility audit + fixes (the main Phase 5 work):
  every FFmpeg filter-embedded path (lut3d `.cube`, drawtext
  `fontfile`, subtitles `.ass`) now goes through
  `render._filter_path()`, which converts backslashes to forward
  slashes and escapes single quotes, so Windows paths with a
  drive-letter colon no longer break the filter parser. Fonts
  resolve from `%SystemRoot%\Fonts\` first (any drive), with a
  `VIBEEDIT_FONT` override, and a missing font is now a clear
  error naming the fix instead of silently skipped text.
  FFmpeg/FFprobe resolve via `render.find_tool()`:
  `VIBEEDIT_FFMPEG_DIR`, then PATH, then next to the script/exe,
  with a clear "not found" error instead of a bare traceback.
  The launchers (`run_vibeedit.bat`, `run_vibeedit.ps1`) now run
  `vibeedit.py` from their own folder, so copying only `windows\`
  elsewhere works (the old `cd ..` + `windows\vibeedit.py` only
  worked for a full repo checkout). The frozen app resolves
  `static/` from `sys._MEIPASS` (or next to the exe) and stores
  its default project next to the exe, not inside bundled data.
  A grep audit found the rest already clean: no hardcoded `/tmp`,
  no `shell=True`, no `os.symlink`, and `os.path.join` throughout
  (see `windows/CHECK_WINDOWS.md` for the full Windows checklist).
- Eq preset strength: `color["preset_strength"]` (0–1, default
  1.0) blends each eq parameter toward neutral (brightness 0,
  contrast 1, saturation 1); strength 0 skips the eq filter.
  Verified: vivid at 0.5 renders exactly
  `brightness=0.01:contrast=1.075:saturation=1.125`, strength 0
  renders identically to no preset, and saturation rises
  monotonically 0 → 0.5 → 1. CLI: `color … --preset-strength N`;
  server/MCP `set_color` pass it through; adjustment layers too.
- Main-track motion+opacity combined rendering FIXED: opacity
  sub-segments now shift their zoompan expression by the segment
  start frame, so a main clip with motion (x/y/scale) AND opacity
  keyframes renders both. Verified with a real render: the
  combined frame at 2.5 s (inside the second opacity segment)
  differs from the motion-only, opacity-only and plain renders,
  duration stays exact (3.0 s), and nothing is reported skipped.
- Karaoke by syllable: a word may carry
  `syllables: [{text, start, end}]`; syllables must join
  (concatenated) to the word text and lie inside the word's time
  range (hard errors otherwise), and the `.ass` builder emits one
  `\k` tag per syllable instead of per word. `karaoke-add` (CLI
  JSON) and MCP pass syllables through unchanged.
- Agent dock: a documented panel in the web UI (no fake
  terminal) with the MCP launch command
  (`python windows\vibeedit.py mcp <project-folder>`), example
  agent commands, and a LIVE tool list fetched from the new
  `GET /api/mcp-tools` endpoint (real registry from `mcp.py`).
- MCP expanded from 54 to 66 real tools (see below).

## What Phase 4 adds (on top of Phase 3)

- OTIO import: `vibeedit.py otio-import <file.otio> <dest-folder>`
  (or the web UI panel, or MCP) reads back the Phase 3 OTIO export
  into a new project, or merges its tracks into an existing project
  (`--merge`). Media paths resolve relative to the .otio file first,
  then as stored; a file that cannot be found is still imported and
  listed in the report's `missing` list — never silently dropped and
  never replaced with invented media. Round-trip verified: export a
  project, import it, and the clip counts, timings and transitions
  match (2 video clips + 1 caption, 1 dissolve, 1 marker in tests).
- Karaoke captions: a text item can carry per-word timings
  (`karaoke-add <item> '[{"text":"Hello","start":0,"end":1},...]'`;
  words must join to the cue text, in order, inside the cue).
  Rendering burns one .ass track with libass `\k` tags via FFmpeg's
  subtitles filter: sung words in yellow, unsung words in white.
  Standalone export: `karaoke-export` writes `render/karaoke.ass`.
- Adjustment layers: `adjustment-add <at> <dur> [--preset NAME]
  [--lut FILE] [--strength N]` adds a colour preset and/or .cube LUT
  that applies to the main-track picture only, for its own time
  range (eq/lut3d with an `enable` window; overlays composited after
  are not adjusted). Overlap on the adjustment track is rejected
  like any other track.
- Beat grid: `beat-detect <media>` decodes the audio with FFmpeg
  and runs an energy-onset detector (no ML model, no fake beats),
  storing seconds in `beatGrid`. The web UI draws the beats as ticks
  on the ruler; `beat-snap` snaps a frame to the nearest beat and
  `beats-to-markers` copies the grid into markers. Measured on
  synthetic burst audio: all 5 bursts found within 0.05 s; silence
  yields no beats. On real music this is a rough grid, not a
  musically exact analysis.
- Music ducking: `ducking [--amount DB] [--off]` stores the config
  in `audio.ducking`; renders sidechain-compress music items with
  the main-track audio as sidechain (asplit, so the main audio can
  feed both the compressor and the mix). Amount sets the ratio as
  10 ** (amount / 20); threshold defaults to 0.02. Measured in an
  isolated sidechain test: music during a dialogue burst was more
  than 3 dB quieter than music during silence.
- Tilt keyframes: `tilt` (-180–180 degrees) joins the keyframe
  properties and renders with FFmpeg's rotate filter (per-frame
  angle expression, output size pinned). Main-track and overlay
  clips both render tilt; still-image clips with keyframes remain
  stored-not-rendered, as before.
- MCP expanded from 38 to 54 real tools (see below).

A Windows re-implementation of the VibeEdit (formerly BashCut) video
editor's core: timeline editing, project JSON, CLI/MCP control and
FFmpeg rendering. The original macOS Swift app is preserved in
`VibeEdit/` in this repo; it cannot run on Windows (SwiftUI, AppKit
and AVFoundation are macOS-only), so this port re-implements the
timeline model in Python and renders with FFmpeg. See
`VibeEdit/docs/windows-port.md` for the full inventory and mapping.

## What Phase 3 adds (on top of Phase 2)

- Full transition library (all rendered with FFmpeg xfade on the
  build in this environment — FFmpeg 8.1.2): whip (wind), iris
  open/close (circleopen/circleclose), zoom-in (zoomin), glitch
  (pixelize), fadeblack/fadewhite, smooth left/right/up/down,
  cover/reveal left/right/up/down, diagonal TL/TR/BL/BR,
  horizontal/vertical slices, hblur, fadegrays, squeeze horizontal/
  vertical, vertical/horizontal open (barn-door equivalent), plus
  circlecrop, rectcrop, distance and wipe-tl/tr/bl/br. Kinds are
  validated the same way as Phase 2 (0.1–2.0 s, clips consecutive,
  no overlap per cut). The transition picker in the web UI lists
  the new kinds. NOT implemented (no xfade effect of that name in
  this FFmpeg build, and never silently replaced by dissolve):
  a true lens iris with mask animation, a glitch effect with RGB
  channel shift, and a zoom-out — `zoom` maps to zoomin only.
- Main-track keyframes now render: position/scale via zoompan
  (linear interpolation, per-frame), opacity via held segments
  (same stepwise approach as Phase 2 overlays), volume via a
  volume expression. The Phase 2 "stored but not rendered"
  limitation for main-track clips is gone, with two honest
  exceptions: a main-track clip that has BOTH motion keyframes
  (x/y/scale) and opacity keyframes renders opacity only and
  reports the motion as skipped (zoompan resets its frame counter
  per segment, so the timing would be wrong); main-track image
  (still) clips with keyframes are stored but not rendered.
- LUT strength (0–1) renders for real: a blended .cube is written
  per render by linearly mixing an identity LUT with the user's
  LUT at the given strength, so strength 0 renders (nearly)
  identical to no LUT and strength 1 is the full LUT. Preset
  colour (eq) is not strength-blended — it is applied at full
  strength, and combining preset + LUT keeps both filters.
- Batch export: `vibeedit.py batch <folder...> [--preset] [--normalize]`
  exports projects sequentially and reports success/failure per
  project without stopping on a failed one; the web UI has a Batch
  & OTIO panel (the open project is always exported first).
- OTIO export: `vibeedit.py otio-export <project>` (or the web UI
  button) writes a real OpenTimelineIO JSON file
  (`render/timeline.otio`): Stack with one Track per project
  track, Clip items with `source_range` (RationalTime at the
  project rate), `ExternalReference` to the media file,
  Transitions (SMPTE_Dissolve for dissolve/crossfade/fade,
  Custom for other kinds, with the VibeEdit kind/id/from/to kept
  in metadata), Markers, and per-clip metadata (id, at, speed,
  keyframes, colour, volume, fades). OTIO import is NOT included.
- Overlay audio: an overlay item whose media has audio renders
  that audio at its timeline position, mixed with main-track
  audio and music. Loudness normalisation: `export --normalize`
  (or the UI checkbox) applies single-pass loudnorm
  (I=-16, TP=-1.5, LRA=11) when audio exists.
- MCP expanded from 23 to 38 real tools (see below).
- Windows installer: `windows\build_windows.bat` (+
  `vibeedit.spec`) builds a one-folder PyInstaller app on Windows,
  and `windows\scripts\install_shortcuts.ps1` creates Start Menu
  + Desktop shortcuts to `run_vibeedit.bat`. The exe was NOT built
  on this Linux VM (PyInstaller cannot cross-build Windows) —
  the scripts are the deliverable, and they must be run on Windows.
- Plugins (minimal, real): `windows/plugins/` modules with a
  `register()` returning named hooks (`transform_text`,
  `apply_color`). Two working examples ship: `uppercase_text`
  and `vivid_color` (`plugin-list` / `plugin-run` CLI commands).
  This is a new Windows-port hook, NOT a port of the original
  macOS plugin system.
- Transcription entry point (real local provider only):
  `vibeedit.py transcribe <project> <media> [--model small]`
  calls faster-whisper when installed and adds segments as
  captions; when faster-whisper is absent it errors clearly with
  the install command and writes nothing. No other provider is
  bundled or stubbed; adding one means implementing the
  `transcribe(path, model) -> [(start_s, end_s, text)]` interface
  in `vibeedit_core/transcribe.py`.

## What Phase 2 adds (on top of Phase 1)

- Transitions between consecutive main-track clips: crossfade
  (dissolve), wipe left/right/up/down, slide left/right/up/down,
  duration 0.1–2.0 s, rendered with FFmpeg xfade/acrossfade. The
  output timeline is shorter than the project timeline by the sum
  of transition durations; overlays, text and music after a
  transition boundary shift earlier by the same amount.
- Keyframes (times in seconds relative to the clip start, edited in
  the inspector): position (x/y) and scale for overlay/text clips,
  opacity for overlay/text clips, volume for audio clips. Position,
  scale and volume are rendered with linear interpolation; text
  opacity is rendered linearly; overlay opacity is rendered
  stepwise (held at each keyframe value) because FFmpeg's
  colorchannelmixer alpha has no time variable. Main-track
  keyframes were stored but not rendered in Phase 2 — Phase 3
  renders them (see above).
- SRT import (into the Captions track, overlap-rejected) and export.
- Colour: per-clip .cube LUT via lut3d (a missing/invalid LUT is a
  hard error, never a silent skip) and eq presets (vivid, warm,
  cool, faded, mono).
- MCP expanded from 9 to 23 real tools (see below).
- Windows launcher: double-click `windows\run_vibeedit.bat` (or
  right-click `windows\run_vibeedit.ps1` → Run with PowerShell);
  it checks Python + FFmpeg, starts the server, polls the port and
  opens the browser. See `windows/INSTALL.md` (Vietnamese).

## What Phase 1 does

- CapCut-style web UI: preview on top, editor/inspector panel in
  the middle, multi-track timeline strip at the bottom (Main,
  Overlay, Captions, Dialogue, Music). Click a clip to select it,
  drag it to move it (including across tracks), click the ruler to
  move the playhead, press `S` to split the selected clip at the
  playhead. Undo/redo (50 steps), media upload, clip/text editing.
- CLI (`vibeedit.py`): new, open, list, timeline, add, text, trim,
  split, move, delete, speed, undo, export, serve, mcp.
- MCP server (`vibeedit_core/mcp.py`): stdio JSON-RPC, tools
  `vibeedit_project_*`, `vibeedit_timeline_*`, `vibeedit_media_list`,
  `vibeedit_export_start` — real operations, not stubs.
- FFmpeg export: project resolution (default 1080x1920) or draft
  (half resolution), H.264/AAC, clips in timeline order, gaps as
  black + silence, text overlays, speed (setpts/atempo), fades,
  overlay video compositing, mixed audio. Preview plays the latest
  export only — it is not a live GPU timeline render.
- Project format: `vibeedit.project/1`, and it also opens original
  `bashcut.project/1` / `project.bashcut.json` files. Unknown
  fields round-trip unchanged.

## What Phase 6 does NOT do yet

Agent dock terminals (the Phase 5 dock is a documented panel +
live tool list, not a terminal emulator), a Windows .exe actually
built and downloaded from a green Actions run (the workflow
exists but has not run yet — it can only run on GitHub after
the user pushes the workflow file, which the GitHub App
connection cannot write), voice providers, additional
transcription providers, or the remaining original MCP tool
names (see `PARITY.md` for the honest list; MCP is now 478
tools: 346 real-operation and 132 check-and-error). Still open: a visual UI check in a
real browser on Windows. See the Phase 8 list in
`VibeEdit/docs/windows-port.md` for what is left, all of which
needs the user's Windows or macOS machine.

## Requirements

- Python 3.10+ (stdlib only, no pip packages).
- FFmpeg + FFprobe in `PATH` (rendering and media probing).
  On Windows, download a build from gyan.dev or use
  `winget install Gyan.FFmpeg`, then make sure `ffmpeg` is on PATH.

## Run the web UI (Windows)

Double-click `windows\run_vibeedit.bat`, or from a terminal:

```bat
cd VibeEdit
python windows\vibeedit.py serve --port 8000
```

Then open http://127.0.0.1:8000/ in a browser. The default project
lives in `windows\projects\default\`. To use another project folder,
pass `--project <folder>`. Put your media files in the project's
`media\` folder (or use the Upload button), add clips from the
editor panel, then Export.

## Run the CLI

```bat
python windows\vibeedit.py new myvideo --dir windows\projects --width 1080 --height 1920
python windows\vibeedit.py add windows\projects\myvideo media\clip1.mp4 v1 0 --dur 90
python windows\vibeedit.py text windows\projects\myvideo t1 0 60 "Hello VibeEdit"
python windows\vibeedit.py transition windows\projects\myvideo <clip1> <clip2> dissolve 0.5
python windows\vibeedit.py keyframe windows\projects\myvideo <clip> 1.0 opacity 0.5
python windows\vibeedit.py color windows\projects\myvideo <clip> --lut C:\luts\my.cube --preset vivid --strength 0.5
python windows\vibeedit.py marker-add windows\projects\myvideo "Intro" 0
python windows\vibeedit.py otio-export windows\projects\myvideo
python windows\vibeedit.py batch windows\projects\a windows\projects\b --normalize
python windows\vibeedit.py transcribe windows\projects\myvideo media\clip1.mp4 --model small
python windows\vibeedit.py plugin-list
python windows\vibeedit.py plugin-run windows\projects\myvideo uppercase_text transform_text <text-item-id>
python windows\vibeedit.py srt-import windows\projects\myvideo captions.srt
python windows\vibeedit.py srt-export windows\projects\myvideo captions_out.srt
python windows\vibeedit.py timeline windows\projects\myvideo
python windows\vibeedit.py export windows\projects\myvideo --preset full
```

Times in CLI arguments are frames (the original's unit). Export
presets: `full` (project resolution) and `draft` (half resolution).

## Open an original BashCut project

Copy the project folder (or at least its `project.bashcut.json` and
its media) into `windows\projects\<name>\`, then:

```bat
python windows\vibeedit.py open windows\projects\<name>
python windows\vibeedit.py serve --project windows\projects\<name>
```

The MVP reads the original schema and preserves fields it does not
understand; saving writes `project.vibeedit.json` next to it (the
original file is left untouched). Media paths are resolved relative
to the project folder; `@assets/...` workspace paths and symlinked
`footage/` folders from macOS are NOT resolved in Phase 1 — copy
the media files into the project folder first.

## MCP server

```bat
python windows\vibeedit.py mcp windows\projects\myvideo
```

The server speaks newline-delimited JSON-RPC 2.0 on stdin/stdout
(`initialize`, `ping`, `tools/list`, `tools/call`). Point any
MCP-compatible agent at it with the `vibeedit-mcp` server name.

478 tools (346 real-operation tools and 132 check-and-error tools that raise a structured NOT_AVAILABLE error with the blocker and port path, never a fake success) — see `PARITY.md` for the current split. Round 3 verified by test that all 249 original CommandCatalog spec names have a registry name (dots/hyphens normalised, 4 via real aliases). Every real tool calls a real Project, export, store or backend operation; none is a stub.

## Tests

```bat
cd windows
python -m unittest discover -s tests -v
```

Tests generate their own media with FFmpeg into a temp folder; no
real footage, no network, no Swift toolchain needed.

## Honest limits

- The renamed Swift tree in `VibeEdit/` has NOT been compiled on
  Windows (impossible) or on macOS in this environment — the macOS
  build needs Xcode 16+ on macOS 14 before any macOS release.
- The web UI has NOT been visually checked in a real browser on
  Windows in this environment (API + unit checks only).
- Logo artwork still shows the old BashCut mark until a VibeEdit
  logo is supplied.
