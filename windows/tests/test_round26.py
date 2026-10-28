"""Round 26: Vietnamese language-consistency sweep.

Pins every string translated in this round (Vietnamese present in the source)
and every string deliberately kept English (test-locked, code-matched, or
intentionally English under the round-14 language rules). No old test file
was modified in this round; all round-26 pins live here.
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CORE = os.path.join(ROOT, "vibeedit_core")
STATIC = os.path.join(ROOT, "static")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def core_sources():
    out = {}
    for name in sorted(os.listdir(CORE)):
        if name.endswith(".py") and name != "mcp.py":
            out[name] = read(os.path.join(CORE, name))
    return out


class TestRound26PyTranslations(unittest.TestCase):
    """A sample of the .py messages translated in round 26, per file."""

    # (file, Vietnamese string that must be present)
    TRANSLATED = [
        ("plugins.py", "Không tìm thấy nguồn plugin: "),
        ("plugins.py", "Tùy chọn không rõ "),
        ("plugins.py", " phải là một trong "),
        ("plugins.py", " (nhận được "),
        ("plugins.py", " (có sẵn: "),
        ("plugins.py", " không có hook "),
        ("plugins.py", " phải là object JSON"),
        ("plugins.py", " có 'entry' không an toàn "),
        ("plugins.py", " không phải JSON hợp lệ: "),
        ("plugins.py", "gói zip: tên entry không an toàn: "),
        ("plugins.py", "nguồn thư mục không có plugin.json ở gốc: "),
        ("plugins.py", "Nguồn plugin phải là thư mục chứa plugin.json hoặc gói .zip, không phải: "),
        ("plugins.py", "Id plugin "),
        ("plugins.py", " đã tồn tại; truyền overwrite=True để thay thế"),
        ("plugins.py", "File đã tải không phải gói .zip hợp lệ"),
        ("plugins.py", "hooks của manifest phải là danh sách chuỗi"),
        ("plugins.py", "register() phải trả về dict có 'name'"),
        ("knowledge.py", "Bài học không rõ: "),
        ("knowledge.py", "Proposal không rõ: "),
        ("knowledge.py", "Nội dung bài học không được để trống"),
        ("knowledge.py", "Khóa fact không được để trống"),
        ("knowledge.py", "Memo rỗng; không có gì để tách"),
        ("knowledge.py", "Kind của proposal phải là lesson, fact, pref hoặc claim"),
        ("knowledge.py", "Proposal bài học không có nội dung"),
        ("export_ops.py", "Không phải file JSON OpenTimelineIO Timeline.1"),
        ("export_ops.py", "Project không có mục karaoke nào"),
        ("export_ops.py", "Transition tham chiếu clip không rõ"),
        ("export_ops.py", "Các clip có transition không kề nhau"),
        ("export_ops.py", "Thư mục đích phải khác thư mục nguồn"),
        ("export_ops.py", "Thư mục đích đã tồn tại: "),
        ("export_ops.py", "Không có file project trong thư mục để merge: "),
        ("export_ops.py", "Thư mục đích đã có project: "),
        ("project.py", " liên kết tới video không rõ "),
        ("project.py", " liên kết tới audio không rõ "),
        ("project.py", " không render được: không có chuỗi filter FFmpeg nào tái tạo được nó; hướng xử lý: đoạn render trước"),
        ("render.py", "reframe cần phân số x/y/w/h dạng số, nhận được "),
        ("round15.py", "đã cập nhật mới nhất"),
        ("round15.py", ": lệch SHA-256 (archive không khớp registry)"),
        ("round15.py", "registry không liệt kê platform nào cho release này; bản ghi chỉ được cài để xem lại"),
        ("round15.py", "plugin provider registry: không có entry .py chạy được trên Windows"),
        ("round15.py", "đã cài ở trạng thái tắt dạng bản ghi registry chỉ để xem lại"),
        ("round15.py", "đã có file không phải kit trùng tên này; từ chối thay vì ghi đè nội dung của người dùng"),
        ("round8.py", "Take giọng đọc tổng hợp trong bản build này không lưu text nên không tính voice rate cho chúng thay vì bịa ra."),
        ("cuts.py", " giây)"),
        ("server.py", "Chưa có bản xuất nào"),
        ("server.py", "Chưa có xem trước cho transition này; "),
        ("server.py", "Không tìm thấy"),
        ("server.py", "Media không rõ"),
        ("server.py", "Không có thumbnail cho media này"),
        ("server.py", "Thiếu file media"),
        ("project.py", "Mục "),
        ("project.py", " chồng lấn "),
        ("project.py", " trên track "),
    ]

    def test_translated_strings_present(self):
        sources = core_sources()
        for fname, text in self.TRANSLATED:
            self.assertIn(text, sources[fname], f"{fname} missing {text!r}")

    # Distinctive old English messages that must be gone from .py sources
    # (excluding mcp.py, which is an API contract and out of scope).
    # Docstring prose (round15 "unsafe entry names", round9 "must be one of
    # the manifest's views") is not user-facing and is not in this list.
    ABSENT_OLD = [
        "Plugin source not found",
        "Unknown lesson",
        "Lesson text must not be empty",
        "Not an OpenTimelineIO",
        "Project has no karaoke items",
        "Transition clips are not consecutive",
        "No project file in folder for merge",
        "Unknown option",
        "must be a JSON object",
        "Plugin destination escapes",
        "No installed plugin folder",
        "without embedded credentials",
        "Download destination already exists",
        "needs a JSON array",
        "does not declare hook",
        "is not valid JSON",
        "folder source: unsafe path",
        "already up to date",
        "Synthesised voice takes",
        "non-kit file with this name",
        "review-only registry record",
        "no Windows-runnable .py entry",
        "links to unknown video",
        "links to unknown audio",
        "reframe needs numeric",
        "No export yet",
        "No preview yet",
        "No thumbnail for this media",
        "Media file missing",
    ]

    def test_old_english_messages_gone(self):
        sources = core_sources()
        for text in self.ABSENT_OLD:
            for fname, src in sources.items():
                self.assertNotIn(text, src, f"{fname} still has {text!r}")


class TestRound26KeptEnglish(unittest.TestCase):
    """Strings deliberately kept English, with the reason in the comment."""

    def test_beat_grid_kept(self):
        # JS matches on it exactly (app.js) AND test_round19 asserts it.
        self.assertIn("No beat grid detected yet", read(os.path.join(CORE, "project.py")))
        self.assertIn("No beat grid detected yet", read(os.path.join(STATIC, "app.js")))

    def test_unknown_transition_kind_kept(self):
        # test_motion_transitions asserts it in an exception string.
        self.assertIn("Unknown transition kind", read(os.path.join(CORE, "project.py")))

    def test_exceeds_messages_kept(self):
        # plugins.py re-raises when "exceeds" appears in the message.
        plugins = read(os.path.join(CORE, "plugins.py"))
        self.assertIn("exceeds", plugins)
        self.assertIn("Plugin bundle exceeds the ", plugins)

    def test_cancel_signals_kept(self):
        # Internal render-cancellation signals, matched by code.
        render = read(os.path.join(CORE, "render.py"))
        self.assertIn("export cancelled", render)

    def test_filelock_guard_kept(self):
        # Internal constructor guard, never shown in the UI.
        self.assertIn("ProjectFileLock needs a project path",
                      read(os.path.join(CORE, "filelock.py")))

    def test_reverted_messages_kept_english(self):
        # Each of these translations broke an existing test, so per the
        # round rule the translation was reverted, not the test.
        self.assertIn("is disabled; enable it first",
                      read(os.path.join(CORE, "plugins.py")))  # round5_tools:223, integration_parity:136
        self.assertIn("has a one-way link to",
                      read(os.path.join(CORE, "project.py")))  # magnetic_linked:196
        self.assertIn("is new/untrusted",
                      read(os.path.join(CORE, "plugins.py")))  # plugin_install:116
        self.assertIn("registry lists only non-Windows platforms for this release",
                      read(os.path.join(CORE, "round15.py")))  # round15:407
        self.assertIn("Could not acquire project lock",
                      read(os.path.join(CORE, "filelock.py")))  # round25:107
        self.assertIn("FFmpeg tool ",
                      read(os.path.join(CORE, "render.py")))  # windows_compat:140
        self.assertIn("not found. Install FFmpeg and add it to PATH",
                      read(os.path.join(CORE, "render.py")))  # windows_compat:140
        plugins = read(os.path.join(CORE, "plugins.py"))
        self.assertIn("Plugin declares code hooks (", plugins)  # plugin_install:117
        self.assertIn("Manifest has no description.", plugins)  # plugin_install:118
        self.assertIn("Manifest has no version.", plugins)  # plugin_install:119

    def test_dropzone_subtext_kept(self):
        # Locked by test_capcut_ui.py:90 and test_round18.py:115.
        html = read(os.path.join(STATIC, "index.html"))
        self.assertIn("Drag and drop videos, photos, and audio files here", html)

    def test_export_cta_kept_english(self):
        # The Export CTA stays English by the round-14 language decision.
        html = read(os.path.join(STATIC, "index.html"))
        self.assertIn("Export video", html)

    def test_timeline_tooltips_kept_english(self):
        # test_round18 pins the timeline icon data-tip/aria-label values.
        html = read(os.path.join(STATIC, "index.html"))
        for tip in ("Split", "Delete", "Magnetic", "Sections", "Snap",
                    "Waveforms", "Fit", "Undo", "Redo"):
            self.assertIn(tip, html)


class TestRound26OverlapRegex(unittest.TestCase):
    """The overlap flash regex is test-locked (test_round22 pins the exact
    English pattern), so the _check_overlap message stays English and the
    regex stays English-only. The validate() overlap error is a different
    message and stays Vietnamese (pinned in TRANSLATED)."""

    PATTERN = r"overlaps (\S+) on track"

    def test_english_regex_in_app_js(self):
        js = read(os.path.join(STATIC, "app.js"))
        self.assertIn(r"/overlaps (\S+) on track/", js)

    def test_regex_matches_english_form(self):
        self.assertEqual(
            re.search(self.PATTERN, "Item overlaps c2 on track t1").group(1), "c2")

    def test_overlap_message_kept_english(self):
        project = read(os.path.join(CORE, "project.py"))
        self.assertIn("Item overlaps ", project)


class TestRound26HtmlJsTranslations(unittest.TestCase):
    """HTML/JS strings translated in this round."""

    def test_html_translations_present(self):
        html = read(os.path.join(STATIC, "index.html"))
        for text in (
            "Tên project",
            "Màn hình chào mừng",
            "Nút hiện thư mục chỉ mở được thư mục trên Windows",
            "Hiện thư mục project (Windows)",
            "Sao chép đường dẫn project",
            "Xem trước transition",
            "Màu — từng thông số (eq)",
            'aria-label="Sửa"',
            'aria-label="Thêm"',
            'aria-label="Xem"',
            'aria-label="Lịch sử"',
            'aria-label="Thu phóng"',
        ):
            self.assertIn(text, html, f"index.html missing {text!r}")

    def test_js_translations_present(self):
        js = read(os.path.join(STATIC, "app.js"))
        for text in (
            "Nhập id skill trước.",
            "Nhập id skill / bài học trước.",
            "Tick ô xác nhận xóa trước",
            "Chọn một media trước.",
            "Nhập đường dẫn model ONNX do người dùng cung cấp trước",
            "Tick ô xác nhận trước — chỉ tải về, không cài đặt.",
            "Review thất bại: ",
            "Đã thêm take voiceover vào track Voiceover.",
            "Tạo take voiceover thất bại: ",
            "Upload thất bại: ",
            "Đã import audio mẫu thành media",
            "Sao chép thất bại: ",
            "Chọn file audio mẫu trước.",
            "Xem trước: vừa khung.",
            "Xem trước: mặc định.",
            "Đã ẩn hướng dẫn safe area.",
            "Đã hiện hướng dẫn safe area",
            "Giúp với clip đang chọn",
            "Giúp với project này",
        ):
            self.assertIn(text, js, f"app.js missing {text!r}")


if __name__ == "__main__":
    unittest.main()
