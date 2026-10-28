"""Knowledge store for agents (Windows port of the original's
knowledge.* commands).

The store lives inside project data under ``data["knowledge"]`` so it
is saved, backed up and undone together with the project — no separate
database file, no network, no model. Every mutation appends a history
entry holding a snapshot of the previous knowledge dict, which is what
``revert`` restores. Nothing here invents lesson/fact content: every
lesson, fact, pref, claim and proposal is supplied by the caller.

Status model (mirrors the original's approve/reject flow): lessons
and proposals start as ``proposed``; ``approve`` marks them active
(and, for proposals, applies their content); ``reject`` marks them
rejected. ``verdicts`` lists proposal outcomes.
"""

import copy
import uuid

_MAX_HISTORY = 200


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def ensure_knowledge(data: dict) -> dict:
    """Return the knowledge dict inside project ``data``, creating
    it (empty) when absent. The dict itself is stored in ``data`` so
    callers that mutate it are mutating the project."""
    knowledge = data.get("knowledge")
    if not isinstance(knowledge, dict):
        knowledge = {
            "lessons": [], "facts": {}, "prefs": {}, "claims": {},
            "proposals": [], "memo": "", "history": [],
        }
        data["knowledge"] = knowledge
    for key, default in (("lessons", []), ("facts", {}), ("prefs", {}),
                         ("claims", {}), ("proposals", []),
                         ("memo", ""), ("history", [])):
        if key not in knowledge:
            knowledge[key] = default
    return knowledge


def _mutate(knowledge: dict, action: str, detail: str, fn) -> dict:
    """Run ``fn`` (which mutates ``knowledge``) while recording a
    pre-mutation snapshot for revert. Returns fn's return value."""
    before = copy.deepcopy(knowledge)
    result = fn()
    knowledge.setdefault("history", []).append({
        "action": action, "detail": detail, "before": before})
    del knowledge["history"][: -_MAX_HISTORY]
    return result


def _find(lessons: list, lesson_id: str) -> dict:
    for lesson in lessons:
        if lesson.get("id") == lesson_id:
            return lesson
    raise KeyError(f"Bài học không rõ: {lesson_id!r}")


def _find_proposal(proposals: list, proposal_id: str) -> dict:
    for proposal in proposals:
        if proposal.get("id") == proposal_id:
            return proposal
    raise KeyError(f"Proposal không rõ: {proposal_id!r}")


# -- lessons ---------------------------------------------------------

def add_lesson(data: dict, text: str, title: str | None = None) -> dict:
    """Add a lesson in ``proposed`` status. Text is caller-supplied;
    empty text is refused, never replaced with invented content."""
    if not str(text).strip():
        raise ValueError("Nội dung bài học không được để trống")
    knowledge = ensure_knowledge(data)

    def _do():
        lesson = {"id": _new_id("lesson"), "title": title or "",
                  "text": str(text), "status": "proposed"}
        knowledge["lessons"].append(lesson)
        return lesson

    return _mutate(knowledge, "add_lesson", text[:80], _do)


def lessons(data: dict) -> list:
    return list(ensure_knowledge(data)["lessons"])


def get_lesson(data: dict, lesson_id: str) -> dict:
    return _find(ensure_knowledge(data)["lessons"], lesson_id)


def update_lesson(data: dict, lesson_id: str, text: str) -> dict:
    if not str(text).strip():
        raise ValueError("Nội dung bài học không được để trống")
    knowledge = ensure_knowledge(data)

    def _do():
        lesson = _find(knowledge["lessons"], lesson_id)
        lesson["text"] = str(text)
        return lesson

    return _mutate(knowledge, "update_lesson", lesson_id, _do)


def remove_lesson(data: dict, lesson_id: str) -> dict:
    knowledge = ensure_knowledge(data)

    def _do():
        lesson = _find(knowledge["lessons"], lesson_id)
        knowledge["lessons"].remove(lesson)
        return {"removed": lesson_id}

    return _mutate(knowledge, "remove_lesson", lesson_id, _do)


def approve_lesson(data: dict, lesson_id: str) -> dict:
    """Approve a lesson (any lesson, including one added directly)."""
    knowledge = ensure_knowledge(data)

    def _do():
        lesson = _find(knowledge["lessons"], lesson_id)
        lesson["status"] = "active"
        return lesson

    return _mutate(knowledge, "approve", lesson_id, _do)


def reject_lesson(data: dict, lesson_id: str) -> dict:
    knowledge = ensure_knowledge(data)

    def _do():
        lesson = _find(knowledge["lessons"], lesson_id)
        lesson["status"] = "rejected"
        return lesson

    return _mutate(knowledge, "reject", lesson_id, _do)


# -- facts / prefs / claims ------------------------------------------

def set_fact(data: dict, key: str, value: str) -> dict:
    if not str(key).strip():
        raise ValueError("Khóa fact không được để trống")
    knowledge = ensure_knowledge(data)

    def _do():
        knowledge["facts"][str(key)] = str(value)
        return {"key": str(key), "value": str(value)}

    return _mutate(knowledge, "set_fact", str(key), _do)


def facts(data: dict) -> dict:
    return dict(ensure_knowledge(data)["facts"])


def set_pref(data: dict, key: str, value: str) -> dict:
    if not str(key).strip():
        raise ValueError("Khóa pref không được để trống")
    knowledge = ensure_knowledge(data)

    def _do():
        knowledge["prefs"][str(key)] = str(value)
        return {"key": str(key), "value": str(value)}

    return _mutate(knowledge, "set_pref", str(key), _do)


def prefs(data: dict) -> dict:
    return dict(ensure_knowledge(data)["prefs"])


def set_claim(data: dict, key: str, statement: str) -> dict:
    if not str(key).strip():
        raise ValueError("Khóa claim không được để trống")
    knowledge = ensure_knowledge(data)

    def _do():
        knowledge["claims"][str(key)] = str(statement)
        return {"key": str(key), "statement": str(statement)}

    return _mutate(knowledge, "set_claim", str(key), _do)


def claims(data: dict) -> dict:
    return dict(ensure_knowledge(data)["claims"])


# -- memo ------------------------------------------------------------

def get_memo(data: dict) -> str:
    return ensure_knowledge(data).get("memo", "")


def set_memo(data: dict, text: str) -> dict:
    knowledge = ensure_knowledge(data)

    def _do():
        knowledge["memo"] = str(text)
        return {"memo": str(text)}

    return _mutate(knowledge, "set_memo", str(text)[:80], _do)


def split_memo(data: dict) -> dict:
    """Split the memo into lessons at blank lines. Each part becomes
    a ``proposed`` lesson; the memo itself is left unchanged."""
    knowledge = ensure_knowledge(data)
    memo = knowledge.get("memo", "")
    parts = [p.strip() for p in str(memo).split("\n\n") if p.strip()]
    if not parts:
        raise ValueError("Memo rỗng; không có gì để tách")

    def _do():
        added = []
        for part in parts:
            lesson = {"id": _new_id("lesson"), "title": "",
                      "text": part, "status": "proposed"}
            knowledge["lessons"].append(lesson)
            added.append(lesson)
        return {"added": [lesson["id"] for lesson in added]}

    return _mutate(knowledge, "split_memo", f"{len(parts)} parts", _do)


# -- proposals / verdicts --------------------------------------------

def propose(data: dict, kind: str, content) -> dict:
    """Store a caller-supplied proposal (kind: lesson/fact/pref/
    claim). Proposals never invent content: ``content`` is stored
    verbatim and only applied on approve."""
    if kind not in ("lesson", "fact", "pref", "claim"):
        raise ValueError(
            "Kind của proposal phải là lesson, fact, pref hoặc claim")
    knowledge = ensure_knowledge(data)

    def _do():
        proposal = {"id": _new_id("proposal"), "kind": kind,
                    "content": content, "status": "pending"}
        knowledge["proposals"].append(proposal)
        return proposal

    return _mutate(knowledge, "propose", f"{kind}", _do)


def proposals(data: dict) -> list:
    return list(ensure_knowledge(data)["proposals"])


def approve_proposal(data: dict, proposal_id: str) -> dict:
    """Approve a proposal and apply its content (lesson → active
    lesson; fact/pref/claim → stored under the proposal's key when
    content is a mapping with a key, else under the proposal id)."""
    knowledge = ensure_knowledge(data)

    def _do():
        proposal = _find_proposal(knowledge["proposals"], proposal_id)
        if proposal["status"] != "pending":
            raise ValueError(
                f"Proposal {proposal_id!r} đã là {proposal['status']}")
        proposal["status"] = "approved"
        content = proposal["content"]
        if proposal["kind"] == "lesson":
            text = content if isinstance(content, str) else \
                content.get("text", "")
            if not str(text).strip():
                raise ValueError("Proposal bài học không có nội dung")
            lesson = {"id": _new_id("lesson"), "title": "",
                      "text": str(text), "status": "active"}
            knowledge["lessons"].append(lesson)
            proposal["applied_as"] = lesson["id"]
        else:
            store = {"fact": knowledge["facts"],
                     "pref": knowledge["prefs"],
                     "claim": knowledge["claims"]}[proposal["kind"]]
            if isinstance(content, dict) and "key" in content:
                store[str(content["key"])] = str(content.get("value", ""))
            else:
                store[proposal_id] = str(content)
        return proposal

    return _mutate(knowledge, "approve_proposal", proposal_id, _do)


def reject_proposal(data: dict, proposal_id: str) -> dict:
    knowledge = ensure_knowledge(data)

    def _do():
        proposal = _find_proposal(knowledge["proposals"], proposal_id)
        if proposal["status"] != "pending":
            raise ValueError(
                f"Proposal {proposal_id!r} đã là {proposal['status']}")
        proposal["status"] = "rejected"
        return proposal

    return _mutate(knowledge, "reject_proposal", proposal_id, _do)


def verdicts(data: dict) -> list:
    """Proposal outcomes: every non-pending proposal with its
    verdict (approved/rejected)."""
    return [{"id": p["id"], "kind": p["kind"], "verdict": p["status"]}
            for p in ensure_knowledge(data)["proposals"]
            if p["status"] in ("approved", "rejected")]


def history(data: dict) -> list:
    """Mutation history without the stored snapshots (those are
    internal to revert)."""
    return [{"action": h.get("action"), "detail": h.get("detail")}
            for h in ensure_knowledge(data).get("history", [])]


def revert(data: dict, steps: int = 1) -> dict:
    """Restore the knowledge dict to its state ``steps`` mutations
    ago, using the stored snapshots. Reverting is itself recorded
    (without a snapshot, so it cannot be reverted twice over)."""
    if steps < 1:
        raise ValueError("steps phải ít nhất bằng 1")
    knowledge = ensure_knowledge(data)
    hist = knowledge.get("history", [])
    if len(hist) < steps:
        raise ValueError(
            f"Chỉ {len(hist)} mutation knowledge để hoàn tác")
    target = hist[-steps]["before"]
    knowledge.clear()
    knowledge.update(copy.deepcopy(target))
    knowledge.setdefault("history", []).append(
        {"action": "revert", "detail": f"{steps} step(s)"})
    del knowledge["history"][: -_MAX_HISTORY]
    return {"reverted_steps": steps}


def migrate(data: dict) -> dict:
    """Migrate a legacy knowledge shape: a top-level
    ``knowledge_notes`` string becomes the memo. Anything else is a
    no-op reported honestly (never a fake migration)."""
    knowledge = ensure_knowledge(data)
    legacy = data.pop("knowledge_notes", None)
    if legacy is None:
        return {"migrated": False,
                "reason": "không có knowledge_notes cũ"}
    if knowledge.get("memo"):
        data["knowledge_notes"] = legacy
        return {"migrated": False,
                "reason": "memo đã đặt; giữ nguyên các ghi chú cũ"}
    knowledge["memo"] = str(legacy)
    knowledge.setdefault("history", []).append(
        {"action": "migrate", "detail": "knowledge_notes -> memo"})
    return {"migrated": True}
