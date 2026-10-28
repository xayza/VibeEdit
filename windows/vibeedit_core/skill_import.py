"""Skill import, plan/preview and Claude Code sync (round 23).

Copy-only, never executes: imported ``.py``/``.js`` files are copied
as inert data (a skill's references may legitimately contain code
samples) and nothing is ever run, imported or fetched from the
network. Zip inputs are defended against zip-slip (``..``,
absolute paths and symlinks are skipped, never extracted) and
bounded (50 MiB / 2000 entries). Imported SKILL.md files are copied
verbatim: no provenance header is added, so an installed skill's
text is exactly the source's text.

``plan_import`` never writes anywhere (it reads zip entries
in-memory and folder files read-only); ``apply_import`` is the only
writer, and it never touches ``skills.json`` — a newly installed
skill is simply absent from the disabled list, which is the store's
default enabled state, not an auto-enable action.

Error messages are Vietnamese: these surface directly in the UI
and the MCP tools.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import zipfile

from .skills import _SAFE_ID, _parse_skill, _resolve_dir, list_skills

MAX_ZIP_BYTES = 50 * 1024 * 1024
MAX_ENTRIES = 2000
_TITLE_READ_BYTES = 64 * 1024
_SKIP_DIRS = {"__pycache__", ".git", "__MACOSX"}
_MANIFEST_NAME = "IMPORT_MANIFEST.json"


def _is_safe_component(name):
    return name not in ("", ".", "..")


def _split_entry(name):
    """Split a zip entry name on / or \\ (Windows separators)."""
    return [part for part in name.replace("\\", "/").split("/") if part]


def _entry_is_unsafe(name):
    """True for absolute paths, drive paths and .. escapes."""
    if name.startswith(("/", "\\")):
        return True
    if len(name) >= 2 and name[1] == ":" and name[0].isalpha():
        return True
    parts = _split_entry(name)
    return any(part == ".." for part in parts)


def _entry_is_symlink(info):
    mode = (info.external_attr >> 16) & 0o170000
    return stat.S_ISLNK(mode)


def _title_from_bytes(raw):
    try:
        text = raw[:_TITLE_READ_BYTES].decode("utf-8")
    except UnicodeDecodeError:
        return None
    title, _source = _parse_skill(text)
    return title


def _read_prefix(path):
    with open(path, "rb") as fh:
        return fh.read(_TITLE_READ_BYTES)


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def _walk_skill_files(root):
    """[(rel, size)] under a folder-form skill root, skip dirs out."""
    out = []
    for dirpath, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS)
        for name in sorted(names):
            full = os.path.join(dirpath, name)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            out.append((os.path.relpath(full, root), size))
    return out


def _candidate(*, skill_id, title, kind, files, root, zip_path,
               zip_prefix, main_rel, warnings):
    total = sum(size for _rel, size in files)
    return {
        "id": skill_id,
        "title": title or skill_id,
        "kind": kind,
        "files": [{"rel": rel, "size": size} for rel, size in files],
        "file_count": len(files),
        "total_bytes": total,
        "total_kb": round(total / 1024, 1),
        "root": root,
        "zip": zip_path,
        "zip_prefix": zip_prefix,
        "main_rel": main_rel,
        "warnings": list(warnings),
        "installable": True,
    }


def _mark_exists(candidates, skills_dir):
    try:
        existing = {entry["id"] for entry in list_skills(skills_dir)}
    except Exception:
        existing = set()
    for cand in candidates:
        cand["exists"] = cand["id"] in existing
    return candidates


def _public(candidates):
    out = []
    for cand in candidates:
        pub = {key: cand[key] for key in (
            "id", "title", "kind", "files", "file_count", "total_bytes",
            "total_kb", "exists", "warnings", "installable")}
        out.append(pub)
    return out


def _discover_file(path):
    """A single .md file is one flat skill (id = file stem)."""
    stem = os.path.splitext(os.path.basename(path))[0]
    warnings = []
    title = _title_from_bytes(_read_prefix(path))
    cand = _candidate(
        skill_id=stem, title=title, kind="flat",
        files=[(os.path.basename(path), os.path.getsize(path))],
        root=os.path.dirname(os.path.abspath(path)), zip_path=None,
        zip_prefix="", main_rel=os.path.basename(path),
        warnings=warnings)
    if not _SAFE_ID.match(stem):
        cand["installable"] = False
        cand["warnings"].append(
            "ID %r không hợp lệ (chỉ dùng chữ, số, - và _); "
            "không cài skill này" % (stem,))
    return [cand], []


def _discover_folder(path):
    """Folder layouts, in precedence order (see module docstring).

    1. ``<dir>/SKILL.md`` -> one folder-form skill.
    2. ``<dir>/skills/<id>/SKILL.md`` -> one per subdir (plugin).
    3. ``<dir>/*.md`` -> one flat skill per file.
    """
    path = os.path.abspath(path)
    warnings = []
    main = os.path.join(path, "SKILL.md")
    if os.path.isfile(main):
        stem = os.path.basename(path)
        title = _title_from_bytes(_read_prefix(main))
        cand = _candidate(
            skill_id=stem, title=title, kind="folder",
            files=_walk_skill_files(path), root=path, zip_path=None,
            zip_prefix="", main_rel="SKILL.md", warnings=[])
        if not _SAFE_ID.match(stem):
            cand["installable"] = False
            cand["warnings"].append(
                "ID %r không hợp lệ (chỉ dùng chữ, số, - và _); "
                "không cài skill này" % (stem,))
        return [cand], warnings
    skills_sub = os.path.join(path, "skills")
    if os.path.isdir(skills_sub):
        out = []
        for name in sorted(os.listdir(skills_sub)):
            sub = os.path.join(skills_sub, name)
            sub_main = os.path.join(sub, "SKILL.md")
            if not (os.path.isdir(sub) and os.path.isfile(sub_main)):
                continue
            title = _title_from_bytes(_read_prefix(sub_main))
            cand = _candidate(
                skill_id=name, title=title, kind="folder",
                files=_walk_skill_files(sub), root=sub, zip_path=None,
                zip_prefix="", main_rel="SKILL.md", warnings=[])
            if not _SAFE_ID.match(name):
                cand["installable"] = False
                cand["warnings"].append(
                    "ID %r không hợp lệ (chỉ dùng chữ, số, - và _); "
                    "không cài skill này" % (name,))
            out.append(cand)
        if out:
            return _dedupe(out), warnings
    flat = []
    for name in sorted(os.listdir(path)):
        full = os.path.join(path, name)
        if not (os.path.isfile(full) and name.endswith(".md")):
            continue
        stem = name[:-3]
        title = _title_from_bytes(_read_prefix(full))
        cand = _candidate(
            skill_id=stem, title=title, kind="flat",
            files=[(name, os.path.getsize(full))], root=path,
            zip_path=None, zip_prefix="", main_rel=name, warnings=[])
        if not _SAFE_ID.match(stem):
            cand["installable"] = False
            cand["warnings"].append(
                "ID %r không hợp lệ (chỉ dùng chữ, số, - và _); "
                "không cài skill này" % (stem,))
        flat.append(cand)
    if flat:
        return _dedupe(flat), warnings
    raise ValueError(
        "Không tìm thấy skill nào trong thư mục %r: cần 1 file .md, "
        "1 thư mục có SKILL.md, hoặc thư mục skills/ kiểu plugin "
        "Claude (skills/<id>/SKILL.md)" % (path,))


def _dedupe(candidates):
    seen = {}
    warnings = []
    for cand in candidates:
        if cand["id"] in seen:
            warnings.append(
                "Trùng ID %r: chỉ giữ bản đầu tiên, bỏ các bản sau"
                % (cand["id"],))
            continue
        seen[cand["id"]] = cand
    for cand in seen.values():
        cand["warnings"].extend(warnings)
    return list(seen.values())


def _discover_zip(path):
    """Zip layouts mirror the folder layouts (SKILL.md roots win;
    otherwise .md files at the root or under one common top dir).
    Nothing is extracted here: entries are read in-memory only.
    """
    size = os.path.getsize(path)
    if size > MAX_ZIP_BYTES:
        raise ValueError(
            "File zip quá lớn (%d MB, giới hạn 50 MB)" % (size // 1024 // 1024,))
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise ValueError("File %r không phải zip hợp lệ" % (path,)) from None
    with zf:
        infos = [info for info in zf.infolist()
                 if not info.is_dir()]
        if len(infos) > MAX_ENTRIES:
            raise ValueError(
                "File zip có quá nhiều entry (%d, giới hạn 2000)"
                % (len(infos),))
        total = sum(info.file_size for info in infos)
        if total > MAX_ZIP_BYTES:
            raise ValueError(
                "Dung lượng giải nén của zip quá lớn (%d MB, giới hạn "
                "50 MB)" % (total // 1024 // 1024,))
        skipped = []
        entries = []
        for info in infos:
            name = info.filename
            parts = _split_entry(name)
            if (not parts or any(part in _SKIP_DIRS for part in parts)
                    or _entry_is_unsafe(name)
                    or _entry_is_symlink(info)):
                skipped.append(name)
                continue
            entries.append((info, "/".join(parts)))
        skill_roots = {}
        for info, name in entries:
            if os.path.basename(name) != "SKILL.md":
                continue
            root = os.path.dirname(name)
            skill_roots.setdefault(root, []).append((info, name))
        if skill_roots:
            out = []
            for root in sorted(skill_roots):
                if root == "":
                    skill_id = os.path.splitext(
                        os.path.basename(path))[0]
                else:
                    skill_id = root.rsplit("/", 1)[-1]
                prefix = (root + "/") if root else ""
                files = []
                main_raw = None
                for info, name in entries:
                    if not name.startswith(prefix):
                        continue
                    rel = name[len(prefix):]
                    if not rel:
                        continue
                    files.append((rel, info.file_size))
                    if rel == "SKILL.md":
                        with zf.open(info) as fh:
                            main_raw = fh.read(_TITLE_READ_BYTES)
                files.sort()
                title = _title_from_bytes(main_raw) if main_raw else None
                cand = _candidate(
                    skill_id=skill_id, title=title, kind="folder",
                    files=files, root="", zip_path=os.path.abspath(path),
                    zip_prefix=prefix, main_rel="SKILL.md", warnings=[])
                if not _SAFE_ID.match(skill_id):
                    cand["installable"] = False
                    cand["warnings"].append(
                        "ID %r không hợp lệ (chỉ dùng chữ, số, - và _); "
                        "không cài skill này" % (skill_id,))
                out.append(cand)
            if skipped:
                warnings = ["Đã bỏ qua %d entry không an toàn trong zip "
                            "(.., đường dẫn tuyệt đối, symlink, .git, "
                            "__pycache__)" % (len(skipped),)]
            else:
                warnings = []
            return _dedupe(out), warnings
        tops = {name.split("/", 1)[0] if "/" in name else ""
                for _info, name in entries}
        flat = []
        for info, name in entries:
            if not name.endswith(".md"):
                continue
            parts = name.split("/")
            if len(parts) == 1:
                rel, prefix = name, ""
            elif len(parts) == 2 and len(tops) == 1:
                rel, prefix = parts[1], parts[0] + "/"
            else:
                continue
            stem = rel[:-3]
            with zf.open(info) as fh:
                raw = fh.read(_TITLE_READ_BYTES)
            cand = _candidate(
                skill_id=stem, title=_title_from_bytes(raw), kind="flat",
                files=[(rel, info.file_size)], root="",
                zip_path=os.path.abspath(path), zip_prefix=prefix,
                main_rel=rel, warnings=[])
            if not _SAFE_ID.match(stem):
                cand["installable"] = False
                cand["warnings"].append(
                    "ID %r không hợp lệ (chỉ dùng chữ, số, - và _); "
                    "không cài skill này" % (stem,))
            flat.append(cand)
        if flat:
            warnings = []
            if skipped:
                warnings.append(
                    "Đã bỏ qua %d entry không an toàn trong zip "
                    "(.., đường dẫn tuyệt đối, symlink, .git, "
                    "__pycache__)" % (len(skipped),))
            return _dedupe(flat), warnings
    raise ValueError(
        "Không tìm thấy skill nào trong zip %r: cần SKILL.md kiểu "
        "thư mục/plugin hoặc file .md ở gốc zip" % (path,))


def _discover(path):
    if not os.path.exists(path):
        raise FileNotFoundError(
            "Không tìm thấy đường dẫn nguồn: %r" % (path,))
    if os.path.isfile(path):
        if path.endswith(".zip"):
            return _discover_zip(path)
        if path.endswith(".md"):
            return _discover_file(path)
        raise ValueError(
            "Chỉ nhận file .md hoặc .zip, không nhận %r" % (path,))
    if os.path.isdir(path):
        return _discover_folder(path)
    raise ValueError("Đường dẫn nguồn không phải file hay thư mục: %r"
                     % (path,))


def plan_import(path, skills_dir=None):
    """Preview an import without writing anything.

    Returns {"source", "skills": [public candidates], "warnings"}.
    A candidate's "exists" flag means the id is already in the store;
    "installable" is False only for unsafe ids (reported, not fixed
    up silently) and duplicates (first copy wins).
    """
    candidates, warnings = _discover(path)
    _mark_exists(candidates, skills_dir)
    return {"source": os.path.abspath(path),
            "skills": _public(candidates),
            "warnings": warnings}


def _read_source_bytes(cand, rel):
    if cand["zip"]:
        with zipfile.ZipFile(cand["zip"]) as zf:
            with zf.open(cand["zip_prefix"] + rel) as fh:
                return fh.read()
    with open(os.path.join(cand["root"], rel), "rb") as fh:
        return fh.read()


def _stream_copy(cand, rel, dest):
    if cand["zip"]:
        with zipfile.ZipFile(cand["zip"]) as zf:
            with zf.open(cand["zip_prefix"] + rel) as src:
                with open(dest, "wb") as out:
                    shutil.copyfileobj(src, out, 1024 * 1024)
    else:
        shutil.copyfile(os.path.join(cand["root"], rel), dest)


def _manifest_path(skills_dir):
    return os.path.join(_resolve_dir(skills_dir), _MANIFEST_NAME)


def _load_manifest(skills_dir):
    try:
        with open(_manifest_path(skills_dir), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def apply_import(path, overwrite=False, only=None, skills_dir=None):
    """Install skills from ``path`` (see :func:`plan_import`).

    ``only`` limits the install to the listed ids (the UI preview's
    ticked rows). Existing skills are skipped unless ``overwrite``
    is true; unsafe ids are skipped with a warning, never renamed
    silently. Returns {"installed", "skipped", "warnings",
    "manifest"}; the manifest is updated only when at least one
    skill was installed.
    """
    candidates, warnings = _discover(path)
    _mark_exists(candidates, skills_dir)
    base = _resolve_dir(skills_dir)
    os.makedirs(base, exist_ok=True)
    only_set = set(only) if only is not None else None
    installed = []
    skipped = []
    for cand in candidates:
        skill_id = cand["id"]
        if only_set is not None and skill_id not in only_set:
            skipped.append({"id": skill_id,
                            "reason": "không được tick chọn"})
            continue
        if not cand["installable"]:
            skipped.append({"id": skill_id,
                            "reason": "; ".join(cand["warnings"])
                            or "ID không hợp lệ"})
            continue
        if cand["exists"] and not overwrite:
            skipped.append({"id": skill_id,
                            "reason": "đã có trong store (cần ghi đè)"})
            continue
        flat_target = os.path.join(base, skill_id + ".md")
        folder_target = os.path.join(base, skill_id)
        if cand["kind"] == "flat":
            if os.path.isdir(folder_target):
                shutil.rmtree(folder_target)
            tmp = flat_target + ".tmp"
            _stream_copy(cand, cand["main_rel"], tmp)
            os.replace(tmp, flat_target)
        else:
            if os.path.isfile(flat_target):
                os.remove(flat_target)
            if os.path.isdir(folder_target):
                shutil.rmtree(folder_target)
            for entry in cand["files"]:
                rel = entry["rel"]
                dest = os.path.join(folder_target, rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                _stream_copy(cand, rel, dest)
        installed.append(skill_id)
    manifest_path = None
    if installed:
        manifest = _load_manifest(skills_dir)
        entries = manifest.setdefault("skills", {})
        by_id = {cand["id"]: cand for cand in candidates}
        for skill_id in installed:
            cand = by_id[skill_id]
            main_raw = _read_source_bytes(cand, cand["main_rel"])
            entries[skill_id] = {
                "source": os.path.abspath(path),
                "sha256": _sha256_bytes(main_raw),
                "kind": cand["kind"],
                "files": [entry["rel"] for entry in cand["files"]],
            }
        manifest_path = _manifest_path(skills_dir)
        tmp = manifest_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2, sort_keys=True)
        os.replace(tmp, manifest_path)
    return {"installed": installed, "skipped": skipped,
            "warnings": warnings, "manifest": manifest_path}


def _default_claude_dir():
    """<repo>/.claude/skills from this file's checkout layout."""
    root = os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, ".claude", "skills")


def sync_claude(skills_dir=None, target_dir=None, overwrite=False):
    """Export skills to a Claude Code skills folder.

    Every skill becomes ``<target>/<id>/SKILL.md`` (a folder holding
    SKILL.md — Claude Code ignores bare ``.md`` files), plus the
    skill's ``references/`` tree when it has one. A destination
    SKILL.md whose content differs from the store's is treated as
    hand-edited and left alone unless ``overwrite`` is true; nothing
    already in the target is ever deleted. Returns {"target",
    "written", "skipped", "note"} with a /reload-skills reminder.
    """
    from .skills import get_skill
    target = os.path.abspath(target_dir) if target_dir \
        else _default_claude_dir()
    written = []
    skipped = []
    for entry in list_skills(skills_dir):
        skill_id = entry["id"]
        dest_dir = os.path.join(target, skill_id)
        dest_file = os.path.join(dest_dir, "SKILL.md")
        if entry["kind"] == "flat":
            content = get_skill(skills_dir, skill_id).encode("utf-8")
            refs = []
        else:
            base = _resolve_dir(skills_dir)
            with open(os.path.join(base, skill_id, "SKILL.md"),
                      "rb") as fh:
                content = fh.read()
            refs_dir = os.path.join(base, skill_id, "references")
            refs = []
            if os.path.isdir(refs_dir):
                for dirpath, dirs, names in os.walk(refs_dir):
                    dirs[:] = sorted(d for d in dirs
                                     if d not in _SKIP_DIRS)
                    for name in sorted(names):
                        full = os.path.join(dirpath, name)
                        refs.append((os.path.relpath(full, refs_dir),
                                     full))
        if os.path.isfile(dest_file):
            with open(dest_file, "rb") as fh:
                existing = fh.read()
            if existing == content:
                skipped.append({"id": skill_id,
                                "reason": "đã đồng bộ"})
                continue
            if not overwrite:
                skipped.append({"id": skill_id,
                                "reason": "file đích đã sửa tay "
                                          "(cần overwrite=true)"})
                continue
        os.makedirs(dest_dir, exist_ok=True)
        with open(dest_file, "wb") as fh:
            fh.write(content)
        for rel, full in refs:
            dest = os.path.join(dest_dir, "references", rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copyfile(full, dest)
        written.append(skill_id)
    return {
        "target": target,
        "written": written,
        "skipped": skipped,
        "note": "Chạy /reload-skills trong Claude Code để tải lại skill.",
    }
