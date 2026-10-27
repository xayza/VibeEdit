"""Phase B3 tests: install_plugin / remove_plugin /
check_plugin_update / download_plugin_bundle (no-network parts).

Run from windows/:  python3 -m unittest discover -s tests
(Windows: py -m unittest discover -s tests)

All tests use temp dirs only -- never the real windows/plugins/
folder. Functions under test accept a plugins_dir parameter for
exactly this. No network calls are made in any test: the URL case
is covered by install_plugin's rejection of URL sources (which
must not download), and download_plugin_bundle itself is not
exercised against a live server here. Stdlib only.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibeedit_core.plugins import (  # noqa: E402
    check_plugin_update, install_plugin, remove_plugin)


def write_manifest(folder, manifest, extra=None):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "plugin.json"), "w",
              encoding="utf-8") as fh:
        json.dump(manifest, fh)
    for name, content in (extra or {}).items():
        path = os.path.join(folder, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)


def make_zip(path, entries):
    """entries: {arcname: text content}."""
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)


def set_disabled(plugins_dir, ids):
    """Write the plugins.json disabled list directly (the same
    state file apply_plugin() enforces). Manifest folders are not
    discovered by load_plugins() yet, so set_plugin_enabled() --
    which requires discovery -- cannot disable them; the parent
    wiring for manifest discovery will change that, but the state
    mechanism tested here is identical."""
    state_path = os.path.join(os.path.dirname(
        os.path.abspath(plugins_dir)), "plugins.json")
    with open(state_path, "w", encoding="utf-8") as fh:
        json.dump({"disabled": sorted(ids)}, fh)


def read_disabled(plugins_dir):
    state_path = os.path.join(os.path.dirname(
        os.path.abspath(plugins_dir)), "plugins.json")
    try:
        with open(state_path, encoding="utf-8") as fh:
            return set(json.load(fh).get("disabled", []))
    except (OSError, ValueError):
        return set()


BASE_MANIFEST = {"id": "demo-plugin", "name": "Demo",
                 "hooks": ["transform_text"],
                 "description": "A demo plugin", "version": "1.0"}


class TestPluginInstall(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.plugins_dir = os.path.join(self.tmp, "plugins")
        os.makedirs(self.plugins_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _src_folder(self, manifest=None, extra=None, name="src"):
        folder = os.path.join(self.tmp, name)
        write_manifest(folder, manifest or dict(BASE_MANIFEST),
                       extra=extra)
        return folder

    def test_valid_folder_install(self):
        src = self._src_folder(extra={"helper.txt": "hello"})
        result = install_plugin(src, plugins_dir=self.plugins_dir)
        self.assertEqual(result["id"], "demo-plugin")
        self.assertEqual(result["name"], "Demo")
        self.assertIn("warnings", result)
        self.assertFalse(result["enabled"])
        dest = os.path.join(self.plugins_dir, "demo-plugin")
        self.assertEqual(result["path"], dest)
        self.assertTrue(os.path.isfile(os.path.join(dest, "plugin.json")))
        self.assertTrue(os.path.isfile(os.path.join(dest, "helper.txt")))
        with open(os.path.join(dest, "install.json"),
                  encoding="utf-8") as fh:
            meta = json.load(fh)
        self.assertEqual(meta["source"], src)
        # New plugins install disabled (untrusted until reviewed).
        self.assertIn("demo-plugin", read_disabled(self.plugins_dir))

    def test_valid_folder_install_warnings(self):
        # Missing description + version, plus declared code hooks,
        # plus a fresh/untrusted id: all must appear in warnings.
        manifest = {"id": "bare-plugin", "name": "Bare", "hooks": ["x"]}
        src = self._src_folder(manifest=manifest, name="src2")
        result = install_plugin(src, plugins_dir=self.plugins_dir)
        joined = " ".join(result["warnings"])
        self.assertIn("untrusted", joined)
        self.assertIn("code hooks", joined)
        self.assertIn("no description", joined)
        self.assertIn("no version", joined)

    def test_valid_zip_install_root_manifest(self):
        zpath = os.path.join(self.tmp, "bundle.zip")
        make_zip(zpath, {
            "plugin.json": json.dumps(BASE_MANIFEST),
            "code.py": "# inert\n",
        })
        result = install_plugin(zpath, plugins_dir=self.plugins_dir)
        self.assertEqual(result["id"], "demo-plugin")
        dest = os.path.join(self.plugins_dir, "demo-plugin")
        self.assertTrue(os.path.isfile(os.path.join(dest, "code.py")))
        self.assertIn("demo-plugin", read_disabled(self.plugins_dir))

    def test_valid_zip_install_single_top_folder(self):
        zpath = os.path.join(self.tmp, "nested.zip")
        manifest = dict(BASE_MANIFEST, id="nested-plugin")
        make_zip(zpath, {
            "nested-plugin/plugin.json": json.dumps(manifest),
            "nested-plugin/data.txt": "data",
        })
        result = install_plugin(zpath, plugins_dir=self.plugins_dir)
        self.assertEqual(result["id"], "nested-plugin")
        dest = os.path.join(self.plugins_dir, "nested-plugin")
        self.assertTrue(os.path.isfile(os.path.join(dest, "data.txt")))
        # No stray top-level folder copy: files land directly in <id>/.
        self.assertFalse(os.path.exists(
            os.path.join(dest, "nested-plugin")))

    def test_manifest_missing_id_rejected_and_nothing_copied(self):
        manifest = {"name": "No Id", "hooks": []}
        src = self._src_folder(manifest=manifest)
        with self.assertRaises(ValueError):
            install_plugin(src, plugins_dir=self.plugins_dir)
        self.assertEqual(os.listdir(self.plugins_dir), [])

    def test_manifest_invalid_json_rejected_and_nothing_copied(self):
        folder = os.path.join(self.tmp, "badjson")
        os.makedirs(folder)
        with open(os.path.join(folder, "plugin.json"), "w",
                  encoding="utf-8") as fh:
            fh.write("{not json")
        with self.assertRaises(ValueError):
            install_plugin(folder, plugins_dir=self.plugins_dir)
        self.assertEqual(os.listdir(self.plugins_dir), [])

    def test_manifest_missing_name_or_hooks_rejected(self):
        for manifest in ({"id": "a-plugin", "hooks": []},
                         {"id": "a-plugin", "name": "A"},
                         {"id": "a-plugin", "name": "A",
                          "hooks": "not-a-list"}):
            src = self._src_folder(manifest=manifest, name="src-bad")
            with self.assertRaises(ValueError):
                install_plugin(src, plugins_dir=self.plugins_dir)
            shutil.rmtree(src, ignore_errors=True)
        self.assertEqual(os.listdir(self.plugins_dir), [])

    def test_unsafe_id_rejected(self):
        for bad_id in ("../evil", "a/b", "a b", "", "a.b"):
            src = self._src_folder(
                manifest={"id": bad_id, "name": "Bad", "hooks": []},
                name="src-unsafe")
            with self.assertRaises(ValueError):
                install_plugin(src, plugins_dir=self.plugins_dir)
            shutil.rmtree(src, ignore_errors=True)
        self.assertEqual(os.listdir(self.plugins_dir), [])

    def test_zip_traversal_entry_rejected_and_nothing_copied(self):
        zpath = os.path.join(self.tmp, "evil.zip")
        make_zip(zpath, {
            "plugin.json": json.dumps(BASE_MANIFEST),
            "../escape.txt": "escape",
        })
        with self.assertRaises(ValueError):
            install_plugin(zpath, plugins_dir=self.plugins_dir)
        self.assertEqual(os.listdir(self.plugins_dir), [])
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "escape.txt")))

    def test_zip_absolute_entry_rejected_and_nothing_copied(self):
        zpath = os.path.join(self.tmp, "abs.zip")
        make_zip(zpath, {
            "plugin.json": json.dumps(BASE_MANIFEST),
            "/tmp/escape.txt": "escape",
        })
        with self.assertRaises(ValueError):
            install_plugin(zpath, plugins_dir=self.plugins_dir)
        self.assertEqual(os.listdir(self.plugins_dir), [])

    def test_zip_symlink_entry_rejected_and_nothing_copied(self):
        zpath = os.path.join(self.tmp, "link.zip")
        with zipfile.ZipFile(zpath, "w") as zf:
            zf.writestr("plugin.json", json.dumps(BASE_MANIFEST))
            info = zipfile.ZipInfo("link.txt")
            info.create_system = 3  # Unix
            info.external_attr = (0o120777 << 16)
            zf.writestr(info, "/etc/passwd")
        with self.assertRaises(ValueError):
            install_plugin(zpath, plugins_dir=self.plugins_dir)
        self.assertEqual(os.listdir(self.plugins_dir), [])

    def test_zip_multiple_top_folders_rejected(self):
        zpath = os.path.join(self.tmp, "multi.zip")
        make_zip(zpath, {
            "one/plugin.json": json.dumps(dict(BASE_MANIFEST, id="one")),
            "two/plugin.json": json.dumps(dict(BASE_MANIFEST, id="two")),
        })
        with self.assertRaises(ValueError):
            install_plugin(zpath, plugins_dir=self.plugins_dir)
        self.assertEqual(os.listdir(self.plugins_dir), [])

    def test_folder_symlink_escape_rejected_and_nothing_copied(self):
        src = self._src_folder()
        outside = os.path.join(self.tmp, "secret.txt")
        with open(outside, "w", encoding="utf-8") as fh:
            fh.write("secret")
        os.symlink(outside, os.path.join(src, "escape.txt"))
        with self.assertRaises(ValueError):
            install_plugin(src, plugins_dir=self.plugins_dir)
        self.assertEqual(os.listdir(self.plugins_dir), [])

    def test_duplicate_id_refused(self):
        src = self._src_folder()
        install_plugin(src, plugins_dir=self.plugins_dir)
        src2 = self._src_folder(name="src2",
                                extra={"other.txt": "changed"})
        with self.assertRaises(ValueError):
            install_plugin(src2, plugins_dir=self.plugins_dir)
        dest = os.path.join(self.plugins_dir, "demo-plugin")
        self.assertFalse(os.path.exists(os.path.join(dest, "other.txt")))

    def test_overwrite_refused_when_enabled(self):
        src = self._src_folder()
        install_plugin(src, plugins_dir=self.plugins_dir)
        # Simulate enabling: drop the id from the disabled list.
        set_disabled(self.plugins_dir, [])
        src2 = self._src_folder(name="src2")
        with self.assertRaises(ValueError):
            install_plugin(src2, plugins_dir=self.plugins_dir,
                           overwrite=True)

    def test_overwrite_after_disable_succeeds(self):
        src = self._src_folder(extra={"v.txt": "v1"})
        install_plugin(src, plugins_dir=self.plugins_dir)
        # Installed disabled by default, so overwrite is allowed.
        src2 = self._src_folder(name="src2", extra={"v.txt": "v2"})
        result = install_plugin(src2, plugins_dir=self.plugins_dir,
                                overwrite=True)
        self.assertTrue(result["overwrite"])
        dest = os.path.join(self.plugins_dir, "demo-plugin")
        with open(os.path.join(dest, "v.txt"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "v2")
        self.assertIn("demo-plugin", read_disabled(self.plugins_dir))

    def test_url_source_rejected_without_download(self):
        with self.assertRaises(ValueError):
            install_plugin("https://example.invalid/plugin.zip",
                           plugins_dir=self.plugins_dir)
        self.assertEqual(os.listdir(self.plugins_dir), [])

    def test_url_recorded_as_metadata_only_via_source_label(self):
        src = self._src_folder()
        result = install_plugin(
            src, plugins_dir=self.plugins_dir,
            source_label="https://example.invalid/plugin.zip")
        self.assertEqual(result["source"],
                         "https://example.invalid/plugin.zip")
        with open(os.path.join(self.plugins_dir, "demo-plugin",
                               "install.json"), encoding="utf-8") as fh:
            self.assertEqual(
                json.load(fh)["source"],
                "https://example.invalid/plugin.zip")

    def test_remove_refuses_when_enabled(self):
        src = self._src_folder()
        install_plugin(src, plugins_dir=self.plugins_dir)
        set_disabled(self.plugins_dir, [])  # simulate enabled
        with self.assertRaises(ValueError):
            remove_plugin("demo-plugin", plugins_dir=self.plugins_dir)
        self.assertTrue(os.path.isdir(
            os.path.join(self.plugins_dir, "demo-plugin")))

    def test_remove_succeeds_when_disabled(self):
        src = self._src_folder()
        install_plugin(src, plugins_dir=self.plugins_dir)
        result = remove_plugin("demo-plugin",
                               plugins_dir=self.plugins_dir)
        self.assertTrue(result["removed"])
        self.assertFalse(os.path.exists(
            os.path.join(self.plugins_dir, "demo-plugin")))
        self.assertNotIn("demo-plugin", read_disabled(self.plugins_dir))

    def test_remove_unknown_raises(self):
        with self.assertRaises(KeyError):
            remove_plugin("no-such-plugin",
                          plugins_dir=self.plugins_dir)

    def test_remove_only_own_folder(self):
        # A neighbouring plugin folder and a top-level .py file must
        # survive removing a different plugin.
        src = self._src_folder()
        install_plugin(src, plugins_dir=self.plugins_dir)
        other = os.path.join(self.plugins_dir, "other-plugin")
        os.makedirs(other)
        with open(os.path.join(other, "plugin.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({"id": "other-plugin", "name": "Other",
                       "hooks": []}, fh)
        with open(os.path.join(self.plugins_dir, "legacy.py"), "w",
                  encoding="utf-8") as fh:
            fh.write("# legacy\n")
        remove_plugin("demo-plugin", plugins_dir=self.plugins_dir)
        self.assertTrue(os.path.isdir(other))
        self.assertTrue(os.path.isfile(
            os.path.join(self.plugins_dir, "legacy.py")))

    def test_update_check_unknown_without_metadata(self):
        manifest = {"id": "plain-plugin", "name": "Plain", "hooks": []}
        src = self._src_folder(manifest=manifest)
        install_plugin(src, plugins_dir=self.plugins_dir)
        result = check_plugin_update("plain-plugin",
                                     plugins_dir=self.plugins_dir)
        self.assertEqual(result["status"], "unknown")
        self.assertFalse(result["fetched"])
        self.assertIsNone(result["update_url"])

    def test_update_check_returns_metadata_when_present(self):
        manifest = dict(BASE_MANIFEST, id="up-plugin",
                        update_url="https://example.invalid/plugin",
                        latest_version="2.0")
        src = self._src_folder(manifest=manifest)
        install_plugin(src, plugins_dir=self.plugins_dir)
        result = check_plugin_update("up-plugin",
                                     plugins_dir=self.plugins_dir)
        self.assertEqual(result["status"], "metadata_only")
        self.assertFalse(result["fetched"])
        self.assertEqual(result["update_url"],
                         "https://example.invalid/plugin")
        self.assertEqual(result["latest_version"], "2.0")
        self.assertEqual(result["installed_version"], "1.0")

    def test_update_check_unknown_plugin_raises(self):
        with self.assertRaises(KeyError):
            check_plugin_update("no-such-plugin",
                                plugins_dir=self.plugins_dir)

    def test_install_never_executes_plugin_code(self):
        """A plugin whose .py would create a side-effect file if run
        must leave no such file after install."""
        marker = os.path.join(self.tmp, "pwned.txt")
        code = (f"open({marker!r}, 'w').write('executed')\n")
        src = self._src_folder(extra={"evil.py": code})
        install_plugin(src, plugins_dir=self.plugins_dir)
        self.assertFalse(os.path.exists(marker))
        # The code file itself is copied inertly, never run.
        self.assertTrue(os.path.isfile(os.path.join(
            self.plugins_dir, "demo-plugin", "evil.py")))


if __name__ == "__main__":
    unittest.main()
