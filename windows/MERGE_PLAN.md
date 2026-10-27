# Kế hoạch hợp nhất (gated merge): đưa bản Windows vào `VibeEdit/`

> **CHỈ LÀ KẾ HOẠCH — CHƯA THỰC HIỆN.** Tài liệu này được viết ở
> vòng 4 để người dùng thực hiện bằng **git thật trên Windows**
> sau khi bản Windows đã được kiểm thử xong. Đợt vòng 4 **không**
> xóa, đổi tên hay di chuyển bất cứ thứ gì trong `VibeEdit/` hay
> `BashCut-main/`, và không tự dọn cây Swift cũ trên remote — vì
> snapshot push của công cụ phát triển **không xóa được file**,
> nên bước dọn dẹp bắt buộc phải làm bằng git thật.
>
> Trạng thái đích đã thống nhất (xem `PARITY.md` § "Cấu trúc đích"):
> chỉ còn hai app — `BashCut-main/` giữ nguyên làm bản macOS gốc,
> `VibeEdit/` là bản Windows hoàn chỉnh. Thư mục `windows/` hiện tại
> là bản port đang phát triển; sau khi hợp nhất xong và kiểm thử
> lại, nội dung của nó chuyển vào `VibeEdit/` và `windows/` không
> còn nữa.

## Cổng kiểm soát: khi nào mới được hợp nhất

**Tất cả** các điều kiện sau phải đúng trước khi bắt đầu. Nếu một
điều kiện chưa đúng, dừng lại, không hợp nhất:

1. Bản Windows trong `windows/` đã chạy được trên **Windows thật**:
   mở app (desktop hoặc web UI), tạo/mở project, import media,
   edit trên timeline, export thành công — không chỉ chạy trên
   máy ảo Linux của nhóm phát triển.
2. Không còn thay đổi chưa commit trong bản sao làm việc
   (`git status` sạch, ngoại trừ file runtime không đưa vào repo
   như `windows/projects/`, `windows/plugins.json`, cache render).
3. Người dùng (hoặc VS Code AI chạy song song) đã pull bản mới
   nhất từ remote và xác nhận không còn sửa đổi nào đang dở trong
   `windows/` hay `VibeEdit/` chưa được đẩy lên.
4. Đã có bản lưu an toàn trước khi hợp nhất (bước 2 dưới đây).

## Bước 0 — Chuẩn bị bản sao làm việc (PowerShell, từ `D:\VibeEdit`)

```powershell
cd D:\VibeEdit
git status
git pull --ff-only
```

- Nếu `git status` báo file đã sửa chưa commit: commit hoặc stash
  chúng trước, và ghi rõ chúng là gì. **Không hợp nhất khi còn
  thay đổi chưa commit mà bạn không hiểu rõ.**
- Nếu `git pull --ff-only` báo lỗi (local và remote đã rẽ nhánh):
  dừng lại, giải quyết rẽ nhánh trước (merge hoặc rebase có chủ
  đích), rồi mới tiếp tục.

## Bước 1 — Kiểm tra `BashCut-main/` còn nguyên

`BashCut-main/` là bản gốc macOS, **không bao giờ được sửa, đổi
tên hay xóa** trong quá trình này. Kiểm tra trước khi động vào
bất cứ thứ gì:

```powershell
git status -- BashCut-main
git log --oneline -3 -- BashCut-main
```

- `git status -- BashCut-main` phải sạch (không file nào bị sửa,
  thêm hay xóa trong cây này).
- Nếu có thay đổi trong `BashCut-main/`: dừng lại, khôi phục
  chúng (`git checkout -- BashCut-main` đối với file đã sửa, hoặc
  hỏi người giữ bản gốc) rồi mới tiếp tục. Không hợp nhất khi cây
  gốc đã bị động vào mà chưa rõ lý do.

## Bước 2 — Đối chiếu cây Swift trong `VibeEdit/` với `BashCut-main/`

Cây `VibeEdit/` hiện là cây Swift đã đổi tên từ BashCut. Trước khi
xóa nó, phải biết nó có thay đổi riêng nào so với `BashCut-main/`
hay không (ví dụ: ai đó đã sửa Swift trong `VibeEdit/` mà không
sửa `BashCut-main/`):

```powershell
# Liệt kê file chỉ có ở một bên, và file khác nhau giữa hai cây
# (so sánh theo tên file sau khi bỏ tiền tố thư mục).
robocopy BashCut-main VibeEdit /L /E /NJH /NJS /NP /NS /NC /NDL
```

Đọc kỹ kết quả:

- **Nếu `VibeEdit/` chỉ là bản đổi tên của `BashCut-main/`** (cùng
  file, chỉ khác tên/đường dẫn, không có logic riêng): ghi chú lại
  và tiếp tục — cây Swift cũ sẽ được giữ trong lịch sử git
  (bước 3) chứ không mất hẳn.
- **Nếu có file Swift trong `VibeEdit/` đã sửa logic so với
  `BashCut-main/`:** dừng lại. Ghi lại từng file khác nhau và
  quyết định: (a) port thay đổi đó sang bản Windows trước rồi mới
  hợp nhất, hoặc (b) lưu file đó sang một thư mục lưu trữ riêng
  ngoài repo trước khi xóa. **Không xóa cây Swift khi còn thay
  đổi riêng chưa được xử lý.**

## Bước 3 — Tạo tag và bản lưu trước khi hợp nhất

Tag là điểm khôi phục: nếu hợp nhất lỗi, quay về tag là xong.

```powershell
git tag -a pre-merge-swift -m "Truoc khi hop nhat: VibeEdit/ con la cay Swift, windows/ la ban Windows"
git push origin pre-merge-swift
```

Ngoài tag, tạo thêm một bản sao nguyên thư mục repo sang ổ khác
hoặc thư mục khác (đề phòng tag bị xóa nhầm):

```powershell
robocopy D:\VibeEdit D:\VibeEdit-backup-pre-merge /E /XD .git
```

Kiểm tra bản sao đã copy đủ (đặc biệt `BashCut-main/` và
`VibeEdit/`).

## Bước 4 — Chuyển nội dung `windows/` vào `VibeEdit/` bằng git

Nguyên tắc: chỉ di chuyển **file đã được git theo dõi** trong
`windows/`; file runtime **không** được chuyển và **không** được
commit: `windows/projects/` (project và media của người dùng),
`windows/plugins.json` (trạng thái runtime),
`windows/render/`, cache thumbnail, `__pycache__`,
`windows/static/logo.png` và `favicon.ico` (file nhị phân cũ đã
hỏng — logo hiện tại nằm dưới dạng data URI trong
`windows/static/index.html`).

```powershell
cd D:\VibeEdit
# 1. Xoa cay Swift cu khoi VibeEdit/ (lich su git van giu lai,
#    khoi phuc duoc bang tag pre-merge-swift).
git rm -r VibeEdit
# 2. Chuyen file da track trong windows/ sang VibeEdit/.
#    (git mv giu lich su file; neu git mv bao loi vi thu muc dich
#    khong con, tao lai thu muc rong truoc: mkdir VibeEdit)
mkdir VibeEdit
git mv windows/vibeedit.py VibeEdit/vibeedit.py
git mv windows/vibeedit_core VibeEdit/vibeedit_core
git mv windows/static VibeEdit/static
git mv windows/tests VibeEdit/tests
git mv windows/plugins VibeEdit/plugins
git mv windows/skills VibeEdit/skills
git mv windows/*.bat VibeEdit/
git mv windows/*.ps1 VibeEdit/
git mv windows/*.md VibeEdit/
git mv windows/.vscode VibeEdit/.vscode
# 3. Kiem tra: khong con file track nao sot trong windows/,
#    khong co file runtime nao bi dua vao VibeEdit/.
git status
```

- Nếu `git mv` báo một file không tồn tại (ví dụ tên file đã đổi
  từ đợt phát triển trước): dừng ở file đó, kiểm tra tên thật
  bằng `git ls-files windows/`, sửa lệnh cho đúng, rồi tiếp tục.
- Sau `git status`, xác nhận: thư mục `windows/` chỉ còn file
  untracked/runtime (projects, plugins.json, cache) — không còn
  file tracked nào; thư mục `VibeEdit/` chứa toàn bộ code Windows.
- Xóa thư mục `windows/` rỗng còn lại bằng tay sau khi đã chắc
  chắn không còn gì cần giữ (file runtime trong đó, nếu cần, copy
  sang vị trí mới trước khi xóa — xem bước 5).

## Bước 5 — Sửa các đường dẫn tham chiếu `windows/`

Sau khi chuyển thư mục, các chỗ sau vẫn còn nhắc tới `windows/`
và phải sửa cho đúng cấu trúc mới (tìm bằng `Select-String` toàn
repo, sửa từng chỗ, không sửa bằng thay thế mù):

```powershell
Select-String -Path VibeEdit\README.md, README.md, VibeEdit\*.bat, VibeEdit\*.ps1 -Pattern "windows\\" -SimpleMatch
```

Những chỗ chắc chắn phải sửa:

- `README.md` ở root repo: mô tả cấu trúc (windows/ là bản port
  đang phát triển → VibeEdit/ là bản Windows; BashCut-main/ giữ
  nguyên).
- `VibeEdit/README.md` (trước đây là `windows/README.md`): đường
  dẫn chạy app (`python VibeEdit\vibeedit.py serve`), thư mục
  project mặc định (`VibeEdit\projects\` thay cho
  `windows\projects\`), lệnh test (`cd VibeEdit; py -m unittest
  discover -s tests -v`).
- Các launcher `.bat`/`.ps1` trong `VibeEdit/`: chúng chạy file
  trong cùng thư mục nên thường vẫn đúng, nhưng kiểm tra lại từng
  file xem có đường dẫn `windows\...` ghi cứng không.
- `VibeEdit/.vscode/launch.json` và `tasks.json`: đường dẫn
  script và thư mục làm việc.
- `VibeEdit/vibeedit.py` và `vibeedit_core/*`: đường dẫn mặc định
  tới thư mục project, thư mục plugins, thư mục skills (tìm chuỗi
  `"windows"` trong code và sửa theo cấu trúc mới).
- Project và media của người dùng: project đang nằm trong
  `windows\projects\` **không** tự chuyển theo code. Copy thư mục
  project sang `VibeEdit\projects\` (copy, không cut, cho tới khi
  kiểm thử xong ở bước 6), rồi mở lại project từ vị trí mới để
  xác nhận media vẫn đúng.

## Bước 6 — Kiểm thử lại app Windows sau hợp nhất

Chạy toàn bộ từ cấu trúc mới, theo thứ tự này. **Tất cả phải
pass thì hợp nhất mới được coi là xong:**

1. Khởi động: double-click launcher trong `VibeEdit/` (hoặc
   `py VibeEdit\vibeedit.py serve --port 8000`) — app mở được,
   không báo thiếu file/thư mục.
2. Mở project: mở project đã copy sang `VibeEdit\projects\` —
   timeline, media và clip hiển thị đúng như trước khi hợp nhất.
3. Import: import một file media mới (tên trùng với file đã có
   càng tốt, để kiểm tra quy tắc không ghi đè) — file mới lưu
   thành `tên-2.ext`, clip cũ không đổi nội dung.
4. Edit: thêm/di chuyển/tách clip, undo/redo, đổi tỉ lệ khung
   hình — không lỗi.
5. Export: export một bản nháp và một bản full — file xuất ra
   phát được, đúng độ dài và tỉ lệ.
6. Test suite: `cd VibeEdit; py -m unittest discover -s tests -v`
   — toàn bộ test pass (so với con số trước khi hợp nhất; nếu
   giảm, tìm test fail do đường dẫn cũ và sửa).
7. MCP: `py VibeEdit\vibeedit.py mcp <project-folder>` — số công
   cụ bằng với số trước khi hợp nhất (đọc từ `/api/mcp-tools`).

## Bước 7 — Commit và đẩy

Chỉ commit khi bước 6 đã pass hết:

```powershell
git add -A
git status
git commit -m "Hop nhat: chuyen ban Windows tu windows/ sang VibeEdit/ (giam sat boi MERGE_PLAN.md)"
git push
```

Sau khi push thành công và kiểm tra trên GitHub rằng cấu trúc
mới đã đúng (VibeEdit/ chứa code Windows, BashCut-main/ nguyên
vẹn, không còn thư mục windows/ với file tracked), mới được xóa
bản sao lưu ở bước 3. Giữ tag `pre-merge-swift` trên remote làm
điểm khôi phục lâu dài.

## Tiêu chí dừng và khôi phục

**Dừng ngay (không commit, không push) khi gặp một trong các
trường hợp sau:**

- `BashCut-main/` có thay đổi chưa rõ lý do (bước 1).
- `VibeEdit/` (Swift) có thay đổi logic riêng so với
  `BashCut-main/` chưa được xử lý (bước 2).
- `git mv` thiếu file, hoặc `git status` sau bước 4 cho thấy file
  runtime (projects, plugins.json, cache) sắp bị commit.
- Bất kỳ kiểm thử nào ở bước 6 fail mà chưa rõ nguyên nhân.

**Khôi phục khi hợp nhất đã commit nhưng phát hiện lỗi:**

```powershell
# Chua push: quay ve trang thai truoc khi hop nhat.
git reset --hard pre-merge-swift
# Da push: revert commit hop nhat (khong rewrite lich su remote).
git revert <commit-hop-nhat>
git push
```

Trong cả hai trường hợp, kiểm tra lại rằng `BashCut-main/` vẫn
nguyên vẹn và app Windows chạy lại được từ cấu trúc cũ
(`windows/`) trước khi thử hợp nhất lại.

## Những gì kế hoạch này KHÔNG làm

- Không tự động hợp nhất bằng snapshot push (không xóa được file
  trên remote).
- Không xóa `BashCut-main/` trong bất kỳ trường hợp nào.
- Không chuyển project/media của người dùng bằng git (project và
  media không thuộc repo; chúng được copy bằng tay ở bước 5).
- Không thay đổi hành vi app: hợp nhất chỉ đổi vị trí file và
  đường dẫn, không thêm/bớt tính năng.
