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
    # plugin.json. Round 4: when the manifest declares an "entry"
    # module, its register() hooks are loaded here exactly like a
    # top-level plugin module, so apply_plugin can run them. A
    # manifest without an entry stays listed-but-not-executable, and
    # a manifest whose entry fails to load is recorded in _errors
    # and listed with its entry error, never as runnable. Keyed by
    # manifest id (the folder name), which is what install_plugin
    # records in the disabled list.
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
            entry_info: dict = {
                "name": pid,
                "display_name": manifest.get("name", pid),
                "description": manifest.get("description", ""),
                "manifest": True,
                "manifest_hooks": sorted(hooks),
                "path": sub,
            }
            if "options" in manifest:
                # Raw manifest options; validated by
                # get_plugin_options() on read, never silently
                # dropped here (a bad schema must error on read,
                # not vanish from the listing).
                entry_info["manifest_options"] = manifest.get("options")
            # Round 8: raw actions/views, validated on read by
            # list_plugin_actions()/get_plugin_view().
            if "actions" in manifest:
                entry_info["manifest_actions"] = manifest.get("actions")
            if "views" in manifest:
                entry_info["manifest_views"] = manifest.get("views")
            entry = manifest.get("entry")
            if entry is not None:
                _validate_manifest(manifest, source_label=name)
                try:
                    reg = _load_manifest_entry(pid, sub, entry)
                except Exception as exc:  # noqa: BLE001 - one bad plugin
                    entry_info["entry_error"] = str(exc)
                    errors[name] = str(exc)
                else:
                    entry_info["manifest_entry"] = entry
                    for key, value in reg.items():
                        if callable(value):
                            entry_info[key] = value
            plugins[pid] = entry_info
        except Exception as exc:  # noqa: BLE001 - one bad plugin
            errors[name] = str(exc)
    plugins["_errors"] = errors
    return plugins


def _state_path(plugins_dir: str | None = None) -> str:
    """plugins.json next to the plugins/ folder (windows/plugins.json
    in a source checkout). Stores enable/disable state and
    user-scope option values only — never plugin code or project
    data. This file is runtime state: it is never pushed to the
    repo."""
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


# ------------------------------------------------------------------
# Plugin options (round 6) — original semantics from
# CommandCatalog+Plugins.swift:
# - plugins.options (read): "Read a plugin's options (schema, scope
#   and current values)."
# - plugins.option (edit): "Set one plugin option like the Plugins
#   sheet: project-scope values are an undoable project edit,
#   user-scope values are saved for this Mac. Omit value to reset
#   it to the default."
# A plugin declares options in register()'s "options" list (or in a
# manifest's "options" list): each entry is {id, type, default,
# scope, description?, choices?} with type in bool/number/integer/
# string/choice and scope in user/project (default user).
# User-scope values live in plugins.json (runtime state, never
# pushed); project-scope values live in the open project's data
# under "plugin_options" and are saved with the project by the
# caller (this module never saves a project itself). A plugin that
# declares no options simply has an empty schema — options is
# never invented for it.
# ------------------------------------------------------------------

OPTION_TYPES = ("bool", "number", "integer", "string", "choice")


def get_plugin_options(plugin_name: str,
                       plugins_dir: str | None = None) -> list[dict]:
    """Normalized declared options schema of one discovered plugin.

    Raises KeyError for an unknown plugin and ValueError for a
    malformed schema (bad id, type, scope, or a choice option
    without choices) — a bad schema errors on read, it is never
    silently dropped or repaired into something else.
    """
    plugins = load_plugins(plugins_dir)
    if plugin_name not in plugins:
        raise KeyError(f"Unknown plugin: {plugin_name!r}")
    info = plugins[plugin_name]
    raw = info.get("options")
    if raw is None:
        raw = info.get("manifest_options")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(
            f"Plugin {plugin_name!r} options must be a list")
    schema: list[dict] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError(
                f"Plugin {plugin_name!r} has a non-object option entry")
        oid = entry.get("id")
        if not isinstance(oid, str) or not oid or oid in seen:
            raise ValueError(
                f"Plugin {plugin_name!r} has a bad/duplicate option id: "
                f"{oid!r}")
        seen.add(oid)
        otype = entry.get("type", "string")
        if otype not in OPTION_TYPES:
            raise ValueError(
                f"Plugin {plugin_name!r} option {oid!r} has unknown "
                f"type {otype!r}")
        scope = entry.get("scope", "user")
        if scope not in ("user", "project"):
            raise ValueError(
                f"Plugin {plugin_name!r} option {oid!r} has unknown "
                f"scope {scope!r}")
        norm: dict = {"id": oid, "type": otype, "scope": scope,
                      "default": entry.get("default"),
                      "description": entry.get("description", "")}
        if otype == "choice":
            choices = entry.get("choices")
            if not isinstance(choices, list) or not choices:
                raise ValueError(
                    f"Plugin {plugin_name!r} choice option {oid!r} "
                    "needs a non-empty choices list")
            norm["choices"] = list(choices)
        schema.append(norm)
    return schema


def coerce_plugin_option_value(option: dict, value):
    """Validate and coerce one option value against its schema
    entry. The original takes the value as text ("on/off, numbers,
    choices"); JSON-native bools/numbers are accepted as the same
    values. Raises ValueError on any mismatch — an out-of-schema
    value is never stored."""
    otype = option["type"]
    oid = option["id"]
    if otype == "bool":
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in ("on", "true", "yes", "1"):
            return True
        if text in ("off", "false", "no", "0"):
            return False
        raise ValueError(
            f"Option {oid!r} needs on/off (got {value!r})")
    if otype == "number":
        try:
            return float(value)
        except (TypeError, ValueError):
            raise ValueError(
                f"Option {oid!r} needs a number (got {value!r})") from None
    if otype == "integer":
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError(
                f"Option {oid!r} needs an integer (got {value!r})") from None
        if number != int(number):
            raise ValueError(
                f"Option {oid!r} needs an integer (got {value!r})")
        return int(number)
    if otype == "choice":
        text = str(value)
        if text not in option["choices"]:
            raise ValueError(
                f"Option {oid!r} must be one of "
                f"{option['choices']} (got {value!r})")
        return text
    return str(value)


def get_plugin_option_values(plugin_name: str,
                             plugins_dir: str | None = None,
                             project_data: dict | None = None) -> dict:
    """Current values for a plugin's options: schema defaults
    overridden by stored values. User-scope values come from
    plugins.json; project-scope values come from the given project
    data (None means no project is open, so project-scope options
    report their defaults)."""
    schema = get_plugin_options(plugin_name, plugins_dir)
    state = load_plugin_state(plugins_dir)
    user_values = state.get("options") or {}
    if not isinstance(user_values, dict):
        user_values = {}
    user_values = user_values.get(plugin_name, {})
    if not isinstance(user_values, dict):
        user_values = {}
    project_values: dict = {}
    if isinstance(project_data, dict):
        all_project = project_data.get("plugin_options") or {}
        if isinstance(all_project, dict):
            project_values = all_project.get(plugin_name, {})
            if not isinstance(project_values, dict):
                project_values = {}
    out: dict = {}
    for opt in schema:
        stored = project_values if opt["scope"] == "project" \
            else user_values
        out[opt["id"]] = stored.get(opt["id"], opt["default"])
    return out


def set_plugin_option(plugin_name: str, option_id: str, value,
                      plugins_dir: str | None = None,
                      project_data: dict | None = None) -> dict:
    """Set one plugin option, or reset it to its default when
    ``value`` is None (the original's "omit value to reset").
    User-scope values are written to plugins.json immediately;
    project-scope values are written into the given project data
    dict and the caller must save the project (project_data=None
    for a project-scope option raises, it never writes nowhere).
    Returns {plugin, option, scope, value, reset} with the
    effective value after the write."""
    schema = get_plugin_options(plugin_name, plugins_dir)
    option = next((o for o in schema if o["id"] == option_id), None)
    if option is None:
        raise ValueError(
            f"Unknown option {option_id!r} for plugin {plugin_name!r}")
    if value is None:
        effective = option["default"]
        reset = True
    else:
        effective = coerce_plugin_option_value(option, value)
        reset = False
    if option["scope"] == "project":
        if not isinstance(project_data, dict):
            raise ValueError(
                f"Option {option_id!r} is project-scope; open a "
                "project first")
        all_project = project_data.get("plugin_options")
        if not isinstance(all_project, dict):
            all_project = {}
            project_data["plugin_options"] = all_project
        values = all_project.get(plugin_name)
        if not isinstance(values, dict):
            values = {}
            all_project[plugin_name] = values
        if reset:
            values.pop(option_id, None)
        else:
            values[option_id] = effective
    else:
        state = load_plugin_state(plugins_dir)
        all_options = state.get("options")
        if not isinstance(all_options, dict):
            all_options = {}
            state["options"] = all_options
        values = all_options.get(plugin_name)
        if not isinstance(values, dict):
            values = {}
            all_options[plugin_name] = values
        if reset:
            values.pop(option_id, None)
        else:
            values[option_id] = effective
        path = _state_path(plugins_dir)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, sort_keys=True)
    return {"plugin": plugin_name, "option": option_id,
            "scope": option["scope"], "value": effective,
            "reset": reset}


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
        # Round 4 trust model: a manifest plugin's code runs
        # in-process with the app's privileges, exactly like a
        # top-level plugin module. That is only acceptable because
        # (a) installs land disabled by default, (b) the user must
        # review the plugin's files and explicitly enable it, and
        # (c) only hooks declared in the manifest may run. A
        # manifest without a runnable entry still refuses cleanly
        # instead of pretending a hook ran.
        if info.get("entry_error"):
            raise ValueError(
                f"Plugin {plugin_name!r} entry failed to load: "
                f"{info['entry_error']}")
        if hook not in (info.get("manifest_hooks") or []):
            raise ValueError(
                f"Plugin {plugin_name!r} does not declare hook "
                f"{hook!r} in its manifest")
        if not callable(info.get(hook)):
            raise ValueError(
                f"Plugin {plugin_name!r} declares hook {hook!r} but "
                "its entry module does not provide it (manifest "
                "plugins without an 'entry' are not executable)")
    fn = info.get(hook)
    if not callable(fn):
        raise ValueError(
            f"Plugin {plugin_name!r} has no hook {hook!r}")
    _, item = project.item(item_id)
    result = fn(project, item_id)
    # Round 8 proposal convention: a hook that wants its edit
    # reviewed returns {"propose": [ops]} instead of mutating the
    # project. The ops are stored as a pending proposal (see
    # apply_plugin_proposal) and NOT applied here, so a reviewing
    # caller can apply or discard them with plugins_proposal.
    # Hooks that mutate and then return a proposal dict are a
    # contract violation by the plugin, documented in PARITY.md.
    if isinstance(result, dict) and isinstance(
            result.get("propose"), list):
        proposal = store_plugin_proposal(
            project, plugin_name, hook, result["propose"])
        return {"proposal": proposal["id"], "applied": False,
                "plugin": plugin_name, "hook": hook}
    return result if isinstance(result, dict) else item


# ---------------------------------------------------------------------------
# Phase B3: install / remove / update-check for manifest plugins.
#
# A manifest plugin is a folder ``windows/plugins/<id>/`` containing a
# ``plugin.json`` manifest plus its code files. The code files are
# copied, never executed, during install. Since round 4, a manifest
# that declares an "entry" module has that module's declared hooks
# loaded by ``load_plugins()`` and executed by ``apply_plugin()``
# in-process — but only after the user has reviewed the files and
# explicitly enabled the plugin (installed plugins land disabled,
# and ``apply_plugin()`` refuses disabled plugins). What this module
# guarantees, with no network and no code execution at install time:
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
    # Round 4: an optional "entry" declares the code module that
    # implements the hooks. It must be a plain file name inside the
    # plugin folder (no directories, no traversal, *.py only) so a
    # manifest can never point execution outside its own folder.
    entry = data.get("entry")
    if entry is not None:
        if not isinstance(entry, str) or not entry.endswith(".py") \
                or entry != os.path.basename(entry) \
                or entry in (".", ".."):
            raise ValueError(
                f"plugin.json in {source_label!r} has an unsafe 'entry' "
                f"{entry!r}: it must be a plain *.py file name inside "
                "the plugin folder")
    # Round 8: optional "actions" (editor actions the plugin adds)
    # and "views" (JSON component models for the plugin's panels).
    # Both are validated here so a bad declaration fails the
    # install/validation, never silently half-registers.
    actions = data.get("actions")
    if actions is not None:
        if not isinstance(actions, list):
            raise ValueError(
                f"plugin.json in {source_label!r} has non-list 'actions'")
        for action in actions:
            if not isinstance(action, dict) \
                    or not isinstance(action.get("id"), str) \
                    or not action["id"] \
                    or not isinstance(action.get("hook"), str) \
                    or not action["hook"]:
                raise ValueError(
                    f"plugin.json in {source_label!r} has an action "
                    "without a string 'id' and 'hook'")
            params = action.get("parameters")
            if params is not None and not isinstance(params, dict):
                raise ValueError(
                    f"plugin.json in {source_label!r} has an action "
                    "whose 'parameters' is not a JSON Schema object")
    views = data.get("views")
    if views is not None:
        if not isinstance(views, list):
            raise ValueError(
                f"plugin.json in {source_label!r} has non-list 'views'")
        for view in views:
            if not isinstance(view, dict) \
                    or not isinstance(view.get("id"), str) \
                    or not view["id"]:
                raise ValueError(
                    f"plugin.json in {source_label!r} has a view "
                    "without a string 'id'")
            components = view.get("components")
            if components is not None:
                if not isinstance(components, list):
                    raise ValueError(
                        f"plugin.json in {source_label!r} has a view "
                        "whose 'components' is not a list")
                for comp in components:
                    if not isinstance(comp, dict) \
                            or not isinstance(comp.get("id"), str) \
                            or not comp["id"] \
                            or comp.get("kind") not in (
                                "text", "input", "button", "list"):
                        raise ValueError(
                            f"plugin.json in {source_label!r} has a "
                            "view component without a string 'id' and "
                            "a kind of text/input/button/list")
    return data


def _load_manifest_entry(pid: str, folder: str, entry: str) -> dict:
    """Import a manifest plugin's declared entry module.

    Returns the dict from its ``register()`` (same contract as a
    top-level plugin module). Any failure raises ValueError so the
    caller can record it without listing a half-loaded plugin as
    runnable. The module runs in-process with the app's privileges:
    that is the trust model (see ``apply_plugin``) — a manifest
    plugin only runs after the user has reviewed its files and
    explicitly enabled it.
    """
    path = os.path.join(folder, entry)
    if not os.path.isfile(path):
        raise ValueError(
            f"Manifest plugin {pid!r} declares entry {entry!r} but "
            f"the file is missing from its folder")
    mod_name = f"vibeedit_manifest_{pid}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load plugin entry module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    info = module.register()
    if not isinstance(info, dict) or "name" not in info:
        raise ValueError(
            f"Manifest plugin {pid!r} entry register() must return a "
            "dict with 'name'")
    return info


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

    # Round 4: a declared entry must actually be in the bundle, or
    # the install is rejected before anything is copied (a plugin
    # whose entry is missing would otherwise install and then fail
    # on first use).
    if manifest.get("entry") is not None:
        if bundle_kind == "folder":
            bundle_names = {r.replace(os.sep, "/") for r in rel_files}
        else:
            bundle_names = {rel for rel, _ in entries}
        if manifest["entry"] not in bundle_names:
            raise ValueError(
                f"Plugin manifest declares entry "
                f"{manifest['entry']!r} but the bundle does not "
                "contain that file")

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


# ---------------------------------------------------------------------------
# Round 8: plugin overlays, actions, views, proposals, replacement.
#
# Original specs: CommandCatalog+PluginViews.swift (plugins.overlays
# / set-overlays / view / view-event / show-view) and
# CommandCatalog+Plugins.swift (plugins.actions / proposal / replace
# / setup). The original's views are SwiftUI; the Windows host is
# headless, so a view here is a JSON component model declared in
# the manifest (kinds text/input/button/list) with session state
# for input values. plugins.show-view stays honest: there is no
# viewer to show a view in. plugins.setup stays honest: pure .py
# plugins declare no dependency recipe to run.
# ---------------------------------------------------------------------------

#: Session-only overlays: {scope: {plugin: [overlay, ...]}}. The
#: original says overlays are NOT saved with the project, so they
#: live only in this process and are lost on restart, by design.
_OVERLAYS: dict = {}

#: Session-only plugin view state: {(scope, plugin, view):
#: {component_id: value}} for input components.
_VIEW_STATE: dict = {}


def _overlay_scope(plugins_dir) -> str:
    return os.path.abspath(_plugins_folder(plugins_dir))


def _validate_overlay(entry: dict) -> dict:
    if not isinstance(entry, dict):
        raise ValueError("Plugin overlays must be objects")
    oid = entry.get("id")
    kind = entry.get("kind")
    if not isinstance(oid, str) or not oid:
        raise ValueError("Plugin overlay needs a string 'id'")
    if kind not in ("range", "marker", "region"):
        raise ValueError(
            "Plugin overlay kind must be range, marker or region")
    for key in ("start", "end"):
        if key in entry and not isinstance(entry[key], (int, float)):
            raise ValueError(
                f"Plugin overlay {key!r} must be a number")
    rect = entry.get("rect")
    if rect is not None:
        if not isinstance(rect, dict):
            raise ValueError("Plugin overlay rect must be an object")
        for key in ("x", "y", "width", "height"):
            value = rect.get(key)
            if not isinstance(value, (int, float)) \
                    or not 0 <= value <= 1:
                raise ValueError(
                    "Plugin overlay rect values must be 0..1 shares")
    return dict(entry)


def set_plugin_overlays(plugin: str, overlays,
                        plugins_dir=None) -> dict:
    """Replace a plugin's overlays (an empty list clears them).
    Session-only: never saved with the project, per the spec."""
    if not isinstance(overlays, list):
        raise ValueError("plugins.set-overlays needs a JSON array")
    cleaned = [_validate_overlay(e) for e in overlays]
    scope = _overlay_scope(plugins_dir)
    _OVERLAYS.setdefault(scope, {})[plugin] = cleaned
    return {"plugin": plugin, "overlays": cleaned}


def list_plugin_overlays(plugin=None, plugins_dir=None) -> dict:
    """List the overlays plugins draw on the timeline and viewer,
    by plugin (or one plugin)."""
    scope = _overlay_scope(plugins_dir)
    by_plugin = _OVERLAYS.get(scope, {})
    if plugin is not None:
        return {"plugin": plugin,
                "overlays": list(by_plugin.get(plugin, []))}
    return {"overlays": {name: list(entries)
                         for name, entries in by_plugin.items()}}


def list_plugin_actions(query=None, plugin=None,
                        plugins_dir=None) -> dict:
    """List actions plugins add to the editor, from manifest
    'actions' declarations. An action is available when its plugin
    is enabled and its hook is runnable (declared + provided by
    the entry module, or a top-level module hook). lastRun is
    null: run history is not tracked in this build."""
    plugins = load_plugins(plugins_dir)
    disabled = _disabled_ids(plugins_dir)
    out = []
    for name, info in sorted(plugins.items()):
        if name.startswith("_"):
            continue
        if plugin is not None and name != plugin:
            continue
        actions = []
        if info.get("manifest"):
            actions = info.get("manifest_actions") or []
        for action in actions:
            if not isinstance(action, dict):
                continue
            hook = action.get("hook")
            runnable = False
            if info.get("manifest"):
                runnable = hook in (info.get("manifest_hooks") or []) \
                    and callable(info.get(hook))
            else:
                runnable = callable(info.get(hook))
            entry = {
                "plugin": name,
                "id": action.get("id"),
                "title": action.get("title", action.get("id")),
                "description": action.get("description", ""),
                "parameters": action.get("parameters") or {},
                "hook": hook,
                "available": name not in disabled and runnable,
                "lastRun": None}
            if query and query.lower() not in (
                    str(entry["id"]) + str(entry["title"])
                    + name).lower():
                continue
            out.append(entry)
    return {"actions": out}


def _manifest_view(info: dict, view_id: str) -> dict:
    views = info.get("manifest_views") or []
    for view in views:
        if isinstance(view, dict) and view.get("id") == view_id:
            return view
    raise KeyError(
        f"Plugin has no view {view_id!r} "
        f"(declared: {[v.get('id') for v in views if isinstance(v, dict)]})")


def get_plugin_view(plugin: str, view_id: str,
                    plugins_dir=None) -> dict:
    """Render a plugin view and return its components as JSON
    (text, lists, inputs with their current values, buttons by
    id). The view model comes from the manifest; there is no
    SwiftUI host headless, so 'open' is not honoured here."""
    plugins = load_plugins(plugins_dir)
    if plugin not in plugins or plugins[plugin].get("_errors"):
        raise KeyError(f"Unknown plugin: {plugin!r}")
    info = plugins[plugin]
    if not info.get("manifest"):
        raise ValueError(
            f"Plugin {plugin!r} is not a manifest plugin and "
            "declares no views")
    view = _manifest_view(info, view_id)
    scope = _overlay_scope(plugins_dir)
    state = _VIEW_STATE.get((scope, plugin, view_id), {})
    components = []
    for comp in view.get("components") or []:
        entry = dict(comp)
        if comp.get("kind") == "input":
            entry["value"] = state.get(
                comp["id"], comp.get("value", ""))
        components.append(entry)
    return {"plugin": plugin, "view": view_id,
            "title": view.get("title", view_id),
            "placement": view.get("placement", "panel"),
            "components": components}


def plugin_view_event(plugin: str, view_id: str, node: str,
                      event_type: str = "click", value=None,
                      project=None, plugins_dir=None) -> dict:
    """Do what a user does in a plugin view: click a button,
    change an input, submit a text field, select a list row or
    press a row button. Returns the view's new components. A
    button with an 'action' hook runs that hook (via
    apply_plugin, which enforces the disabled gate); other
    events only update session view state."""
    view = get_plugin_view(plugin, view_id, plugins_dir)
    components = view["components"]
    comp = next((c for c in components if c["id"] == node), None)
    if comp is None:
        raise KeyError(
            f"View {view_id!r} has no component {node!r}")
    scope = _overlay_scope(plugins_dir)
    if event_type in ("change", "submit", "select"):
        state = _VIEW_STATE.setdefault((scope, plugin, view_id), {})
        state[node] = value
    elif event_type in ("click", "row-button"):
        action = comp.get("action")
        if action:
            if project is None:
                raise ValueError(
                    "Button action needs an open project")
            item_id = comp.get("item")
            if item_id is None:
                raise ValueError(
                    "Button action needs the view component to "
                    "carry an 'item' id")
            apply_plugin(project, plugin, action, item_id,
                         plugins_dir=plugins_dir)
    elif event_type not in ("click",):
        raise ValueError(f"Unknown view event type: {event_type!r}")
    return get_plugin_view(plugin, view_id, plugins_dir)


def store_plugin_proposal(project, plugin: str, hook: str,
                          ops) -> dict:
    """Store a hook-proposed edit as pending (see apply_plugin's
    proposal convention). Ops are validated on apply, not here,
    so a proposal can be inspected before anything runs."""
    if not isinstance(ops, list) or not ops:
        raise ValueError("Plugin proposal needs a non-empty ops list")
    proposals = project.data.setdefault("plugin_proposals", [])
    pid = f"prop-{len(proposals) + 1:04d}"
    record = {"id": pid, "plugin": plugin, "hook": hook,
              "ops": ops, "status": "pending"}
    proposals.append(record)
    project._bump()
    return record


def apply_plugin_proposal(project, proposal_id: str,
                          decision: str) -> dict:
    """Apply or discard an edit a plugin hook proposed. Apply
    validates every op before applying any of them (atomic):
    set_clip_field (volume/muted/fadeIn/fadeOut via the item
    dict), set_text, and add_text on a text track. Unknown ops
    refuse the whole proposal."""
    if decision not in ("apply", "discard"):
        raise ValueError(
            "plugins.proposal decision must be 'apply' or 'discard'")
    proposals = project.data.get("plugin_proposals") or []
    record = next((p for p in proposals if p["id"] == proposal_id),
                  None)
    if record is None:
        raise KeyError(f"Unknown proposal: {proposal_id!r}")
    if record.get("status") != "pending":
        raise ValueError(
            f"Proposal {proposal_id!r} is already "
            f"{record.get('status')}")
    if decision == "discard":
        record["status"] = "discarded"
        project._bump()
        return {"id": proposal_id, "status": "discarded",
                "rev": project.rev}
    # Validate everything first.
    for op in record["ops"]:
        if not isinstance(op, dict) or "op" not in op:
            raise ValueError("Proposal op must be an object with 'op'")
        if op["op"] == "set_clip_field":
            _, item = project.item(op["item"])
            if op.get("field") not in ("volume", "muted", "fadeIn",
                                       "fadeOut"):
                raise ValueError(
                    "Proposal set_clip_field field must be volume, "
                    "muted, fadeIn or fadeOut")
        elif op["op"] == "set_text":
            _, item = project.item(op["item"])
            if "text" not in item:
                raise ValueError(
                    "Proposal set_text target has no text field")
        elif op["op"] == "add_text":
            track = project.track(op["track"])
            if track["kind"] != "text":
                raise ValueError(
                    "Proposal add_text target must be a text track")
        else:
            raise ValueError(
                f"Unknown proposal op: {op['op']!r}")
    applied = []
    for op in record["ops"]:
        if op["op"] == "set_clip_field":
            _, item = project.item(op["item"])
            item[op["field"]] = op["value"]
            applied.append(op["op"])
        elif op["op"] == "set_text":
            project.set_text(op["item"], op["text"])
            applied.append(op["op"])
        elif op["op"] == "add_text":
            project.add_text(op["track"], op["text"],
                             int(op["at"]), int(op["dur"]))
            applied.append(op["op"])
    record["status"] = "applied"
    project._bump()
    return {"id": proposal_id, "status": "applied",
            "applied": applied, "rev": project.rev}


def replace_plugin(plugin_id: str, source,
                   plugins_dir: str | None = None) -> dict:
    """Replace an installed plugin with a new version from a
    folder, its plugin.json or a .zip bundle, in the same scope.
    The new files must carry the same plugin ID (checked before
    anything is copied); like install overwrite, the installed
    plugin must already be disabled — only the user enables it
    again after reviewing the new files. Reuses install_plugin's
    validation and copy paths, so a failed replacement never
    leaves a half-installed plugin."""
    _validate_id(plugin_id)
    installed = _load_installed_manifest(plugin_id, plugins_dir)
    _ = installed
    if plugin_id not in _disabled_ids(plugins_dir) and \
            _existing_folder_id(plugin_id, plugins_dir) is not None:
        raise ValueError(
            f"Plugin {plugin_id!r} is enabled; disable it first "
            "before replacing it")
    if isinstance(source, str) and _URL_RE.match(source.strip()):
        raise ValueError(
            "replace_plugin never downloads: download the bundle "
            "first with download_plugin_bundle(), then replace "
            "from the downloaded file")
    src = os.fspath(source)
    if not os.path.exists(src):
        raise FileNotFoundError(f"Plugin source not found: {src!r}")
    if os.path.isdir(src):
        manifest_path = os.path.join(src, "plugin.json")
        if not os.path.isfile(manifest_path):
            raise ValueError(
                f"folder source has no plugin.json at its root: {src!r}")
        with open(manifest_path, "rb") as fh:
            candidate = _parse_manifest_bytes(fh.read(),
                                              source_label=src)
    elif os.path.isfile(src) and src.lower().endswith(".zip"):
        candidate, _entries = _scan_zip_source(src)
    else:
        raise ValueError(
            "Plugin source must be a folder containing plugin.json "
            f"or a .zip bundle, not: {src!r}")
    if candidate.get("id") != plugin_id:
        raise ValueError(
            f"Replacement plugin id {candidate.get('id')!r} does not "
            f"match installed plugin {plugin_id!r}")
    result = install_plugin(src, plugins_dir=plugins_dir,
                            overwrite=True)
    result["replaced"] = True
    return result
