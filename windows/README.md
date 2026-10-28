# VibeEdit — Windows (chuyển toàn bộ BashCut macOS sang Windows)

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

## Vòng rà soát thứ hai — knowledge, skills ghi, reorder, marker, font, caption MCP

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
- **Kiểm chứng:** 454 tests OK trên Linux VM (404 trước vòng năm + 50
  test vòng năm mới: 14 công cụ MCP, 20 desktop, 14 nút chết giao
  diện, 2 đường dẫn skills khi đóng băng).

## Phase 0 — bảng parity và an toàn dữ liệu

Mục tiêu sản phẩm là **chuyển TOÀN BỘ BashCut gốc macOS thành ứng dụng
Windows mang tên VibeEdit** — không giới hạn ở MVP hay Giai đoạn 1, và
không chủ động bỏ tính năng nào của bản gốc. Bảng parity đầy đủ ở
[`PARITY.md`](PARITY.md): mỗi tính năng ghi works / partial /
missing — planned to port kèm mức độ xác minh (Windows thật / Linux VM /
chỉ đọc source gốc). Không có tính năng gốc nào bị ghi là "out of scope".
Vòng 9 bổ sung: backdrop clip (blur/màu, render thật), state panel
chạy (dismiss/toggle/follow), request follow-up fix-issues /
another-recipe đúng wording gốc, và mở view plugin (show-view).

Trạng thái hiện tại (sau đợt full-parity vòng 14): **MCP 479 công cụ
(401 thao tác thật, 78 kiểm tra-và-báo-lỗi)** — số live đọc từ
`/api/mcp-tools` trong app; số trong tài liệu sẽ cũ đi khi thêm công cụ
mới. Đã hoạt động thêm từ các đợt full-parity: magnetic đầy đủ +
linked audio + reorder, cài plugin, skills (đọc + ghi), knowledge
store, vision (khi máy có backend), motion transitions, reframe,
caption transcribe/generate/align (khi máy có faster-whisper), font
import, hoãn/bỏ qua cập nhật, tìm library/plugin, chạy plugin qua hook
đã khai báo, phân tích media bằng ffprobe, proxy media, desktop
single-instance + fallback trình duyệt khi thiếu pywebview/WebView2,
pipeline media.analyze thật (tech/picture/sound, speech map, strip,
sync), motion clip từ preset gốc + xoay framing (render bằng crop
expression), thay nhạc giữ volume/fade, cửa sổ lời dẫn, kho outcomes,
run log + checklist, mô tả media, đo tốc độ nói, khóa style ảnh +
disclose, đóng/gỡ gói library, phân tích item library, brand pose từ
ảnh, plugin overlays/actions/views/proposal/replace, kit check/install,
trim chính xác theo khung hình, cửa sổ enable overlay nửa mở
[start, end), kiểm chứng tích hợp end-to-end (export tổng hợp khớp
report, server smoke tắt sạch) và checklist test Windows
(`WINDOWS_TEST_CHECKLIST.md`, chỉ là tài liệu chuẩn bị — chưa yêu cầu
người dùng test).
Hoạt động một phần: Compare chưa khóa khung hình, export
preset ProRes/4K mới render trên Linux VM từ clip giả lập chưa kiểm
chứng trên footage 4K gốc; desktop tắt
sạch, HiDPI, phím tắt Ctrl và test chạy trên Windows đã làm xong về
code ở Phase 2, chỉ còn chưa kiểm tra bằng mắt / bằng `py` trên
Windows thật. Còn thiếu và sẽ port tiếp (không bỏ): bộ cài/.exe cho
máy Windows sạch, Windows CI, clone giọng nói (giọng Edge/Piper đã
có, chỉ clone từ mẫu giọng là chưa có),
app updater tự thay app đang chạy (chỉ mới có handoff + hoãn/bỏ qua),
model
segmentation học sâu cho cutout, `clip_send_to_agent`,
`plugins_setup`, `agent_kit_update`/`agent_kit_later`,
`image_generate`, `library_generate`, và hợp nhất vào `VibeEdit/` —
xem `PARITY.md` để có danh sách thật.

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

## Full-parity vòng 9 — backdrop clip, run-panel actions, plugins.show-view: 7 công cụ từ honest thành thật

- **Đọc spec gốc trước khi code:** `ClipBackdrop.swift` +
  `ProjectDocument+Backdrop.swift` + `ClipBackdropTests.swift`
  (P3-J7), `UIAction.swift` + `ProjectDocument+UIActions.swift` +
  `RunPanelModel.swift` + `AgentFollowUp.swift`,
  `ProjectDocument+PluginViews.swift` + `PluginViewModel.swift`.
- **`clip_backdrop` thật (`project.py` + `render.py`):**
  `validate_backdrop`/`set_backdrop` theo đúng ngữ nghĩa gốc
  (kind blur/color, blur 0–0,5 mặc định 0,05, dim 0–1, màu
  #RRGGBB mặc định đen; kind lạ/blur vượt khoảng/dim vượt
  khoảng/màu sai định dạng đều bị từ chối — test validation gốc
  từ chối blur=2 và kind glow; màu sai gốc parse thành đen còn
  bản này từ chối rõ để typo không lặng thành đen). Render thật
  cho main track still/video/freeze: ảnh fit phủ lên nền là bản
  sao fill-scale của chính khung hình + blur Gaussian (bán kính =
  blur × cạnh ngắn, dưới 0,5 px thì không blur như gốc) hoặc màu
  solid, dim nhân RGB (đi qua gbrp — nhân trong YUV sẽ rửa
  chroma); fades/màu/motion/tilt chạy trên composite nên backdrop
  di chuyển, mờ dần và grading cùng clip như gốc. Bằng chứng
  pixel (still nửa đỏ/nửa xanh 200×100 fit vào 320×180): không
  backdrop thì fill phủ kín canvas; màu xanh lá thì bar xanh lá
  và ảnh vẫn đỏ/xanh; blur thì bar trái đỏ/phải xanh; dim 0,5 thì
  bar đỏ tối đúng khoảng như test gốc. Thu hẹp thật: chỉ main
  track — item overlay track bị từ chối rõ vì chưa có lớp
  backdrop (render lặng mà không báo mới là giả).
- **Run-panel actions thật (`round9.py`):** vòng 8 giữ honest vì
  "headless không có panel"; vòng 9 xét lại — widget panel là
  chuyện viewer, còn trạng thái shown/dismissed/follow là state
  thật lưu trong project data, `run_checklist` nay kèm trường
  `panel` để quan sát được. `run_dismiss`/`run_toggle`/
  `run_follow` đổi state thật (toggle khi ẩn thì show, khi hiện
  thì dismiss; follow bật/tắt cờ, headless không có viewer để
  cuộn nên chỉ cờ là thật và ghi rõ vậy). `run_fix_issues`/
  `run_another_recipe` trả đúng text follow-up AgentFollowUp gốc
  (fix cần result + issues còn lại, đếm fresh từ validation;
  validate Windows chỉ có errors nên warnings luôn 0); headless
  không có session agent để deliver nên tool trả request cho
  agent gọi MCP thực thi, không bao giờ tuyên bố đã gửi.
- **`plugins_show_view` thật (`round9.py`):** validate như
  panelPlugin gốc (plugin có views, đang bật — disabled bị từ
  chối; view phải có trong manifest), trả plugin + view +
  location theo placement; placement inspector trả shown=False
  và không đổi state (đúng bản gốc: view inspector theo
  selection, không có gì để mở); placement khác ghi view đang mở
  vào project data để lần gọi sau thấy cùng view đang mở.
  `plugins_view` vẫn là đường render component.
- **Sửa lỗi do test spec bắt được:** module mới `round9` chưa có
  trong `vibeedit.spec` — test spec bắt mọi module core phải là
  hidden import, thiếu nó bản frozen sẽ hỏng như vòng 8 từng gặp
  với `round8`; đã thêm `vibeedit_core.round9` (nay 20 hidden
  import).
- **Lỗi đã biết phát hiện trong vòng 9 (chưa sửa, ghi trong
  `PARITY.md`):** freeze ở fps mà khung cuối không rơi đúng mốc
  thập phân 3 chữ số (30 fps: 29/30 → "0.967" làm mất khung) nên
  đoạn freeze render 0 khung và file ngắn hơn report; lỗi có sẵn
  giống hệt khi có/không backdrop, test vòng 9 dùng 25 fps để
  kiểm chứng nhánh freeze backdrop thật mà không sửa lặng lỗi
  chung (hướng sửa: tăng độ chính xác timestamp trim ở đường
  freeze, cần chạy lại toàn bộ test render).
- **Số liệu:** MCP vẫn **479** (không thêm công cụ mới),
  **401 thật / 78 honest**; **552 tests OK** trên Linux VM
  (549 + 3 test vòng mười mới). Cây Swift không động, không hợp
  nhất, chưa đẩy. Smoke server trên project tạm riêng: `GET /`
  200, `/api/mcp-tools` 479 công cụ gồm cả 7 công cụ vòng 9,
  `/api/info` 200 (Python 3.12.3, FFmpeg 8.1.2).

## Vòng 14 — làm lại giao diện theo app gốc + spec Neon Nights, đồng bộ preview/playhead

Vòng trình bày, không thêm/bớt tính năng hay MCP (479 = 401 thật + 78
honest). Agent sang sidebar trái; rail + library, preview, Inspector,
timeline full-width dưới cùng. Top bar icon SVG kiểu Lucide, CTA Export
Video gradient cyan→pink góc phải. Timeline: header mã track, clip
video cyan + thumbnail thật, audio green + sóng thật, title pink,
caption chip tím, chip hiệu ứng và icon transition chỉ từ dữ liệu thật,
playhead đỏ, timecode mm:ss.cs. Preview đồng bộ hai chiều với playhead
(sai số <1 frame, kiểm chứng bằng test Node trích nguyên văn hàm
mapping); caption overlay đúng vị trí/thời gian; trạng thái trống thay
khung đen giả. Nhãn tự do dùng tiếng Việt, giữ tiếng Anh cho CTA và
thuật ngữ kỹ thuật (xem `UI_MAP.md` §8). Kiểm chứng: py_compile,
node --check, full suite 584 tests OK trên Linux VM, smoke
server project tạm (GET / 200, `/api/mcp-tools` 479, `/api/info` 200,
`/api/agent-status` 200, tắt sạch). Chi tiết và giới hạn còn lại ở
[`PARITY.md`](PARITY.md) mục vòng 14 và [`UI_MAP.md`](UI_MAP.md).

## Vòng 15 — agent kit đầy đủ qua kênh releases đã ký + plugin registry fetch

Không thêm công cụ MCP mới (tổng vẫn 479); 2 công cụ từ báo-lỗi
thành thật (`agent_kit_update`, `agent_kit_later`) nên 479 = 403
thật + 76 honest. Module mới `vibeedit_core/round15.py` (stdlib
only). Kit thật từ repo công khai `dongnguyenvie/bashcut-agent-kit`
— bản **0.1.56**, giấy phép **MIT**: 17 skill chép nguyên văn vào
`windows/skills/` (cộng 4 skill cũ thành 21), nguồn + phiên bản +
SHA-256 từng file trong `skills/KIT_MANIFEST.json`, LICENSE nguyên
văn ở `skills/KIT_LICENSE.txt`. `agent_kit_update` đọc
`releases.json`, tải bản mới, kiểm size + SHA-256 + chữ ký Ed25519
của publisher (thuật toán thuần stdlib, kiểm chứng bằng vector RFC
8032 và chữ ký thật của kit 0.1.56), staging + validate skill rồi
mới swap, giữ bản cũ tới khi swap thành công, khôi phục khi lỗi;
file người dùng trùng tên không bao giờ bị ghi đè.
`agent_kit_later` ghi hoãn 7 ngày vào `KIT_STATE.json`.
Registry plugin từ file tĩnh `registry.json` của repo
`bashcut-plugins` (10 plugin): fetch có cache 24 giờ
(`plugin_registry_cache.json`, runtime state, không push),
`plugins_search` thêm `source=registry`/`all`,
`plugins_updates` thêm `check_registry=true`, `plugins_install`
thêm `registry_plugin` (download → SHA-256 → chữ ký publisher →
staging → manifest khớp id/version registry → swap → sidecar +
trạng thái tắt). Giới hạn trung thực: manifest registry dùng id có
dấu chấm + tên map `{en, vi}` và script macOS nên không qua
validation nghiêm ngặt của `install_plugin` (cố tình không nới);
bản registry chỉ liệt kê để xem, không chạy được và không bật được
trên Windows, mọi bản đều kèm cảnh báo chỉ có nền tảng macOS.
Kiểm chứng: py_compile, node --check, MCP 479 = 403 + 76, test 249
tên gốc vẫn đủ, full suite trên Linux VM, smoke server project tạm.
Chi tiết ở [`PARITY.md`](PARITY.md) mục vòng 15.

## Giao diện vòng 16 — hài hòa màu, cột AI Agent to hơn

- **Chrome về trung tính:** nút primary nền #1e1e24 chữ trắng không glow; vạch accent trước tiêu đề vùng, badge Windows MVP, link, nhãn import, tiêu đề Details, hover, safe-area, divider Compare đều về xám; cyan chỉ còn ở trạng thái active/selected/focus, nút CTA chính, màu clip theo loại và playhead.
- **CTA Export Video dịu lại:** gradient từ #06b6d4→#ec4899 thành #0e7490→#be185d, glow giảm; màu clip giữ phân theo loại nhưng mờ xuống (fill 0.08 + viền 0.45); playhead giữ đường đỏ #ef4444 làm điểm nhấn chức năng duy nhất.
- **Cột AI Agent 300px → 340px** (tổng ở 1280 vẫn 1256 ≤ 1280; hành vi gập ở màn hẹp giữ nguyên).
- Kiểm chứng: node --check, py_compile, 48 test mục tiêu OK, full suite 584 test OK trên Linux VM; chỉ sửa `static/style.css` + assertion CTA trong `test_round14.py`; cây Swift không động.

## Giao diện vòng 17 — thanh công cụ lên hàng ngang trên cùng, sửa lệch playhead timeline

- **Thanh công cụ dọc thành hàng ngang trên cùng (kiểu CapCut):** `<nav class="tool-rail">` dời ra khỏi cột trái, thành hàng full-width ngay dưới topbar; đủ 12 nút theo đúng thứ tự cũ (Media, Audio, Text, Stickers, Effects, Transitions, Filters, Voice, Knowledge, Vision, Timeline, More) với cùng data-tab/data-action nên handler chuyển panel giữ nguyên; cột panel công cụ vẫn ở bên trái preview, thu từ 356px về 280px; cột AI Agent giữ 340px; màn hẹp hàng tự cuộn ngang trong chính nó.
- **Sửa lệch playhead:** nguyên nhân là thước và lane dùng hai gốc tọa độ khác nhau — vạch lane đặt trong `.track-lane` (sau cột nhãn 128px + gap 10px) còn thước đứng riêng với gốc là mép trái timeline-wrap, lệch đúng 138px. Cách sửa: `.ruler` thêm `margin-left: 138px` (94px ở breakpoint ≤720px, nơi nhãn thu về 84px) để hai gốc trùng nhau; handler click thước dùng `rect.left` của ruler nên tự đúng theo, không cần sửa JS. Test `tests/test_round17.py` (12 test mới) chứng minh tick thước = vạch lane = vị trí clip tại cùng thời điểm (sai số ≤1px) và click thước đặt playhead đúng trong 1 frame.
- Kiểm chứng: node --check, py_compile, 60 test mục tiêu OK, full suite 617 test OK trên Linux VM; MCP giữ 479 = 403 + 76; cây Swift không động, không merge.

## Vòng 19 — công cụ honest thành thật + tay kéo đổi cỡ + sửa từ test thật

- **MCP 479 = 420 thật + 59 honest (tổng không đổi, không thêm công cụ mới):** 17 công cụ chuyển honest→thật, chứng minh bằng hành vi thật trong `tests/test_round19.py` (không chỉ đổi mô tả): 13 dialog `show_*` thành alias của công cụ đọc thật tương ứng (`show_about`→`app_version`, `show_commands`→`mcp_tools_list`, `show_plugins`→`plugins_list`, `show_history`→`project_history`, `show_assets`→`media_list`, `show_batch`→`batch_status`, `show_export`/`show_export_progress`→`export_status`, `show_review`→`review_get`, `show_doctor`→`doctor_run`, `show_agent_kit`→`agent_kit_check`, `show_updates`→`app_update_check`, `show_sections`→`markers_list`), `agent_quick_edit`→`timeline_apply`, và 3 công cụ trạng thái session mới (`ui_select` đặt/đọc selection đã validate trên project đang mở, `ui_seek` đặt playhead session theo frame tuyệt đối có kẹp ≥0, `context_get` chụp nhanh project + session — dùng đúng session state sẵn có của server). Vẫn honest với lý do thật: `show_settings`/`show_shortcuts` (không có store/shortcut map phía server), `ui_frame`/`ui_frames` (không có ảnh khung hình headless), `view_compare`/`view_safe_area` (toggle của trình duyệt), playback, chat/terminal agent trong app (giữ mô hình agent ngoài), voice clone (3), `image_generate`/`library_generate`, `app_update` (tự thay app đang chạy), `plugins_setup`, `clip_send_to_agent`, `acme_voice_fast`. Cập nhật số đếm trong test cũ chỉ gồm assertion số exact và xóa tên khỏi danh sách honest (đúng thông lệ repo, xem báo cáo vòng 19).
- **Bug chặn fps (làm trước mọi mục khác):** `dur` là frame PROJECT ở mọi nơi tiêu thụ (timeline, server duration, render) nhưng code cũ dùng frame NGUỒN làm dur: media 113,45s @ 59,94fps = 6797 frame trong project 29,97fps hiện 226,79s, 2 clip báo 453,59s trong khi file xuất chỉ 226,76s. Sửa triệt để hai phía: `add_clip` mặc định, `source_insert` (server + MCP), `overwrite_insert` đều quy đổi seconds-first (frame_nguồn / fps_nguồn × fps_project); client `mediaDurFrames`/`mediaDurationS` quy đổi tương tự; `in` vẫn là frame nguồn (render chia cho fps media); render không cần sửa (đã đọc dur bằng frame project). Migration một lần khi mở project cũ (kèm backup file trước migration, đóng dấu `fps_units`, clip thiếu fps media thì bỏ qua và báo skipped); clip xếp chồng khít (at = at trước + dur trước, theo đơn vị cũ) được dời `at` theo cùng tỉ lệ của clip trước để không còn khoảng trống thừa, còn clip có khoảng trống hoặc cố định vị trí giữ nguyên `at`; project test của người dùng sau pull sẽ hiện ~226,9s mà không cần import lại. Cùng gốc: upload dedupe theo SHA-256 (cùng file → dùng lại media id cũ, báo "File này đã có, dùng lại media …"; khác file trùng tên vẫn name-2/name-3), parser multipart chịu cả LF, tên file giữ nguyên sau sanitize (kể cả đường dẫn Windows).
- **Tay kéo đổi cỡ:** 4 tay kéo (cột trái, Details, cao timeline, drawer Agent) bằng Pointer Events, giới hạn trái 180–480px / Details 220–520px / timeline 180px–60vh / drawer 280–520px, nhớ cỡ qua localStorage `vibeedit_panel_sizes` (kiểm tra hợp lệ, hỏng thì mặc định), double-click tay kéo trả về mặc định; mặc định và rule CSS bị khóa không đổi, đổi cỡ chỉ bằng inline style do JS đặt.
- **Tooltip nút icon:** chẩn đoán thật — CSS tooltip `::after` dưới nút bị chính toolbar (overflow-x auto) cắt; sửa bằng tooltip nổi cấp body (`#uiTooltip`, fixed, z-index 100, nội dung từ aria-label, hiện khi hover + focus, ẩn khi rời/chuột xuống/scroll); không thêm title (tránh tooltip đôi); rule CSS cũ giữ nguyên văn vì test khóa.
- **Gộp nút Nhập:** dropzone thành nút nhập duy nhất nhìn thấy được (bấm → mở hộp chọn file, kéo-thả giữ luồng cũ, chọn file → tự tải lên); input file và nút submit ẩn khỏi mắt nhìn nhưng vẫn trong DOM (giữ id); chữ phụ tiếng Anh trong dropzone GIỮ NGUYÊN vì test khóa (`test_capcut_ui.py:90`, `test_round18.py:115`).
- **Sửa từ test thật trên Windows:** helper `post` duy nhất ở cấp top-level (14 nút Knowledge/Vision/Plugin chết vì `post is not defined`); Magnetic đảo thật + trạng thái tiếng Việt; "Về đầu" luôn về frame 0; Undo/Redo báo trạng thái mới kèm rev; Sections thành toggle thật (aria-pressed + marker trên ruler); Voice kiểm tra backend thật trước khi tạo; đổi tên commit bằng Enter + báo tên mới; nhịp 0-beat báo rõ đã chạy nhưng không tìm thấy nhịp; ducking/đổi tên đã kiểm chứng persist thật; Ollama vốn đã báo trung thực "chưa kết nối trong app"; server nuốt lặng traceback khi đóng tab (override ở tầng server).
- **Review batch:** poster frame đầu clip main khi chưa có bản xuất (qua `/api/media` sẵn có, không endpoint mới); drawer Details trượt từ phải ở ≤1100px + nút X cho cả hai drawer + aria-pressed rõ ràng; nhãn trung thực cho ô lệnh nhanh (placeholder "Nhập lệnh nhanh (help để xem danh sách)", badge "lệnh nhanh — chưa phải AI", nút "Gửi"→"Chạy"); làm đẹp không vướng khóa (clip radius 6, lane #14141a/#17171e, playhead giữ #ef4444 chỉ mờ phần dưới, "INSPECTOR" 11px, topbar giữ 48px, logo giữ data URI); zoom −/+ theo đúng pxPerSec; hint footer có title đủ text; nút "Mở Cài đặt" vốn đã nối vào Settings; chỉ báo "Đã lưu" sau POST /api/save thành công thật; lane trống 28px bằng class riêng; ruler chỉ render tick trong vùng nhìn thấy (tick phụ 500ms khi đủ thưa).
- Kiểm chứng: py_compile các file chạm tới, node --check, nhóm mục tiêu (test_round18 + test_round19) OK, full suite (xem báo cáo vòng 19), smoke server với project tạm; cây Swift không động, không merge. Kiểm chứng trực quan trên Windows thật vẫn để lại cho người dùng sau khi pull.

## Vòng 20 — shortcut map suy từ app.js + frame timeline render thật

- **MCP 479 = 423 thật + 56 honest (tổng không đổi, không thêm công cụ mới):** 3 công cụ chuyển honest→thật, chứng minh bằng hành vi thật trong `tests/test_round20.py` (không chỉ đổi mô tả). `show_shortcuts` KHÔNG giữ bảng copy tay (copy tay sẽ drift): parser đọc `static/app.js` lúc chạy — quét comment kiểu string-aware, trích body các keydown listener của document bằng cân bằng ngoặc, rồi đọc từng branch theo quy tắc cơ học (nhóm modifier, test `key === "..."`, chuỗi quy tắc action: api → hàm đã khai báo → click/railClick → pause/play → dòng đầu branch). Kết quả đúng 30 phím tắt (Ctrl+S/Z/Shift+Z/Y, Ctrl+K/Shift+K/N/O/E/T/R, Alt+Shift+C, Shift+Z/A/B/Backspace, Delete, Space, S, I/O/E/Q, Escape, J/K/L, arrows, A); phím cố tình không bind (Ctrl+C/V/X/A/G, Shift+P/X…) vắng mặt vì comment vòng 18 đã bị lược trước khi parse; test đột biến (xóa một branch khỏi bản copy) chứng minh map suy từ file thật. `ui_frame`/`ui_frames` render timeline bằng FFmpeg (preset draft) rồi trích frame chính xác tại thời điểm yêu cầu (mặc định dùng playhead session từ vòng 19, hoặc `time`/`times`/`count` cho trước) — test pixel chứng minh frame 0,5s đỏ và 1,5s xanh trên project đỏ→xanh, khác với frame đầu của file media; thời gian ngoài timeline và project rỗng báo lỗi rõ. Vẫn honest với lý do chính xác: `show_settings` (không có settings nào thuộc server — modal chỉ có format project, thông tin chỉ đọc và localStorage trình duyệt, bịa key không ai đọc là giả), `platforms_get` (không có bảng platform facts ở cả hai cây; preset chỉ có width/height/bitrate, bịa maxSeconds/LUFS/safeArea/giới hạn ký tự là bịa dữ liệu), cộng các giữ honest cấu trúc từ trước (chat/terminal agent trong app, playback, toggle trình duyệt, voice clone, sinh ảnh, updater tự thay app, `plugins_setup`, `clip_send_to_agent`, `acme_voice_fast`). Cập nhật số đếm trong test cũ chỉ gồm assertion số exact và xóa tên khỏi danh sách honest.
- **Dọn §10 UI_MAP.md:** ghi chú plugin/agent-kit cũ (4 skill, thiếu auto-update, plugin chỉ local) đã lỗi thời từ vòng 15 — thay bằng ghi chú ngắn trỏ sang `PARITY.md` (21 skill, update có chữ ký, registry fetch review-only); các chuỗi khóa vòng 16 giữ nguyên.
- Kiểm chứng: py_compile các file chạm tới, không chạm static nên không cần node --check lại, nhóm mục tiêu (test_round18 + test_round19 + test_round20) OK, full suite (xem báo cáo vòng 20), smoke server với project tạm; cây Swift không động, không merge. Kiểm chứng trực quan trên Windows thật vẫn để lại cho người dùng sau khi pull.

## Vòng 21 — agent_status là kit status + debug log file thật

- **MCP 479 = 425 thật + 54 honest (tổng không đổi, không thêm công cụ mới):** 2 công cụ chuyển honest→thật, chứng minh bằng hành vi thật trong `tests/test_round21.py` (không chỉ đổi mô tả). `agent_status`: spec gốc chứng minh nó là kit status (folder/version/skills của kit + trạng thái setup theo tab/CLI, KHÔNG phải terminal session) nên nội dung headless của nó chính là dữ liệu `agent_kit_check` (alias, mô tả ghi rõ phần per-tab/per-CLI không được theo dõi ở đây); test assert hai công cụ trả dữ liệu bằng nhau. `app_vibeedit_debug_log`: server thực sự ghi một dòng cho mỗi lần gọi MCP vào file debug log (theo đúng thiết kế DebugLog gốc: một file text chung, cap byte, `VIBEEDIT_DEBUG_LOG_PATH` đổi đích), công cụ đọc lại đúng các dòng đó (mặc định 100 dòng cuối, 1–1000); thời gian + tên công cụ, KHÔNG ghi argument (có thể chứa nội dung người dùng), các lần đọc debug log không tự ghi để không làm bẩn log; file chưa có thì trả rỗng kèm ghi chú, không bịa dòng nào. Vẫn honest với lý do đã kiểm chứng lại trên code hiện tại (không copy lý do cũ): `agent_setup` (hành động privileged cài kit vào tab/CLI ngoài — port không có tab và không ghi config CLI ngoài; `kit_install` chỉ cài vào thư mục kit của app), `agent_setup_show` (card setup là checklist 2 bước cần trạng thái kit-install theo từng CLI + danh sách starter bundle — cả hai đều không được theo dõi, không có trạng thái enum nào ánh xạ "không biết"), `agent_show_changes`/`dismiss`/`undo_changes` (không có AgentChangeRecord nào — author/label/changed IDs + vòng đời notice đều không tồn tại; file backup chỉ là trạng thái trước, không phải bản ghi thay đổi), `app_vibeedit`/`automation_clients` (không có Unix-socket server hay registry client nào), nhóm terminal/chat/playback/toggle trình duyệt (không có machinery tương ứng trong `vibeedit_core`, không có view flag nào trong `server.py`), `show_settings`/`platforms_get` (đã kiểm lại: modal không có setting thuộc server; spec platforms tồn tại nhưng không có bảng facts nào trong cả hai cây).
- Kiểm chứng: py_compile các file chạm tới, không chạm static nên không cần node --check lại, nhóm mục tiêu (test_round18 + test_round19 + test_round20 + test_round21) OK, full suite (xem báo cáo vòng 21), smoke server với project tạm; cây Swift không động, không merge. Kiểm chứng trực quan trên Windows thật vẫn để lại cho người dùng sau khi pull.

## Vòng 22 — vòng sửa lỗi từ test thật trên Windows (rev sync P0, zoompan-fps #0, export nền, inputSchema)

- **MCP 479 = 427 thật + 52 honest:** giữ 2 chuyển đổi của phần audit (agent_terminals, app_vibeedit_automation_clients — danh sách rỗng thật vì server theo thiết kế không có phần tử nào); vòng sửa lỗi không tự đổi số đếm. Test mới chỉ trong `tests/test_round22.py` (giữ nguyên phần audit, thêm test sửa lỗi).
- **P0 rev sync:** app giữ project trong RAM và ghi đè khi lưu nên edit của agent ngoài qua MCP mất âm thầm (đĩa rev 107, 35 marker → sau POST set_speed vẫn rev 107, 34 marker). Sửa: refresh từ đĩa khi đĩa mới hơn RAM trước mọi apply web và mọi call MCP (trừ project_open tự nạp), xóa undo stack cũ khi trạng thái đổi từ ngoài, đọc lỗi không động vào RAM; kịch bản báo cáo nay giữ cả marker lẫn speed mới, rev tăng đơn điệu; race ghi thật sự cùng lúc vẫn là giới hạn (cần file locking).
- **#0 zoompan-fps:** clip 59,94 fps có keyframe scale bị nhân đôi vì zoompan phát lại frame theo fps của chính nó và bỏ qua setpts (người dùng: timeline 226,827 s → video 330,16 s, audio 226,86 s; bỏ keyframe thì đúng 226,76 s). Sửa: chèn `fps={fps project}` TRƯỚC zoompan ở cả hai điểm sinh zoompan (clip main qua `_motion_filter`, still-image overlay) và giữ fps của zoompan bằng fps project; cấm fps trailing sau zoompan. Bằng chứng: thí nghiệm filter cô lập (120 frame 59,94 qua zoompan fps=29,97: 120 frame/4,004 s không có fps trước, 60 frame/2,002 s khi có) + test thứ tự filter (fail-trước). Render đầy đủ nhỏ đúng cả ở code cũ vì `-shortest` cắt video nhân đôi tại cuối audio — đó là guard không hồi quy, không phải bằng chứng fail-trước; vì sao `-shortest` không cắt file 330 s của người dùng vẫn còn mở và cần preset/lệnh xuất chính xác của người dùng để đóng lại. Lưới an toàn mới: sau render ffprobe file, lệch >1,0 s so với timeline thì cảnh báo lớn (không chặn export).
- **#1 export nền:** `do_POST` từng giữ `state.lock` suốt render đồng bộ nên GET /api/project timeout trong lúc render (người dùng: 4/5 timeout 6 s). Sửa: worker thread từ snapshot deepcopy, trả job ngay, endpoint trạng thái không cần lock chính, UI poll 1 s + thanh progress không xác định (không bịa % giả) + nút Hủy (chỉ chặn publish, FFmpeg đang chạy vẫn chạy nền); test HTTP chứng minh GET /api/project <2 s trong lúc render giả chậm 2,5 s. Nguyên nhân 400 trên console chưa truy ra request/body cụ thể — ghi rõ là chưa đóng.
- **#2–#6:** Magnetic — `load()` đọc sai shape response (`mg.magnetic` thay vì `result.magnetic`) nên aria-pressed luôn false và click luôn gửi enabled:true; nay `magnetic` lên top-level của project view, `load()` đồng bộ từ đó, bỏ fetch magnetic_get. #3 — không phải Delete push 2 snapshot mà `magnetic_get` bị push snapshot qua mỗi lần `load()` (nay early-return không snapshot). #4 — Vision/Knowledge/voice/chuyển tab nay gọi `setStatus` (toast 4 s giữ nguyên). #5 OTIO — import chỉ giải quyết theo thư mục .otio trong khi export ghi path theo project nên luôn trượt rồi lưu record hỏng (Missing: media/mp4); nay thử 6 ứng viên (kể cả sourceFolder từ metadata) và giữ nguyên target trong `missing` khi không tìm thấy. #6 — tab-close Windows ném ConnectionAbortedError (anh em, không phải subclass, của ConnectionResetError) nên filter vòng 19 trượt; nay nuốt cả ba, lỗi khác vẫn in traceback.
- **MCP (a)** notification không id → không response (kể cả không ghi `"null"`); method lạ có id → -32603. **(b) inputSchema** trích bằng AST từ code handler cho đủ 479 công cụ: 270 có properties không rỗng, 209 rỗng thật (157 zero-arg thật + 52 honest) — test assert đúng 270/209 thay vì "mọi công cụ non-empty" (bịa property sẽ vi phạm quy tắc không-bịa); alias kế thừa schema gốc; các fix tay đã kiểm chứng từ code tiêu thụ. **(c) nút Sao chép** sinh lệnh thật từ vị trí app (python .venv/Scripts → .venv/bin → sys.executable; script + thư mục project tuyệt đối) qua `/api/agent-status`; JS điền cả hai ô lệnh từ đó. **.gitignore** mới cho `windows/`.
- **Mục vague:** picker mở project thứ hai gãy thật ở `open_project` (từ chối path tuyệt đối ngoài `projects/`; nay cho phép + ô nhập path ở welcome); Welcome/Tạo take/Faces/Cutout không tái hiện lỗi handler; Batch rỗng chỉ thêm note UI (server cố tình xuất project hiện tại); "Xem bản xuất" nay disable khi chưa có `last_export`; overlap là đúng, không sửa; chuỗi tiếng Anh bị test khóa giữ nguyên; gộp import 3-control chưa đóng (cần audit DOM visibility).
- **Góp ý vòng 19/21 còn hoạt động:** poster frame đầu clip main, chỉ báo "Đã lưu", ruler ảo hoá, badge "lệnh nhanh — chưa phải AI", icon SVG, lane/clip radius 6 + ring cyan, ruler thưa tick; media card đúng (chữ "mp4" là record hỏng từ OTIO, #5 xử lý gốc). Logo giữ data URI (pipeline push chỉ cho text).
- Kiểm chứng: py_compile các file chạm tới, node --check, nhóm mục tiêu (test_round18 + 19 + 20 + 21 + 22) OK, full suite (xem báo cáo vòng 22), smoke server với project tạm + GET trong lúc render <2 s; cây Swift không động, không merge. Kiểm chứng trực quan trên Windows thật vẫn để lại cho người dùng sau khi pull.

## Vòng 23 — skill dạng thư mục + import + đồng bộ Claude Code

- **MCP 481 = 429 thật + 52 honest:** thêm 2 công cụ mới (`skills_import_plan`, `skills_import`); skill thư mục (`skills/<id>/SKILL.md` + `references/` + `kit/`), import từ .md/thư mục/plugin Claude/.zip (chỉ copy, chống zip-slip, 50 MB/2000 entry), đồng bộ sang `.claude/skills/` (dạng thư mục, không ghi đè file sửa tay nếu không có overwrite), `resources/list` + `resources/read` cho skill (`vibeedit-skill://<id>`).
- Kiểm chứng: 21 skill phẳng không đổi; full suite 813 test OK trên Linux VM.

## Vòng 24 — audit honest + hardening từ vòng 22

- **MCP 481 = 432 thật + 49 honest:** 3 công cụ honest chuyển thật dạng rỗng-by-design (`voice_clone_list` → `{"clones": []}`, `ui_dialog` → `{"dialogs": []}`, `chat_status` → `{"agents": []}`); 49 công cụ còn lại vẫn honest, lý do pin trong `tests/test_round24.py`.
- Hardening: hasAudio dò file thật (ffprobe) thay vì tin bản ghi; hủy xuất kill FFmpeg thật, xóa file dở; `MCPServer.call` kiểm tra tham số bắt buộc trước mọi tác dụng phụ; `plugins_install`/`ui_select` không còn schema bắt buộc thừa.
- Kiểm chứng: full suite 832 test OK trên Linux VM.

## Vòng 25 — khóa file project + chẩn đoán xuất

- **Không đổi số đếm (481 = 432 + 49).** Khóa file `<project>.lock` (stdlib, `O_CREAT|O_EXCL`, token `pid:uuid`, timeout 10 s → lỗi to, stale 60 s, tái nhập theo luồng); giữ khóa chỉ quanh đoạn [refresh, mutate, save, rev bump]; tool chạy lâu + `project_open` giữ refresh-first không khóa.
- Báo cáo xuất thêm chẩn đoán: `ffmpeg_command`, `filter_complex`, `shortest`, `audio_map`, `clip_fps` (fps nguồn/null + `source_fps_known: false` khi bản ghi không có fps, không lặng lẽ thay bằng fps project), `output_durations` (video_s/audio_s đo từ file xuất, null + ghi chú khi dò lỗi).
- Kiểm chứng: 3 tiến trình × 4 `markers_add` → đủ 12 marker, rev đơn điệu, không còn file `.lock`; full suite 844 test OK trên Linux VM.

## Vòng 26 — quét nhất quán ngôn ngữ: chuỗi tiếng Anh còn lại sang tiếng Việt

- Ba cổng mỗi chuỗi (không test nào khóa, không code nào match, không thuộc diện cố tình giữ tiếng Anh); khoảng 600 phần thông điệp sang tiếng Việt (19 file `vibeedit_core` + HTML/JS); 10 bản dịch revert sau lần chạy suite đầu vì test khóa (không sửa test); giữ tiếng Anh có pin trong `tests/test_round26.py` (dropzone subtext, CTA Export video, tooltip icon timeline, `No beat grid detected yet`, `Unknown transition kind`, thông điệp chứa `exceeds`, tín hiệu hủy xuất, guard filelock, mô tả `mcp.py`).
- Kiểm chứng: full suite 860 test OK trên Linux VM.

## Vòng 27 — rà soát bổ sung: bản dịch phần 2, đóng pipe stderr, sửa lệch tài liệu

- **Không đổi số đếm (481 = 432 + 49), không tool nào chuyển thật.** Vòng 26 bỏ sót các chuỗi viết dạng literal nối dòng (nối chuỗi ngầm nhiều dòng): bản này dịch nốt các chuỗi qua đủ ba cổng (lý do analysis/speech-map, cảnh báo OTIO/media, cảnh báo plugin, lỗi transition, cảnh báo lệch thời lượng, ghi chú render bị bỏ qua, ghi chú round8/round9/round15, body lỗi HTTP `Unknown export job`, ghi chú skill/updater, nút danh sách + trạng thái trống trong app.js).
- Sửa rò rỉ pipe stderr trong `decode_sound_levels` và `_decode_mono_8k_envelope` (suite từng báo ResourceWarning ở hai chỗ này).
- Sửa lệch tài liệu: tiêu đề PARITY.md + dòng bảng mục 8 về đúng 481 = 432 + 49; README.md đổi tiêu đề khỏi cụm "Phase 8…" cũ (mục tiêu là chuyển toàn bộ, không giới hạn phase) và thêm các mục vòng 23–27; checklist Windows sửa dòng registry (registry tồn tại từ vòng 15; chỉ phần chạy plugin registry trên Windows là chưa có) và thêm mục kiểm chứng vòng 23–26; UI_MAP.md thêm mục vòng 27.
- Kiểm chứng: target test 31 test OK + full suite 891 test OK (201 s) trên Linux VM; MCP 481 = 432 + 49 không đổi; 3 bản dịch revert sau khi suite bắt được test khóa (xem PARITY.md vòng 27).

## Giao diện vòng 18 — bố cục tổng thể theo app gốc + phím tắt

- **Topbar 48px một hàng:** sửa đúng 3 nguyên nhân gây wrap (flex-wrap, label dạng cột, status chiếm cả hàng); `#status` dời khỏi header thành toast cố định góc dưới-trái, tự ẩn sau 4s; các mục phụ (Export report, Plugins, Review, Settings, tỉ lệ, preset xuất) gom vào `<details class="top-more">` trong header, giữ nguyên id; thêm nút mở Agent và nút đóng/mở Details cạnh Export; xóa thẻ "Windows MVP" khỏi giao diện (cả tiêu đề tab).
- **Agent thành drawer phải:** cố định top 98px, rộng 340px, có backdrop, đóng bằng Esc hoặc click backdrop, khi đóng không chiếm chỗ; mở mặc định khi viewport ≥1600px, trạng thái lưu localStorage; drawer giữ nguyên nội dung dock hiện có (lệnh MCP + lệnh an toàn), đúng mô hình agent ngoài qua MCP/CLI của app gốc, không thêm chat AI trong app.
- **Thư viện / preview / token:** vùng import tách riêng khỏi danh sách media (giữ đúng 3 cột, nút "+" overlay khi hover/focus, xóa dòng mã media m-0001); preview canvas đúng tỉ lệ project qua `--project-aspect`, cao tối đa min(52vh,600px); token màu chuẩn hóa, CSS gộp mỗi khối thành một khai báo gốc.
- **Phím tắt (hai đợt):** đã nối Ctrl+N/O/S/Z/Shift+Z/Y, Delete, Space, J (tua lùi 1 giây, không phải phát ngược), K, L, mũi tên ±1 frame, Alt+Shift+C, Ctrl+E/T, Shift+Z, Ctrl+K tách, Ctrl+Shift+K tách tất cả, S chuyển thành Magnetic, Shift+A/A, Shift+Backspace khít khoảng trống, Ctrl+R bảng tốc độ, Shift+B đường cong tốc độ. Chưa nối vì app chưa có chức năng gốc (không gán bừa): Ctrl+C/V/X, Ctrl+A, Ctrl+Shift+S/F, V/C, Ctrl+L, Shift+P, Shift+X/Alt+X, Ctrl+G, Alt+G.
- Kiểm chứng: node --check, py_compile, 129 test mục tiêu OK, full suite 663 test OK trên Linux VM; MCP giữ 479 = 403 + 76; cây Swift không động, không merge. Kiểm chứng trực quan 4 kích thước trên Windows thật vẫn để lại cho người dùng sau khi pull.

## Full-parity vòng 13 — kiểm chứng tích hợp end-to-end, rà soát docs, checklist test Windows

- **Export tổng hợp (test `tests/test_round13.py`, dữ liệu giả lập
  tạm, không dùng project/media mẫu của người dùng):** project
  320×180 @ 30 fps gồm clip main hẹp có backdrop blur, clip main
  thứ hai, dissolve 0,5 s giữa hai clip, freeze 30 khung sau clip
  thứ hai, overlay video đã trim, overlay still, một caption, nhạc
  sine và narration sine phủ toàn timeline. Kết quả đo được, khớp
  nhau giữa report và file: report duration 4,5 s, transitions 1,
  text_overlays 1, overlay_clips 2, skipped rỗng; file
  103.766 byte, H.264 320×180, đúng 135 khung đọc được (60 + 60 +
  30 − 15 khung chồng transition), duration format đúng 4,5 s,
  audio AAC 48 kHz stereo; khung cuối (4,2 s) vẫn là màu xanh của
  clip main bị freeze, không đen.
- **Cắt/ghép giữ project hợp lệ:** split clip 90 khung tại khung 30
  rồi trim nửa phải về khung 75, project vẫn validate OK, tổng
  75 khung.
- **Server smoke:** server thật chạy trong thread ở cổng tạm: `GET /`
  200 (có `compareWipe`), `/api/mcp-tools` trả `count` 479,
  `/api/info` 200 (có `python`); shutdown + server_close + join
  thread xong, cổng bind lại được ngay — không sót process.
- **Rà soát docs:** sửa các chỗ lệch số/trạng thái (tiêu đề trạng
  thái hiện tại ở `PARITY.md` và `README.md` còn ghi "vòng 9", số
  MCP 394/85 còn sót trong một dòng bảng `PARITY.md` trong khi
  chính dòng đó kết luận 78 honest, hai nhãn "(mới nhất)" cũ ở
  vòng 2 và vòng 9). Quét lại: không chỗ nào gọi FFmpeg bundle là
  LGPL (mọi lần nhắc đều là "không phải LGPL, là GPLv3"); các mục
  "còn thiếu" hiện tại chỉ còn những thứ thật sự chưa có (clone
  giọng, segmentation học sâu, registry, .exe/CI, updater tự thay
  app, hợp nhất). Các mục lịch sử theo vòng giữ nguyên như lúc
  viết, không sửa ngược.
- **Checklist test Windows (`WINDOWS_TEST_CHECKLIST.md`, chỉ viết
  tài liệu, không yêu cầu người dùng làm ngay):** thứ tự git pull
  đúng cách, launcher, UI fit ở 4 kích thước × scaling 100/125/150%,
  import kể cả trùng tên, edit/split/copy-paste, text, transition,
  backdrop, freeze, nhạc/voiceover ghi micro, export kể cả
  youtube4k/proRes422HQ, desktop pywebview/HiDPI/phím tắt Ctrl,
  chạy full suite bằng `py`, và mục "báo lại cho bimo cái gì"
  (ảnh chụp + kích thước cửa sổ + scaling + lỗi nguyên văn).
- **Số liệu:** MCP không đổi **479** (không thêm công cụ mới),
  **401 thật / 78 honest**; **567 tests OK** trên Linux VM
  (563 + 4 test vòng mười ba mới); test 249 tên gốc chạy lại
  vẫn đủ. Cây Swift không động, không hợp nhất, chưa đẩy.

## Full-parity vòng 12 — cửa sổ enable của overlay chuyển sang nửa mở [start, end) theo đúng spec gốc

- **Quyết định sau khi đọc spec gốc (không đoán):** bản gốc đặt
  mọi item video (cả track chính lẫn overlay) bằng
  `CMTimeRange(start: destination, duration: fps.time(duration))`
  (CompositionBuilder.swift ~155 và ~215); CMTimeRange theo định
  nghĩa là nửa mở; `item.end` là `at + duration`
  (Project.swift:99); lane được tái dùng khi `prev.end <= start`
  (VideoCompositionLanes.swift: `take`). Vì vậy khung ở `end`
  thuộc về item kế tiếp, và hành vi `between()` bao hàm cũ của
  bản Windows là sai so với gốc — vòng 12 sửa chứ không giữ.
- **Sửa (render.py, helper `_enable_window`):**
  `gte(t, start)*lt(t, end)` thay cho `between(t, start, end)` ở
  cả 5 vị trí dùng cùng mẫu: overlay video đường thường, overlay
  video chia theo opacity, overlay still, adjustment layer, text
  drawtext. Cả hai biên đều cắt ngắn về 6 chữ số thập phân (không
  làm tròn): làm tròn đầu cuối lên sẽ đưa khung biên trở lại
  (29/30 s thành "0.967" đã vượt timestamp 0,9667 s của chính
  khung đó), làm tròn đầu bắt đầu lên sẽ làm rớt khung đầu tiên.
- **Tái hiện (test `tests/test_round12.py`, 7 test, fail trước
  sửa, pass sau sửa):** overlay video 30 khung nay khung 30 chỉ
  còn main; overlay 29 khung (kết thúc 0,9667 s không rơi đúng
  mili-giây) nay khung 29 chỉ còn main; overlay chia opacity,
  overlay still, adjustment mono trên nền đỏ và text đều hết
  khung lặp ở đúng thời điểm kết thúc.
- **Trường hợp bình thường không đổi:** hồi quy overlay chạy
  riêng 107 test OK (vòng 9, 10, 11, 12, phase 4, phase 8, motion,
  integration, halftone); khung đầu tiên của overlay không đổi
  (đầu bắt đầu vẫn bao hàm, chỉ cắt ngắn xuống để không rớt
  khung).
- **Số liệu:** MCP vẫn **479** (không thêm công cụ mới),
  **401 thật / 78 honest**; **563 tests OK** trên Linux VM
  (556 + 7 test vòng mười hai mới); test 249 tên gốc chạy lại
  vẫn đủ. Cây Swift không động, không hợp nhất, chưa đẩy.
  Smoke server trên project tạm riêng: `GET /` 200,
  `/api/mcp-tools` 479 công cụ, `/api/info` 200 (Python 3.12.3,
  FFmpeg 8.1.2).

## Full-parity vòng 11 — trim chính xác theo khung hình cho overlay video + cửa sổ transition, sửa lỗi `-shortest` ăn khung cuối

- **Overlay video + transition (tái hiện trước, sửa sau):**
  `_frame_trim` của vòng 10 nay mở rộng sang trim overlay video
  (đường chia theo opacity và đường thường, dùng fps của media
  nguồn) và các chia pre/tail/head/post của transition motion
  (dùng fps project, vì chuỗi chain đã chuẩn hoá về fps project
  qua filter `fps`). Test tái hiện `tests/test_round11.py`
  (4 test, fail trước sửa, pass sau sửa): overlay bắt đầu ở
  khung nguồn 29 nay hiện đúng khung đỏ đầu tiên; dip-black
  58 + 60 khung với cửa sổ 29 khung nay ra đúng 89 khung;
  spin cùng hình học nay đặt đúng khung trắng duy nhất ở khung
  xuất 58. Nhánh dip-black trong (chia nửa) giữ nguyên vì đã
  chứng minh cho cùng kết quả (xem `PARITY.md`).
- **Lỗi chặn phát hiện trong lúc tái hiện:** lệnh xuất dùng
  `-shortest` mà chuỗi âm thanh im lặng làm tròn `.3f` nên ngắn
  hơn video một chút, khiến `-shortest` loại đúng khung video
  cuối cùng trên mọi render có tổng thời lượng không rơi đúng
  mốc mili-giây (nối 58 + 60 không transition: 117 khung khi có
  `-shortest`, 118 khi bỏ nó). Đã sửa bằng cách pad mix âm
  thanh cuối thêm một khung hình quá cuối video: video luôn là
  luồng ngắn nhất nên `-shortest` chỉ cắt đuôi âm thanh ở cuối
  video, thời lượng file vẫn bằng thời lượng video. Atrim,
  xfade/acrossfade giữ nguyên có chủ ý.
- **Trường hợp bình thường không đổi:** nối không transition
  58 + 60 nay ra đúng 118 khung; transition rơi đúng mili-giây
  (dip-black/spin 30 khung) vẫn ra đúng 88 khung; still chính
  29 khung vẫn ra đúng 29 khung (trim `end` ở đường still đã
  kiểm chứng là chính xác, không phải lỗi). Quan sát kề bên
  chưa sửa: cửa sổ enable của overlay dạng bao hàm cả hai đầu
  nên overlay còn hiện thêm một khung lặp ở đúng thời điểm kết
  thúc — cần vòng riêng quyết định ngữ nghĩa enable kèm kiểm
  tra hồi quy overlay trước khi đổi.
- **Số liệu:** MCP vẫn **479** (không thêm công cụ mới),
  **401 thật / 78 honest**; **556 tests OK** trên Linux VM
  (552 + 4 test vòng mười một mới); test 249 tên gốc chạy lại
  vẫn đủ. Cây Swift không động, không hợp nhất, chưa đẩy.
  Smoke server trên project tạm riêng: `GET /` 200,
  `/api/mcp-tools` 479 công cụ, `/api/info` 200 (Python 3.12.3,
  FFmpeg 8.1.2).

## Full-parity vòng 8 — state/workflow + provider-local thật, 28 công cụ từ honest thành thật

- **Nhóm state/workflow (đọc spec gốc trước khi code):**
  `clip_motion` (10 preset MotionPreset chép nguyên từ
  `Keyframes.swift` của gốc: zoom-in/out, pan 4 hướng, fade-in-out,
  pop-in, slide-up, zoom-punch; map zoom→scale, pan share→x, tilt
  share→y — tilt gốc là pan dọc, KHÔNG phải xoay; custom keyframes
  JSON với thời gian `t`/`s`/`frame`; lưu qua `set_keyframes` nên
  render bằng zoompan/tilt/opacity; framing focus bị từ chối kèm
  hướng tới `clip_reframe`), `clip_change_framing` (xoay preset
  ReframePreset gốc wide/medium/close/left/right, transform
  zoom/pan/tilt chép nguyên từ `Project.swift`, render bằng crop
  expression `(iw-ow)/2+pan` có clamp — không phải số tĩnh, vì kích
  thước scale thật phụ thuộc tỉ lệ nguồn), `music_replace` (thay
  đoạn Music giữ volume/muted/fade của clip đầu, lặp trừ khi
  loop=false), `narration_windows` (khoảng trống giữa từ caption và
  item voiceover, anchor afterWord/firstCut/firstBeat/section,
  budget từ chỉ khi có rate; từ transcript của analysis record là
  thời gian nguồn, KHÔNG phải thời gian timeline nên cố tình không
  dùng), `outcomes_import`/`outcomes_map` (JSON/CSV, curve giữ đơn
  vị `t` giây hoặc `position` phần trăm, map lên marker section rồi
  mới toàn video, percent→fraction), `run_append`/`run_checklist`
  (run log trong project data đi cùng save/backup/undo; cổng:
  done không evidence → unverified, skipped không reason → lỗi,
  review-done khi stage bắt buộc còn mở → `stage_pending`).
- **Nhóm provider/model — phân biệt phần local làm được:**
  `media_describe`/`media_description`/`media_digest` (tóm tắt từ
  shot facts do người gọi cung cấp + analysis record, không bịa mô
  tả; coverage tính shot đo được mô tả ≥ một nửa), `speech_rate`
  (ĐO từ từ transcript: tiếng Việt đếm âm tiết, CJK đếm ký tự, còn
  lại đếm từ; p10/p50/p90 theo cụm ngắt >0,5 s — không phải cài đặt
  TTS), `image_style`/`image_disclose`/`image_generate_list` (khóa
  style là state thuần của project; disclose gắn một text item nhỏ
  góc trên-trái mỗi run clip đã generate trên track captions, không
  có label cấu hình thì không thêm gì), `library_export_pack`/
  `library_import_pack` (đóng gói `pack.json` + file có kiểm tra
  licence: `redistribute: false` bị từ chối và nêu tên, thiếu
  licence liệt kê `unknownLicenses`; import chống traversal, ID
  trùng → lưu version mới `id-v{n}`, cap 50 MiB),
  `library_analyze` (ffprobe tech + loudnorm/true peak + landmark
  envelope + tempo, lưu version mới), `library_brand_pose` (chỉ
  đường ảnh: OpenCV grabCut → sticker PNG dưới `brand/`; đường
  generate bị từ chối kèm tên provider thiếu), `agent_kit_check`
  (kit local + skills; channel/newer null kèm ghi chú chưa cấu hình
  kênh releases nên không kiểm tra bản mới hơn) và
  `agent_kit_install` (copy skill pack .md, id an toàn, trùng/không
  an toàn bị từ chối).
- **Plugin (đọc spec gốc trước khi code):** manifest nhận thêm
  `actions`/`views` (ghi raw như `options`); hook trả `{"propose":
  [ops]}` chỉ lưu proposal chờ duyệt, không áp dụng ngay; overlay
  chỉ trong session, không lưu vào project; `plugins_view`/
  `plugins_view_event` (mô hình component JSON, state input trong
  session, nút có action chạy qua `apply_plugin` kèm cổng disabled);
  `plugins_proposal` (kiểm tra nguyên tử trước khi áp dụng; op cho
  phép: set_clip_field volume/muted/fade, set_text, add_text);
  `plugins_replace` (kiểm tra ID ứng viên == ID đã cài TRƯỚC khi
  copy, plugin đã cài phải disabled như install overwrite).
- **Giữ honest có bằng chứng (không code nửa vời):** `clip_backdrop`
  (render chain chỉ fill-scale/crop, chưa có nền fitted-picture),
  `clip_send_to_agent` (không có session agent trong server
  headless), `run_dismiss`/`run_toggle`/`run_follow`/`run_fix_issues`/
  `run_another_recipe` (UIAction của panel chạy, headless không có
  panel), `plugins_setup` (plugin .py thuần không khai báo recipe
  phụ thuộc), `plugins_show_view` (headless không có viewer; dữ liệu
  view lấy qua `plugins_view`), `agent_kit_update` (cần kênh
  releases đã ký, chưa cấu hình) / `agent_kit_later` (chỉ đóng
  prompt UI), `image_generate` / `library_generate` (cần provider
  sinh), clone giọng (cần model clone), `acme_voice_fast` (chuỗi
  capability của provider acme, không phải spec lệnh; không có
  provider acme nào được nối).
- **Số liệu:** MCP vẫn **479** (không thêm công cụ mới),
  **394 thật / 85 honest**; **531 tests OK** trên Linux VM
  (506 + 25 test vòng tám mới). `vibeedit.spec` nay liệt kê 19
  hidden import (`round8` mới — test spec bắt mọi module core phải
  có mặt). Cây Swift không động, không hợp nhất,
  chưa đẩy. Smoke server trên project tạm riêng: `GET /` 200,
  `/api/mcp-tools` 479 công cụ, `clip_motion` và `run_append` có
  mặt.

## Full-parity vòng 7 — pipeline media.analyze thật, speech map, strip, sync

- **Pipeline `media.analyze` thật (`vibeedit_core/analysis.py`,
  FFmpeg + Python thuần, không thêm dependency):** `media_analyze`
  đo tech từ ffprobe (codec, kích thước, rotation, frame timing
  cho VFR khi dưới 30000 khung hình, colour transfer/primaries/
  bit depth, độ dài track), picture samples ở tốc độ cho trước
  (mặc định 4/s, tham số `rate` 0,5–30): luma/spread/change/peak
  trên thumbnail xám 24×24 đúng định nghĩa review.picture,
  sharpness bằng Laplacian trên khung xám 256 px, colourfulness
  Hasler–Süsstrunk trên thumbnail RGB 24×24, và mọi bước nhảy
  từ 0,04 trở lên được thu hẹp tới đúng cặp khung hình bằng
  cách giải mã khoảng đó ở tốc độ đầy đủ; sound RMS mỗi 0,1 s
  trên mọi kênh (giải mã 48 kHz), peak, tương quan stereo.
  Bản ghi sống trên media entry (`analysis_record`, key =
  SHA-256 của kích thước + 1 MiB đầu/cuối file theo đúng hình
  thức key của bản gốc), dùng lại khi chưa `force`, force đo
  lại và bỏ corrections. Transcript chỉ đo khi faster-whisper
  đã cài (tiny, word timestamps khi model cho); vắng backend
  thì words rỗng kèm lý do nêu lệnh cài, các phần còn lại vẫn
  thật. `media_analysis` nay đọc bản ghi đó (cuts theo
  minScore + corrections, shots với motion = mean/peak change
  trong shot đúng ReviewShots.motion, summary, histogram độ
  dài shot, cuts mỗi 10 s, sound floor/median/loud/active
  spans/curve) và chỉ rơi về metadata + ffprobe khi chưa có
  bản ghi. Bản ghi analyze tách biệt với bản ghi `media_cuts`
  vòng sáu (scene filter): hai danh sách cắt là hai phép đo
  khác nhau, không gộp lặng.
- **`media_speech_map` thật:** cổng đúng SpeechMap.swift
  (Otsu bin 0,5 dB, bỏ cửa sổ lặng số, cần ít nhất 10 cửa sổ
  âm thanh và dải ít nhất 0,5 dB; separation clear/weak/none/
  given; spans/gaps null kèm lý do khi không tách được;
  transcript khi bản ghi có từ). Kiểm chứng trên clip tổng
  hợp tone/lặng/tone: spans đúng [0,1] và [2,3], gap đúng
  [1,2]; clip quiet/loud cho spans đúng nửa sau; ép
  minSeparationDb = 60 cho separation none đúng spec.
- **`media_strip` thật:** khung hình ở giữa mỗi ô trên
  from…to (mặc định 8, tối đa 24), thước thời gian, mức âm
  -60…0 dBFS từ bản ghi hoặc đo ngay, gaps từ speech map tô
  đậm, từ transcript ở đúng thời gian, vẽ thành một PNG bằng
  Pillow (1600 px mặc định); vắng Pillow thì vẫn trả dữ liệu
  strip với path null kèm lý do; audio không có hàng hình
  nên frames rỗng và không có PNG.
- **`media_sync` thật:** cổng đúng AudioSync.swift (envelope
  log RMS 10 ms ở mono 8 kHz, coarse 10/s rồi fine 100/s
  quanh lag tốt nhất ±0,3 s, halves khớp nhau trong 0,02 s
  mới steady; correlation dưới 0,4 nghĩa là không có âm thanh
  chung; kèm map in-point của clip qua `item`). Kiểm chứng
  trên clip tổng hợp lệch đúng 0,5 s: đo đúng 0,5 s,
  correlation 1,0, halves cùng 0,5 s, steady; hai tần số khác
  nhau cho correlation 0,109 → sharedSound false.
- **Độ lệch trung thực cần ghi:** thu hẹp cut candidate tới
  đúng khung hình giả định CFR (giải mã khoảng rồi map theo
  số thứ tự khung hình); file VFR mà khoảng giải mã không cho
  cặp khung hình thì candidate giữ ở khung sample kèm ghi chú
  trong bản ghi. Sync bằng Python thuần có prefix sums nên
  file dài chạy chậm hơn đường Accelerate của bản gốc (ghi chú
  hiệu năng, không phải lệch kết quả).
- **Số liệu:** MCP vẫn **479** (không thêm công cụ mới),
  **366 thật / 113 honest**; **506 tests OK** trên Linux VM
  (486 + 20 test vòng bảy mới). `vibeedit.spec` nay liệt kê 18
  hidden import (`analysis` mới). Cây Swift không động, không
  hợp nhất, chưa đẩy.

## Full-parity vòng 6 — GPLv3 cho FFmpeg bundle, media_cuts thật, options plugin

- **Đóng gói giấy phép GPLv3 cho FFmpeg bundle (kết luận vòng 5 nay
  làm thật):** toàn văn GPLv3 lấy từ trang chính thức của GNU
  (`gnu.org/licenses/gpl-3.0.html`, đọc bằng trình duyệt) lưu tại
  `windows/THIRD_PARTY_LICENSES/GPLv3.txt` kèm ghi chú nguồn ở
  `THIRD_PARTY_LICENSES/README.md`. `scripts/package_licenses.py`
  (gọi qua `scripts/package_licenses.bat`, `build_windows.bat`
  cũng gọi ở cuối) copy file đó vào
  `dist\VibeEdit\THIRD_PARTY_LICENSES\` và sinh `SOURCE_OFFER.txt`
  từ chính binary trong build đó (dòng `-version` thật + bundle
  URL khi có) cùng `THIRD_PARTY_NOTICE.txt`. Workflow CI nay có
  bước packaging ngay sau bước bundle FFmpeg và bước kiểm tra làm
  fail run nếu thiếu 1 trong 3 file; `CHECK_WINDOWS.md` có
  checklist packaging trước khi phân phối. Chưa xong: lần chạy CI
  xanh đầu tiên (workflow vẫn phải do người dùng đẩy bằng git
  thật/web UI vì GitHub App 403) và rà soát pháp lý thật trước
  khi phân phối công khai.
- **`media_cuts` thật:** đọc đúng ngữ nghĩa gốc
  (`CommandCatalog+Media.swift`) — đây là sửa danh sách cắt của
  media đã phân tích, không phải phát hiện cắt thuần túy. Bản này
  đo bằng FFmpeg scene filter (ngưỡng mặc định 0.4, thang khác
  với minScore gốc nên không tuyên bố bằng nhau), lưu bản ghi
  trên media entry; add/remove/clear/remeasure đúng ngữ nghĩa
  gốc (xóa khớp trong một khoảng mẫu = một khung hình; đo lại
  thì bỏ các sửa trước đó); `media_analysis` nay kèm theo danh
  sách cắt đã sửa. Kiểm chứng trên clip tổng hợp đỏ 1s → xanh
  1s: đúng 1 cắt ở ~1.0s; file chỉ có audio báo lỗi rõ thay vì
  "không có cắt".
- **Options plugin thật:** `plugins_options`/`plugins_option`
  theo đúng ngữ nghĩa gốc — schema + scope + giá trị hiện tại;
  ghi một option kèm kiểm tra theo schema, bỏ value thì reset
  về default; user-scope lưu `plugins.json` (runtime state,
  không push), project-scope lưu trong project data.
  `plugins_set` nay là công tắc bật/tắt; per-hook switch vẫn báo
  lỗi rõ vì bản này không có công tắc theo hook. `plugins_setup`
  giữ honest: plugin Windows là module `.py` thuần, không có
  dependency recipe để chạy lại.
- **Còn honest vì lý do rõ, không code nửa vời:**
  `media_strip` (cần filmstrip PNG + level record + speech-map +
  transcript — tức toàn bộ pipeline đo `media.analyze` chưa có),
  `media_sync` (cần provider tương quan âm thanh giữa hai bản
  ghi — không có provider nào), `media_speech_map` (cần level
  window 0.1s + tách Otsu của `media.analyze` chưa có). Cả ba
  giữ nguyên báo lỗi trung thực kèm lý do trong `PARITY.md`.
- **Số liệu:** MCP vẫn **479** (không thêm công cụ mới),
  **363 thật / 116 honest**; **486 tests OK** trên Linux VM
  (454 + 32 test vòng sáu mới). `vibeedit.spec` nay liệt kê 17
  hidden import (`cuts` mới). Cây Swift không động, không hợp
  nhất, chưa đẩy.

## Full-parity vòng 5 — rà soát 132 công cụ honest, nút chết giao diện, desktop, bộ cài

- **Rà soát toàn bộ 132 công cụ kiểm tra-và-báo-lỗi:** quét thực nghiệm
  cho thấy chỉ `vision_cutout` là sai mô tả (handler đã thật từ trước,
  chỉ sửa mô tả); 12 công cụ chuyển thành thật, honest còn **120**,
  thật lên **359**, tổng giữ **479**: `app_update_later`/`skip` (ghi
  lựa chọn hoãn/bỏ qua version vào `updater.json`, hoạt động cả khi
  chưa cấu hình kênh; `later` lưu `remind_after` = nay + số ngày, mặc
  định 7; ghi file kiểu temp+replace, không ghi đè `releases_url`),
  `library_search`, `plugins_search`/`run`/`invoke` (chạy đúng hook đã
  khai báo của plugin đang bật qua `apply_plugin`, plugin tắt bị từ
  chối), `media_ocr`/`media_subjects` (alias của `vision_text`/
  `vision_faces` đã thật), `media_analysis`/`analyze` (metadata +
  ffprobe trực tiếp), `media_proxy` (transcode proxy H.264, file dẫn
  xuất, không đăng ký thành media timeline). 120 còn lại chia 3 nhóm
  ghi rõ trong `PARITY.md` mục 8: kiểm tra theo thiết kế (headless),
  cần provider/model không tồn tại, cần state/workflow chưa có.
- **Quét nút chết giao diện:** toàn bộ ~130 nút trong `index.html` +
  `app.js` đối chiếu với route thật trong `server.py` — không phát
  hiện endpoint giả nào. Sửa 4 điểm: nút Plugins trên topbar nay cuộn
  tới panel Plugins thật ở cột Details (thông điệp cũ "chưa có panel"
  là sai); tab Source của player nay giữ preview và hiện file nguồn
  đã chọn (trước đây ẩn cả khung preview nên ghi chú không bao giờ
  hiện); panel Captions nay có nút mở trong panel Text (trước đây
  không có nút nào mở được nó); nút Write VO đổi nhãn trung thực
  "Write VO — chưa có (cần AI viết kịch bản)" thay vì bấm chỉ để báo
  không có. Test quét khẳng định 0 nút bấm-không-làm-gì (trừ nút đã
  ghi rõ là chưa có kèm lý do).
- **Desktop:** chạy lần 2 trên cùng cổng tự mở trình duyệt tới
  instance đang chạy và thoát (probe HTTP bằng stdlib, không lock
  file); thiếu pywebview hoặc WebView2 lỗi thì rơi về trình duyệt kèm
  thông điệp tiếng Việt không dấu thay vì traceback; cổng ngoài
  1–65535 bị từ chối trước khi bind; launcher desktop ưu tiên
  `.venv\Scripts\python.exe` khi có.
- **Bộ cài:** `vibeedit.spec` nay đóng gói cả data `skills/` (trước
  đây thiếu — app đóng băng sẽ liệt kê 0 skill) và liệt kê rõ 16
  hidden import `vibeedit_core.*`; `build_windows.bat` sửa dòng echo
  chứa dấu ngoặc trong block ngoặc, thêm kiểm tra file exe sau build
  và xử lý lỗi pip/venv; `skills.py` nay có nhánh `_MEIPASS` như
  `plugins.py`. **Giấy phép bundle FFmpeg (kiểm chứng từ
  ffmpeg.org/legal.html + LICENSE + gyan.dev, không phải tư vấn pháp
  lý):** build CI tải là build tĩnh GPLv3 của gyan.dev, không phải
  LGPL — khi phân phối phải kèm text GPLv3 + nguồn tương ứng cho đúng
  build đó + ghi nhận; workflow hiện chưa kèm các file này nên phải
  bổ sung thành bước packaging trước khi phân phối công khai.
- **Đối chiếu lại + tài liệu:** test vòng ba chạy lại vẫn đủ 249 tên
  gốc; `PARITY.md` cập nhật trạng thái vòng năm (kể cả bảng phân loại
  120 honest và kết luận giấy phép FFmpeg đầy đủ); chưa hợp nhất,
  không động cây Swift.
- **Vẫn còn thật (không bịa):** clone giọng (cần model provider
  clone), thực thi model segmentation học sâu cho cutout (cần model
  ONNX + runtime do người dùng cung cấp), fetch cập nhật plugin từ
  registry (không có registry nào tồn tại), bộ cài/.exe + CI Windows
  (workflow vẫn phải do người dùng đẩy bằng git thật/web UI vì
  GitHub App bị chặn 403; .exe chưa build, CI chưa chạy; file
  licence/source offer cho FFmpeg bundle nay đã có bước packaging
  (script + workflow, vòng 6) nhưng vẫn cần lần chạy CI xanh đầu
  tiên để chứng minh),
  tự thay app đang chạy (chỉ có handoff + hoãn/bỏ qua), và mọi kiểm
  chứng trên Windows thật.

## Full-parity vòng 4 — ghi âm voiceover, Compare wipe, plugin manifest, halftone, updater handoff

- **Ghi âm voiceover trong app:** panel Voice ghi âm bằng
  MediaRecorder/getUserMedia của trình duyệt (quyền micro do trình
  duyệt hỏi; bị từ chối thì báo rõ, không tạo file giả); bản ghi
  tải lên endpoint thật `POST /api/voiceover/record` (chỉ nhận
  audio, tên duy nhất không ghi đè, đăng ký thành media audio thật
  rồi đặt lên track Voiceover bằng form sẵn có). Micro thật chưa
  kiểm chứng được trên máy ảo Linux (không có micro) — cần thử
  trên Windows thật.
- **Compare wipe có mặt nạ:** thay dạng chia đôi 2 player bằng một
  khung hình duy nhất — Before ở trái vạch chia, After ở phải vạch
  chia, kéo vạch hoặc thanh trượt để so sánh; hai video đồng bộ
  thời gian qua play/pause/seek/timeupdate (lệch >0,3s thì đồng bộ
  lại), ghi rõ là đồng bộ thời gian chứ không khóa khung hình tuyệt
  đối ở mức mẫu.
- **Thực thi code plugin dạng manifest:** manifest khai báo
  `"entry"` thì `load_plugins` nạp `register()` của entry và
  `apply_plugin` chạy đúng hook đã khai báo; plugin tắt vẫn bị từ
  chối, manifest hỏng hoặc entry thiếu file đều báo lỗi rõ. Mô hình
  tin cậy ghi rõ trong code: code plugin chạy cùng quyền với app
  (đúng mô hình plugin của bản gốc) nên chỉ chấp nhận được vì plugin
  cài xong ở trạng thái tắt, người dùng phải xem file rồi bật tường
  minh, và chỉ hook đã khai báo mới được chạy.
- **Transition halftone:** render thật hai đường — timeline bằng mask
  chấm động geq + `alphamerge`/`overlay` (chọn cứng, không pha; khung
  giữa transition chứa cả pixel đỏ thuần và xanh thuần, loại trừ
  dissolve/cut/pixelize giả mạo; `maskedmerge` đã thử và bị loại vì
  cho khung pha tím ngay cả trong RGB) và segment độc lập bằng Pillow
  + FFmpeg (`render_halftone_segment`). `add_transition` nay chấp
  nhận halftone.
- **Updater handoff:** `prepare_update` + công cụ MCP mới
  `app_update_prepare` — download + verify SHA-256 + ghi script
  `vibeedit-update-run.bat` (chờ PID của app thoát qua vòng lặp
  tasklist rồi mới chạy installer; script chỉ được ghi ra, không
  bao giờ tự chạy). App vẫn không tự thay chính nó; vị trí releases
  thật vẫn cần người dùng chọn.
- **Đối chiếu lại + tài liệu:** test vòng ba chạy lại vẫn đủ 249 tên
  gốc; `PARITY.md` cập nhật trạng thái vòng bốn; mục cài đặt dưới
  đây viết lại đầy đủ cho máy Windows sạch; `MERGE_PLAN.md` mới là
  kế hoạch hợp nhất có cổng kiểm soát để người dùng thực hiện bằng
  git thật sau khi kiểm thử xong (vòng này chỉ chuẩn bị, không hợp
  nhất).
- **Vẫn còn thật (không bịa):** clone giọng (cần model provider
  clone), thực thi model segmentation học sâu cho cutout (cần model
  ONNX + runtime do người dùng cung cấp), fetch cập nhật plugin từ
  registry (không có registry nào tồn tại), bộ cài/.exe + CI Windows
  (workflow vẫn phải do người dùng đẩy bằng git thật/web UI vì
  GitHub App bị chặn 403), và mọi kiểm chứng trên Windows thật.

## Full-parity batch — MCP, magnetic, plugin install, skills, vision, motion

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
Soát tiếp từ code gốc và cập nhật: timeline redo (MCP), export preset theo đúng ExportPreset của bản gốc (TikTok/Reels/Shorts 1080x1920 8 Mbps, Feed 4:5 5 Mbps, Square, Portrait 3:4, YouTube 1080p 12 Mbps, YouTube 4K 45 Mbps, Quick Draft 720p 4 Mbps, ProRes 422 HQ qua prores_ks .mov), đường cong tốc độ (montage/hero/bullet/jump-cut/flash-in/flash-out theo đúng điểm trong SpeedCurve.swift), đảo ngược clip (reverse/areverse), đóng băng khung hình, quy trình review chạy/chấp nhận/kiểm tra lại, màn hình chào mừng với project gần đây + Reveal (Windows) + Copy đường dẫn + xóa khỏi gần đây (không xóa file project), thư viện clip + brand kit, panel plugin có bật/tắt/quét lại, thêm loại transition của bản gốc mà FFmpeg xfade có thật (shutter, double-exposure, seamless/infinite/crash zoom, blur, flash/blink, roll). MCP lúc đó: 144 công cụ (đã tăng lên 479 ở các đợt full-parity sau). Chưa làm trong đợt này: vision/OCR/cutout (cần model ML), kho kiến thức/skill (21+8 công cụ), di chuyển magnetic cả khối + âm thanh gắn liền, và các loại transition chỉ có bằng motion của bản gốc (spin, swing/arc, diamond, kaleidoscope). Tất cả các mục này đã được bổ sung ở các đợt full-parity sau đó, trừ model segmentation học sâu cho cutout — xem `PARITY.md` để biết trạng thái thật hiện tại.

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
  command `python windows\vibeedit.py mcp <project-folder>` (479
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
  build (GPLv3); see CHECK_WINDOWS.md for the licence note.
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
names (see `PARITY.md` for the honest list; MCP is now 479
tools: 359 real-operation and 120 check-and-error). Still open: a visual UI check in a
real browser on Windows. See the Phase 8 list in
`VibeEdit/docs/windows-port.md` for what is left, all of which
needs the user's Windows or macOS machine.

## Cài đặt trên máy Windows sạch — những gì còn phải cài tay

> Nói thẳng: **chưa có bộ cài một lần bấm là xong**. Chưa có file
> `.exe` nào được build (workflow `build-windows.yml` vẫn phải do
> người dùng đẩy bằng git thật hoặc giao diện web GitHub vì GitHub
> App bị chặn 403, và chưa kiểm tra điều khoản phân phối của
> FFmpeg bundle). Danh sách dưới đây là toàn bộ những gì người
> dùng cuối phải tự cài trên một máy Windows 10/11 sạch để chạy
> được bản hiện tại. Mục nào ghi "tùy chọn" thì thiếu nó app vẫn
> chạy, chỉ tính năng đó báo lỗi rõ và không hoạt động.

### Bắt buộc

1. **Git cho Windows** — để clone repo lần đầu và để cập nhật
   bằng `git pull` (xem mục "Cập nhật" dưới đây).
2. **Python 3.10 trở lên** (đã kiểm chứng trên Windows với Python
   3.12.10). Khi cài đặt, tick chọn "Add python.exe to PATH".
   App lõi chỉ cần Python chuẩn — không cần gói pip nào để mở app,
   tạo project, edit timeline và export H.264.
3. **FFmpeg + FFprobe** — bắt buộc cho mọi render, thumbnail và
   dò media. Cài một trong ba cách, launcher sẽ tự tìm theo thứ tự
   này:
   - Đặt biến môi trường `VIBEEDIT_FFMPEG_DIR` trỏ tới thư mục
     chứa `ffmpeg.exe`/`ffprobe.exe`; hoặc
   - cho `ffmpeg` lên PATH (tải build từ gyan.dev, hoặc
     `winget install Gyan.FFmpeg`); hoặc
   - copy `ffmpeg.exe`/`ffprobe.exe` vào cạnh file app (cùng thư
     mục với `vibeedit.py`).
   - Nếu không tìm thấy FFmpeg, app báo rõ ba cách trên thay vì
     lỗi khó hiểu.

### Tùy chọn, theo tính năng muốn dùng

- **Cửa sổ desktop** (thay cho mở trình duyệt): `pip install
  pywebview` (cần WebView2 trên Windows — Windows 10/11 mới
  thường đã có sẵn). Không có pywebview, launcher desktop tự rơi
  về mở trình duyệt, app vẫn chạy bình thường.
- **Cutout vision và segment halftone độc lập:** `pip install
  pillow`. Core editor/export không cần Pillow; chỉ hai đường
  trên import Pillow khi chạy.
- **OCR (đọc chữ trong ảnh/video):** cài binary Tesseract cho
  Windows và cho `tesseract` lên PATH. Thiếu Tesseract, công cụ
  OCR báo rõ tên binary thiếu và cách cài, không trả chữ giả.
- **Detect mặt / cutout grabCut:** `pip install
  opencv-python-headless` (hoặc `opencv-python`). Thiếu OpenCV,
  các công cụ đó báo rõ và không hoạt động.
- **Phụ đề tự động (transcription):** `pip install faster-whisper`
  (mặc định dùng model `tiny`, chạy offline sau khi tải model;
  model lớn hơn tải theo nhu cầu). Thiếu faster-whisper, app báo
  rõ và không bịa phụ đề.
- **Tạo giọng nói Edge TTS:** `pip install edge-tts` (tổng hợp qua
  mạng; giọng `vi-VN-HoaiMyNeural`/`vi-VN-NamMinhNeural` và các
  giọng Edge khác).
- **Tạo giọng nói Piper (offline):** tải binary `piper` cho lên
  PATH và tự chuẩn bị file model `.onnx` rồi chỉ đường dẫn model
  cho app — repo **không bundle** model Piper nào và không bịa
  model mặc định.
- **Cutout học sâu (learned segmentation):** tự chuẩn bị file
  model ONNX + `pip install onnxruntime`, rồi chỉ đường dẫn model
  cho app (khe cắm `cutout_segmented` — xem `PARITY.md`). Thiếu
  model hoặc thiếu runtime đều báo rõ, không bao giờ trả kết quả
  grabCut giả làm "learned".
- **Không có, và không cài được từ repo:** model clone giọng (chưa
  có provider clone nào), vị trí releases thật cho updater (người
  dùng phải chọn thì updater mới có kênh), registry plugin (không
  tồn tại — plugin chỉ cài từ folder/.zip/URL do người dùng chỉ
  định).

### Chạy bằng double-click (không cần gõ lệnh)

Từ thư mục `windows/` (sau này là `VibeEdit/` sau khi hợp nhất):

- `run_vibeedit.bat` — mở giao diện web (mặc định
  `http://127.0.0.1:8000/`; nếu cổng bận, app báo và gợi ý cổng
  kế tiếp).
- `run_vibeedit_desktop.bat` — mở cửa sổ desktop (cần pywebview;
  thiếu thì rơi về trình duyệt kèm hướng dẫn cài).
- `update_and_run.bat` / `update_and_run.ps1` — cập nhật bằng
  `git pull --ff-only` rồi chạy app (pull lỗi thì vẫn chạy bản
  hiện có và báo rõ).
- Mở bằng VS Code: nhấn F5 với file `windows/.vscode/launch.json`
  có sẵn (chạy `serve --port 8000 --open-browser`).
- Lưu ý cửa sổ terminal giữ prompt khi server đang chạy là bình
  thường (server chạy thì terminal không trả prompt) — không phải
  app bị treo.

### Cập nhật

```bat
cd D:\VibeEdit
git pull --ff-only
```

hoặc double-click `update_and_run.bat`. **Không tải file ZIP đè
lên bản sao git** — ZIP đè lên sẽ làm mất lịch sử pull và gây
xung đột với các sửa đổi đang có. Sau mỗi lần nhóm phát triển đẩy
bản mới, pull trước rồi mới để VS Code AI sửa tiếp, để tránh hai
bên sửa cùng file gây conflict.

### Giới hạn còn lại trên máy Windows sạch (đọc trước khi dùng)

- Chưa có `.exe`/installer: phải cài Python + FFmpeg tay như trên.
  Lưu ý giấy phép: nếu sau này phân phối kèm binary FFmpeg từ build
  tĩnh của gyan.dev thì đó là GPLv3, phải kèm text GPLv3 + nguồn
  tương ứng cho đúng build đó + ghi nhận (xem `PARITY.md` mục 10) —
  không gọi artifact đó là "FFmpeg LGPL".
- Chưa từng chạy toàn bộ test suite bằng `py` trên Windows thật;
  chưa kiểm chứng cửa sổ desktop/pywebview, HiDPI, phím tắt Ctrl,
  micro ghi âm, giọng Edge/Piper thật, OCR/cutout thật và footage
  4K gốc trên Windows thật — tất cả mới chỉ kiểm chứng trên máy
  ảo Linux (xem `PARITY.md` để biết từng mục).
- Project và media của người dùng nằm trong `windows\projects\`
  (không thuộc repo, không bị git ghi đè); backup project nằm
  trong chính thư mục project (`project.json.bak` + `backups/`).

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

481 tools (432 real-operation tools and 49 check-and-error tools that raise a structured NOT_AVAILABLE error with the blocker and port path, never a fake success) — see `PARITY.md` for the current split. Round 3 verified by test that all 249 original CommandCatalog spec names have a registry name (dots/hyphens normalised, 6 via real aliases). Every real tool calls a real Project, export, store or backend operation; none is a stub. Round 23 added skill import (`vibeedit_skills_import_plan` / `vibeedit_skills_import`, from a .md file, a folder, a Claude-plugin folder or a .zip, copy-only) and folder-form skills (`<id>/SKILL.md` + `references/` + `kit/`) alongside the 21 flat skills; the Knowledge panel now lists skills as a clickable table with rendered markdown detail, a search box, a file-import preview/install flow, and a Claude Code sync button (see `PARITY.md` round 23). Round 24 audited all honest tools (3 empty-by-design conversions: `voice_clone_list`, `ui_dialog`, `chat_status`), made export probe real audio streams before emitting `[i:a]` (unprobed streamless records no longer kill the whole export), made export cancel SIGKILL the running FFmpeg process and remove partial output, and clarified required-argument errors to ValueError naming the missing keys (see `PARITY.md` round 24). Round 25 added a cross-process project file lock (O_CREAT|O_EXCL, stdlib-only, so the web app and an external MCP agent can no longer lose each other's simultaneous writes; long-running tools run outside the lock by design) and export-report diagnostics (exact FFmpeg command, filter graph, -shortest flag, audio map, per-clip source-vs-project fps, and ffprobe-measured output video/audio durations) plus a Review-panel diagnostics line (see `PARITY.md` round 25). Round 26 swept the remaining user-visible English strings to Vietnamese under a three-gate rule (no test locks it, no code matches on it, not intentionally English), covering HTML labels, JS status strings and server/plugin/project/render messages, with 10 messages reverted after the first full-suite run showed old tests asserting their English forms (see `PARITY.md` round 26).

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
