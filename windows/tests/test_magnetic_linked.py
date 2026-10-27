"""Phase B2: full magnetic Main + linked audio (Project model only).

Real timeline data, temp dirs only, no FFmpeg, no network. Run from
windows/: python3 -m unittest discover -s tests (Linux) / py -m
unittest discover -s tests (Windows).

Conventions used here: Main is track "v1", Dialogue is "a1"
(the defaults from new_project). Magnetic is ON by default.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibeedit_core.project import Project, new_project  # noqa: E402


def make_project():
    tmp = tempfile.mkdtemp()
    proj = Project(new_project("MagneticTest", fps=(30, 1)), tmp)
    video = proj.add_media("clip.mp4", kind="video",
                           fps=[30, 1], frames=900)["id"]
    audio = proj.add_media("voice.mp3", kind="audio")["id"]
    return proj, tmp, video, audio


def main_clips(proj):
    track = proj.track("v1")
    return {c["id"]: (c["at"], c["dur"]) for c in track["items"]}


def track_clips(proj, track_id):
    track = proj.track(track_id)
    return {c["id"]: (c["at"], c["dur"]) for c in track["items"]}


def add_main(proj, media_id, at, dur):
    return proj.add_clip(media_id, "v1", at, 0, dur)


class TestLinkedAudio(unittest.TestCase):
    def setUp(self):
        self.proj, self.tmp, self.video, self.audio = make_project()

    def linked_pair(self, v_at=0, v_dur=60):
        v = add_main(self.proj, self.video, v_at, v_dur)
        a = self.proj.add_clip(self.audio, "a1", v_at, 0, v_dur)
        self.proj.link_audio(v["id"], a["id"])
        return v, a

    def test_link_stores_reciprocal_fields(self):
        v, a = self.linked_pair()
        _, v_item = self.proj.item(v["id"])
        _, a_item = self.proj.item(a["id"])
        self.assertEqual(v_item["linked_audio"], [a["id"]])
        self.assertEqual(a_item["linked_video"], v["id"])
        self.assertEqual([x["id"] for x in self.proj.linked_audio(v["id"])],
                         [a["id"]])

    def test_link_move_video_moves_audio_same_delta(self):
        v, a = self.linked_pair()
        self.proj.move(v["id"], "v1", 30)
        _, v_item = self.proj.item(v["id"])
        _, a_item = self.proj.item(a["id"])
        self.assertEqual((v_item["at"], a_item["at"]), (30, 30))
        self.assertEqual(v_item["linked_audio"], [a["id"]])

    def test_link_move_refused_on_audio_collision_leaves_data_unchanged(self):
        v, a = self.linked_pair()
        blocker = self.proj.add_clip(self.audio, "a1", 60, 0, 60)
        before = self.proj.snapshot()
        with self.assertRaises(ValueError):
            self.proj.move(v["id"], "v1", 10)
        # Audio would land at 10-70, overlapping the blocker at 60-120.
        self.assertEqual(self.proj.snapshot(), before)
        _, v_item = self.proj.item(v["id"])
        _, a_item = self.proj.item(a["id"])
        self.assertEqual(v_item["at"], 0)
        self.assertEqual(a_item["at"], 0)
        self.assertIn(blocker["id"], track_clips(self.proj, "a1"))

    def test_link_trim_video_trims_audio_both_edges(self):
        v, a = self.linked_pair()
        self.proj.trim(v["id"], "start", 10)
        _, v_item = self.proj.item(v["id"])
        _, a_item = self.proj.item(a["id"])
        self.assertEqual((v_item["at"], v_item["dur"], v_item["in"]),
                         (10, 50, 10))
        self.assertEqual((a_item["at"], a_item["dur"], a_item["in"]),
                         (10, 50, 10))
        self.proj.trim(v["id"], "end", 40)
        _, v_item = self.proj.item(v["id"])
        _, a_item = self.proj.item(a["id"])
        self.assertEqual((v_item["at"], v_item["dur"]), (10, 30))
        self.assertEqual((a_item["at"], a_item["dur"]), (10, 30))

    def test_link_trim_audio_trims_video(self):
        v, a = self.linked_pair()
        self.proj.trim(a["id"], "end", 40)
        _, v_item = self.proj.item(v["id"])
        _, a_item = self.proj.item(a["id"])
        self.assertEqual((v_item["at"], v_item["dur"]), (0, 40))
        self.assertEqual((a_item["at"], a_item["dur"]), (0, 40))

    def test_link_split_video_splits_audio_with_rewired_links(self):
        v, a = self.linked_pair()
        right_v = self.proj.split(v["id"], 30)
        _, v_left = self.proj.item(v["id"])
        _, a_left = self.proj.item(a["id"])
        # The right video half links the right audio half (a new id).
        _, right_a = self.proj.item(right_v["linked_audio"][0])
        self.assertEqual((v_left["at"], v_left["dur"]), (0, 30))
        self.assertEqual((right_v["at"], right_v["dur"]), (30, 30))
        self.assertEqual((a_left["at"], a_left["dur"]), (0, 30))
        self.assertEqual(v_left["linked_audio"], [a["id"]])
        self.assertEqual(right_a["linked_video"], right_v["id"])
        self.assertEqual(a_left["linked_video"], v["id"])
        self.assertEqual((right_a["at"], right_a["dur"]), (30, 30))
        self.assertNotEqual(right_a["id"], a["id"])

    def test_link_split_audio_splits_video(self):
        v, a = self.linked_pair()
        right_a = self.proj.split(a["id"], 30)
        _, v_left = self.proj.item(v["id"])
        # The right video half is the Main clip starting at 30.
        right_v_item = [c for c in self.proj.track("v1")["items"]
                        if c["at"] == 30][0]
        # Left video keeps the left audio; right video links the
        # right audio (the split audio's new half).
        self.assertEqual(v_left["linked_audio"], [a["id"]])
        self.assertEqual(right_v_item["linked_audio"], [right_a["id"]])
        self.assertEqual(right_a["linked_video"], right_v_item["id"])
        self.assertEqual((right_v_item["at"], right_v_item["dur"]),
                         (30, 30))

    def test_link_split_refused_when_audio_does_not_cover_point(self):
        v, a = self.linked_pair()
        # Misalign the audio (move it alone is impossible while
        # linked, so shift it by hand to stage the broken state).
        _, a_item = self.proj.item(a["id"])
        a_item["at"] = 30
        before = self.proj.snapshot()
        with self.assertRaises(ValueError):
            self.proj.split(v["id"], 20)
        self.assertEqual(self.proj.snapshot(), before)

    def test_link_delete_video_deletes_audio(self):
        v, a = self.linked_pair()
        self.proj.delete(v["id"])
        with self.assertRaises(KeyError):
            self.proj.item(v["id"])
        with self.assertRaises(KeyError):
            self.proj.item(a["id"])

    def test_link_delete_audio_keeps_video_unlinked(self):
        v, a = self.linked_pair()
        self.proj.delete(a["id"])
        _, v_item = self.proj.item(v["id"])
        self.assertEqual((v_item["at"], v_item["dur"]), (0, 60))
        self.assertNotIn("linked_audio", v_item)
        with self.assertRaises(KeyError):
            self.proj.item(a["id"])

    def test_unlink_stops_propagation(self):
        v, a = self.linked_pair()
        self.proj.unlink_audio(v["id"], a["id"])
        self.proj.move(v["id"], "v1", 20)
        _, a_item = self.proj.item(a["id"])
        self.assertEqual(a_item["at"], 0)
        self.assertNotIn("linked_video", a_item)

    def test_link_errors(self):
        v, a = self.linked_pair()
        with self.assertRaises(KeyError):
            self.proj.link_audio(v["id"], "no-such-clip")
        with self.assertRaises(ValueError):
            self.proj.link_audio(v["id"], a["id"])  # already linked
        other_video = add_main(self.proj, self.video, 60, 30)
        with self.assertRaises(ValueError):
            self.proj.link_audio(other_video["id"], a["id"])
        text = self.proj.add_text("t1", "hi", 0, 30)
        with self.assertRaises(ValueError):
            self.proj.link_audio(v["id"], text["id"])
        with self.assertRaises(ValueError):
            self.proj.unlink_audio(v["id"], other_video["id"])

    def test_validate_reports_one_way_link(self):
        v, a = self.linked_pair()
        _, a_item = self.proj.item(a["id"])
        a_item.pop("linked_video")
        result = self.proj.validate()
        self.assertFalse(result["ok"])
        self.assertTrue(any("one-way" in err for err in result["errors"]))


class TestMagneticMain(unittest.TestCase):
    def setUp(self):
        self.proj, self.tmp, self.video, self.audio = make_project()

    def three_packed(self):
        c1 = add_main(self.proj, self.video, 0, 30)
        c2 = add_main(self.proj, self.video, 30, 30)
        c3 = add_main(self.proj, self.video, 60, 30)
        return c1, c2, c3

    def test_magnetic_default_on_and_toggle_persisted(self):
        self.assertTrue(self.proj.magnetic_enabled)
        self.assertTrue(self.proj.data["magnetic"])
        self.proj.set_magnetic(False)
        self.assertFalse(self.proj.magnetic_enabled)
        self.assertFalse(self.proj.data["magnetic"])
        again = Project(self.proj.snapshot(), self.tmp)
        self.assertFalse(again.magnetic_enabled)
        self.proj.set_magnetic(True)
        self.assertTrue(self.proj.magnetic_enabled)

    def test_magnetic_delete_shifts_followers_left_no_gap(self):
        c1, c2, c3 = self.three_packed()
        self.proj.delete(c1["id"])
        positions = main_clips(self.proj)
        self.assertEqual(positions[c2["id"]], (0, 30))
        self.assertEqual(positions[c3["id"]], (30, 30))

    def test_magnetic_delete_carries_linked_audio_once(self):
        c1, c2, c3 = self.three_packed()
        a2 = self.proj.add_clip(self.audio, "a1", 30, 0, 30)
        self.proj.link_audio(c2["id"], a2["id"])
        self.proj.delete(c1["id"])
        _, a2_item = self.proj.item(a2["id"])
        self.assertEqual((a2_item["at"], a2_item["dur"]), (0, 30))
        self.assertEqual(main_clips(self.proj)[c3["id"]], (30, 30))

    def test_magnetic_insert_shifts_followers_right(self):
        c1, c2 = add_main(self.proj, self.video, 0, 30), \
            add_main(self.proj, self.video, 30, 30)
        new = add_main(self.proj, self.video, 30, 30)
        positions = main_clips(self.proj)
        self.assertEqual(positions[new["id"]], (30, 30))
        self.assertEqual(positions[c2["id"]], (60, 30))
        self.assertEqual(positions[c1["id"]], (0, 30))

    def test_magnetic_insert_inside_clip_refused_data_unchanged(self):
        c1, c2 = add_main(self.proj, self.video, 0, 30), \
            add_main(self.proj, self.video, 30, 30)
        before = self.proj.snapshot()
        with self.assertRaises(ValueError):
            add_main(self.proj, self.video, 15, 30)
        self.assertEqual(self.proj.snapshot(), before)
        self.assertEqual(main_clips(self.proj)[c1["id"]], (0, 30))
        self.assertEqual(main_clips(self.proj)[c2["id"]], (30, 30))

    def test_magnetic_move_shifts_followers(self):
        c1, c2, c3 = self.three_packed()
        self.proj.move(c1["id"], "v1", 10)
        positions = main_clips(self.proj)
        self.assertEqual(positions[c1["id"]], (10, 30))
        self.assertEqual(positions[c2["id"]], (40, 30))
        self.assertEqual(positions[c3["id"]], (70, 30))

    def test_magnetic_move_over_predecessor_refused(self):
        c1, c2, c3 = self.three_packed()
        before = self.proj.snapshot()
        with self.assertRaises(ValueError):
            self.proj.move(c2["id"], "v1", 0)
        self.assertEqual(self.proj.snapshot(), before)

    def test_magnetic_trim_end_shifts_followers(self):
        c1 = add_main(self.proj, self.video, 0, 60)
        c2 = add_main(self.proj, self.video, 60, 30)
        self.proj.trim(c1["id"], "end", 40)
        positions = main_clips(self.proj)
        self.assertEqual(positions[c1["id"]], (0, 40))
        self.assertEqual(positions[c2["id"]], (40, 30))

    def test_magnetic_trim_start_leaves_followers(self):
        c1 = add_main(self.proj, self.video, 0, 60)
        c2 = add_main(self.proj, self.video, 60, 30)
        self.proj.trim(c1["id"], "start", 20)
        positions = main_clips(self.proj)
        self.assertEqual(positions[c1["id"]], (20, 40))
        self.assertEqual(positions[c2["id"]], (60, 30))

    def test_magnetic_off_delete_leaves_followers(self):
        c1, c2, c3 = self.three_packed()
        self.proj.set_magnetic(False)
        self.proj.delete(c1["id"])
        positions = main_clips(self.proj)
        self.assertEqual(positions[c2["id"]], (30, 30))
        self.assertEqual(positions[c3["id"]], (60, 30))

    def test_magnetic_off_insert_is_old_overlap_rejection(self):
        c1, c2 = add_main(self.proj, self.video, 0, 30), \
            add_main(self.proj, self.video, 30, 30)
        self.proj.set_magnetic(False)
        before = self.proj.snapshot()
        with self.assertRaises(ValueError):
            add_main(self.proj, self.video, 30, 30)
        self.assertEqual(self.proj.snapshot(), before)

    def test_magnetic_off_linked_propagation_still_applies(self):
        v = add_main(self.proj, self.video, 0, 60)
        a = self.proj.add_clip(self.audio, "a1", 0, 0, 60)
        self.proj.link_audio(v["id"], a["id"])
        self.proj.set_magnetic(False)
        self.proj.move(v["id"], "v1", 15)
        _, a_item = self.proj.item(a["id"])
        self.assertEqual(a_item["at"], 15)

    def test_magnetic_delete_refused_on_audio_collision(self):
        c1 = add_main(self.proj, self.video, 0, 30)
        c2 = add_main(self.proj, self.video, 30, 30)
        a2 = self.proj.add_clip(self.audio, "a1", 30, 0, 30)
        self.proj.link_audio(c2["id"], a2["id"])
        # An unlinked Dialogue clip already sits where the linked
        # audio would land after the ripple.
        self.proj.add_clip(self.audio, "a1", 0, 0, 30)
        before = self.proj.snapshot()
        with self.assertRaises(ValueError):
            self.proj.delete(c1["id"])
        self.assertEqual(self.proj.snapshot(), before)

    def test_magnetic_move_off_main_closes_gap(self):
        c1, c2 = add_main(self.proj, self.video, 0, 30), \
            add_main(self.proj, self.video, 30, 30)
        self.proj.move(c1["id"], "v2", 0)
        self.assertEqual(main_clips(self.proj)[c2["id"]], (0, 30))

    def test_undo_restores_all_moved_clips(self):
        c1, c2, c3 = self.three_packed()
        a2 = self.proj.add_clip(self.audio, "a1", 30, 0, 30)
        self.proj.link_audio(c2["id"], a2["id"])
        before = self.proj.snapshot()
        self.proj.delete(c1["id"])
        self.assertEqual(main_clips(self.proj)[c2["id"]], (0, 30))
        self.proj.restore(before)
        positions = main_clips(self.proj)
        self.assertEqual(positions[c1["id"]], (0, 30))
        self.assertEqual(positions[c2["id"]], (30, 30))
        self.assertEqual(positions[c3["id"]], (60, 30))
        _, a2_item = self.proj.item(a2["id"])
        self.assertEqual((a2_item["at"], a2_item["dur"]), (30, 30))
        _, c2_item = self.proj.item(c2["id"])
        self.assertEqual(c2_item["linked_audio"], [a2["id"]])
        self.assertEqual(self.proj.rev, before["rev"])


class TestOverwriteAndCloseGapsLinked(unittest.TestCase):
    def setUp(self):
        self.proj, self.tmp, self.video, self.audio = make_project()

    def test_overwrite_trims_linked_audio_with_video(self):
        v = add_main(self.proj, self.video, 0, 60)
        a = self.proj.add_clip(self.audio, "a1", 0, 0, 60)
        self.proj.link_audio(v["id"], a["id"])
        new = self.proj.overwrite_insert(self.video, 0, 30, 30)
        _, v_item = self.proj.item(v["id"])
        _, a_item = self.proj.item(a["id"])
        self.assertEqual((v_item["at"], v_item["dur"]), (0, 30))
        self.assertEqual((a_item["at"], a_item["dur"]), (0, 30))
        self.assertEqual(v_item["linked_audio"], [a["id"]])
        self.assertEqual(new["at"], 30)

    def test_overwrite_deletes_fully_covered_linked_pair(self):
        v = add_main(self.proj, self.video, 0, 60)
        a = self.proj.add_clip(self.audio, "a1", 0, 0, 60)
        self.proj.link_audio(v["id"], a["id"])
        self.proj.overwrite_insert(self.video, 0, 60, 0)
        with self.assertRaises(KeyError):
            self.proj.item(v["id"])
        with self.assertRaises(KeyError):
            self.proj.item(a["id"])

    def test_overwrite_splits_linked_audio_with_spanning_video(self):
        v = add_main(self.proj, self.video, 0, 90)
        a = self.proj.add_clip(self.audio, "a1", 0, 0, 90)
        self.proj.link_audio(v["id"], a["id"])
        self.proj.overwrite_insert(self.video, 0, 30, 30)
        _, v_left = self.proj.item(v["id"])
        left_audio_id = v_left["linked_audio"][0]
        _, a_left = self.proj.item(left_audio_id)
        self.assertEqual((v_left["at"], v_left["dur"]), (0, 30))
        self.assertEqual((a_left["at"], a_left["dur"]), (0, 30))
        # The right part of the video links the right part of the audio.
        right_v = [c for c in self.proj.track("v1")["items"]
                   if c["at"] == 60][0]
        right_a = self.proj.item(right_v["linked_audio"][0])[1]
        self.assertEqual((right_v["at"], right_v["dur"]), (60, 30))
        self.assertEqual((right_a["at"], right_a["dur"]), (60, 30))
        self.assertEqual(right_a["linked_video"], right_v["id"])

    def test_overwrite_linked_audio_itself_refused(self):
        v = add_main(self.proj, self.video, 0, 60)
        a = self.proj.add_clip(self.audio, "a1", 0, 0, 60)
        self.proj.link_audio(v["id"], a["id"])
        before = self.proj.snapshot()
        with self.assertRaises(ValueError):
            self.proj.overwrite_insert(self.audio, 0, 30, 0, "a1")
        self.assertEqual(self.proj.snapshot(), before)

    def test_close_gaps_carries_linked_audio(self):
        v1 = add_main(self.proj, self.video, 0, 30)
        v2 = add_main(self.proj, self.video, 60, 30)
        a2 = self.proj.add_clip(self.audio, "a1", 60, 0, 30)
        self.proj.link_audio(v2["id"], a2["id"])
        result = self.proj.close_gaps("v1")
        self.assertIn(v2["id"], result["moved"])
        _, a2_item = self.proj.item(a2["id"])
        self.assertEqual((a2_item["at"], a2_item["dur"]), (30, 30))
        self.assertEqual(main_clips(self.proj)[v1["id"]], (0, 30))
        self.assertEqual(main_clips(self.proj)[v2["id"]], (30, 30))


if __name__ == "__main__":
    unittest.main()
