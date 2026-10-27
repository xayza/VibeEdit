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
  playhead thước trắng thành đỏ).
- Toolbar icon tối giản + CTA Export Video gradient cyan→pink, góc
  phải, bo góc: ĐẠT (SVG inline + `.sr-only` giữ nhãn cho test và
  trình đọc màn hình).
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

## 10. Ghi chú plugin/agent-kit (không phải việc của vòng giao diện)

Agent kit (bashcut-agent-kit) và plugins (bashcut-plugins) đều CẦN cho
parity đầy đủ nhưng không cần để editor lõi chạy. Bản Windows hiện chỉ
có 4 skill (`windows/skills/`), `agent_kit_check`/`install` chạy từ
thư mục local, thiếu auto-update bản phát hành đã ký; plugin hiện chỉ
tìm trong máy local, thiếu fetch registry — lưu ý: registry TỒN TẠI
(static `registry.json` trong bashcut-plugins), bản ghi cũ nói "không
tồn tại" là sai. Cả hai xếp SAU vòng giao diện, dưới dạng chức năng.
