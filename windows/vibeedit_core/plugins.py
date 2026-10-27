"""Phase 3 plugin hook for the Windows port — a small, real hook,
not a port of the original macOS plugin system.

A plugin is a Python module in ``windows/plugins/`` exposing
``register()`` returning a dict with at least ``name`` and one
hook. Hooks available in Phase 3:

- ``transform_text(project, item_id)`` — may edit a text item's
  ``text`` field in place and must return the item dict.
- ``apply_color(project, item_id)`` — may set a clip's ``color``
  dict (via Project.set_color) and must return the item dict.

``load_plugins()`` imports every ``*.py`` module in the plugins
folder (skipping ``__init__.py`` and files starting with ``_``).
``apply_plugin()`` runs one hook on one item and returns the item.
Plugins run in-process with the project's data; they cannot delete
items or touch files outside the project folder by this interface
(they receive only the Project object and an item id).

The bundled example plugins (in windows/plugins/):
- ``uppercase_text`` — uppercases a text item's text.
- ``vivid_color`` — sets the clip's colour preset to vivid.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import sys
import zipfile

def _plugins_dir() -> str:
    """plugins/ folder: bundled data under _MEIPASS (or next to the
    executable) for a frozen app, file-relative in a source checkout
    — same frozen-app reasoning as server._static_dir()."""
    if getattr(sys, "frozen", False):
        for base in (getattr(sys, "_MEIPASS", None),
                     os.path.dirname(os.path.abspath(sys.executable))):
            if base:
                candidate = os.path.join(base, "plugins")
                if os.path.isdir(candidate):
                    return candidate
        return os.path.join(getattr(sys, "_MEIPASS",
                                    os.path.dirname(
                                        os.path.abspath(sys.executable))),
                            "plugins")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "plugins")


PLUGINS_DIR = _plugins_dir()


def load_plugins(plugins_dir: str | None = None) -> dict[str, dict]:
    """Load all plugin modules from ``plugins_dir``. Broken modules
    are reported in the returned dict under ``_errors`` instead of
    crashing the host."""
    folder = plugins_dir or PLUGINS_DIR
    plugins: dict[str, dict] = {}
    errors: dict[str, str] = {}
    if not os.path.isdir(folder):
        return {"_errors": errors}
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".py") or name.startswith("_"):
            continue
        mod_name = f"vibeedit_plugin_{name[:-3]}"
        path = os.path.join(folder, name)
        try:
            spec = importlib.util.spec_from_file_location(mod_name, path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot load plugin module: {path}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)
            info = module.register()
            if not isinstance(info, dict) or "name" not in info:
                raise ValueError("register() must return a dict with 'name'")
            plugins[str(info["name"])] = info
        except Exception as exc:  # noqa: BLE001 - one bad plugin
            errors[name] = str(exc)
    # Manifest plugins (Phase B3 installs): a subfolder containing a
    # plugin.json. These are listed and enable/disable-able, but their
    # code is NOT imported here: manifest code execution is remaining
    # work, so apply_plugin reports that clearly instead of running
    # anything. Keyed by manifest id (the folder name), which is what
    # install_plugin records in the disabled list.
    import json as _json
    for name in sorted(os.listdir(folder)):
        if name.startswith("_") or name.startswith("."):
            continue
        sub = os.path.join(folder, name)
        if not os.path.isdir(sub):
            continue
        manifest_path = os.path.join(sub, "plugin.json")
        if not os.path.isfile(manifest_path):
            continue
        try:
            with open(manifest_path, encoding="utf-8") as fh:
                manifest = _json.load(fh)
            if not isinstance(manifest, dict):
                raise ValueError("plugin.json must be an object")
            pid = manifest.get("id") or name
            if not isinstance(pid, str) or not SAFE_ID_RE.match(pid):
                raise ValueError(f"unsafe manifest id: {pid!r}")
            hooks = manifest.get("hooks")
            if hooks is None:
                hooks = []
            if not isinstance(hooks, list) or \
                    not all(isinstance(h, str) for h in hooks):
                raise ValueError("manifest hooks must be a list of strings")
            plugins[pid] = {
                "name": pid,
                "display_name": manifest.get("name", pid),
                "description": manifest.get("description", ""),
                "manifest": True,
                "manifest_hooks": sorted(hooks),
                "path": sub,
            }
        except Exception as exc:  # noqa: BLE001 - one bad plugin
            errors[name] = str(exc)
    plugins["_errors"] = errors
    return plugins


def _state_path(plugins_dir: str | None = None) -> str:
    """plugins.json next to the plugins/ folder (windows/plugins.json
    in a source checkout). Stores enable/disable state only — never
    plugin code or project data."""
    folder = plugins_dir or PLUGINS_DIR
    return os.path.join(os.path.dirname(os.path.abspath(folder)),
                        "plugins.json")


def load_plugin_state(plugins_dir: str | None = None) -> dict:
    try:
        import json as _json
        with open(_state_path(plugins_dir), encoding="utf-8") as fh:
            data = _json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def set_plugin_enabled(name: str, enabled: bool,
                       plugins_dir: str | None = None) -> dict:
    """Enable/disable a plugin by name. The name must be a discovered
    plugin (unknown names error, never silently create an entry)."""
    plugins = load_plugins(plugins_dir)
    if name not in plugins:
        raise KeyError(f"Unknown plugin: {name!r}")
    import json as _json
    state = load_plugin_state(plugins_dir)
    disabled = set(state.get("disabled", []))
    if enabled:
        disabled.discard(name)
    else:
        disabled.add(name)
    state["disabled"] = sorted(disabled)
    path = _state_path(plugins_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        _json.dump(state, fh, indent=2, sort_keys=True)
    return {"plugin": name, "enabled": enabled}


def list_plugins(plugins_dir: str | None = None) -> list[dict]:
    """Discovered plugins with enable state. Disabled plugins are
    listed but never run (apply_plugin refuses them). Re-scanning
    the folder is the reload: load_plugins() imports fresh each call."""
    plugins = load_plugins(plugins_dir)
    disabled = set(load_plugin_state(plugins_dir).get("disabled", []))
    out = []
    for name, info in sorted(plugins.items()):
        if name.startswith("_"):
            continue
        hooks = sorted(k for k, v in info.items() if callable(v))
        if info.get("manifest"):
            # Declared hooks of a manifest plugin (its code is not
            # imported, so there are no callables to derive from).
            hooks = list(info.get("manifest_hooks", []))
        out.append({"name": name, "description": info.get("description", ""),
                    "hooks": hooks, "enabled": name not in disabled,
                    "manifest": bool(info.get("manifest"))})
    errors = plugins.get("_errors", {})
    if errors:
        out.append({"name": "_errors", "description": "",
                    "hooks": [], "enabled": False, "errors": errors})
    return out


def apply_plugin(project, plugin_name: str, hook: str,
                 item_id: str, plugins_dir: str | None = None) -> dict:
    """Run one plugin hook on one item. Returns the updated item."""
    plugins = load_plugins(plugins_dir)
    if plugin_name not in plugins:
        raise KeyError(
            f"Unknown plugin: {plugin_name!r} "
            f"(available: {', '.join(sorted(k for k in plugins if not k.startswith('_')))})")
    if plugin_name in set(load_plugin_state(plugins_dir).get("disabled", [])):
        raise ValueError(f"Plugin {plugin_name!r} is disabled; enable it first")
    info = plugins[plugin_name]
    if info.get("manifest"):
        # Manifest plugins are listed/enabled, but their code is not
        # executed in this build (remaining work); never pretend a
        # hook ran.
        raise ValueError(
            f"Plugin {plugin_name!r} is a manifest plugin: its hooks "
            f"({', '.join(info.get('manifest_hooks', [])) or 'none'}) are "
            f"declared but not executable in this build; executing "
            f"manifest plugin code is remaining work")
    fn = info.get(hook)
    if not callable(fn):
        raise ValueError(
            f"Plugin {plugin_name!r} has no hook {hook!r}")
    _, item = project.item(item_id)
    result = fn(project, item_id)
    return result if isinstance(result, dict) else item


# ---------------------------------------------------------------------------
# Phase B3: install / remove / update-check for manifest plugins.
#
# A manifest plugin is a folder ``windows/plugins/<id>/`` containing a
# ``plugin.json`` manifest plus its (inert, copied, never executed
# here) files. This is deliberately separate from the Phase 3
# ``*.py`` discovery above: ``load_plugins()`` only imports top-level
# ``*.py`` modules, so a manifest plugin installed here is NOT
# discovered or run by ``load_plugins()``/``apply_plugin()`` until
# manifest discovery is wired in (parent work: server endpoint + MCP
# tools). What this module does guarantee, with no network and no
# code execution at any point:
#
# - install_plugin() validates the manifest and every bundle entry
#   BEFORE copying anything, then copies into
#   ``plugins_dir/<id>/`` only. The new plugin is installed DISABLED
#   (its id is added to the same ``plugins.json`` disabled list that
#   ``apply_plugin()`` already enforces), so enabling/applying
#   remains gated by that existing disabled-list enforcement.
# - install_plugin() NEVER imports, execs, evals, or subprocess-runs
#   any plugin file, and never downloads anything. A URL passed as
#   ``source`` is rejected outright; use download_plugin_bundle()
#   first (a separate, explicitly gated step) and then install the
#   downloaded bundle, passing the URL as ``source_label`` so it is
#   stored as metadata only.
# - remove_plugin() deletes only the plugin's own folder under
#   ``plugins_dir`` and only while the plugin is disabled.
# - check_plugin_update() never touches the network and invents no
#   registry: it reports "unknown" unless the installed manifest
#   itself carries an update URL / latest-version field, in which
#   case it returns that metadata verbatim, unfetched.
# ---------------------------------------------------------------------------

#: Ids are used as a single folder name under plugins_dir, so only
#: letters, digits, '-' and '_' are allowed -- no '.', no separators,
#: no path tricks of any kind.
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

#: Hard cap for a downloaded bundle and for the total uncompressed
#: size of a zip bundle's installed files (50 MiB).
MAX_BUNDLE_BYTES = 50 * 1024 * 1024

#: Content-Types accepted by download_plugin_bundle(). A server that
#: answers with anything else (e.g. text/html for an error page) is
#: rejected before any body is saved.
ALLOWED_BUNDLE_CONTENT_TYPES = frozenset({
    "application/zip",
    "application/x-zip-compressed",
    "application/octet-stream",
    "application/x-compressed",
})

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_SYMLINK_MODE = 0o120000
_FILE_TYPE_MASK = 0o170000


def _validate_id(plugin_id) -> str:
    if not isinstance(plugin_id, str) or not plugin_id \
            or not SAFE_ID_RE.match(plugin_id):
        raise ValueError(
            "plugin.json 'id' must be a non-empty string using only "
            "letters, digits, '-' and '_'")
    return plugin_id


def _validate_manifest(data, *, source_label: str) -> dict:
    """Validate a parsed plugin.json. Returns the manifest dict.

    Raises ValueError on any problem; nothing has been copied yet
    when this raises, because callers validate before copying.
    """
    if not isinstance(data, dict):
        raise ValueError(
            f"plugin.json in {source_label!r} must be a JSON object")
    plugin_id = _validate_id(data.get("id"))
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(
            f"plugin.json in {source_label!r} must have a non-empty "
            "string 'name'")
    hooks = data.get("hooks")
    if not isinstance(hooks, list):
        raise ValueError(
            f"plugin.json in {source_label!r} must have a 'hooks' list")
    for hook in hooks:
        if not isinstance(hook, str) or not hook.strip():
            raise ValueError(
                f"plugin.json in {source_label!r} has a non-string or "
                "empty entry in 'hooks'")
    return data


def _parse_manifest_bytes(raw: bytes, *, source_label: str) -> dict:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"plugin.json in {source_label!r} is not valid JSON: {exc}"
        ) from exc
    return _validate_manifest(data, source_label=source_label)


def _warnings_for_manifest(manifest: dict, *, has_code_files: bool) -> list[str]:
    """Warning list returned for EVERY install (possibly empty of
    optional-field warnings, but never empty overall: a fresh id is
    always untrusted until a human has reviewed it)."""
    plugin_id = manifest["id"]
    warnings = [
        f"Plugin '{plugin_id}' is new/untrusted: installed from an "
        "untrusted source; review its files before enabling it.",
    ]
    hooks = manifest.get("hooks") or []
    if hooks:
        warnings.append(
            f"Plugin declares code hooks ({', '.join(hooks)}); plugin "
            "code was NOT executed during install or validation.")
    if has_code_files:
        warnings.append(
            "Plugin bundle contains Python (.py) code files; they "
            "were copied as inert files and were NOT executed during "
            "install or validation.")
    if not isinstance(manifest.get("description"), str) \
            or not manifest["description"].strip():
        warnings.append("Manifest has no description.")
    if not isinstance(manifest.get("version"), str) \
            or not manifest["version"].strip():
        warnings.append("Manifest has no version.")
    return warnings


def _write_state(state: dict, plugins_dir: str | None) -> None:
    path = _state_path(plugins_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)


def _disabled_ids(plugins_dir: str | None) -> set:
    disabled = load_plugin_state(plugins_dir).get("disabled", [])
    return set(disabled) if isinstance(disabled, list) else set()


def _set_disabled(plugin_id: str, disabled: bool,
                  plugins_dir: str | None) -> None:
    """Add/remove one id in the plugins.json disabled list, keeping
    every other state key untouched. This reads the state file
    directly (rather than via set_plugin_enabled, which requires the
    plugin to be discovered by load_plugins -- manifest folders are
    not discovered there yet)."""
    state = load_plugin_state(plugins_dir)
    current = state.get("disabled", [])
    ids = set(current) if isinstance(current, list) else set()
    if disabled:
        ids.add(plugin_id)
    else:
        ids.discard(plugin_id)
    state["disabled"] = sorted(ids)
    _write_state(state, plugins_dir)


def _plugins_folder(plugins_dir: str | None) -> str:
    folder = plugins_dir or PLUGINS_DIR
    return os.path.abspath(folder)


def _dest_for(plugin_id: str, plugins_dir: str | None) -> str:
    return os.path.join(_plugins_folder(plugins_dir), plugin_id)


def _check_dest_within_plugins(dest: str, plugins_dir: str | None) -> None:
    folder = _plugins_folder(plugins_dir)
    if os.path.commonpath([folder, dest]) != folder \
            or os.path.dirname(dest) != folder:
        raise ValueError("Plugin destination escapes the plugins folder")


def _existing_folder_id(plugin_id: str, plugins_dir: str | None) -> str | None:
    """Case-insensitive match against existing folders (Windows
    filesystems are case-insensitive, so 'Foo' and 'foo' collide).
    Returns the existing folder name, or None."""
    folder = _plugins_folder(plugins_dir)
    if not os.path.isdir(folder):
        return None
    lowered = plugin_id.lower()
    for entry in sorted(os.listdir(folder)):
        if entry.lower() == lowered \
                and os.path.isdir(os.path.join(folder, entry)):
            return entry
    return None


def _check_no_symlink_escape(root: str, path: str, *, label: str) -> None:
    """Reject a symlink whose resolved target leaves ``root``."""
    resolved_root = os.path.realpath(root)
    resolved = os.path.realpath(path)
    if os.path.commonpath([resolved_root, resolved]) != resolved_root:
        raise ValueError(
            f"{label}: symlink escapes the bundle: {path!r}")


def _scan_folder_source(source_dir: str) -> list[str]:
    """Walk a folder source, rejecting escaping symlinks, symlinked
    directories, and non-regular files. Returns relative file paths
    (os separators) for regular files plus internal symlinks-to-files
    (copied by content, never recreated as symlinks)."""
    files: list[str] = []
    for root, dirs, names in os.walk(source_dir):
        # os.walk with followlinks=False lists symlinked dirs in
        # dirs but does not descend into them: reject them all, since
        # copying a directory symlink could re-create an escape.
        for dirname in list(dirs):
            full = os.path.join(root, dirname)
            if os.path.islink(full):
                _check_no_symlink_escape(source_dir, full,
                                         label="folder source")
                raise ValueError(
                    f"folder source: symlinked directory not supported: "
                    f"{os.path.relpath(full, source_dir)!r}")
        for name in names:
            full = os.path.join(root, name)
            if os.path.islink(full):
                _check_no_symlink_escape(source_dir, full,
                                         label="folder source")
                if not os.path.isfile(full):
                    raise ValueError(
                        "folder source: symlink does not point to a "
                        f"regular file: {os.path.relpath(full, source_dir)!r}")
            elif not os.path.isfile(full):
                raise ValueError(
                    "folder source: not a regular file: "
                    f"{os.path.relpath(full, source_dir)!r}")
            files.append(os.path.relpath(full, source_dir))
    return sorted(files)


def _check_zip_entry_name(name: str) -> None:
    """Reject absolute paths, '..' traversal, backslash separators
    and empty path components in a zip entry name."""
    if not name or name.startswith("/") or name.startswith("\\") \
            or _DRIVE_RE.match(name) or "\\" in name:
        raise ValueError(f"zip bundle: unsafe entry name: {name!r}")
    parts = name.split("/")
    for part in parts[:-1]:
        if part in ("", ".", ".."):
            raise ValueError(f"zip bundle: unsafe entry name: {name!r}")
    if parts[-1] in ("", ".", "..") and not name.endswith("/"):
        raise ValueError(f"zip bundle: unsafe entry name: {name!r}")
    if parts[-1] == "..":
        raise ValueError(f"zip bundle: unsafe entry name: {name!r}")


def _scan_zip_source(zip_path: str):
    """Validate a .zip bundle WITHOUT extracting anything.

    Returns (manifest, [(relative_path, ZipInfo), ...]) where
    relative_path uses '/' separators and is relative to the bundle
    root: either the zip root (plugin.json at the root) or exactly
    one top-level folder containing plugin.json. Files outside that
    single top-level folder are rejected.
    """
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"Not a valid .zip bundle: {zip_path!r}") from exc
    with zf:
        infos = zf.infolist()
        for info in infos:
            _check_zip_entry_name(info.filename)
            if (info.external_attr >> 16) & _FILE_TYPE_MASK == _SYMLINK_MODE:
                raise ValueError(
                    f"zip bundle: symlink entry rejected: "
                    f"{info.filename!r}")
        files = [i for i in infos if not i.filename.endswith("/")]
        manifest_names = []
        for info in files:
            parts = info.filename.split("/")
            if len(parts) == 1 and parts[0] == "plugin.json":
                manifest_names.append((info, ""))
            elif len(parts) == 2 and parts[1] == "plugin.json":
                manifest_names.append((info, parts[0] + "/"))
        if not manifest_names:
            raise ValueError(
                "zip bundle: no plugin.json at the root or in exactly "
                "one top-level folder")
        roots = {root for _, root in manifest_names}
        if len(roots) != 1:
            raise ValueError(
                "zip bundle: plugin.json found in multiple top-level "
                "folders; bundle must contain exactly one plugin")
        manifest_info, root = manifest_names[0]
        try:
            raw = zf.read(manifest_info)
        except (KeyError, RuntimeError) as exc:
            raise ValueError(
                f"zip bundle: cannot read plugin.json: {exc}") from exc
        manifest = _parse_manifest_bytes(raw, source_label=zip_path)
        entries: list[tuple[str, zipfile.ZipInfo]] = []
        seen: set[str] = set()
        total = 0
        for info in files:
            if not info.filename.startswith(root):
                raise ValueError(
                    "zip bundle: file outside the plugin folder: "
                    f"{info.filename!r}")
            rel = info.filename[len(root):]
            if not rel:
                continue
            if rel.lower() in seen:
                raise ValueError(
                    f"zip bundle: duplicate entry for {rel!r}")
            seen.add(rel.lower())
            total += info.file_size
            if total > MAX_BUNDLE_BYTES:
                raise ValueError(
                    "zip bundle: total uncompressed size exceeds the "
                    f"{MAX_BUNDLE_BYTES}-byte limit")
            entries.append((rel, info))
    # Re-open on demand by the caller via the path; return the entry
    # list so extraction re-validates each target path below.
    return manifest, entries


def _copy_validated_folder(source_dir: str, dest: str,
                           rel_files: list[str]) -> None:
    os.makedirs(dest, exist_ok=True)
    for rel in rel_files:
        src = os.path.join(source_dir, rel)
        target = os.path.join(dest, rel)
        if os.path.commonpath([os.path.abspath(dest), os.path.abspath(target)]) \
                != os.path.abspath(dest):
            raise ValueError(f"folder source: unsafe path: {rel!r}")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        # copyfile follows internal symlinks and writes plain bytes;
        # no symlink is ever recreated in the destination.
        shutil.copyfile(src, target)


def _copy_validated_zip(zip_path: str, dest: str,
                        entries: list[tuple[str, zipfile.ZipInfo]]) -> None:
    os.makedirs(dest, exist_ok=True)
    dest_abs = os.path.abspath(dest)
    with zipfile.ZipFile(zip_path) as zf:
        for rel, info in entries:
            target = os.path.join(dest, *rel.split("/"))
            target_abs = os.path.abspath(target)
            if os.path.commonpath([dest_abs, target_abs]) != dest_abs:
                raise ValueError(f"zip bundle: unsafe path: {rel!r}")
            os.makedirs(os.path.dirname(target_abs), exist_ok=True)
            with zf.open(info, "r") as src, open(target_abs, "wb") as out:
                shutil.copyfileobj(src, out)


def install_plugin(source, plugins_dir: str | None = None,
                   overwrite: bool = False,
                   source_label: str | None = None) -> dict:
    """Install a manifest plugin from a local folder or .zip bundle.

    ``source`` is a local folder path containing a ``plugin.json``
    at its root, or a ``.zip`` file containing ``plugin.json`` at
    its root (or in exactly one top-level folder). ``plugins_dir``
    is the plugins folder to install into (defaults to the real
    ``windows/plugins/``; tests pass a temp dir).

    Validation happens BEFORE anything is copied: the manifest must
    be valid JSON with a safe non-empty string ``id``, a non-empty
    string ``name`` and a ``hooks`` list; zip entries must not use
    absolute paths, ``..`` traversal or symlinks, and folder sources
    must not contain symlinks escaping the folder. A duplicate id
    is refused unless ``overwrite=True`` AND the existing plugin is
    already disabled (disable first; enabling is gated by the
    plugins.json disabled list that apply_plugin() enforces).

    NEVER executes plugin code: no import, exec, eval or subprocess
    runs on any plugin file during install or validation, and no
    network access happens here. If ``source`` is an http(s) URL it
    is rejected: download it first with download_plugin_bundle()
    (a separate step the caller gates behind user confirmation),
    then install the downloaded bundle, passing the URL as
    ``source_label`` so it is recorded as metadata only.

    The installed plugin is recorded as DISABLED in plugins.json
    and its source is recorded in ``<id>/install.json`` metadata
    (``source_label`` if given, else the literal ``source`` string)
    plus the returned dict. Returns a dict with ``id``, ``name``,
    ``path``, ``source``, ``warnings`` (always present, see
    _warnings_for_manifest), ``overwrite`` and ``enabled`` (False).
    Raises ValueError / FileNotFoundError / KeyError-style errors
    (ValueError for duplicates and enabled-overwrite refusals)
    without copying anything on failure.
    """
    if isinstance(source, str) and _URL_RE.match(source.strip()):
        raise ValueError(
            "install_plugin never downloads: a URL source must be "
            "downloaded first with download_plugin_bundle() (gated "
            "behind user confirmation) and then installed from the "
            "downloaded bundle; pass the URL as source_label to "
            "record it as metadata only")
    src = os.fspath(source)
    if not os.path.exists(src):
        raise FileNotFoundError(f"Plugin source not found: {src!r}")
    recorded = source_label if source_label is not None else str(source)

    if os.path.isdir(src):
        manifest_path = os.path.join(src, "plugin.json")
        if not os.path.isfile(manifest_path):
            raise ValueError(
                f"folder source has no plugin.json at its root: {src!r}")
        rel_files = _scan_folder_source(src)
        if "plugin.json" not in {r.replace(os.sep, "/") for r in rel_files} \
                and not os.path.isfile(manifest_path):
            raise ValueError(
                f"folder source has no plugin.json at its root: {src!r}")
        with open(manifest_path, "rb") as fh:
            manifest = _parse_manifest_bytes(fh.read(), source_label=src)
        has_code = any(r.lower().endswith(".py") for r in rel_files)
        bundle_kind = "folder"
    elif os.path.isfile(src) and src.lower().endswith(".zip"):
        manifest, entries = _scan_zip_source(src)
        has_code = any(rel.lower().endswith(".py") for rel, _ in entries)
        bundle_kind = "zip"
    else:
        raise ValueError(
            "Plugin source must be a folder containing plugin.json "
            f"or a .zip bundle, not: {src!r}")

    plugin_id = manifest["id"]
    dest = _dest_for(plugin_id, plugins_dir)
    _check_dest_within_plugins(dest, plugins_dir)
    folder = _plugins_folder(plugins_dir)
    if os.path.realpath(src) == os.path.realpath(dest) \
            and os.path.exists(dest):
        raise ValueError("Plugin source is already the install destination")
    existing = _existing_folder_id(plugin_id, plugins_dir)
    if existing is not None:
        if not overwrite:
            raise ValueError(
                f"Plugin id {plugin_id!r} already exists; pass "
                "overwrite=True to replace it")
        disabled = _disabled_ids(plugins_dir)
        # The stored folder name may differ in case from the id;
        # disabled under either spelling counts as disabled.
        if plugin_id not in disabled and existing not in disabled:
            raise ValueError(
                f"Plugin {plugin_id!r} is enabled; disable it first "
                "before overwriting")
        # Remove the old folder only now, after all validation.
        old_dest = os.path.join(folder, existing)
        _check_dest_within_plugins(old_dest, plugins_dir)
        shutil.rmtree(old_dest)
        if existing != plugin_id:
            _set_disabled(existing, False, plugins_dir)

    os.makedirs(folder, exist_ok=True)
    try:
        if bundle_kind == "folder":
            _copy_validated_folder(src, dest, rel_files)
        else:
            _copy_validated_zip(src, dest, entries)
        with open(os.path.join(dest, "install.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({"id": plugin_id, "source": recorded}, fh,
                      indent=2, sort_keys=True)
    except Exception:
        # A failed copy must not leave a half-installed plugin behind.
        if os.path.isdir(dest):
            shutil.rmtree(dest, ignore_errors=True)
        raise
    # New plugins start disabled: untrusted code must be reviewed
    # and explicitly enabled before apply_plugin() will run it.
    _set_disabled(plugin_id, True, plugins_dir)
    return {"id": plugin_id, "name": manifest["name"], "path": dest,
            "source": recorded,
            "warnings": _warnings_for_manifest(manifest,
                                               has_code_files=has_code),
            "overwrite": bool(overwrite), "enabled": False}


def remove_plugin(plugin_id: str, plugins_dir: str | None = None) -> dict:
    """Remove an installed manifest plugin's folder.

    Refuses (ValueError) while the plugin is enabled -- disable it
    first -- and only ever deletes ``plugins_dir/<id>/`` itself
    (never a top-level ``*.py`` plugin, never anything outside the
    plugins folder). Raises KeyError if no such folder is installed.
    On success the id is also dropped from the disabled list so no
    stale entry lingers. Returns ``{"id", "removed": True, "path"}``.
    """
    _validate_id(plugin_id)
    folder = _plugins_folder(plugins_dir)
    dest = os.path.join(folder, plugin_id)
    _check_dest_within_plugins(dest, plugins_dir)
    if not os.path.isdir(dest):
        raise KeyError(f"No installed plugin folder for id {plugin_id!r}")
    if plugin_id not in _disabled_ids(plugins_dir):
        raise ValueError(
            f"Plugin {plugin_id!r} is enabled; disable it first "
            "before removing it")
    shutil.rmtree(dest)
    _set_disabled(plugin_id, False, plugins_dir)
    return {"id": plugin_id, "removed": True, "path": dest}


def _load_installed_manifest(plugin_id: str,
                             plugins_dir: str | None) -> dict:
    dest = os.path.join(_plugins_folder(plugins_dir), plugin_id)
    manifest_path = os.path.join(dest, "plugin.json")
    if not os.path.isdir(dest) or not os.path.isfile(manifest_path):
        raise KeyError(f"No installed plugin folder for id {plugin_id!r}")
    with open(manifest_path, "rb") as fh:
        return _parse_manifest_bytes(fh.read(),
                                     source_label=manifest_path)


def check_plugin_update(plugin_id: str,
                        plugins_dir: str | None = None) -> dict:
    """Honest update check: NO network, NO invented registry.

    Returns ``status="unknown"`` unless the installed manifest
    itself carries an update URL (``update_url``/``updateUrl``) or a
    ``latest_version`` field, in which case ``status="metadata_only"``
    and those fields are returned verbatim, unfetched
    (``fetched`` is always False). ``installed_version`` is the
    manifest's own ``version`` when present. Raises KeyError if the
    plugin is not installed, ValueError if its manifest is invalid.
    """
    _validate_id(plugin_id)
    manifest = _load_installed_manifest(plugin_id, plugins_dir)
    update_url = None
    for key in ("update_url", "updateUrl"):
        value = manifest.get(key)
        if isinstance(value, str) and value.strip():
            update_url = value
            break
    latest = manifest.get("latest_version")
    latest = latest if isinstance(latest, str) and latest.strip() else None
    installed = manifest.get("version")
    installed = installed if isinstance(installed, str) \
        and installed.strip() else None
    if update_url is None and latest is None:
        return {"id": plugin_id, "status": "unknown", "fetched": False,
                "update_url": None, "latest_version": None,
                "installed_version": installed}
    return {"id": plugin_id, "status": "metadata_only", "fetched": False,
            "update_url": update_url, "latest_version": latest,
            "installed_version": installed}


def download_plugin_bundle(url: str, dest,
                           max_bytes: int = MAX_BUNDLE_BYTES,
                           timeout: int = 30) -> dict:
    """Download a plugin .zip bundle -- SEPARATE from install.

    This is the only function in this module that touches the
    network, and it must be gated behind an explicit user
    confirmation by the caller (server endpoint / UI); it performs
    no confirmation itself and never installs or executes anything
    it downloads. Validates: http(s) scheme only, no credentials in
    the URL, HTTP 200, a zip-like Content-Type when the server sends
    one, and a size limit enforced from Content-Length when present
    and again while streaming (partial files are deleted on any
    failure). The result is verified to look like a zip (magic
    bytes + zipfile check) before being returned; callers should
    then pass the downloaded file to install_plugin(), with the URL
    as ``source_label``. Raises ValueError on any validation or
    download failure. ``dest`` must not already exist.
    """
    import urllib.parse
    import urllib.request
    import urllib.error

    if not isinstance(url, str):
        raise ValueError("URL must be a string")
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme.lower() not in ("http", "https") \
            or not parsed.netloc or parsed.username is not None \
            or parsed.password is not None:
        raise ValueError(
            "Plugin bundle URL must be an http(s) URL without "
            "embedded credentials")
    dest_path = os.fspath(dest)
    if os.path.exists(dest_path):
        raise FileExistsError(f"Download destination already exists: "
                              f"{dest_path!r}")
    parent = os.path.dirname(os.path.abspath(dest_path))
    os.makedirs(parent, exist_ok=True)
    tmp_path = dest_path + ".part"
    request = urllib.request.Request(
        url, headers={"User-Agent": "VibeEdit plugin installer"})
    try:
        try:
            response = urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.URLError as exc:
            raise ValueError(f"Plugin bundle download failed: {exc}") \
                from exc
        with response:
            if getattr(response, "status", 200) != 200:
                raise ValueError(
                    "Plugin bundle download failed: HTTP "
                    f"{getattr(response, 'status', '?')}")
            content_type = response.headers.get("Content-Type")
            if content_type:
                base = content_type.split(";", 1)[0].strip().lower()
                if base not in ALLOWED_BUNDLE_CONTENT_TYPES:
                    raise ValueError(
                        "Plugin bundle download rejected: unexpected "
                        f"Content-Type {base!r}")
            length = response.headers.get("Content-Length")
            if length is not None:
                try:
                    if int(length) > max_bytes:
                        raise ValueError(
                            "Plugin bundle exceeds the "
                            f"{max_bytes}-byte size limit")
                except ValueError as exc:
                    if "exceeds" in str(exc):
                        raise
                    # Unparseable length: enforce while streaming.
            total = 0
            with open(tmp_path, "wb") as out:
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError(
                            "Plugin bundle exceeds the "
                            f"{max_bytes}-byte size limit")
                    out.write(chunk)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
    try:
        with open(tmp_path, "rb") as fh:
            magic = fh.read(4)
        if magic not in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"):
            raise ValueError(
                "Downloaded file does not look like a .zip bundle")
        if not zipfile.is_zipfile(tmp_path):
            raise ValueError(
                "Downloaded file is not a valid .zip bundle")
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
    os.replace(tmp_path, dest_path)
    return {"path": dest_path, "size": total, "url": url}
