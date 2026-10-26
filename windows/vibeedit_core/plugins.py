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
import os
import sys

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
    plugins["_errors"] = errors
    return plugins


def apply_plugin(project, plugin_name: str, hook: str,
                 item_id: str, plugins_dir: str | None = None) -> dict:
    """Run one plugin hook on one item. Returns the updated item."""
    plugins = load_plugins(plugins_dir)
    if plugin_name not in plugins:
        raise KeyError(
            f"Unknown plugin: {plugin_name!r} "
            f"(available: {', '.join(sorted(k for k in plugins if not k.startswith('_')))})")
    info = plugins[plugin_name]
    fn = info.get(hook)
    if not callable(fn):
        raise ValueError(
            f"Plugin {plugin_name!r} has no hook {hook!r}")
    _, item = project.item(item_id)
    result = fn(project, item_id)
    return result if isinstance(result, dict) else item
