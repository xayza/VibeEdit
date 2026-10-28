"""Portable project-file lock (round 25).

Round 22 fixed the SEQUENTIAL rev-sync interleave (MCP edit then web
edit, or the reverse, both survive via refresh_from_disk when disk rev
> RAM rev). What remained was TRUE SIMULTANEOUS writes: if the web app
and an external MCP agent write the same project file at the same
instant, both read rev N, both mutate, both write rev N+1, and one
update is silently lost. save_project() is already atomic (temp file +
os.replace), so the file is never torn — but atomicity of the WRITE
does not make the READ-MODIFY-WRITE sequence atomic. This lock does:
every project write path holds it across [refresh, mutate, save, rev
bump], so two writers serialize instead of racing.

Portability: the lock is a plain file created with O_CREAT|O_EXCL, so
it works on Windows and Linux with stdlib only — no fcntl (POSIX-only)
and no msvcrt (Windows-only). The lock file lives next to the project
file as ``<project>.lock`` (e.g. ``project.json.lock``); the projects/
folder is gitignored, so lock files never reach the repo.

Rules, all deliberate:
- Held ONLY around the short critical section (refresh, mutate, save).
  It is never held across renders, exports, transcription, or network
  calls: long-running tools run outside the lock (see
  MCPServer.LONG_RUNNING_TOOLS and State.apply's transcribe bypass),
  so a minutes-long render can never wedge project writes.
- Bounded wait: acquisition retries until ``timeout`` (default 10s)
  and then raises ProjectLockTimeout loudly — a writer that cannot
  get the lock NEVER silently overwrites.
- Stale detection: a lock file older than ``stale_after`` (default
  60s) is treated as abandoned (its holder crashed) and removed so a
  dead holder cannot wedge the app forever. 60s is far above any real
  critical section (a project JSON save is milliseconds, even for a
  large project), so a live holder is never mistaken for stale.
- Ownership on release: the lock file carries a pid+uuid token and
  release removes it only when the content still matches, so a writer
  whose lock was stolen as stale cannot delete the new owner's lock.
- Re-entrant within one thread: a handler that calls back into a
  locked entry point on the SAME thread (e.g. vibeedit_plan_apply
  dispatching to vibeedit_timeline_apply through MCPServer.call) just
  deepens a per-thread count instead of waiting out its own timeout;
  the file itself is removed only when the outermost holder
  releases. A different thread still waits on the file, so
  cross-thread and cross-process exclusion are unchanged.

What this does NOT cover (documented, not hidden): two writers in the
same instant where one of them is a long-running tool running outside
the lock (transcription saves, project_open's one-time migration
save); those keep the round-22 sequential behaviour (refresh first)
and remain last-writer-wins only if they truly overlap a locked
write. project_create targets a fresh folder, so it needs no lock.
"""

import os
import threading
import time
import uuid


class ProjectLockTimeout(TimeoutError):
    """Raised when the project lock cannot be acquired in time.

    Subclasses TimeoutError so callers can catch either. The message
    names the lock file and the timeout so the user can tell a
    genuinely busy project (another writer is active) from a wedged
    one (a stale lock that should have been reaped).
    """


# In-process re-entrancy registry: lock path -> [thread ident, depth,
# token]. A handler that calls back into a locked entry point on the
# SAME thread (e.g. vibeedit_plan_apply dispatching to
# vibeedit_timeline_apply through MCPServer.call) must not wait out
# its own timeout: the outer acquisition already serializes this
# thread against other processes, so re-entry just deepens the count.
# A DIFFERENT thread still waits on the file itself, so cross-thread
# and cross-process mutual exclusion are unchanged. The registry is
# consulted before any stale reap, so a live in-process holder is
# never reaped by another thread of the same process.
_ACTIVE: dict[str, list] = {}
_ACTIVE_GUARD = threading.Lock()


class ProjectFileLock:
    """Cross-process mutex for one project file, via O_EXCL create."""

    def __init__(self, project_path: str, timeout: float = 10.0,
                 stale_after: float = 60.0, poll: float = 0.05):
        if not project_path:
            raise ValueError("ProjectFileLock needs a project path")
        self.project_path = os.path.abspath(project_path)
        self.lock_path = self.project_path + ".lock"
        self.timeout = float(timeout)
        self.stale_after = float(stale_after)
        self.poll = float(poll)
        self._token: str | None = None
        self._reentrant = False

    @property
    def locked(self) -> bool:
        return self._token is not None

    def acquire(self) -> None:
        # Re-entrant fast path: this thread already holds this path.
        with _ACTIVE_GUARD:
            entry = _ACTIVE.get(self.lock_path)
            if entry is not None and entry[0] == threading.get_ident():
                entry[1] += 1
                self._token = entry[2]
                self._reentrant = True
                return
        token = f"{os.getpid()}:{uuid.uuid4().hex}"
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                fd = os.open(self.lock_path,
                             os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if self._is_stale():
                    try:
                        os.remove(self.lock_path)
                    except OSError:
                        pass  # lost the race to remove; retry below
                    continue
                if time.monotonic() >= deadline:
                    raise ProjectLockTimeout(
                        f"Could not acquire project lock "
                        f"{self.lock_path} within {self.timeout:g}s: "
                        f"another writer is active (or a stale lock "
                        f"younger than {self.stale_after:g}s). "
                        f"Nothing was written.")
                time.sleep(self.poll)
                continue
            try:
                os.write(fd, token.encode("utf-8"))
            finally:
                os.close(fd)
            with _ACTIVE_GUARD:
                _ACTIVE[self.lock_path] = [threading.get_ident(), 1,
                                           token]
            self._token = token
            self._reentrant = False
            return

    def _is_stale(self) -> bool:
        # Never reap a lock a live thread of this process holds, even
        # if its mtime aged past the threshold (e.g. a paused thread).
        with _ACTIVE_GUARD:
            if self.lock_path in _ACTIVE:
                return False
        try:
            age = time.time() - os.path.getmtime(self.lock_path)
        except OSError:
            return False  # gone already; the create retry will win
        return age > self.stale_after

    def release(self) -> None:
        token, self._token = self._token, None
        if token is None:
            return
        with _ACTIVE_GUARD:
            entry = _ACTIVE.get(self.lock_path)
            if entry is not None and entry[0] == threading.get_ident():
                entry[1] -= 1
                if entry[1] > 0:
                    return  # outer acquisition still holds the file
                del _ACTIVE[self.lock_path]
        try:
            with open(self.lock_path, encoding="utf-8") as fh:
                current = fh.read()
        except OSError:
            return  # already gone (stolen as stale, or removed)
        if current == token:
            try:
                os.remove(self.lock_path)
            except OSError:
                pass

    def __enter__(self) -> "ProjectFileLock":
        self.acquire()
        return self

    def __exit__(self, *exc) -> bool:
        self.release()
        return False
