# VibeEdit — Bản đồ giao diện (UI map, vòng 14)

Nguồn cấu trúc: đọc trực tiếp code Swift gốc (chỉ đọc, không sửa)
trong `VibeEdit/VibeEdit/Views/` và hai ảnh mẫu của người dùng
(CapCut desktop, app gốc project di-choi-buon-lang — chỉ học bố cục,
không copy nội dung trong ảnh). Bản đầy đủ đọc từ Swift nằm ở
`/tmp/vibeedit-ui-map.md` (file tạm, không commit).

## 1. Cửa sổ app gốc, theo thứ tự từ trên xuống dưới

| # | Vùng | Mặc định | File Swift nguồn |
|---|------|----------|------------------|
| 1 | Toolbar 38pt: menu project (tên + chấm Edited/Saved + rev), Undo, Redo, menu khổ (W×H·fps), Spacer, Plugins, Review, Export | Luôn hiện | `EditorView+Toolbar.swift` |
| 2 | Banner conflict | Chỉ khi file đổi trên đĩa | `EditorView.swift` |
| 3 | Rail trái 54pt: Media, Audio, Text, Stickers, Effects, Transitions, Filters, Brand, Tools, More | Luôn hiện; bấm tab đang mở thì gập pane | `EditorView+Rail.swift`, `EditorView+PluginRail.swift` |
| 4 | Library pane 300–520pt (mặc định 372pt ≥1680, 300pt còn lại): đúng MỘT tab rail đang chọn | Hiện mặc định | `EditorView+LibraryPane.swift`, `LibraryView.swift` |
| 5 | Viewer giữa: tab Timeline/Source, Fit (mặc định), Compare, Safe area (mặc định TẮT), transport + timecode | Luôn hiện; Source thay thế viewer khi mở | `EditorView+Viewer.swift`, `ViewerModeSwitch.swift`, `SourceViewer.swift`, `TransportBar.swift` |
| 6 | Inspector phải 300/340pt: tab theo loại item (clip: Video/Audio/Color/Speed; text: Text/Video; audio: Audio/Speed; adjustment: Color) | Hiện mặc định; tab bar chỉ khi có item được chọn; chưa chọn gì thì hiện ProjectInspector (tên, khổ, fps, độ dài, sections, outputs) | `InspectorView.swift`, `InspectorHeader.swift`, `ProjectInspectorView.swift`, `InspectorView+Crop.swift`, `InspectorView+Speed.swift` |
| 7 | Timeline toolbar + Timeline: Split, Delete, Add layer, Snap (mặc định BẬT), Sections, Waveforms; ruler 22pt, row 29pt, Main 46pt; track trống GẬP mặc định | Luôn hiện, full chiều rộng cột editor | `EditorView+TimelineToolbar.swift`, `Views/Timeline/*` |
| 8 | Agent dock: cột riêng chạy suốt chiều cao cửa sổ, BÊN PHẢI timeline; header + tab provider (phiên agent ngoài) + nội dung công việc + nút Survey/Write VO/Review; KHÔNG có chat LLM trong app (model-API panel đã gỡ) | Hiện mặc định, tắt bằng ⌘J | `AgentDockView.swift` |
| 9 | Status bar dưới cùng: tóm tắt lựa chọn, Length, nút jobs khi có job | Luôn hiện | `StatusBarView.swift` |

Tiết lộ dần (progressive disclosure) của app gốc: Knowledge chỉ qua
icon sách trong dock; Skills chỉ qua menu More/Agent Skills; Vision
KHÔNG có panel/tab/tool tên Vision trong Views đã đọc; Templates
KHÔNG có rail panel tên Templates (chỉ preset/kits); Batch chỉ qua
menu File → Batch… (cửa sổ riêng); plugin qua rail More, nút Plugins,
sheet PluginManager, proposal sheet; mọi sheet khác (Export, Review,
Settings, Doctor, Update…) đều mở theo thao tác, không hiện sẵn.

## 2. Ảnh CapCut desktop (mục tiêu hình ảnh thứ nhất)

Hàng icon trên cùng (Media, Audio, Text, Stickers, Effects,
Transitions, Captions, Filters, Adjustment, Templates, AI); sidebar
trái (Import, Media, Timeline, Subprojects, Yours, Generate, Spaces,
Library); giữa là vùng Import lớn + "No media? Create with these
tools"; panel phải Details (Name, Path, Floating-point, Imported
media, Arrange layers, Proxy, Aspect ratio, Resolution, Frame rate,
Modify); dưới cùng là timeline trống "Drag material here and start
to create". Ảnh thứ hai (có media) cho thấy preview có timecode, AI
clipper, timeline có clip video + dải sóng audio, Details "Smart
suggestions / Global edits".

## 3. Ảnh app gốc di-choi-buon-lang (mục tiêu timeline + AGENT)

Top bar gọn một hàng (tên, 1920×1080, 29.97fps, Edited rev, Export
report, Plugins, Review, Export). Timeline toolbar riêng (TIMELINE,
Split, Delete, Add Layer, Snap, Sections, Ask agent, zoom). Captions
là chip từ nhỏ màu cam; Main có thumbnail + tên file + thời lượng;
Dialogue/Voiceover có sóng âm + tên take, màu phân biệt; Music là dải
sóng tím liền mạch; playhead đỏ dọc xuyên mọi track; hàng thấp gọn.
Panel Voice mở sẵn (Voiceover, Provider Automatic, Generate → takes,
Record, Import take). Panel AGENT: tab provider + bảng kịch bản
(thời điểm + câu thoại) + ghi chú công việc + nút Survey/Write VO/
Review/Project context/Workspace + dòng "auto mode on".

## 4. Ảnh timeline mẫu đẹp (chuẩn thẩm mỹ timeline)

Header track gọn (mã V2/V1/A1/A2 + tên + icon mắt/loa/khóa/CC);
thước mm:ss + playhead kèm đồng hồ hiện tại/tổng; clip bo góc, màu
phân loại (title card hồng chữ trắng, video có thumbnail + tên,
audio xanh lá có sóng + tên); chip hiệu ứng nhỏ trên đầu clip video;
icon transition nhỏ ở điểm nối; tên dài cắt bằng "…".

## 5. Xung đột giữa các nguồn và cách giải quyết (ảnh thắng)

- CapCut dùng toolbar icon ngang trên cùng, app gốc dùng rail dọc
  trái. GIẢI QUYẾT: giữ rail dọc (test khóa rail + ảnh timeline mục
  tiêu là app gốc); toolbar trên chỉ gọn lại thành icon, không thêm
  toolbar icon ngang kiểu CapCut.
- App gốc đặt Agent ở cột phải full-height; spec Neon Nights mới nhất
  đặt Agent ở sidebar TRÁI; bản web trước đó đặt Agent trong cột phải
  dưới Inspector. GIẢI QUYẾT (spec mới nhất thắng): Agent dời sang
  sidebar trái ngoài cùng; timeline vẫn full-width dưới cùng; rail +
  library + preview + inspector giữ thứ tự trái → phải.
- Ảnh gốc: Music tím; ảnh đẹp: audio xanh lá. GIẢI QUYẾT (spec Neon
  Nights thắng): mọi audio = green + waveform; video = cyan mờ viền
  sáng; title = pink neon; caption = chip tím; vai trò phân biệt bằng
  chip mã track (V1/V2/A1…), không bằng màu clip.
- Ảnh gốc: tab AGENT tên Claude/Director; dòng "auto mode on".
  GIẢI QUYẾT: KHÔNG copy — tab dùng provider thật (MCP/Ollama), vì
  đặt tên Claude/Director sẽ ngụ ý phiên không tồn tại; không có dòng
  auto mode vì không có chế độ đó; trạng thái kết nối chỉ một dòng +
  lệnh MCP copy được.
- Ảnh gốc: icon mắt/loa/khóa trên header track. GIẢI QUYẾT: chỉ hiện
  mắt (đang hiển thị) và loa (track âm thanh) dạng chỉ báo tĩnh, vì
  bản port không có hide/mute/lock — không làm nút giả.

## 6. Điểm của app gốc KHÔNG copy 1:1 sang web (và cách thay thế)

- Control native macOS: AVPlayerView → `<video>`; TimelineCanvas vẽ tay
  → div/lane HTML + hit-test riêng; SwiftTerm PTY → không có (dock chỉ
  chạy lệnh an toàn có sẵn + lệnh MCP cho agent ngoài); NSMenu/Finder/
  traffic-light → menu trong trang, không mở Finder; SF Symbols → SVG
  inline kiểu Lucide; sheet/popover → `<details>`/modal tự viết.
- Cột Agent full-height cạnh timeline: bản web giữ timeline full-width
  (đúng ảnh CapCut) nên Agent là sidebar trái, không phải cột cạnh
  timeline.
- Hide/mute/lock track, keyframe diamonds trên canvas, trim handle
  hover: chưa có trong bản port nên không vẽ giả.
- Terminal/scopes/questions của agent ngoài: bản web không host PTY;
  thay bằng dòng trạng thái + lệnh MCP + các lệnh an toàn.

## 7. Spec Neon Nights (vòng 14, chính thức) — đối chiếu nhanh

- Nền app #09090b, panel #16161a/#18181b, viền 1px #27272a/#3f3f46,
  chữ mặc định #a1a1aa, active trắng: ĐẠT (biến CSS `:root`).
- Font stack hệ thống Inter/SF Pro, không tải font ngoài: ĐẠT.
- Accent neon chỉ pink #ec4899, cyan #06b6d4, purple #8b5cf6, green
  #10b981; playhead đỏ #ef4444: ĐẠT; không còn viền trắng (đã sửa cả
  playhead thước trắng thành đỏ). Vòng 16 hài hòa lại: chrome về
  trung tính (nút primary #1e1e24 chữ trắng, không glow; vạch tiêu
  đề vùng #52525b), cyan chỉ còn ở active/selected/focus + CTA +
  màu clip + playhead; CTA dịu thành #0e7490→#be185d; clip mờ fill
  0.08 + viền 0.45.
- Toolbar icon tối giản + CTA Export Video gradient (vòng 14:
  cyan→pink; vòng 16 dịu thành #0e7490→#be185d), góc phải, bo góc:
  ĐẠT (SVG inline + `.sr-only` giữ nhãn cho test và trình đọc màn
  hình).
- Media Library grid 3 cột, thumbnail bo 6px, badge thời lượng nền
  đen mờ: ĐẠT (badge lấy từ duration thật của media).
- Player khung đen, điều khiển dưới, timecode trắng nhỏ mm:ss.cs:
  ĐẠT (`00:03.90 / 02:31.46`).
- Inspector text-xs, input nền #09090b viền mờ: ĐẠT.
- Timeline: thước giây nhỏ xám, playhead đỏ/hồng xuyên track, track
  tách bằng viền mảnh, clip theo loại, bo góc, tên text-xs trắng cắt
  "…": ĐẠT (clip ngắn <90px tự ẩn thumbnail + thời lượng).
- Stack: HTML/CSS/JS thuần, không React/Tailwind/Node build: ĐẠT.
- Responsive 1280–1920 ở 100/125/150% không cuộn ngang trang,
  Inspector không cắt, timeline không khuất: ĐẠT ở 1280/1600/1920 ở
  100% và 125% (thang breakpoint 1160→300px, 859→280px); ở 1280@150%
  (853px hiệu dụng, dưới chiều rộng tối thiểu 1161pt của app gốc)
  preview bị bóp hẹp nhưng trang vẫn không cuộn ngang, Inspector và
  timeline còn nguyên; gập Agent trong Settings để lấy lại chỗ.
- Vòng 16: cột Agent 300px→340px (tổng ở 1280 vẫn ≤1280). Vòng 17:
  rail dọc thành hàng ngang trên cùng, thước và lane dùng chung gốc
  (margin-left thước 138px, 94px ở ≤720px) nên playhead thẳng hàng.

## 8. Ngôn ngữ giao diện (quyết định, vòng 14)

Toàn bộ nhãn tự do dùng tiếng Việt. Giữ nguyên tiếng Anh cho: (a) nút
CTA "Export Video" (theo đúng brief); (b) thuật ngữ kỹ thuật mà người
dùng đã dùng bằng tiếng Anh (Timeline, Inspector, Preview, Source,
Fit, Compare, Safe area, Project, Review, Plugins, MCP, clip/track);
(c) nhãn gốc của app gốc mà người dùng chỉ vào (rail Media/Audio/
Text…, INSPECTOR, AGENT, Edited rev, Export report, nút Survey/Write
VO/Review, Voiceover/Clone voice/Import a voiceover take); (d) chuỗi
bị test khóa (dropzone, empty-hint, create-tools). Từ khóa lệnh của
agent (help, list clips, export, review, stats) giữ tiếng Anh vì đó là
tên lệnh, không phải nhãn.

## 9. Đồng bộ preview/playhead hai chiều (thiết kế)

- Timeline → preview: `seekPreviewToPlayhead()`; clip đang chọn thì
  đổi qua hàm thuần `timelineToSourceSeconds()` (giây timeline → giây
  nguồn theo in/speed, kẹp theo duration); chưa có metadata thì chờ
  `loadedmetadata` thay vì bỏ seek như trước.
- Preview → timeline: `timeupdate` + `seeked` trên `<video>` đổi ngược
  qua `sourceToTimelineSeconds()`; lệch ≤1 frame được coi là echo của
  chính seek vừa gửi (do làm tròn) nên chỉ refresh caption, không
  render lại timeline.
- Caption overlay: item text đang active tại playhead (hoặc từ karaoke
  đang active) tại đúng `textStyle.positionX/positionY`; chỉ ở chế độ
  Source (bản xuất đã có subtitle đốt sẵn).
- Trạng thái trống: `#previewEmpty` hiện khi chưa có nguồn preview nào;
  video/ảnh nguồn luôn load toàn bộ file qua `/api/media/<id>`, không
  cắt đoạn; sóng audio trên track lấy từ toàn bộ file qua
  `/api/waveform` (backend giải mã toàn file, chia bucket).
- Sau khi sửa (split/trim/move), `load()` giữ nguyên playhead và
  seek lại preview theo playhead mới — không chuyển chế độ, không tải
  lại trang.

## 10. Ghi chú plugin/agent-kit (ĐÃ CŨ — xem vòng 15, giữ lại để rõ lịch sử)

Ghi chú gốc ở đây (4 skill, thiếu auto-update, plugin chỉ tìm local)
đã lỗi thời từ vòng 15: hiện có 21 skill kèm manifest SHA-256,
`agent_kit_update`/`agent_kit_later` đã thật (kiểm chữ ký Ed25519),
plugin đã fetch registry `bashcut-plugins` (cache 24 giờ, kiểm SHA-256
+ chữ ký, cài dạng review-only vì manifest registry là macOS-only).
Chi tiết đúng hiện tại nằm ở `PARITY.md`, không phải mục này.

## 11. Bố cục vòng 18 (bổ sung sau, không sửa các mục 1–10)

- **Topbar đúng 48px một hàng, không wrap:** `#status` dời khỏi header
  thành toast cố định tự ẩn sau 4s; các mục phụ gom vào
  `<details class="top-more">` trong header; hai nút toggle Agent và
  Inspector nằm NGOÀI top-more nên luôn nhìn thấy được.
- **Agent là drawer phải cố định:** top 98px, rộng 340px (giữ nguyên
  giá trị khóa vòng 16), có backdrop, đóng bằng Esc / click backdrop /
  nút X (vòng 19); mở mặc định khi viewport ≥1600px, trạng thái lưu
  localStorage; drawer giữ nguyên nội dung dock (lệnh MCP + lệnh an
  toàn), đúng mô hình agent ngoài qua MCP/CLI của app gốc.
- **Thư viện tách riêng:** dropzone tách khỏi danh sách media (giữ
  đúng 3 cột, nút "+" overlay khi hover/focus); vòng 19 gộp tiếp thành
  MỘT nút "+ Nhập" duy nhất (dropzone là nút, input file ẩn bằng
  class visually-hidden, submit ẩn khỏi mắt nhìn nhưng vẫn trong DOM).
- **Preview canvas:** đúng tỉ lệ project qua `--project-aspect`, cao
  tối đa min(52vh,600px); vòng 19 thêm poster: chưa có bản xuất thì
  hiện frame đầu của clip main qua `/api/media/<id>` sẵn có (không
  endpoint mới), không còn hộp đen; chỉ còn một thông báo trống chính
  (`#previewEmpty`), nhãn phụ ẩn khi trống.
- **Phím tắt vòng 18:** Ctrl+N/O/S/Z/Shift+Z/Y, Delete, Space, J (tua
  lùi 1 giây, không phải phát ngược), K, L, mũi tên ±1 frame,
  Alt+Shift+C, Ctrl+E/T, Shift+Z, Ctrl+K tách, Ctrl+Shift+K tách tất
  cả, S = Magnetic, Shift+A/A, Shift+Backspace khít khoảng trống,
  Ctrl+R bảng tốc độ, Shift+B đường cong tốc độ.
- **Giá trị khóa phải giữ (vòng 18):** tool-col 280px, agent-col 340px,
  track-label 128px, gap 10px, ruler margin-left 138px (94px ở
  ≤720px), timeline-wrap padding ngang 14px, mediaList đúng 3 cột,
  details-col 300/340px, workbench grid
  `280px minmax(0, 1fr) auto`, thứ tự rail, nav tool-rail trước
  workbench, agent-col trước tool-col, details-col trước timeline-wrap.

## 12. Vòng 19: tay kéo đổi cỡ, tooltip icon, sửa từ test thật

- **Tay kéo đổi cỡ (kéo thả, Pointer Events):** giữa tool-col và cột
  giữa (đổi rộng cột trái), giữa cột giữa và details-col (đổi rộng
  Details), giữa workbench và timeline (đổi cao timeline), cạnh trái
  drawer Agent (đổi rộng drawer, không xung đột logic đóng/mở).
  Mặc định không đổi (280/340/300-340px, timeline
  clamp(240px,32vh,340px)); đổi cỡ chỉ bằng inline style do JS đặt,
  không sửa rule CSS bị khóa. Giới hạn: trái 180–480px, Details
  220–520px, timeline 180px–60vh, drawer 280–520px. Nhớ cỡ qua
  localStorage key `vibeedit_panel_sizes` (kiểm tra hợp lệ trước khi
  áp, hỏng thì dùng mặc định); double-click tay kéo trả vùng đó về
  mặc định.
- **Tooltip nút icon:** nguyên nhân thật vòng 18 — CSS tooltip
  `::after` đặt DƯỚI nút nhưng toolbar có overflow-x auto nên cả hai
  trục đều thành scroll container, tooltip bị chính toolbar cắt
  (z-index không thắng được overflow clipping). Sửa: một
  `#uiTooltip` duy nhất do JS tạo ở cấp body, position fixed,
  z-index 100, nội dung lấy từ aria-label, hiện khi hover và khi
  focus bàn phím, ẩn khi rời chuột/phím, khi pointerdown, khi scroll;
  không thêm thuộc tính title (tránh tooltip đôi). Rule CSS cũ giữ
  nguyên văn vì test khóa.
- **Sửa từ test thật trên Windows:** helper `post` duy nhất ở cấp
  top-level (trước đây chỉ sống trong một IIFE nên 14 nút
  Knowledge/Vision/Plugin chết với `post is not defined`); Magnetic
  toggle nay đảo thật + trạng thái tiếng Việt; "Về đầu" luôn về
  frame 0; Undo/Redo báo trạng thái mới kèm rev; Sections thành
  toggle thật (aria-pressed + marker trên ruler); Voice kiểm tra
  backend thật (voice_check) trước khi tạo, thiếu thì báo rõ, không
  im lặng; đổi tên project commit bằng Enter + báo tên mới; nhịp
  0-beat báo rõ đã chạy nhưng không tìm thấy nhịp; ducking và đổi
  tên đã kiểm chứng persist thật (handler + status đã có, không
  phải bug mới); Ollama vốn đã báo trung thực "chưa kết nối trong
  app"; server nuốt lặng ConnectionResetError/BrokenPipeError khi
  đóng tab (override ở tầng server, vì handler không có
  handle_error).
- **Bug chặn fps (làm trước mọi mục khác):** `dur` là frame PROJECT
  ở mọi nơi tiêu thụ (timeline, server duration, render) nhưng
  add_clip mặc định, source_insert và overwrite_insert cũ dùng frame
  NGUỒN làm dur → clip 60fps trong project 30fps dài gấp đôi. Sửa:
  quy đổi seconds-first (frame_nguồn / fps_nguồn × fps_project) ở
  cả client (mediaDurFrames, mediaDurationS) và server; `in` vẫn là
  frame nguồn (render chia cho fps media); migration một lần khi mở
  project cũ (đổi dur của clip video, đóng dấu `fps_units`,
  backup file trước migration, clip thiếu fps media thì bỏ qua và
  báo skipped); project test của người dùng (2 clip 59,94fps, đang
  hiện 453s) sau pull sẽ hiện ~226,9s mà không cần import lại.
  Cùng gốc: upload dedupe theo SHA-256 (cùng file → dùng lại media
  id cũ, báo rõ; khác file trùng tên vẫn name-2/name-3), parser
  multipart chịu cả LF (lỗi cũ lưu file tên "mp4" do header lọt vào
  tên), tên file giữ nguyên sau sanitize (cả đường dẫn Windows).
- **Làm đẹp / chi tiết (chỉ phần không vướng test khóa):** clip
  radius 6 + viền rgba(255,255,255,.06), lane #14141a / lẻ #17171e /
  kẻ #22222a, playhead giữ #ef4444 (chỉ phần dưới mờ 40%), nhãn
  "INSPECTOR" 11px uppercase letter-spacing .08em màu #8a8579,
  topbar GIỮ 48px (test khóa, không đổi sang 44px), logo GIỮ data
  URI (pipeline đẩy snapshot text-only làm hỏng PNG nhị phân),
  toolbar đã là SVG nên không còn glyph Unicode để đổi (giữ
  stroke-width 2 cho cùng bộ topbar), nút zoom −/+ bước theo đúng
  pxPerSec (kẹp 10–200), hint footer có max-width + title đủ text
  (giữ nowrap vì test khóa), nút "Mở Cài đặt" (btnDetailsModify)
  vốn đã nối vào Settings nên không xóa, chỉ báo "Đã lưu" sau khi
  POST /api/save thành công thật (lúc ghi hiện "Đang lưu…" nhấp
  nháy), lane trống 28px bằng class riêng `.is-empty`, ruler chỉ
  render tick trong vùng nhìn thấy (tick phụ 500ms khi đủ thưa).
- **Dừng do test khóa (không sửa test):** chữ phụ tiếng Anh trong
  dropzone ("Drag and drop videos, photos, and audio files here")
  GIỮ NGUYÊN vì test_capcut_ui.py:90 và test_round18.py:115 khóa
  chuỗi đó.
- **Ghi chú sửa mục 10 (không sửa nội dung mục 10):** mục 10 viết
  trước vòng 15 nên đã cũ — skills hiện là 21 (không phải 4) và
  agent_kit_update/later đã thật từ vòng 15; xem PARITY vòng 19.

