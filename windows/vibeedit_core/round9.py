"""Round 9: run-panel actions, plugin show-view, and the backdrop's
tool-side helpers for the Windows port.

Every function here works only with data the project already holds
plus stdlib. Nothing here invents AI output.

Original specs (read before coding, VibeEdit Swift tree, read-only):
- ``UIAction.swift`` + ``ProjectDocument+UIActions.swift``:
  ``run.dismiss`` / ``run.toggle`` / ``run.follow`` /
  ``run.fix-issues`` / ``run.another-recipe`` are UIAction run-panel
  actions. Round 8 left them honest ("no run panel headless").
  Round 9 re-examines that: the panel widget is a viewer concern,
  but whether it is shown, dismissed or following is plain project
  state, so dismiss/toggle/follow are implemented as real persisted
  state (see ``project.run_panel_snapshot``), reported by
  ``run.checklist``. Fix-issues and another-recipe in the original
  *deliver* a follow-up request to the open agent; headless there
  is no agent session to deliver to — but the MCP caller IS the
  agent, so these tools return the exact follow-up request text
  (verbatim ``AgentFollowUp`` wording) for the caller to execute,
  gated exactly like the original (a run result must exist;
  fix-issues additionally needs issues left). They never claim
  delivery.
- ``ProjectDocument+PluginViews.swift``: ``plugins.show-view``
  validates the plugin (panel plugin: has views, ready) and the
  view, shows it where it lives (panel / dock / sheet / window;
  inspector views need nothing opened — they follow the
  selection), and returns plugin + view + location. Headless the
  "showing" is recorded as the project's currently-shown view, so
  later calls see the same shown view; ``plugins.view`` stays the
  render path. Inspector placement returns shown=False, matching
  the original's no-op for inspector views.
- ``clip.backdrop`` (P3-J7) is implemented in ``project.py``
  (``validate_backdrop`` / ``set_backdrop``) and ``render.py``;
  this module holds no backdrop code.
"""

from __future__ import annotations

from .plugins import _disabled_ids, _manifest_view, load_plugins
from .project import run_panel_snapshot


# ---------------------------------------------------------------------------
# run panel state — dismiss / toggle / follow
# ---------------------------------------------------------------------------

def _panel(proj) -> dict:
    """The project's run-panel state dict, created on first use."""
    return proj.data.setdefault("run_panel", {})


def run_panel_dismiss(proj) -> dict:
    """Close the run panel until it is shown again (original
    ``run.dismiss``: dismissed = current run, shown_by_user = False).
    Returns the panel snapshot plus rev."""
    panel = _panel(proj)
    panel["dismissed"] = True
    panel["shown_by_user"] = False
    proj._bump()
    snap = run_panel_snapshot(proj.data)
    snap["rev"] = proj.rev
    return snap


def run_panel_toggle(proj) -> dict:
    """Open or close the run panel (original ``run.toggle``: if
    visible dismiss, else show). Returns the snapshot plus the
    action taken and rev."""
    before = run_panel_snapshot(proj.data)
    panel = _panel(proj)
    if before["visible"]:
        panel["dismissed"] = True
        panel["shown_by_user"] = False
        action = "dismissed"
    else:
        panel["dismissed"] = False
        panel["shown_by_user"] = True
        action = "shown"
    proj._bump()
    snap = run_panel_snapshot(proj.data)
    snap["rev"] = proj.rev
    snap["action"] = action
    return snap


def run_panel_follow(proj, on=None) -> dict:
    """Follow the agent's run or stop following it (original
    ``run.follow`` toggles follow mode; the timeline scrolls to
    where the agent works). Headless there is no viewer to scroll,
    so this stores the follow flag itself — the state the panel
    reads — and says so; it never claims scrolling happened.
    Without ``on`` the flag toggles, like the original."""
    panel = _panel(proj)
    if on is None:
        panel["follow"] = not bool(panel.get("follow"))
    else:
        panel["follow"] = bool(on)
    proj._bump()
    snap = run_panel_snapshot(proj.data)
    snap["rev"] = proj.rev
    return snap


# ---------------------------------------------------------------------------
# run follow-ups — fix-issues / another-recipe request texts
# ---------------------------------------------------------------------------

def _require_run_result(proj) -> dict:
    """The original gates both follow-ups on runPanel.result; here
    the stored review run is the result (see Project.run_review).
    Without one there is nothing to follow up on."""
    review = proj.data.get("review")
    if not review or review.get("status") not in (
            "run", "verified", "accepted"):
        raise ValueError(
            "No run result yet; run a review first "
            "(vibeedit_review_run)")
    return review


def run_fix_issues(proj, output: str | None = None) -> dict:
    """Draft the result card's Fix remaining issues request.

    Original ``fixRunIssues``: the open review issues to the
    agent, then the same export again. Gated on a run result with
    issues left. The request text below is verbatim
    ``AgentFollowUp.fixIssues`` wording (``VibeEdit/VibeEdit/Core/
    Agent/AgentFollowUp.swift``): errors/warnings are counted fresh
    from the project's validation (real, current numbers, never
    the stale stored count), output is the last export path when
    the caller supplies one. One honest narrowing: the Windows
    ``Project.validate()`` reports errors only (its dict has no
    warnings key — ``run_review`` already defaults them to []),
    so the warnings count in the request is always 0 in this
    build. Headless there is no agent session to deliver to, so
    the request is RETURNED for the calling agent (the MCP
    caller) to execute — delivery is never claimed.
    """
    _require_run_result(proj)
    validation = proj.validate()
    errors = len(validation.get("errors", []))
    warnings = len(validation.get("warnings", []))
    if errors + warnings == 0:
        raise ValueError(
            "No review issues left to fix; the result card's "
            "Fix remaining issues needs issuesLeft > 0")
    exported = f"The export is done ({output}). " if output else ""
    request = (
        exported
        + f"The review still shows {errors} errors and {warnings} "
        + "warnings on the current timeline. Fix them: review run "
        + "--summary, one labelled edit per issue, prove each with "
        + "review verify, and accept with a reason only what cannot "
        + "be fixed. Then export again with the same settings and "
        + "say in two lines what changed.")
    return {"errors": errors, "warnings": warnings,
            "output": output, "request": request,
            "delivered": False,
            "note": "Headless: no agent session exists to deliver "
            "this to, so the request is returned for the calling "
            "agent to execute; delivery is not claimed."}


def run_another_recipe(proj) -> dict:
    """Draft the result card's Try another recipe request.

    Original ``tryAnotherRecipe``: a new version with another
    recipe, this one kept. Gated on a run result. The current
    recipe skill comes from the plan (``plan.recipe`` may be a
    dict with ``skill`` — the original's shape — or a plain
    string); without one the no-current-recipe wording is used.
    The request text is verbatim ``AgentFollowUp.anotherRecipe``
    wording. As with fix-issues, it is returned for the calling
    agent to execute, never claimed delivered.
    """
    _require_run_result(proj)
    plan = proj.data.get("plan") or {}
    recipe = plan.get("recipe")
    if isinstance(recipe, dict):
        current = recipe.get("skill")
    elif isinstance(recipe, str):
        current = recipe
    else:
        current = None
    if current:
        pick = (
            "Make another version of this video with a different "
            f"recipe than {current}: pick the one that best fits "
            "the footage and the brief, and say why in one line.")
    else:
        pick = (
            "Make another version of this video with a recipe: "
            "pick the one that best fits the footage and the "
            "brief, and say why in one line.")
    request = (
        pick + " Keep this version as it is (project derive for "
        "the new one), plan the new version from the recipe, "
        "edit, review and export it like this one.")
    return {"current_recipe": current, "request": request,
            "delivered": False,
            "note": "Headless: no agent session exists to deliver "
            "this to, so the request is returned for the calling "
            "agent to execute; delivery is not claimed."}


# ---------------------------------------------------------------------------
# plugins.show-view
# ---------------------------------------------------------------------------

def show_plugin_view(proj, plugin: str, view_id: str,
                     plugins_dir=None) -> dict:
    """Show a plugin view (original ``plugins.show-view``).

    Validates like the original's panelPlugin: the plugin must be
    known and declare views, and must be ready (enabled — a
    disabled plugin is refused, as apply_plugin refuses it). The
    view must be one of the manifest's views. Returns plugin +
    view + location (the manifest's placement, default panel).
    Inspector views follow the selection in the original, so
    there is nothing to open: they return shown=False and change
    no state. Other placements record the view as the project's
    currently-shown view (``data['plugin_views_shown']``), so
    later calls observe the same shown view — that recorded state
    is the headless form of "showing" it.
    """
    plugins = load_plugins(plugins_dir)
    if plugin not in plugins or plugins[plugin].get("_errors"):
        raise KeyError(f"Unknown plugin: {plugin!r}")
    info = plugins[plugin]
    views = info.get("manifest_views") or []
    if not views:
        raise ValueError(
            f"Plugin {plugin!r} has no views; see plugins list "
            "--views")
    if plugin in _disabled_ids(plugins_dir):
        raise ValueError(
            f"Plugin {plugin!r} is disabled; enable it first")
    view = _manifest_view(info, view_id)
    location = view.get("placement", "panel")
    if location == "inspector":
        return {"plugin": plugin, "view": view_id,
                "location": "inspector", "shown": False,
                "note": "Inspector views follow the selection; "
                "there is nothing to open."}
    shown = proj.data.setdefault("plugin_views_shown", {})
    key = f"{plugin}/{view_id}"
    proj._bump()
    shown[key] = {"plugin": plugin, "view": view_id,
                  "location": location, "rev": proj.rev}
    return {"plugin": plugin, "view": view_id,
            "location": location, "shown": True, "rev": proj.rev}
