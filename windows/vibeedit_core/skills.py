"""Knowledge/skills store reader for the Windows port.

Mirrors the original BashCut store's read shape only (see
``VibeEdit/VibeEdit/Core/Automation/CommandCatalog+Skills.swift``:
``skills.list`` / ``skills.get`` over SKILL.md files, with scopes
project / user / plugin / kit). This module is the *reader* for one
skills directory — typically ``windows/skills/`` (the kit-level set
shipped with the Windows port). Writing, enabling, proposing and
exporting skills (``skills.save`` / ``skills.enable`` / ``skills.propose``
in the original) are NOT implemented here; the parent wires this
reader into server endpoints and MCP tools first.

Provenance honesty rule: every ``windows/skills/*.md`` file starts
with a provenance header line. ``list_skills`` reports it verbatim as
``source`` (``"original"`` or ``"derived"``); content invented for the
Windows port is never presented as the original's text.

Only the standard library is used, so importing this module never
fails for a missing optional dependency.
"""

from __future__ import annotations

import os
import re
import sys


def _default_skills_dir() -> str:
    """skills/ folder: bundled data under _MEIPASS (or next to the
    executable) for a frozen app — same frozen-app reasoning as
    plugins._plugins_dir() — file-relative in a source checkout
    (windows/vibeedit_core/skills.py -> windows/skills/). Without
    the frozen branch, a frozen app would resolve skills/ relative
    to the bundled module path and silently list zero skills even
    though the spec now ships the skills/ data folder (round 5)."""
    if getattr(sys, "frozen", False):
        for base in (getattr(sys, "_MEIPASS", None),
                     os.path.dirname(os.path.abspath(sys.executable))):
            if base:
                candidate = os.path.join(base, "skills")
                if os.path.isdir(candidate):
                    return candidate
        return os.path.join(getattr(sys, "_MEIPASS",
                                    os.path.dirname(
                                        os.path.abspath(sys.executable))),
                            "skills")
    return os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "..", "skills"))


DEFAULT_SKILLS_DIR = _default_skills_dir()

# Original skill names are lowercase, hyphenated (CommandCatalog+Skills:
# "Skill name (lowercase, hyphenated)"). Accept letters, digits,
# hyphens and underscores; nothing else, so no path separator or
# traversal can ever pass validation.
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def _resolve_dir(skills_dir):
    if skills_dir is None:
        skills_dir = DEFAULT_SKILLS_DIR
    return os.path.normpath(os.path.abspath(skills_dir))


def _skill_path(skills_dir, skill_id):
    """Return the .md path for skill_id, or raise ValueError if unsafe."""
    if not isinstance(skill_id, str) or not _SAFE_ID.match(skill_id):
        raise ValueError(
            "Invalid skill id %r: use a plain lowercase hyphenated name "
            "with no path separators, extensions or '..'" % (skill_id,)
        )
    base = _resolve_dir(skills_dir)
    path = os.path.normpath(os.path.join(base, skill_id + ".md"))
    if os.path.dirname(path) != base:
        raise ValueError("Invalid skill id %r: escapes the skills directory"
                         % (skill_id,))
    return path


def _parse_skill(text):
    """Extract (title, source) from a skill file's text.

    Title: the first ``# `` heading, else the frontmatter ``name:``
    value, else None (caller falls back to the id). Source: the
    provenance header on the FIRST line only — ``"original"`` when it
    says the text is the original skill text, ``"derived"`` when it
    says it was derived from the original's docs, else ``"unknown"``.
    (Only the first line is inspected: derived headers contain the
    phrase "NOT original skill text", which must not misclassify them.)
    """
    heading = None
    frontmatter_name = None
    source = "unknown"
    lines = text.splitlines()
    if lines:
        low = lines[0].strip().lower()
        if "original skill text" in low and "not original" not in low:
            source = "original"
        elif "derived from" in low:
            source = "derived"
    for line in lines:
        stripped = line.strip()
        if heading is None and stripped.startswith("# "):
            heading = stripped[2:].strip()
        elif frontmatter_name is None and stripped.lower().startswith("name:"):
            frontmatter_name = stripped.split(":", 1)[1].strip()
    return heading or frontmatter_name, source


def list_skills(skills_dir=None):
    """Return [{id, title, source}] for every .md file in skills_dir.

    Sorted by id. A missing directory yields an empty list (no skills
    installed yet is a normal state, not an error). Files that fail to
    decode are skipped rather than breaking the whole listing.
    """
    base = _resolve_dir(skills_dir)
    if not os.path.isdir(base):
        return []
    out = []
    for name in sorted(os.listdir(base)):
        if not name.endswith(".md"):
            continue
        skill_id = name[:-3]
        if not _SAFE_ID.match(skill_id):
            continue
        try:
            with open(os.path.join(base, name), "r",
                      encoding="utf-8", errors="strict") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        title, source = _parse_skill(text)
        out.append({"id": skill_id, "title": title or skill_id,
                    "source": source,
                    "enabled": skill_id not in _disabled_ids(base)})
    return out


def get_skill(skills_dir, skill_id):
    """Return the full markdown text of one skill.

    Raises ValueError for unsafe ids (``..``, separators, extensions)
    and FileNotFoundError when the skill does not exist.
    """
    path = _skill_path(skills_dir, skill_id)
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _state_path(skills_dir) -> str:
    """Enabled/disabled state lives next to the skills folder
    (``windows/skills.json`` in a source checkout), mirroring the
    plugins.json pattern. State never holds skill content."""
    base = _resolve_dir(skills_dir)
    return os.path.join(os.path.dirname(base), "skills.json")


def _load_state(skills_dir) -> dict:
    try:
        import json as _json
        with open(_state_path(skills_dir), encoding="utf-8") as fh:
            data = _json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_state(skills_dir, state: dict) -> None:
    import json as _json
    path = _state_path(skills_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        _json.dump(state, fh, indent=2, sort_keys=True)


def _disabled_ids(skills_dir) -> set:
    disabled = _load_state(skills_dir).get("disabled", [])
    return set(disabled) if isinstance(disabled, list) else set()


def save_skill(skills_dir, skill_id: str, title: str, body: str,
               overwrite: bool = False) -> dict:
    """Write a caller-supplied skill file. The file gets a
    ``Provenance: User-written skill`` header so it is never mistaken
    for original BashCut text. Refuses to overwrite an existing skill
    unless ``overwrite`` is passed; empty bodies are refused."""
    if not str(body).strip():
        raise ValueError("Skill body must not be empty")
    path = _skill_path(skills_dir, skill_id)
    if os.path.exists(path) and not overwrite:
        raise ValueError(
            f"Skill {skill_id!r} already exists; pass overwrite to "
            f"replace it")
    base = _resolve_dir(skills_dir)
    os.makedirs(base, exist_ok=True)
    text = ("Provenance: User-written skill — this is NOT original "
            "BashCut text.\n\n# " + str(title or skill_id) + "\n\n"
            + str(body).lstrip() + "\n")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return {"id": skill_id, "path": path, "title": str(title or skill_id)}


def set_skill_enabled(skills_dir, skill_id: str,
                      enabled: bool) -> dict:
    """Enable/disable a skill by id. The skill must exist; unknown
    ids error, never silently create a state entry."""
    if not any(e["id"] == skill_id for e in list_skills(skills_dir)):
        raise KeyError(f"Unknown skill: {skill_id!r}")
    state = _load_state(skills_dir)
    disabled = _disabled_ids(skills_dir)
    if enabled:
        disabled.discard(skill_id)
    else:
        disabled.add(skill_id)
    state["disabled"] = sorted(disabled)
    _save_state(skills_dir, state)
    return {"skill": skill_id, "enabled": enabled}


def export_skill(skills_dir, skill_id: str, dest: str | None = None) -> dict:
    """Return a skill's content; when ``dest`` is given, also copy
    the file there (parent dirs created). Nothing is invented: the
    exported text is the stored file, verbatim."""
    text = get_skill(skills_dir, skill_id)
    if dest is None:
        return {"skill": skill_id, "content": text}
    import shutil
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    shutil.copyfile(_skill_path(skills_dir, skill_id), dest)
    return {"skill": skill_id, "dest": dest}


def remove_skill(skills_dir, skill_id: str, confirm: bool = False) -> dict:
    """Delete a skill file. Requires explicit ``confirm`` (deletion
    is irreversible except via git); shipped skills deleted this way
    are gone until restored from the repo, which the return value
    states plainly."""
    if not confirm:
        raise ValueError(
            f"Removing skill {skill_id!r} needs confirm: true")
    path = _skill_path(skills_dir, skill_id)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Unknown skill: {skill_id!r}")
    os.remove(path)
    state = _load_state(skills_dir)
    disabled = _disabled_ids(skills_dir)
    disabled.discard(skill_id)
    state["disabled"] = sorted(disabled)
    _save_state(skills_dir, state)
    return {"removed": skill_id,
            "note": "restore shipped skills from the repo if needed"}


def propose_skill(skills_dir, skill_id: str, title: str,
                  body: str) -> dict:
    """Store a caller-supplied draft as a *proposal* (under
    ``proposals/`` inside the skills dir). Proposals are not listed
    as active skills and their content is the caller's draft,
    verbatim — nothing is generated or approved here."""
    if not str(body).strip():
        raise ValueError("Proposal body must not be empty")
    base = _resolve_dir(skills_dir)
    proposals_dir = os.path.join(base, "proposals")
    os.makedirs(proposals_dir, exist_ok=True)
    path = os.path.join(proposals_dir, skill_id + ".md")
    if not _SAFE_ID.match(skill_id):
        raise ValueError(f"Invalid skill id {skill_id!r}")
    if os.path.exists(path):
        raise ValueError(f"Proposal {skill_id!r} already exists")
    text = ("Provenance: User-proposed skill draft — NOT an active "
            "skill and NOT original BashCut text.\n\n# "
            + str(title or skill_id) + "\n\n" + str(body).lstrip() + "\n")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return {"proposal": skill_id, "path": path, "status": "pending"}


def search_skills(skills_dir, query):
    """Plain case-insensitive substring search over titles and bodies.

    Returns the same [{id, title, source}] entries as list_skills,
    limited to skills whose title or body contains ``query``. An
    empty query returns every skill.
    """
    needle = (query or "").strip().lower()
    base = _resolve_dir(skills_dir)
    results = []
    for entry in list_skills(base):
        if not needle:
            results.append(entry)
            continue
        try:
            body = get_skill(base, entry["id"])
        except (OSError, ValueError):
            continue
        if needle in entry["title"].lower() or needle in body.lower():
            results.append(entry)
    return results
