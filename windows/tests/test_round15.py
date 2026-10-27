"""Round 15 tests: agent-kit signed releases + plugin registry.

No real network anywhere in this file: fetchers and downloaders
are fakes, digests are real SHA-256 values of the test bytes, and
the Ed25519 verifier itself is checked against the RFC 8032 test
vector and the real kit 0.1.56 signature (digest + publisher key
from the public releases catalog).
"""

import base64
import hashlib
import io
import json
import os
import shutil
import tempfile
import unittest
import zipfile
from unittest import mock

from vibeedit_core import round15 as r15
from vibeedit_core.mcp import MCPServer
from vibeedit_core.plugins import load_plugins, set_plugin_enabled

PUBLISHER_KEY = "ed25519:q+RG+vvYLwP2xxRtVjNxPCbb3LhvuRyKNxSx3c1p6C4="
# Real kit 0.1.56 release data (public releases.json, 2026-10-18).
KIT_056_DIGEST = ("acfd822724ccc40585a5cf740a1833db24491a57083d81cb64326cb85"
                  "f4876fd")
KIT_056_SIG = ("ed25519:9nnm3IJwt4Drojaa17xaRWLiYvBUm1705arZzthjFJ8NB4fe/"
               "2K06Vs7BPDeAa//8VdTH3UGswISCkIyf/3wBA==")
FAKE_SIG = "ed25519:" + base64.b64encode(b"\x00" * 64).decode()


def _skill_md(skill_id):
    return (f"---\nname: {skill_id}\ndescription: test skill {skill_id}\n---\n"
            f"# {skill_id}\n\nBody.\n").encode("utf-8")


def _kit_zip_bytes(skill_ids, top="bashcut-agent-kit"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for sid in skill_ids:
            zf.writestr(f"{top}/skills/{sid}/SKILL.md", _skill_md(sid))
        zf.writestr(f"{top}/LICENSE", "MIT License\n")
    return buf.getvalue()


def _kit_catalog(versions):
    """versions: [(version, url, sha256, size)] -> releases.json bytes."""
    return json.dumps({
        "schemaVersion": 1, "kit": "bashcut",
        "versions": [{"version": v, "url": u, "sha256": s,
                      "signature": FAKE_SIG, "size": n,
                      "releasedAt": "2026-10-18T00:00:00Z",
                      "minAppVersion": "0.0.25"}
                     for v, u, s, n in versions],
    }).encode("utf-8")


def _registry_zip_bytes(plugin_id, version, name_map=True):
    buf = io.BytesIO()
    name = {"en": f"{plugin_id} EN", "vi": f"{plugin_id} VI"} \
        if name_map else plugin_id
    manifest = {"id": plugin_id, "version": version, "name": name,
                "hooks": None}
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{plugin_id}/plugin.json",
                    json.dumps(manifest).encode("utf-8"))
        zf.writestr(f"{plugin_id}/bin/setup", "#!/bin/sh\n")
        zf.writestr(f"{plugin_id}/README.md", "# readme\n")
    return buf.getvalue()


def _registry_bytes(plugin_entries):
    """plugin_entries: [(id, [(version, url, sha256, size, platforms)])]."""
    plugins = []
    for pid, versions in plugin_entries:
        plugins.append({
            "id": pid, "name": {"en": pid + " EN", "vi": pid + " VI"},
            "summary": {"en": "summary", "vi": "tom tat"},
            "category": "test", "publisher": "bashcut",
            "homepage": "https://example.invalid",
            "capabilities": [],
            "versions": [{"version": v, "url": u, "sha256": s,
                          "signature": FAKE_SIG, "size": n,
                          "platforms": plats, "releasedAt": "2026-01-01"}
                         for v, u, s, n, plats in versions],
        })
    return json.dumps({
        "schemaVersion": 1,
        "publishers": {"bashcut": {"name": "BashCut", "keys": [PUBLISHER_KEY],
                                   "verified": True}},
        "plugins": plugins,
    }).encode("utf-8")


class TestEd25519(unittest.TestCase):
    def test_rfc8032_vector1(self):
        pk = bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325"
                           "af021a68f707511a")
        sig = bytes.fromhex(
            "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
            "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")
        self.assertTrue(r15.ed25519_verify(pk, sig, b""))
        self.assertFalse(r15.ed25519_verify(pk, sig[:-1] + b"\x01", b""))
        self.assertFalse(r15.ed25519_verify(b"\x00" * 32, sig, b""))

    def test_real_kit_056_signature(self):
        # The real release digest + signature + publisher key.
        self.assertTrue(r15.verify_release_signature(KIT_056_DIGEST,
                                                     KIT_056_SIG))
        self.assertFalse(r15.verify_release_signature("00" * 32, KIT_056_SIG))
        self.assertFalse(r15.verify_release_signature(
            KIT_056_DIGEST, KIT_056_SIG,
            keys=("ed25519:" + base64.b64encode(b"\x01" * 32).decode(),)))


class TestKitReleases(unittest.TestCase):
    def test_parse_valid_and_latest(self):
        raw = _kit_catalog([
            ("0.1.0", "https://example.invalid/k1.zip", "ab" * 32, 100),
            ("0.1.9", "https://example.invalid/k2.zip", "cd" * 32, 200),
            ("0.1.56", "https://example.invalid/k3.zip", "ef" * 32, 300),
        ])
        parsed = r15.parse_kit_releases(raw)
        latest = r15._latest_release(parsed)
        # Numeric sort: 0.1.56 beats 0.1.9 (string sort would not).
        self.assertEqual(latest["version"], "0.1.56")
        self.assertEqual(r15._latest_release(parsed, "0.1.9")["version"],
                         "0.1.9")
        with self.assertRaises(ValueError):
            r15._latest_release(parsed, "9.9.9")

    def test_parse_rejects_bad_entries(self):
        base = json.loads(_kit_catalog(
            [("0.1.0", "https://example.invalid/k.zip", "ab" * 32, 100)]))
        bad = dict(base)
        bad["versions"][0]["sha256"] = "not-a-digest"
        with self.assertRaises(ValueError):
            r15.parse_kit_releases(json.dumps(bad).encode())
        bad = json.loads(_kit_catalog(
            [("0.1.0", "https://example.invalid/k.zip", "ab" * 32, 100)]))
        del bad["versions"][0]["signature"]
        with self.assertRaises(ValueError):
            r15.parse_kit_releases(json.dumps(bad).encode())
        bad = dict(base)
        bad["schemaVersion"] = 2
        with self.assertRaises(ValueError):
            r15.parse_kit_releases(json.dumps(bad).encode())


class TestKitInstall(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="vibeedit-r15-kit-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_install_verbatim_and_user_file_refused(self):
        kit_dir = os.path.join(self.tmp, "skills")
        os.makedirs(kit_dir)
        # A user file with a name the new kit also wants.
        with open(os.path.join(kit_dir, "review.md"), "w",
                  encoding="utf-8") as fh:
            fh.write("user content\n")
        zpath = os.path.join(self.tmp, "kit.zip")
        with open(zpath, "wb") as fh:
            fh.write(_kit_zip_bytes(["review", "rough-cut"]))
        res = r15.kit_install_from_zip(zpath, kit_dir)
        self.assertEqual([s["id"] for s in res["installed"]], ["rough-cut"])
        self.assertEqual([x["id"] for x in res["refused"]], ["review"])
        with open(os.path.join(kit_dir, "review.md"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "user content\n")
        with open(os.path.join(kit_dir, "rough-cut.md"), "rb") as fh:
            self.assertEqual(fh.read(), _skill_md("rough-cut"))

    def test_install_managed_overwrite(self):
        kit_dir = os.path.join(self.tmp, "skills")
        os.makedirs(kit_dir)
        with open(os.path.join(kit_dir, "rough-cut.md"), "w",
                  encoding="utf-8") as fh:
            fh.write("old\n")
        zpath = os.path.join(self.tmp, "kit.zip")
        with open(zpath, "wb") as fh:
            fh.write(_kit_zip_bytes(["rough-cut"]))
        res = r15.kit_install_from_zip(zpath, kit_dir,
                                       managed_ids={"rough-cut"})
        self.assertEqual(res["refused"], [])
        with open(os.path.join(kit_dir, "rough-cut.md"), "rb") as fh:
            self.assertEqual(fh.read(), _skill_md("rough-cut"))

    def test_zip_frontmatter_mismatch_refused(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("kit/skills/rough-cut/SKILL.md",
                        "---\nname: other\ndescription: x\n---\n# x\n")
        zpath = os.path.join(self.tmp, "kit.zip")
        with open(zpath, "wb") as fh:
            fh.write(buf.getvalue())
        with self.assertRaises(ValueError):
            r15.kit_zip_skills(zpath)

    def test_update_success_swap_and_stale_removal(self):
        kit_dir = os.path.join(self.tmp, "skills")
        os.makedirs(kit_dir)
        old_zip = _kit_zip_bytes(["old-skill", "rough-cut"])
        r15.kit_install_from_zip(
            self._write_zip(old_zip), kit_dir)
        r15.write_kit_manifest(kit_dir, {
            "source": "https://github.com/dongnguyenvie/bashcut-agent-kit",
            "version": "0.1.0", "license": "MIT",
            "installed": [{"id": "old-skill",
                           "sha256": hashlib.sha256(
                               _skill_md("old-skill")).hexdigest()},
                          {"id": "rough-cut",
                           "sha256": hashlib.sha256(
                               _skill_md("rough-cut")).hexdigest()}],
        })
        new_zip = _kit_zip_bytes(["rough-cut", "new-skill"])
        new_sha = hashlib.sha256(new_zip).hexdigest()
        catalog = _kit_catalog([
            ("0.1.0", "https://example.invalid/old.zip", "ab" * 32, 10),
            ("0.2.0", "https://example.invalid/new.zip", new_sha,
             len(new_zip)),
        ])

        def fake_fetch(url):
            if url == r15.KIT_RELEASES_URL:
                return catalog
            return new_zip

        with mock.patch.object(r15, "ed25519_verify", return_value=True):
            res = r15.kit_update(kit_dir, fetcher=fake_fetch)
        self.assertTrue(res["updated"])
        self.assertEqual(res["version"], "0.2.0")
        self.assertEqual(res["previous_version"], "0.1.0")
        self.assertFalse(os.path.exists(os.path.join(kit_dir, "old-skill.md")))
        self.assertTrue(os.path.exists(os.path.join(kit_dir, "new-skill.md")))
        self.assertEqual(r15.read_kit_manifest(kit_dir)["version"], "0.2.0")

    def test_update_sha_mismatch_leaves_old_kit(self):
        kit_dir = os.path.join(self.tmp, "skills")
        os.makedirs(kit_dir)
        r15.kit_install_from_zip(self._write_zip(_kit_zip_bytes(["a-skill"])),
                                 kit_dir)
        r15.write_kit_manifest(kit_dir, {
            "source": "x", "version": "0.1.0", "license": "MIT",
            "installed": [{"id": "a-skill", "sha256": "00" * 32}]})
        new_zip = _kit_zip_bytes(["b-skill"])
        catalog = _kit_catalog([
            ("0.2.0", "https://example.invalid/new.zip", "ff" * 32,
             len(new_zip)),
        ])

        def fake_fetch(url):
            return catalog if url == r15.KIT_RELEASES_URL else new_zip

        with mock.patch.object(r15, "ed25519_verify", return_value=True):
            with self.assertRaises(ValueError):
                r15.kit_update(kit_dir, fetcher=fake_fetch)
        self.assertTrue(os.path.exists(os.path.join(kit_dir, "a-skill.md")))
        self.assertFalse(os.path.exists(os.path.join(kit_dir, "b-skill.md")))
        self.assertEqual(r15.read_kit_manifest(kit_dir)["version"], "0.1.0")

    def test_update_already_current_is_noop(self):
        kit_dir = os.path.join(self.tmp, "skills")
        r15.write_kit_manifest(kit_dir, {
            "source": "x", "version": "0.2.0", "license": "MIT",
            "installed": []})
        catalog = _kit_catalog([
            ("0.2.0", "https://example.invalid/new.zip", "ff" * 32, 10)])
        res = r15.kit_update(kit_dir,
                             fetcher=lambda url: catalog)
        self.assertFalse(res["updated"])
        self.assertEqual(res["version"], "0.2.0")

    def test_update_failure_restores_backup(self):
        kit_dir = os.path.join(self.tmp, "skills")
        os.makedirs(kit_dir)
        with open(os.path.join(kit_dir, "rough-cut.md"), "w",
                  encoding="utf-8") as fh:
            fh.write("old rough\n")
        r15.write_kit_manifest(kit_dir, {
            "source": "x", "version": "0.1.0", "license": "MIT",
            "installed": [{"id": "rough-cut", "sha256": "00" * 32}]})
        new_zip = _kit_zip_bytes(["rough-cut", "new-skill"])
        catalog = _kit_catalog([
            ("0.2.0", "https://example.invalid/new.zip",
             hashlib.sha256(new_zip).hexdigest(), len(new_zip)),
        ])

        def fake_fetch(url):
            return catalog if url == r15.KIT_RELEASES_URL else new_zip

        # Fail AFTER the swap's file writes (manifest write) so the
        # restore path must put the old file back and drop new files.
        with mock.patch.object(r15, "ed25519_verify", return_value=True), \
                mock.patch.object(r15, "write_kit_manifest",
                                  side_effect=RuntimeError("disk full")):
            with self.assertRaises(RuntimeError):
                r15.kit_update(kit_dir, fetcher=fake_fetch)
        with open(os.path.join(kit_dir, "rough-cut.md"),
                  encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "old rough\n")
        self.assertFalse(os.path.exists(os.path.join(kit_dir, "new-skill.md")))

    def test_later_and_status(self):
        kit_dir = os.path.join(self.tmp, "skills")
        res = r15.kit_later(kit_dir, days=7)
        self.assertTrue(res["later_until"].endswith("Z"))
        status = r15.kit_status(kit_dir)
        self.assertEqual(status["later_until"], res["later_until"])
        self.assertEqual(status["channel"], r15.KIT_RELEASES_URL)
        self.assertIsNone(status["newer"])
        # check_updates with a failing fetcher reports, never crashes.
        status = r15.kit_status(
            kit_dir, check_updates=True,
            fetcher=lambda url: (_ for _ in ()).throw(ValueError("offline")))
        self.assertIsNone(status["newer"])
        self.assertIn("offline", status["fetch_error"])

    def _write_zip(self, data):
        path = os.path.join(self.tmp, "kit.zip")
        with open(path, "wb") as fh:
            fh.write(data)
        return path


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="vibeedit-r15-reg-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _sample(self):
        zip_bytes = _registry_zip_bytes("bashcut.antigravity", "0.0.4")
        sha = hashlib.sha256(zip_bytes).hexdigest()
        reg = _registry_bytes([
            ("bashcut.antigravity",
             [("0.0.4", "https://example.invalid/anti.zip", sha,
               len(zip_bytes), ["macos-arm64"])]),
            ("bashcut.director",
             [("0.0.3", "https://example.invalid/dir.zip", "aa" * 32, 10,
               ["macos-arm64"]),
              ("0.0.4", "https://example.invalid/dir2.zip", "bb" * 32, 20,
               ["macos-arm64"])]),
        ])
        return zip_bytes, sha, json.loads(reg.decode("utf-8"))

    def test_parse_and_search(self):
        _, _, reg = self._sample()
        parsed = r15.parse_registry(json.dumps(reg).encode("utf-8"))
        self.assertEqual(len(parsed["plugins"]), 2)
        found = r15.search_registry(parsed, "antigravity")
        self.assertEqual([x["id"] for x in found], ["bashcut.antigravity"])
        self.assertEqual(found[0]["name"], "bashcut.antigravity VI")
        self.assertEqual(found[0]["latest_version"], "0.0.4")
        self.assertEqual(len(r15.search_registry(parsed, "")), 2)
        self.assertEqual(r15.search_registry(parsed, "zzz-no-match"), [])
        with self.assertRaises(ValueError):
            r15.parse_registry(b'{"schemaVersion": 2}')

    def test_fetch_cache(self):
        calls = []
        reg_bytes = _registry_bytes([
            ("bashcut.x", [("0.0.1", "https://example.invalid/x.zip",
                            "cc" * 32, 10, [])])])
        cache = os.path.join(self.tmp, "plugin_registry_cache.json")

        def fake_fetch(url):
            calls.append(url)
            return reg_bytes

        reg, meta = r15.fetch_registry(fetcher=fake_fetch, cache_path=cache)
        self.assertFalse(meta["cached"])
        self.assertEqual(len(calls), 1)
        reg2, meta2 = r15.fetch_registry(fetcher=fake_fetch, cache_path=cache)
        self.assertTrue(meta2["cached"])
        self.assertEqual(len(calls), 1)
        r15.fetch_registry(fetcher=fake_fetch, cache_path=cache, force=True)
        self.assertEqual(len(calls), 2)
        # Corrupt cache is ignored and refetched, not fatal.
        with open(cache, "w", encoding="utf-8") as fh:
            fh.write("{broken")
        r15.fetch_registry(fetcher=fake_fetch, cache_path=cache)
        self.assertEqual(len(calls), 3)

    def test_registry_install_success_and_listing(self):
        zip_bytes, sha, reg = self._sample()
        parsed = r15.parse_registry(json.dumps(reg).encode("utf-8"))
        plugs = os.path.join(self.tmp, "plugins")

        def fake_download(url, dest):
            with open(dest, "wb") as fh:
                fh.write(zip_bytes)
            return {"path": dest}

        with mock.patch.object(r15, "ed25519_verify", return_value=True):
            res = r15.install_registry_plugin(
                parsed, "bashcut.antigravity", plugins_dir=plugs,
                downloader=fake_download)
        self.assertFalse(res["runnable"])
        self.assertFalse(res["enabled"])
        self.assertTrue(any("macOS" in w or "macos" in w.lower()
                            for w in res["warnings"]))
        self.assertIn("only non-Windows platforms",
                      " ".join(res["warnings"]))
        loaded = load_plugins(plugs)
        self.assertNotIn("bashcut.antigravity", loaded.get("_errors", {}))
        rec = loaded["bashcut.antigravity"]
        self.assertTrue(rec["registry"])
        self.assertFalse(rec["runnable"])
        self.assertEqual(rec["registry_version"], "0.0.4")
        # The macOS shell scripts were copied but never executed and
        # the record cannot be enabled.
        self.assertTrue(os.path.isfile(os.path.join(
            plugs, "bashcut.antigravity", "bin", "setup")))
        with self.assertRaises(ValueError):
            set_plugin_enabled("bashcut.antigravity", True, plugs)

    def test_registry_install_refusals(self):
        zip_bytes, sha, reg = self._sample()
        parsed = r15.parse_registry(json.dumps(reg).encode("utf-8"))
        plugs = os.path.join(self.tmp, "plugins")

        def fake_download(url, dest):
            with open(dest, "wb") as fh:
                fh.write(zip_bytes)
            return {"path": dest}

        # SHA mismatch: nothing installed.
        bad = json.loads(json.dumps(reg))
        bad["plugins"][0]["versions"][0]["sha256"] = "00" * 32
        bad_parsed = r15.parse_registry(json.dumps(bad).encode("utf-8"))
        with mock.patch.object(r15, "ed25519_verify", return_value=True):
            with self.assertRaises(ValueError):
                r15.install_registry_plugin(bad_parsed, "bashcut.antigravity",
                                            plugins_dir=plugs,
                                            downloader=fake_download)
        self.assertFalse(os.path.exists(
            os.path.join(plugs, "bashcut.antigravity")))
        # Bad signature: nothing installed.
        with mock.patch.object(r15, "ed25519_verify", return_value=False):
            with self.assertRaises(ValueError):
                r15.install_registry_plugin(parsed, "bashcut.antigravity",
                                            plugins_dir=plugs,
                                            downloader=fake_download)
        self.assertFalse(os.path.exists(
            os.path.join(plugs, "bashcut.antigravity")))
        # Manifest version mismatch: nothing installed.
        wrong_ver = _registry_zip_bytes("bashcut.antigravity", "9.9.9")

        def fake_download_wrong(url, dest):
            with open(dest, "wb") as fh:
                fh.write(wrong_ver)
            return {"path": dest}

        with mock.patch.object(r15, "ed25519_verify", return_value=True):
            with self.assertRaises(ValueError):
                r15.install_registry_plugin(parsed, "bashcut.antigravity",
                                            plugins_dir=plugs,
                                            downloader=fake_download_wrong)
        self.assertFalse(os.path.exists(
            os.path.join(plugs, "bashcut.antigravity")))

    def test_registry_install_overwrite_rules(self):
        zip_bytes, sha, reg = self._sample()
        parsed = r15.parse_registry(json.dumps(reg).encode("utf-8"))
        plugs = os.path.join(self.tmp, "plugins")

        def fake_download(url, dest):
            with open(dest, "wb") as fh:
                fh.write(zip_bytes)
            return {"path": dest}

        with mock.patch.object(r15, "ed25519_verify", return_value=True):
            r15.install_registry_plugin(parsed, "bashcut.antigravity",
                                        plugins_dir=plugs,
                                        downloader=fake_download)
            # Installed records are disabled, but overwrite still
            # needs the explicit flag.
            with self.assertRaises(ValueError):
                r15.install_registry_plugin(parsed, "bashcut.antigravity",
                                            plugins_dir=plugs,
                                            downloader=fake_download)
            res = r15.install_registry_plugin(
                parsed, "bashcut.antigravity", plugins_dir=plugs,
                downloader=fake_download, overwrite=True)
        self.assertEqual(res["version"], "0.0.4")

    def test_check_registry_updates(self):
        zip_bytes, sha, reg = self._sample()
        parsed = r15.parse_registry(json.dumps(reg).encode("utf-8"))
        plugs = os.path.join(self.tmp, "plugins")

        def fake_download(url, dest):
            with open(dest, "wb") as fh:
                fh.write(zip_bytes)
            return {"path": dest}

        with mock.patch.object(r15, "ed25519_verify", return_value=True):
            r15.install_registry_plugin(parsed, "bashcut.antigravity",
                                        plugins_dir=plugs,
                                        downloader=fake_download)
        up = r15.check_registry_updates("bashcut.antigravity", parsed,
                                        plugins_dir=plugs)
        self.assertEqual(up["status"], "up_to_date")
        # A newer registry version appears.
        reg2 = json.loads(json.dumps(reg))
        reg2["plugins"][0]["versions"].append({
            "version": "0.0.5", "url": "https://example.invalid/anti5.zip",
            "sha256": "dd" * 32, "signature": FAKE_SIG, "size": 30,
            "platforms": ["macos-arm64"]})
        parsed2 = r15.parse_registry(json.dumps(reg2).encode("utf-8"))
        up2 = r15.check_registry_updates("bashcut.antigravity", parsed2,
                                         plugins_dir=plugs)
        self.assertEqual(up2["status"], "update_available")
        self.assertEqual(up2["latest_version"], "0.0.5")
        self.assertEqual(r15.check_registry_updates(
            "bashcut.unknown", parsed2, plugins_dir=plugs)["status"],
            "not_in_registry")


class TestMCPHandlers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="vibeedit-r15-mcp-")
        self.srv = MCPServer()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_plugins_search_registry_and_all(self):
        zip_bytes = _registry_zip_bytes("bashcut.antigravity", "0.0.4")
        reg_bytes = _registry_bytes([
            ("bashcut.antigravity",
             [("0.0.4", "https://example.invalid/anti.zip",
               hashlib.sha256(zip_bytes).hexdigest(), len(zip_bytes),
               ["macos-arm64"])]),
        ])
        plugs = os.path.join(self.tmp, "plugins")
        with mock.patch.object(r15, "_http_get", return_value=reg_bytes):
            res = self.srv.call("vibeedit_plugins_search",
                                {"query": "antigravity", "source": "registry",
                                 "plugins_dir": plugs})
        self.assertEqual(res["registry_count"], 1)
        self.assertEqual(res["registry"][0]["id"], "bashcut.antigravity")
        self.assertIsNone(res["registry_error"])
        # Failing fetch with source=all: local results + explicit error.
        # A fresh parent dir (the cache lives next to plugins.json,
        # i.e. per parent dir, so a sibling plugins dir would still
        # hit the cache written by the successful call above).
        plugs_fresh = os.path.join(self.tmp, "other-root", "plugins")
        with mock.patch.object(r15, "_http_get",
                               side_effect=ValueError("offline")):
            res = self.srv.call("vibeedit_plugins_search",
                                {"query": "", "source": "all",
                                 "plugins_dir": plugs_fresh})
        self.assertIn("offline", res["registry_error"])
        # Failing fetch with source=registry: hard error, no fallback.
        with mock.patch.object(r15, "_http_get",
                               side_effect=ValueError("offline")):
            with self.assertRaises(ValueError):
                self.srv.call("vibeedit_plugins_search",
                              {"query": "", "source": "registry",
                               "plugins_dir": plugs_fresh})

    def test_plugins_install_registry_via_mcp(self):
        zip_bytes = _registry_zip_bytes("bashcut.antigravity", "0.0.4")
        reg_bytes = _registry_bytes([
            ("bashcut.antigravity",
             [("0.0.4", "https://example.invalid/anti.zip",
               hashlib.sha256(zip_bytes).hexdigest(), len(zip_bytes),
               ["macos-arm64"])]),
        ])
        plugs = os.path.join(self.tmp, "plugins")
        from vibeedit_core import plugins as _plugins
        with mock.patch.object(r15, "_http_get", return_value=reg_bytes), \
                mock.patch.object(r15, "ed25519_verify", return_value=True), \
                mock.patch.object(_plugins, "download_plugin_bundle") as dl:
            def _dl(url, dest, max_bytes=None, timeout=30):
                with open(dest, "wb") as fh:
                    fh.write(zip_bytes)
                return {"path": dest}
            dl.side_effect = _dl
            res = self.srv.call("vibeedit_plugins_install",
                                {"registry_plugin": "bashcut.antigravity",
                                 "plugins_dir": plugs})
        self.assertFalse(res["runnable"])
        self.assertTrue(os.path.isfile(os.path.join(
            plugs, "bashcut.antigravity", "vibeedit-registry.json")))
        upd = self.srv.call("vibeedit_plugins_updates",
                            {"plugin": "bashcut.antigravity",
                             "check_registry": True, "plugins_dir": plugs})
        self.assertEqual(upd["status"], "up_to_date")

    def test_kit_update_via_mcp(self):
        kit_dir = os.path.join(self.tmp, "skills")
        new_zip = _kit_zip_bytes(["rough-cut"])
        catalog = _kit_catalog([
            ("0.2.0", "https://example.invalid/new.zip",
             hashlib.sha256(new_zip).hexdigest(), len(new_zip)),
        ])

        def fake_get(url, **kw):
            return catalog if url == r15.KIT_RELEASES_URL else new_zip

        with mock.patch.object(r15, "_http_get", side_effect=fake_get), \
                mock.patch.object(r15, "ed25519_verify", return_value=True):
            res = self.srv.call("vibeedit_agent_kit_update",
                                {"kit_dir": kit_dir})
            later = self.srv.call("vibeedit_agent_kit_later",
                                  {"kit_dir": kit_dir, "days": 7})
            status = self.srv.call("vibeedit_agent_kit_check",
                                   {"kit_dir": kit_dir})
        self.assertTrue(res["updated"])
        self.assertEqual(res["version"], "0.2.0")
        self.assertTrue(later["later_until"].endswith("Z"))
        self.assertEqual(status["version"], "0.2.0")
        self.assertEqual(status["later_until"], later["later_until"])
        self.assertIn("rough-cut", status["skills"])


if __name__ == "__main__":
    unittest.main()
