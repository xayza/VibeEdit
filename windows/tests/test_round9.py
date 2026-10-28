"""Round 9: clip_backdrop renders, run-panel actions, plugins.show-view.

Run from windows/: python3 -m unittest discover -s tests -v
(or: py -m unittest discover -s tests -v on Windows).

Backdrop pixels mirror the original ClipBackdropTests: a 200x100
still, left half red and right half blue, fitted into a 320x180
canvas (fit scale 1.6 -> 320x160, bars top/bottom). Without a
backdrop the bars are black; a colour fills them; blur fills them
with the picture itself, filled and blurred; dim darkens it. A
plain fill-scale render could never show green bars, and a black
pad would hide the backdrop, so these pixels cannot pass for a
substitution.

Run-panel actions mirror UIAction.swift /
ProjectDocument+UIActions.swift: dismiss closes until shown again,
toggle opens-or-closes, follow toggles the follow flag, and the
follow-ups return the exact AgentFollowUp request texts (the
headless caller is the agent; delivery is never claimed).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image  # noqa: E402

from vibeedit_core.mcp import MCPServer, TOOLS  # noqa: E402
from vibeedit_core.project import (  # noqa: E402
    Project, new_project, save_project, validate_backdrop)
from vibeedit_core.render import probe_media, render  # noqa: E402
from vibeedit_core.round8 import (  # noqa: E402
    append_run_entry, run_checklist)
from vibeedit_core.round9 import (  # noqa: E402
    run_another_recipe, run_fix_issues, run_panel_dismiss,
    run_panel_follow, run_panel_toggle, show_plugin_view)


def _make_project(tmp, width=320, height=180):
    data = new_project("round9", width=width, height=height)
    proj = Project(data, tmp)
    save_project(data, os.path.join(tmp, "project.vibeedit.json"))
    return proj


def _half_image(path):
    img = Image.new("RGB", (200, 100))
    for x in range(200):
        for y in range(100):
            img.putpixel((x, y), (255, 0, 0) if x < 100 else (0, 0, 255))
    img.save(path)


def _grab_frame(video, when, out):
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", str(when),
         "-i", video, "-frames:v", "1", out],
        capture_output=True, check=True)
    return Image.open(out).convert("RGB")


def _still_project(tmp, backdrop=None, kind="image"):
    """A 2s main clip of the half red/blue still, backdrop optional."""
    _half_image(os.path.join(tmp, "photo.png"))
    proj = _make_project(tmp)
    medium = proj.add_media("photo.png", kind="image", width=200,
                            height=100, fps=30, frames=100000)
    clip = proj.add_clip(medium["id"], "v1", 0, 0, 60)
    if backdrop is not None:
        proj.set_backdrop(clip["id"], backdrop)
    return proj, clip


def _render(proj, tmp, name="out.mp4"):
    out = os.path.join(tmp, name)
    report = render(proj.data, tmp, out)
    assert os.path.isfile(out), report
    return out


class BackdropValidationTest(unittest.TestCase):
    def test_defaults_and_normalisation(self):
        bd = validate_backdrop({"kind": "blur"})
        self.assertEqual(bd, {"kind": "blur", "color": "#000000",
                              "blur": 0.05, "dim": 0})
        self.assertEqual(validate_backdrop(
            {"kind": "color", "color": "#00ff00"})["color"], "#00FF00")

    def test_rejections_match_original_validation(self):
        for bad in ({"kind": "glow"}, {"kind": "blur", "blur": 2},
                    {"kind": "blur", "blur": -0.1},
                    {"kind": "blur", "dim": 1.5},
                    {"kind": "color", "color": "green"},
                    {"kind": "color", "color": "#12345"},
                    "blur", None, {}):
            with self.assertRaises(ValueError, msg=repr(bad)):
                validate_backdrop(bad)

    def test_set_and_remove_and_track_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj, clip = _still_project(tmp)
            item = proj.set_backdrop(
                clip["id"], {"kind": "color", "color": "#00FF00"})
            self.assertEqual(item["backdrop"]["color"], "#00FF00")
            # A second main clip keeps its own backdrop; removal
            # clears only the named item.
            medium = proj.data["media"][0]
            clip2 = proj.add_clip(medium["id"], "v1", 60, 0, 60)
            proj.set_backdrop(clip2["id"], {"kind": "blur"})
            proj.set_backdrop(clip["id"], None)
            self.assertNotIn("backdrop", proj.item(clip["id"])[1])
            self.assertIn("backdrop", proj.item(clip2["id"])[1])
            with self.assertRaises(KeyError):
                proj.set_backdrop("nope", {"kind": "blur"})
            # Overlay video track: stored backdrop would never
            # render, so it is refused, not silently kept.
            over = proj.add_clip(medium["id"], "v2", 0, 0, 60)
            with self.assertRaises(ValueError):
                proj.set_backdrop(over["id"], {"kind": "blur"})
            # Text item (no media): refused.
            proj.data["tracks"][2]["items"].append(
                {"id": "txt1", "text": "hi", "at": 0, "dur": 30})
            with self.assertRaises(ValueError):
                proj.set_backdrop("txt1", {"kind": "blur"})

    def test_mcp_multi_item_and_atomic_reject(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj, clip = _still_project(tmp)
            medium = proj.data["media"][0]
            clip2 = proj.add_clip(medium["id"], "v1", 60, 0, 60)
            save_project(proj.data,
                         os.path.join(tmp, "project.vibeedit.json"))
            server = MCPServer(tmp)
            result = server.call("vibeedit_clip_backdrop", {
                "items": f"{clip['id']},{clip2['id']}",
                "kind": "color", "color": "#00FF00"})
            self.assertEqual(result["items"], [clip["id"], clip2["id"]])
            self.assertEqual(result["backdrop"]["color"], "#00FF00")
            self.assertEqual(
                server.project.item(clip["id"])[1]["backdrop"]["color"],
                "#00FF00")
            # One bad id rejects the whole call: the good item
            # must not keep a backdrop from a half-applied edit.
            server.project.item(clip["id"])[1].pop("backdrop", None)
            with self.assertRaises(Exception):
                server.call("vibeedit_clip_backdrop", {
                    "items": f"{clip['id']},nope", "kind": "blur"})
            self.assertNotIn(
                "backdrop", server.project.item(clip["id"])[1])

    def test_mcp_selection_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj, clip = _still_project(tmp)
            save_project(proj.data,
                         os.path.join(tmp, "project.vibeedit.json"))
            server = MCPServer(tmp)
            server.call("vibeedit_timeline_select_all", {})
            result = server.call("vibeedit_clip_backdrop",
                                 {"kind": "color", "color": "#FF0000"})
            self.assertIn(clip["id"], result["items"])


class BackdropRenderTest(unittest.TestCase):
    def test_fill_covers_canvas_without_backdrop(self):
        # No backdrop means the plain chain's fill scale: there are
        # no bars at all, the picture covers the whole canvas
        # (top corners are picture, not black). The colour/blur
        # tests below prove the backdrop replaces that fill with a
        # fitted picture plus filled bars.
        with tempfile.TemporaryDirectory() as tmp:
            proj, _ = _still_project(tmp)
            frame = _grab_frame(_render(proj, tmp), 1.0,
                                os.path.join(tmp, "plain.png"))
            self.assertGreater(frame.getpixel((5, 5))[0], 200)
            self.assertGreater(frame.getpixel((315, 5))[2], 200)
            self.assertGreater(frame.getpixel((80, 90))[0], 200)
            self.assertGreater(frame.getpixel((240, 90))[2], 200)

    def test_colour_fills_bars_picture_on_top(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj, _ = _still_project(
                tmp, {"kind": "color", "color": "#00FF00"})
            frame = _grab_frame(_render(proj, tmp), 1.0,
                                os.path.join(tmp, "green.png"))
            bar = frame.getpixel((160, 5))
            self.assertGreater(bar[1], 200)
            self.assertLess(bar[0], 40)
            self.assertLess(bar[2], 40)
            self.assertGreater(frame.getpixel((80, 90))[0], 200)
            self.assertGreater(frame.getpixel((240, 90))[2], 200)

    def test_blur_fills_bars_with_picture_and_dim_darkens(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj, _ = _still_project(tmp, {"kind": "blur",
                                           "blur": 0.02})
            frame = _grab_frame(_render(proj, tmp), 1.0,
                                os.path.join(tmp, "blur.png"))
            left = frame.getpixel((10, 5))
            right = frame.getpixel((310, 5))
            self.assertGreater(left[0], 180)
            self.assertLess(left[2], 60)
            self.assertGreater(right[2], 180)
            self.assertLess(right[0], 60)
            proj2, _ = _still_project(
                tmp, {"kind": "blur", "blur": 0.02, "dim": 0.5})
            # Second render needs its own output name in the same tmp.
            dimmed = _grab_frame(_render(proj2, tmp, "dim.mp4"), 1.0,
                                 os.path.join(tmp, "dim.png"))
            half = dimmed.getpixel((10, 5))
            self.assertGreater(half[0], 120)
            self.assertLess(half[0], left[0] - 30)
            self.assertGreater(dimmed.getpixel((80, 90))[0], 200)

    def test_video_clip_and_freeze_backdrop(self):
        # 25 fps on purpose: at 30 fps the freeze path's old
        # 3-decimal trim (29/30 -> "0.967") used to drop the held
        # frame — the round 9 defect, fixed in round 10 by the
        # exact frame-index trim (see test_round10.py, which
        # covers 30 fps freeze with and without a backdrop).
        # At 25 fps the last frame (24/25 = 0.960) lands exactly
        # on the trim boundary, so this test genuinely exercises
        # the freeze backdrop branch.
        with tempfile.TemporaryDirectory() as tmp:
            _half_image(os.path.join(tmp, "photo.png"))
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-loop", "1",
                 "-i", os.path.join(tmp, "photo.png"),
                 "-t", "2", "-r", "25", "-pix_fmt", "yuv420p",
                 os.path.join(tmp, "clip.mp4")],
                capture_output=True, check=True)
            data = new_project("round9", width=320, height=180,
                               fps=(25, 1))
            proj = Project(data, tmp)
            info = probe_media(os.path.join(tmp, "clip.mp4"))
            medium = proj.add_media("clip.mp4", kind="video", **info)
            clip = proj.add_clip(medium["id"], "v1", 0, 0, 25)
            proj.set_backdrop(clip["id"],
                              {"kind": "color", "color": "#00FF00"})
            frozen = proj.freeze_clip(clip["id"], 25)
            # freeze_clip deep-copies the item, so the held frame
            # keeps the backdrop; the frame at 1.5s is the freeze.
            self.assertEqual(frozen["backdrop"]["color"], "#00FF00")
            frame = _grab_frame(_render(proj, tmp), 1.5,
                                os.path.join(tmp, "fz.png"))
            bar = frame.getpixel((160, 5))
            self.assertGreater(bar[1], 200)
            self.assertLess(bar[0], 40)


class RunPanelTest(unittest.TestCase):
    def _logged(self, tmp):
        proj = _make_project(tmp)
        append_run_entry(proj, "stage", {
            "stage": "rough-cut", "status": "started"})
        return proj

    def test_dismiss_toggle_follow_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            self.assertFalse(run_checklist(proj)["panel"]["visible"])
            proj = self._logged(tmp)
            self.assertTrue(run_checklist(proj)["panel"]["visible"])
            snap = run_panel_dismiss(proj)
            self.assertTrue(snap["dismissed"])
            self.assertFalse(snap["visible"])
            self.assertFalse(run_checklist(proj)["panel"]["visible"])
            snap = run_panel_toggle(proj)
            self.assertEqual(snap["action"], "shown")
            self.assertTrue(snap["visible"])
            snap = run_panel_toggle(proj)
            self.assertEqual(snap["action"], "dismissed")
            self.assertFalse(snap["visible"])
            snap = run_panel_follow(proj)
            self.assertTrue(snap["follow"])
            snap = run_panel_follow(proj, False)
            self.assertFalse(snap["follow"])
            self.assertTrue(run_checklist(proj)["panel"]["follow"] is False)

    def test_mcp_panel_tools_save_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = self._logged(tmp)
            save_project(proj.data,
                         os.path.join(tmp, "project.vibeedit.json"))
            server = MCPServer(tmp)
            out = server.call("vibeedit_run_dismiss", {})
            self.assertTrue(out["dismissed"])
            self.assertFalse(
                server.call("vibeedit_run_checklist", {})["panel"]["visible"])
            out = server.call("vibeedit_run_toggle", {})
            self.assertEqual(out["action"], "shown")
            out = server.call("vibeedit_run_follow", {})
            self.assertTrue(out["follow"])

    def test_fix_issues_gates_and_exact_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            with self.assertRaises(ValueError):
                run_fix_issues(proj)
            proj.run_review()
            with self.assertRaises(ValueError):
                run_fix_issues(proj)
            # One real validation error: a dangling media reference.
            proj.data["tracks"][0]["items"].append(
                {"id": "bad1", "media": "missing", "at": 0, "dur": 30})
            proj.run_review()
            out = run_fix_issues(proj, output="out.mp4")
            self.assertEqual(out["errors"], 1)
            self.assertEqual(out["warnings"], 0)
            self.assertFalse(out["delivered"])
            self.assertTrue(out["request"].startswith(
                "The export is done (out.mp4). "))
            self.assertIn(
                "The review still shows 1 errors and 0 warnings",
                out["request"])
            self.assertIn("review run --summary", out["request"])
            self.assertIn("export again with the same settings",
                          out["request"])

    def test_another_recipe_text_with_and_without_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            with self.assertRaises(ValueError):
                run_another_recipe(proj)
            proj.run_review()
            out = run_another_recipe(proj)
            self.assertIsNone(out["current_recipe"])
            self.assertIn("with a recipe: pick the one that best fits",
                          out["request"])
            self.assertIn("Keep this version as it is", out["request"])
            proj.data["plan"] = {"recipe": {"skill": "bc:montage"}}
            out = run_another_recipe(proj)
            self.assertEqual(out["current_recipe"], "bc:montage")
            self.assertIn("different recipe than bc:montage",
                          out["request"])


def _demo_plugin_dir(tmp):
    pdir = os.path.join(tmp, "plugins")
    folder = os.path.join(pdir, "demo")
    os.makedirs(folder)
    manifest = {"id": "demo", "name": "Demo",
                "views": [
                    {"id": "main", "title": "Main",
                     "placement": "panel", "components": []},
                    {"id": "side", "title": "Side",
                     "placement": "inspector", "components": []}]}
    with open(os.path.join(folder, "plugin.json"), "w",
              encoding="utf-8") as fh:
        json.dump(manifest, fh)
    return pdir


class ShowViewTest(unittest.TestCase):
    def test_show_panel_view_records_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            pdir = _demo_plugin_dir(tmp)
            out = show_plugin_view(proj, "demo", "main", pdir)
            self.assertEqual(out, {"plugin": "demo", "view": "main",
                                   "location": "panel", "shown": True,
                                   "rev": proj.rev})
            self.assertEqual(
                proj.data["plugin_views_shown"]["demo/main"]["location"],
                "panel")

    def test_inspector_view_opens_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            pdir = _demo_plugin_dir(tmp)
            out = show_plugin_view(proj, "demo", "side", pdir)
            self.assertFalse(out["shown"])
            self.assertEqual(out["location"], "inspector")
            self.assertNotIn("plugin_views_shown", proj.data)

    def test_show_view_rejections(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            pdir = _demo_plugin_dir(tmp)
            with self.assertRaises(KeyError):
                show_plugin_view(proj, "nope", "main", pdir)
            with self.assertRaises(KeyError):
                show_plugin_view(proj, "demo", "nope", pdir)
            # The state file lives NEXT TO the plugins folder
            # (plugins._state_path), not inside it.
            with open(os.path.join(tmp, "plugins.json"), "w",
                      encoding="utf-8") as fh:
                json.dump({"disabled": ["demo"]}, fh)
            with self.assertRaises(ValueError):
                show_plugin_view(proj, "demo", "main", pdir)

    def test_mcp_show_view_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            pdir = _demo_plugin_dir(tmp)
            save_project(proj.data,
                         os.path.join(tmp, "project.vibeedit.json"))
            server = MCPServer(tmp)
            out = server.call("vibeedit_plugins_show_view", {
                "plugin": "demo", "view": "main",
                "plugins_dir": pdir})
            self.assertTrue(out["shown"])
            self.assertIn("demo/main",
                          server.project.data["plugin_views_shown"])


class RegistryCountTest(unittest.TestCase):
    def test_round9_counts(self):
        honest = [t for t in TOOLS
                  if (t.get("description") or "").startswith(
                      "Not available")]
        self.assertEqual(len(TOOLS), 481)
        self.assertEqual(len(honest), 49)  # Round 22: 54 -> 52; Round 24: 52 -> 49 (voice_clone_list/ui_dialog/chat_status empty-by-design)
        self.assertEqual(len(TOOLS) - len(honest), 432)
        for name in ("vibeedit_clip_backdrop", "vibeedit_run_dismiss",
                     "vibeedit_run_toggle", "vibeedit_run_follow",
                     "vibeedit_run_fix_issues",
                     "vibeedit_run_another_recipe",
                     "vibeedit_plugins_show_view"):
            tool = next(t for t in TOOLS if t["name"] == name)
            self.assertFalse(
                tool["description"].startswith("Not available"), name)


if __name__ == "__main__":
    unittest.main()
