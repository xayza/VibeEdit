"""Round 15: agent-kit signed releases + plugin registry (Browse/Updates).

Two features the original BashCut app has that the Windows port only
had in honest form:

1. Agent kit. The original ships the bashcut-agent-kit (editing
   skills: footage survey, beat cuts, audio mix, captions, colour,
   effects, voiceover, ...) and updates it through signed releases:
   ``releases.json`` on the kit repo lists each version with a
   download URL, size, SHA-256 digest and an Ed25519 signature over
   that digest, made with the BashCut publisher key. This module
   implements the same chain with stdlib only: fetch the catalog,
   download the archive, verify size + SHA-256 + signature, stage
   and validate every skill, then swap -- the old kit stays in place
   until the new one validates, and is restored on failure.

2. Plugin registry. The original browses and updates plugins from a
   static ``registry.json`` in the bashcut-plugins repo (download,
   SHA-256 check, staging, validation, approval before running).
   This module fetches that registry (cached, 24 h), searches it,
   installs verified releases from it, and compares installed
   versions against it.

Honest limits, stated here and in PARITY.md rather than hidden:

* The kit's ``minAppVersion`` gates BashCut releases, not this port;
  it is reported, not enforced.
* Registry plugins are macOS provider plugins: their manifests use
  dotted ids and ``{en, vi}`` name maps, and their bundles contain
  macOS shell scripts, not a Windows-runnable ``.py`` entry. They
  therefore CANNOT pass the port's strict manifest validation, and
  this module deliberately does NOT weaken that validation. A
  registry install is recorded as a review-only record (sidecar
  ``vibeedit-registry.json`` + disabled state): it is listed, never
  executed, and cannot be enabled until a Windows-runnable entry
  exists. The macOS-only platform list is always reported as a
  warning on registry installs.
* In headless MCP there is no UI approval dialog; the caller's
  explicit install command IS the approval for a registry install,
  exactly as the round-5 ``plugins_download`` gate documents for
  downloads. No code runs before validation either way.

No network call happens in tests: every fetcher is a module-level
function (``_http_get``) or an injectable callable, so tests pass a
fake and assert on real SHA-256 digests.
"""

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

# ---------------------------------------------------------------- feeds

KIT_REPO = "dongnguyenvie/bashcut-agent-kit"
KIT_RELEASES_URL = (
    "https://raw.githubusercontent.com/dongnguyenvie/bashcut-agent-kit"
    "/main/releases.json"
)
PLUGIN_REPO = "dongnguyenvie/bashcut-plugins"
REGISTRY_URL = (
    "https://raw.githubusercontent.com/dongnguyenvie/bashcut-plugins"
    "/main/registry.json"
)
REGISTRY_CACHE_TTL_S = 24 * 60 * 60  # one day, stated on every cache read
KIT_LICENSE_NAME = "MIT"

# Publisher Ed25519 public key, taken from the plugins registry
# (publishers.bashcut.keys, fetched 2026-10-27) and from the kit
# releases it signs. The same key signs both repos' releases; it is
# pinned here so a tampered feed cannot substitute its own key.
# Refresh the pin when the registry publishes a new publisher key.
PUBLISHER_KEYS = (
    "ed25519:q+RG+vvYLwP2xxRtVjNxPCbb3LhvuRyKNxSx3c1p6C4=",
)

KIT_MANIFEST_NAME = "KIT_MANIFEST.json"
KIT_STATE_NAME = "KIT_STATE.json"
REGISTRY_CACHE_NAME = "plugin_registry_cache.json"

_MAX_FEED_BYTES = 5 * 1024 * 1024
_MAX_KIT_ZIP_BYTES = 20 * 1024 * 1024
_MAX_KIT_SKILL_BYTES = 2 * 1024 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


# ---------------------------------------------------------------- Ed25519

# Pure-Python Ed25519 (RFC 8032), stdlib only. The port must verify
# publisher signatures without adding a dependency; the
# implementation is checked against the RFC 8032 test vector in
# tests/test_round15.py.
_B = 2 ** 255 - 19
_D = (-121665 * pow(121666, _B - 2, _B)) % _B
_I = pow(2, (_B - 1) // 4, _B)


def _edwards_add(P, Q):
    x1, y1 = P
    x2, y2 = Q
    denom = pow(1 + _D * x1 * x2 * y1 * y2, _B - 2, _B)
    x3 = (x1 * y2 + x2 * y1) * denom % _B
    denom2 = pow(1 - _D * x1 * x2 * y1 * y2, _B - 2, _B)
    y3 = (y1 * y2 + x1 * x2) * denom2 % _B
    return (x3, y3)


def _scalarmult(P, e):
    Q = (0, 1)
    while e:
        if e & 1:
            Q = _edwards_add(Q, P)
        P = _edwards_add(P, P)
        e >>= 1
    return Q


def _decode_point(data):
    y = int.from_bytes(data, "little") & ((1 << 255) - 1)
    sign = (data[31] >> 7) & 1
    x = _recover_x(y)
    if x is None:
        raise ValueError("điểm Ed25519 không hợp lệ")
    if (x & 1) != sign:
        x = _B - x
    return (x, y)


def _recover_x(y):
    xx = (y * y - 1) * pow(_D * y * y + 1, _B - 2, _B) % _B
    x = pow(xx, (_B + 3) // 8, _B)
    if (x * x - xx) % _B != 0:
        x = (x * _I) % _B
    if (x * x - xx) % _B != 0:
        return None
    if x & 1:
        x = _B - x
    return x


_BASE_X = 15112221349535400772501151409588531511454012693041857206046113283949847762202
_BASE_Y = 46316835694926478169428394003475163141307993866256225615783033603165251855960
_BASE_POINT = (_BASE_X, _BASE_Y)


def _sha512(data):
    return hashlib.sha512(data).digest()


def ed25519_verify(public_key_bytes, signature, message):
    """Verify an Ed25519 signature. Returns True/False, never raises
    for malformed input (a bad signature is a failed check, not a
    crash -- callers turn False into a refusal)."""
    try:
        if len(public_key_bytes) != 32 or len(signature) != 64:
            return False
        A = _decode_point(public_key_bytes)
        R = _decode_point(signature[:32])
        S = int.from_bytes(signature[32:], "little")
        if S >= (1 << 253):
            return False
        h = int.from_bytes(
            _sha512(signature[:32] + public_key_bytes + message), "little")
        return _scalarmult(_BASE_POINT, S) == _edwards_add(
            R, _scalarmult(A, h))
    except Exception:
        return False


def _decode_key(key_text):
    """Decode an ``ed25519:<base64>`` publisher key to 32 raw bytes."""
    import base64
    if not isinstance(key_text, str) or not key_text.startswith("ed25519:"):
        raise ValueError(f"không phải ed25519: khóa nhà phát hành: {key_text!r}")
    raw = base64.b64decode(key_text[len("ed25519:"):])
    if len(raw) != 32:
        raise ValueError("khóa nhà phát hành ed25519 không phải 32 byte")
    return raw


def _decode_signature(sig_text):
    import base64
    if not isinstance(sig_text, str) or not sig_text.startswith("ed25519:"):
        raise ValueError(f"không phải ed25519: chữ ký: {sig_text!r}")
    raw = base64.b64decode(sig_text[len("ed25519:"):])
    if len(raw) != 64:
        raise ValueError("chữ ký ed25519 không phải 64 byte")
    return raw


def verify_release_signature(sha256_hex, signature_text, keys=PUBLISHER_KEYS):
    """Verify a release signature over the SHA-256 *digest bytes*
    (not the hex string, not the raw archive bytes -- this is the
    convention the kit and plugin releases use, proven against the
    real kit 0.1.56 signature in tests/test_round15.py)."""
    if not _SHA256_RE.match(sha256_hex or ""):
        raise ValueError(f"digest release không phải hex SHA-256: {sha256_hex!r}")
    digest = bytes.fromhex(sha256_hex)
    sig = _decode_signature(signature_text)
    for key in keys:
        if ed25519_verify(_decode_key(key), sig, digest):
            return True
    return False


# ---------------------------------------------------------------- HTTP

def _http_get(url, timeout=30, max_bytes=_MAX_FEED_BYTES):
    """Fetch one https URL with stdlib urllib. Module-level seam so
    tests monkeypatch ``round15._http_get`` instead of the network."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise ValueError(f"URL feed phải là https: {url!r}")
    request = urllib.request.Request(
        url, headers={"User-Agent": "VibeEdit kit/registry fetcher"})
    try:
        response = urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.URLError as exc:
        raise ValueError(f"tải thất bại ({url}): {exc}") from exc
    with response:
        if response.status != 200:
            raise ValueError(f"tải thất bại ({url}): HTTP {response.status}")
        chunks = []
        total = 0
        while True:
            chunk = response.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"tải quá lớn (>{max_bytes} byte): {url}")
            chunks.append(chunk)
    return b"".join(chunks)


def _version_key(version):
    """Numeric version sort key: '0.1.56' > '0.1.9' (plain string
    sort would get this wrong). Non-numeric segments count as 0."""
    parts = []
    for piece in str(version).split("."):
        digits = ""
        for ch in piece:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def _is_https_url(value):
    if not isinstance(value, str):
        return False
    parsed = urllib.parse.urlparse(value.strip())
    return parsed.scheme.lower() == "https" and bool(parsed.netloc)


# ---------------------------------------------------------------- kit paths

def _default_kit_dir(kit_dir=None):
    if kit_dir:
        return os.path.abspath(kit_dir)
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), "skills")


def _kit_manifest_path(kit_dir):
    return os.path.join(_default_kit_dir(kit_dir), KIT_MANIFEST_NAME)


def _kit_state_path(kit_dir):
    return os.path.join(_default_kit_dir(kit_dir), KIT_STATE_NAME)


def read_kit_manifest(kit_dir=None):
    path = _kit_manifest_path(kit_dir)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def write_kit_manifest(kit_dir, manifest):
    folder = _default_kit_dir(kit_dir)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, KIT_MANIFEST_NAME)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)
    return path


def read_kit_state(kit_dir=None):
    path = _kit_state_path(kit_dir)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_kit_state(kit_dir, state):
    folder = _default_kit_dir(kit_dir)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, KIT_STATE_NAME)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)
    return path


# ---------------------------------------------------------------- kit releases

def parse_kit_releases(raw):
    """Validate a kit releases.json document. Strict: any malformed
    version entry fails the whole catalog (fail closed -- never
    install from a half-valid catalog)."""
    if isinstance(raw, (bytes, bytearray)):
        try:
            data = json.loads(bytes(raw).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError(f"kit releases.json không phải JSON hợp lệ: {exc}") from exc
    else:
        data = raw
    if not isinstance(data, dict):
        raise ValueError("kit releases.json: cấp cao nhất phải là object")
    if data.get("schemaVersion") != 1:
        raise ValueError(f"kit releases.json: schemaVersion không hỗ trợ (mong đợi 1, nhận được {data.get('schemaVersion')!r})")
    if data.get("kit") != "bashcut":
        raise ValueError(f"kit releases.json: kit không mong đợi {data.get('kit')!r} (mong đợi 'bashcut')")
    versions = data.get("versions")
    if not isinstance(versions, list) or not versions:
        raise ValueError("kit releases.json: 'versions' phải là danh sách không rỗng")
    out = []
    for entry in versions:
        if not isinstance(entry, dict):
            raise ValueError("kit releases.json: entry version phải là object")
        version = entry.get("version")
        url = entry.get("url")
        sha256 = entry.get("sha256")
        signature = entry.get("signature")
        size = entry.get("size")
        if not isinstance(version, str) or not version:
            raise ValueError("kit releases.json: entry version thiếu chuỗi version")
        if not _is_https_url(url):
            raise ValueError(f"kit releases.json: version {version!r} không có url https")
        if not isinstance(sha256, str) or not _SHA256_RE.match(sha256):
            raise ValueError(f"kit releases.json: version {version!r} không có digest sha256 hợp lệ")
        if not isinstance(signature, str) \
                or not signature.startswith("ed25519:"):
            raise ValueError(f"kit releases.json: version {version!r} không có chữ ký ed25519")
        if not isinstance(size, int) or size <= 0:
            raise ValueError(f"kit releases.json: version {version!r} không có kích thước dương")
        out.append({
            "version": version,
            "url": url,
            "sha256": sha256,
            "signature": signature,
            "size": size,
            "releasedAt": entry.get("releasedAt"),
            "minAppVersion": entry.get("minAppVersion"),
        })
    return {"schemaVersion": 1, "kit": "bashcut", "versions": out}


def fetch_kit_releases(fetcher=None):
    fetch = fetcher or _http_get
    return parse_kit_releases(fetch(KIT_RELEASES_URL))


def _latest_release(releases, version=None):
    versions = releases["versions"]
    if version is not None:
        for entry in versions:
            if entry["version"] == version:
                return entry
        raise ValueError(f"version kit không có trong catalog releases: {version!r}")
    return max(versions, key=lambda e: _version_key(e["version"]))


# ---------------------------------------------------------------- kit install

def _parse_skill_frontmatter(text, skill_id):
    """A kit SKILL.md must carry frontmatter ``name: <id>`` matching
    its directory, like the real kit files do. Anything else is a
    malformed skill, not a kit skill."""
    if not text.startswith("---"):
        raise ValueError(f"skill kit {skill_id!r}: thiếu frontmatter")
    end = text.find("\n---", 3)
    if end < 0:
        raise ValueError(f"skill kit {skill_id!r}: frontmatter chưa đóng")
    name = None
    for line in text[3:end].splitlines():
        if line.startswith("name:"):
            name = line.split(":", 1)[1].strip().strip("\"'")
    if name != skill_id:
        raise ValueError(f"skill kit {skill_id!r}: tên frontmatter {name!r} không khớp thư mục của nó")


def kit_zip_skills(zip_path):
    """Scan a kit zip WITHOUT extracting: returns [(skill_id, bytes)]
    for every ``skills/<id>/SKILL.md`` entry, verbatim. Refuses
    unsafe entry names, duplicate ids, oversized files, and skills
    whose frontmatter name does not match their directory. The zip
    may have one top-level folder (as the real releases do) or none.
    """
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"kit zip không phải .zip hợp lệ: {zip_path!r}") from exc
    from vibeedit_core.plugins import _check_zip_entry_name
    skills = {}
    with zf:
        for info in zf.infolist():
            if info.filename.endswith("/"):
                continue
            _check_zip_entry_name(info.filename)
            parts = info.filename.split("/")
            # skills/<id>/SKILL.md, optionally under one top folder
            if len(parts) == 3 and parts[0] == "skills" \
                    and parts[2] == "SKILL.md":
                skill_id = parts[1]
            elif len(parts) == 4 and parts[1] == "skills" \
                    and parts[3] == "SKILL.md":
                skill_id = parts[2]
            else:
                continue
            if not _SAFE_ID_RE.match(skill_id):
                raise ValueError(f"kit zip: id skill không an toàn {skill_id!r}")
            if skill_id in skills:
                raise ValueError(f"kit zip: skill trùng lặp {skill_id!r}")
            if info.file_size > _MAX_KIT_SKILL_BYTES:
                raise ValueError(f"kit zip: skill {skill_id!r} quá lớn")
            raw = zf.read(info)
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(
                    f"skill kit {skill_id!r} không phải UTF-8") from exc
            _parse_skill_frontmatter(text, skill_id)
            skills[skill_id] = raw
    if not skills:
        raise ValueError("kit zip: không tìm thấy entry skills/*/SKILL.md nào")
    return sorted(skills.items())


def kit_install_from_zip(zip_path, kit_dir=None, managed_ids=None):
    """Copy kit skills from a staged zip into the kit folder,
    verbatim (no provenance header is added -- that would falsify
    'verbatim'; provenance lives in KIT_MANIFEST.json, and the
    skills.py docstring records this exception).

    ``managed_ids`` is the set of ids the previous kit owned: those
    files may be overwritten. Any other existing file is a user file
    and is refused, never overwritten. Returns
    {kitFolder, installed, refused} where refused entries carry a
    reason. Files are only written after ALL entries validate, so a
    bad zip leaves the folder untouched.
    """
    folder = _default_kit_dir(kit_dir)
    os.makedirs(folder, exist_ok=True)
    skills = kit_zip_skills(zip_path)
    managed = set(managed_ids or ())
    refused = []
    to_write = []
    for skill_id, raw in skills:
        target = os.path.join(folder, skill_id + ".md")
        if os.path.exists(target) and skill_id not in managed:
            refused.append({"id": skill_id,
                            "reason": "đã có file không phải kit trùng tên này; từ chối thay vì ghi đè nội dung của người dùng"})
            continue
        to_write.append((skill_id, raw, target))
    installed = []
    for skill_id, raw, target in to_write:
        tmp = target + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(raw)
        os.replace(tmp, target)
        installed.append({"id": skill_id,
                          "sha256": hashlib.sha256(raw).hexdigest()})
    return {"kitFolder": folder, "installed": installed, "refused": refused}


def kit_status(kit_dir=None, check_updates=False, fetcher=None):
    """Local kit status, optionally compared against the releases
    channel. A failed channel fetch is reported in ``fetch_error``,
    never silently replaced by 'no update'."""
    from vibeedit_core.skills import list_skills
    folder = _default_kit_dir(kit_dir)
    manifest = read_kit_manifest(folder)
    state = read_kit_state(folder)
    try:
        skills = list_skills(folder)
        skill_ids = [s["id"] for s in skills]
    except Exception:
        skill_ids = sorted(f[:-3] for f in os.listdir(folder)
                           if f.endswith(".md")) if os.path.isdir(folder) else []
    result = {
        "kitFolder": folder,
        "skills": skill_ids,
        "count": len(skill_ids),
        "version": manifest.get("version") if manifest else None,
        "source": manifest.get("source") if manifest else None,
        "license": manifest.get("license") if manifest else None,
        "channel": KIT_RELEASES_URL,
        "later_until": state.get("later_until"),
        "newer": None,
        "fetch_error": None,
    }
    if check_updates:
        try:
            releases = fetch_kit_releases(fetcher)
            latest = _latest_release(releases)
            installed = result["version"]
            if installed is None \
                    or _version_key(latest["version"]) > _version_key(installed):
                result["newer"] = {
                    "version": latest["version"],
                    "url": latest["url"],
                    "releasedAt": latest["releasedAt"],
                    "minAppVersion": latest["minAppVersion"],
                }
        except Exception as exc:
            result["fetch_error"] = str(exc)
    return result


def kit_update(kit_dir=None, version=None, fetcher=None, downloader=None):
    """Update the kit from the signed releases channel.

    Steps, in order, exactly like the original: fetch releases.json,
    pick the requested version (or the newest), download the archive,
    check size, then SHA-256, then the publisher Ed25519 signature
    over the digest, stage the zip, validate every skill, back up the
    old kit-managed files, swap, delete stale managed files, write
    the new manifest. Any failure before the swap leaves the old kit
    untouched; a failure during the swap restores the backup. The
    caller gets the full result, including refused user-file
    collisions and the informational minAppVersion note.
    """
    folder = _default_kit_dir(kit_dir)
    manifest = read_kit_manifest(folder)
    installed_version = manifest.get("version") if manifest else None
    old_ids = [s["id"] for s in manifest.get("installed", [])] \
        if manifest and isinstance(manifest.get("installed"), list) else []
    releases = fetch_kit_releases(fetcher)
    target = _latest_release(releases, version)
    if installed_version is not None and version is None \
            and _version_key(installed_version) >= _version_key(target["version"]):
        return {"updated": False,
                "version": installed_version,
                "latest": target["version"],
                "reason": "đã cập nhật mới nhất"}
    fetch = fetcher or _http_get
    archive = fetch(target["url"], max_bytes=_MAX_KIT_ZIP_BYTES) \
        if fetcher is None and downloader is None \
        else (downloader(target["url"]) if downloader is not None
              else fetch(target["url"]))
    if not isinstance(archive, (bytes, bytearray)):
        raise ValueError("tải kit không trả về byte")
    archive = bytes(archive)
    if len(archive) != target["size"]:
        raise ValueError(f"kit {target['version']}: lệch kích thước (registry ghi {target['size']}, nhận được {len(archive)})")
    digest = hashlib.sha256(archive).hexdigest()
    if digest != target["sha256"]:
        raise ValueError(f"kit {target['version']}: lệch SHA-256 (archive không khớp catalog releases)")
    if not verify_release_signature(digest, target["signature"]):
        raise ValueError(f"kit {target['version']}: xác minh chữ ký nhà phát hành thất bại; từ chối cài đặt")
    # Back up old kit-managed files before touching anything.
    backup = tempfile.mkdtemp(prefix="vibeedit-kit-backup-")
    backed_up = []
    stage_path = None
    new_skill_ids = []
    try:
        for skill_id in old_ids:
            src = os.path.join(folder, skill_id + ".md")
            if os.path.isfile(src):
                shutil.copyfile(src, os.path.join(backup, skill_id + ".md"))
                backed_up.append(skill_id)
        stage = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        stage.write(archive)
        stage.close()
        stage_path = stage.name
        new_skill_ids = [sid for sid, _ in kit_zip_skills(stage_path)]
        result = kit_install_from_zip(stage_path, folder,
                                      managed_ids=set(old_ids))
        # Delete stale kit-managed files not present in the new kit.
        new_ids = {s["id"] for s in result["installed"]}
        for skill_id in old_ids:
            if skill_id not in new_ids:
                victim = os.path.join(folder, skill_id + ".md")
                if os.path.isfile(victim):
                    os.unlink(victim)
        write_kit_manifest(folder, {
            "source": "https://github.com/" + KIT_REPO,
            "version": target["version"],
            "license": KIT_LICENSE_NAME,
            "installed": result["installed"],
            "previous_version": installed_version,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
    except Exception:
        # Restore: put back backed-up files, remove new-only files
        # that a failed swap may already have written.
        for skill_id in backed_up:
            shutil.copyfile(os.path.join(backup, skill_id + ".md"),
                            os.path.join(folder, skill_id + ".md"))
        for skill_id in new_skill_ids:
            if skill_id not in old_ids:
                victim = os.path.join(folder, skill_id + ".md")
                if os.path.isfile(victim):
                    os.unlink(victim)
        raise
    finally:
        if stage_path is not None:
            try:
                os.unlink(stage_path)
            except OSError:
                pass
        shutil.rmtree(backup, ignore_errors=True)
    return {"updated": True,
            "version": target["version"],
            "previous_version": installed_version,
            "installed": result["installed"],
            "refused": result["refused"],
            "minAppVersion": target["minAppVersion"],
            "minAppVersionNote": "minAppVersion gates BashCut releases; "
                                 "the Windows port reports it but does "
                                 "not enforce it."}


def kit_later(kit_dir=None, days=7):
    """Record a deferral of the kit update offer (7 days by default,
    the same pattern as the round-5 app-update deferral). There is
    no UI prompt in this headless server, so the record itself IS
    the deferral behaviour; kit_check reports it."""
    folder = _default_kit_dir(kit_dir)
    later_until = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + days * 86400))
    state = read_kit_state(folder)
    state["later_until"] = later_until
    state["later_days"] = days
    _write_kit_state(folder, state)
    return {"kitFolder": folder, "later_until": later_until, "days": days}


# ---------------------------------------------------------------- registry

def registry_cache_path(plugins_dir=None):
    if plugins_dir:
        folder = os.path.abspath(plugins_dir)
    else:
        from vibeedit_core.plugins import PLUGINS_DIR
        folder = os.path.abspath(PLUGINS_DIR)
    return os.path.join(os.path.dirname(folder), REGISTRY_CACHE_NAME)


def parse_registry(raw):
    """Validate a plugins registry.json document. Strict on
    structure and on the fields an install needs (id, versions with
    https url + SHA-256); a signature is required at install time,
    not at parse time, so a catalog entry without one can still be
    browsed but never installed."""
    if isinstance(raw, (bytes, bytearray)):
        try:
            data = json.loads(bytes(raw).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError(f"registry.json không phải JSON hợp lệ: {exc}") from exc
    else:
        data = raw
    if not isinstance(data, dict):
        raise ValueError("registry.json: cấp cao nhất phải là object")
    if data.get("schemaVersion") != 1:
        raise ValueError(f"registry.json: schemaVersion không hỗ trợ (mong đợi 1, nhận được {data.get('schemaVersion')!r})")
    publishers = data.get("publishers")
    if not isinstance(publishers, dict) or not publishers:
        raise ValueError("registry.json: 'publishers' phải là object không rỗng")
    for pub_id, pub in publishers.items():
        if not isinstance(pub, dict) \
                or not isinstance(pub.get("keys"), list) \
                or not pub["keys"]:
            raise ValueError(f"registry.json: nhà phát hành {pub_id!r} không có khóa")
        for key in pub["keys"]:
            if not isinstance(key, str) or not key.startswith("ed25519:"):
                raise ValueError(f"registry.json: nhà phát hành {pub_id!r} có khóa không phải ed25519")
    plugins = data.get("plugins")
    if not isinstance(plugins, list):
        raise ValueError("registry.json: 'plugins' phải là danh sách")
    out = []
    for entry in plugins:
        if not isinstance(entry, dict) or not entry.get("id"):
            raise ValueError("registry.json: entry plugin thiếu id")
        versions = entry.get("versions")
        if not isinstance(versions, list) or not versions:
            raise ValueError(f"registry.json: plugin {entry['id']!r} không có version nào")
        clean_versions = []
        for ver in versions:
            if not isinstance(ver, dict) or not ver.get("version"):
                raise ValueError(f"registry.json: plugin {entry['id']!r} có entry version thiếu version")
            if not _is_https_url(ver.get("url")):
                raise ValueError(f"registry.json: plugin {entry['id']!r} version {ver['version']!r} không có url https")
            if not isinstance(ver.get("sha256"), str) \
                    or not _SHA256_RE.match(ver["sha256"]):
                raise ValueError(f"registry.json: plugin {entry['id']!r} version {ver['version']!r} không có digest sha256 hợp lệ")
            clean_versions.append({
                "version": ver["version"],
                "url": ver["url"],
                "sha256": ver["sha256"],
                "signature": ver.get("signature"),
                "size": ver.get("size"),
                "platforms": ver.get("platforms") or [],
                "releasedAt": ver.get("releasedAt"),
            })
        out.append({
            "id": entry["id"],
            "name": entry.get("name"),
            "summary": entry.get("summary"),
            "category": entry.get("category"),
            "publisher": entry.get("publisher"),
            "homepage": entry.get("homepage"),
            "capabilities": entry.get("capabilities") or [],
            "versions": clean_versions,
        })
    return {"schemaVersion": 1, "publishers": publishers, "plugins": out}


def fetch_registry(fetcher=None, cache_path=None, max_age_s=REGISTRY_CACHE_TTL_S,
                   force=False):
    """Fetch the plugin registry, using the cache when it is fresh.
    Returns (registry, meta) with meta.cached / fetched_at / url.
    A corrupt cache is ignored and refetched; a failed fetch raises
    (never silently falls back to stale data for a browse, and never
    to local plugins)."""
    path = cache_path or registry_cache_path()
    if not force and os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                cached = json.load(fh)
            age = time.time() - float(cached["fetched_at"])
            if age < max_age_s:
                return parse_registry(cached["registry"]), {
                    "cached": True, "fetched_at": cached["fetched_at"],
                    "url": REGISTRY_URL}
        except Exception:
            pass  # corrupt or stale cache: fall through to a fresh fetch
    fetch = fetcher or _http_get
    registry = parse_registry(fetch(REGISTRY_URL))
    fetched_at = time.time()
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"fetched_at": fetched_at, "url": REGISTRY_URL,
                       "registry": registry}, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except OSError:
        pass  # cache is a convenience; a failed cache write is not fatal
    return registry, {"cached": False, "fetched_at": fetched_at,
                      "url": REGISTRY_URL}


def resolve_localized(value):
    """Resolve a registry string-or-map (``{en, vi}``) to one string,
    preferring Vietnamese, then English, then any string value."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for lang in ("vi", "en"):
            if isinstance(value.get(lang), str) and value[lang]:
                return value[lang]
        for item in value.values():
            if isinstance(item, str) and item:
                return item
    return ""


def search_registry(registry, query=None):
    """Pure search over a parsed registry: id, name, summary and
    category, case-insensitive substring. No network."""
    needle = (query or "").strip().lower()
    results = []
    for entry in registry["plugins"]:
        latest = registry_latest(entry)
        row = {
            "id": entry["id"],
            "name": resolve_localized(entry.get("name")),
            "summary": resolve_localized(entry.get("summary")),
            "category": entry.get("category"),
            "publisher": entry.get("publisher"),
            "homepage": entry.get("homepage"),
            "capabilities": entry.get("capabilities"),
            "latest_version": latest["version"],
            "versions": [v["version"] for v in entry["versions"]],
            "platforms": latest["platforms"],
        }
        if not needle:
            results.append(row)
        else:
            hay = " ".join(str(v) for v in
                           (row["id"], row["name"], row["summary"],
                            row["category"])).lower()
            if needle in hay:
                results.append(row)
    return results


def registry_plugin(registry, plugin_id):
    for entry in registry["plugins"]:
        if entry["id"] == plugin_id:
            return entry
    raise ValueError(f"plugin không có trong registry: {plugin_id!r}")


def registry_latest(entry, version=None):
    if version is not None:
        for ver in entry["versions"]:
            if ver["version"] == version:
                return ver
        raise ValueError(f"plugin {entry['id']!r}: version {version!r} không có trong registry")
    return max(entry["versions"], key=lambda v: _version_key(v["version"]))


def _installed_registry_record(plugins_dir, plugin_id):
    """Sidecar written by install_registry_plugin, or None."""
    from vibeedit_core.plugins import _plugins_folder
    sidecar = os.path.join(_plugins_folder(plugins_dir), plugin_id,
                           "vibeedit-registry.json")
    if not os.path.isfile(sidecar):
        return None
    try:
        with open(sidecar, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def check_registry_updates(plugin_id, registry, plugins_dir=None):
    """Compare an installed plugin's version against the registry
    latest. Installed version comes from the registry sidecar for
    registry installs, else from the local manifest's ``version``.
    A plugin absent from the registry reports that explicitly."""
    try:
        entry = registry_plugin(registry, plugin_id)
    except ValueError:
        return {"id": plugin_id, "status": "not_in_registry",
                "installed_version": None, "latest_version": None}
    latest = registry_latest(entry)
    installed = None
    sidecar = _installed_registry_record(plugins_dir, plugin_id)
    if sidecar is not None:
        installed = sidecar.get("registry_version")
    if installed is None:
        from vibeedit_core.plugins import load_plugins
        loaded = load_plugins(plugins_dir)
        info = loaded.get("plugins", {}).get(plugin_id)
        if info is not None:
            installed = info.get("version")
    if installed is None:
        return {"id": plugin_id, "status": "unknown_installed_version",
                "installed_version": None,
                "latest_version": latest["version"],
                "url": latest["url"], "sha256": latest["sha256"]}
    if _version_key(installed) < _version_key(latest["version"]):
        status = "update_available"
    else:
        status = "up_to_date"
    return {"id": plugin_id, "status": status,
            "installed_version": installed,
            "latest_version": latest["version"],
            "url": latest["url"], "sha256": latest["sha256"]}


def _scan_registry_zip(zip_path):
    """Scan a registry plugin zip WITHOUT extracting and WITHOUT
    the strict manifest validation (registry manifests use dotted
    ids and {en, vi} name maps, which that validation rejects by
    design). Returns (manifest, [(rel, ZipInfo), ...]) with the same
    safety rules as the strict scan: no absolute/traversal/symlink
    entries, exactly one top-level folder (or root), no duplicates,
    no files outside the plugin folder. The manifest itself is
    validated leniently by the caller."""
    from vibeedit_core.plugins import _check_zip_entry_name
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"registry zip không phải .zip hợp lệ: {zip_path!r}") from exc
    with zf:
        infos = zf.infolist()
        for info in infos:
            _check_zip_entry_name(info.filename)
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f"registry zip: đã từ chối entry symlink: {info.filename!r}")
        files = [i for i in infos if not i.filename.endswith("/")]
        manifest_names = []
        for info in files:
            parts = info.filename.split("/")
            if len(parts) == 1 and parts[0] == "plugin.json":
                manifest_names.append((info, ""))
            elif len(parts) == 2 and parts[1] == "plugin.json":
                manifest_names.append((info, parts[0] + "/"))
        if not manifest_names:
            raise ValueError("registry zip: không có plugin.json ở gốc hay trong đúng một thư mục cấp cao nhất")
        roots = {root for _, root in manifest_names}
        if len(roots) != 1:
            raise ValueError("registry zip: tìm thấy plugin.json trong nhiều thư mục cấp cao nhất")
        manifest_info, root = manifest_names[0]
        try:
            raw = zf.read(manifest_info)
        except (KeyError, RuntimeError) as exc:
            raise ValueError(f"registry zip: không đọc được plugin.json: {exc}") from exc
        try:
            manifest = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError(f"registry zip: plugin.json không phải JSON hợp lệ: {exc}") from exc
        if not isinstance(manifest, dict):
            raise ValueError("registry zip: plugin.json phải là object")
        entries = []
        seen = set()
        total = 0
        for info in files:
            if not info.filename.startswith(root):
                raise ValueError(f"registry zip: file nằm ngoài thư mục plugin: {info.filename!r}")
            rel = info.filename[len(root):]
            if not rel:
                continue
            if rel.lower() in seen:
                raise ValueError(f"registry zip: entry trùng lặp cho {rel!r}")
            seen.add(rel.lower())
            total += info.file_size
            if total > 50 * 1024 * 1024:
                raise ValueError("registry zip: gói vượt quá 50 MiB")
            entries.append((rel, info))
    return manifest, entries


def install_registry_plugin(registry, plugin_id, version=None,
                            plugins_dir=None, downloader=None,
                            overwrite=False):
    """Install a verified registry release.

    Order: resolve version -> download -> size check -> SHA-256
    check -> publisher signature check -> staging scan -> manifest
    check (id and version must match the registry entry) -> swap
    (old folder kept as backup until the new one validates) ->
    sidecar + disabled state. No code runs at any step; the record
    is listed by load_plugins but is not runnable and cannot be
    enabled (see the module docstring). The caller's explicit
    install command is the approval in headless MCP. An existing
    folder is refused unless overwrite is true AND the existing
    record is disabled, mirroring install_plugin.
    """
    from vibeedit_core.plugins import (
        _copy_validated_zip, _dest_for, _disabled_ids, _plugins_folder,
        _set_disabled, download_plugin_bundle)
    entry = registry_plugin(registry, plugin_id)
    ver = registry_latest(entry, version)
    warnings = []
    platforms = ver["platforms"] or []
    if platforms and not any("windows" in str(p).lower() for p in platforms):
        warnings.append(
            f"registry lists only non-Windows platforms for this release ({', '.join(platforms)}); the record is installed for review only and cannot run on Windows")
    elif not platforms:
        warnings.append("registry không liệt kê platform nào cho release này; bản ghi chỉ được cài để xem lại")
    publisher = entry.get("publisher")
    publishers = registry.get("publishers", {})
    pub_keys = publishers.get(publisher, {}).get("keys") if publisher else None
    if not pub_keys:
        raise ValueError(f"plugin registry {plugin_id!r}: nhà phát hành {publisher!r} không có khóa trong registry; từ chối cài khi chưa ký")
    if not ver.get("signature"):
        raise ValueError(f"plugin registry {plugin_id!r} version {ver['version']!r}: không có chữ ký nhà phát hành trong registry; từ chối cài đặt")
    folder = _plugins_folder(plugins_dir)
    os.makedirs(folder, exist_ok=True)
    dest = _dest_for(plugin_id, plugins_dir)
    if os.path.exists(dest) and not (
            overwrite and plugin_id in _disabled_ids(plugins_dir)):
        raise ValueError(f"plugin {plugin_id!r} đã cài rồi; hãy tắt nó trước rồi truyền overwrite=true để thay thế")
    tmp_dir = tempfile.mkdtemp(prefix="vibeedit-regdl-")
    try:
        zip_path = os.path.join(tmp_dir, "bundle.zip")
        if downloader is not None:
            downloaded = downloader(ver["url"], zip_path)
            if isinstance(downloaded, (bytes, bytearray)):
                with open(zip_path, "wb") as fh:
                    fh.write(bytes(downloaded))
            elif isinstance(downloaded, dict) and downloaded.get("path"):
                zip_path = downloaded["path"]
        else:
            download_plugin_bundle(ver["url"], zip_path)
        with open(zip_path, "rb") as fh:
            archive = fh.read()
        if ver.get("size") is not None and len(archive) != ver["size"]:
            raise ValueError(f"plugin registry {plugin_id!r}: lệch kích thước (registry ghi {ver['size']}, nhận được {len(archive)})")
        digest = hashlib.sha256(archive).hexdigest()
        if digest != ver["sha256"]:
            raise ValueError(f"plugin registry {plugin_id!r}: lệch SHA-256 (archive không khớp registry)")
        if not verify_release_signature(digest, ver["signature"],
                                        keys=tuple(pub_keys)):
            raise ValueError(f"plugin registry {plugin_id!r}: xác minh chữ ký nhà phát hành thất bại; từ chối cài đặt")
        manifest, entries = _scan_registry_zip(zip_path)
        if manifest.get("id") != plugin_id:
            raise ValueError(f"id manifest registry zip {manifest.get('id')!r} không khớp plugin registry {plugin_id!r}")
        if manifest.get("version") != ver["version"]:
            raise ValueError(f"version manifest registry zip {manifest.get('version')!r} không khớp version registry {ver['version']!r}")
        name = resolve_localized(manifest.get("name"))
        if not name:
            raise ValueError("manifest registry zip không có tên dùng được")
        backup = None
        if os.path.exists(dest):
            backup = dest + ".bak"
            if os.path.exists(backup):
                shutil.rmtree(backup)
            os.rename(dest, backup)
        try:
            _copy_validated_zip(zip_path, dest, entries)
            sidecar = {
                "registry_id": plugin_id,
                "registry_version": ver["version"],
                "sha256": digest,
                "signature_verified": True,
                "publisher": publisher,
                "platforms": platforms,
                "capabilities": entry.get("capabilities") or [],
                "installed_from": ver["url"],
                "warnings": warnings,
                "runnable": False,
                "reason": "plugin provider registry: không có entry .py chạy được trên Windows; script provider macOS không chạy được trên Windows; bản ghi chỉ để xem lại",
            }
            with open(os.path.join(dest, "vibeedit-registry.json"), "w",
                      encoding="utf-8") as fh:
                json.dump(sidecar, fh, indent=2, sort_keys=True)
                fh.write("\n")
        except Exception:
            shutil.rmtree(dest, ignore_errors=True)
            if backup is not None:
                os.rename(backup, dest)
            raise
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)
        _set_disabled(plugin_id, True, plugins_dir)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return {"id": plugin_id, "version": ver["version"], "path": dest,
            "enabled": False, "runnable": False,
            "warnings": warnings,
            "reason": "đã cài ở trạng thái tắt dạng bản ghi registry chỉ để xem lại; nó được liệt kê nhưng không bao giờ chạy, và không bật được nếu thiếu entry chạy được trên Windows"}
