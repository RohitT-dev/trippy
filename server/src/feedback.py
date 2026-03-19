"""Human-feedback bridge between CrewAI flow threads and the frontend.

When CrewAI's @human_feedback decorator calls Python's built-in input() to
collect human input, our monkey-patched replacement blocks the flow thread
on a per-session Queue and waits for the frontend to POST feedback via
  POST /api/plan/{session_id}/feedback

Usage from main.py:
    import src.feedback as feedback_mod        # patches input() on import

    feedback_mod.register_session(session_id)  # before starting thread

    def _run():
        feedback_mod.set_thread_session(session_id)
        try:
            flow.kickoff()
        finally:
            feedback_mod.cleanup_session(session_id)

Usage from the feedback endpoint:
    success = feedback_mod.submit_feedback(session_id, text)
"""

import builtins
import queue
import threading
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------

#: Maps session_id → Queue[str] where a single feedback text will be placed.
_queues: dict[str, queue.Queue] = {}
_lock = threading.Lock()

#: Thread-local storage so patched input() knows which session it is serving.
_local = threading.local()

#: Preserve the original built-in before we replace it.
_real_input = builtins.input


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def register_session(session_id: str) -> None:
    """Create a feedback slot for *session_id*.  Call BEFORE starting the thread."""
    with _lock:
        _queues[session_id] = queue.Queue(maxsize=1)
    logger.debug("feedback: registered session %s", session_id)


def set_thread_session(session_id: str) -> None:
    """Associate the CURRENT THREAD with *session_id*.  Call from inside the thread."""
    _local.session_id = session_id


def submit_feedback(session_id: str, text: str) -> bool:
    """Deliver *text* to the flow thread waiting for session *session_id*.

    Returns True on success, False if there is no pending slot.
    """
    with _lock:
        q = _queues.get(session_id)
    if q is None:
        logger.warning("feedback: no pending slot for session %s", session_id)
        return False
    try:
        q.put_nowait(text)
        logger.info("feedback: delivered to session %s", session_id)
        return True
    except queue.Full:
        logger.warning("feedback: queue full for session %s (duplicate submit?)", session_id)
        return False


def cleanup_session(session_id: str) -> None:
    """Remove the feedback slot for *session_id*.  Call from thread's finally block."""
    with _lock:
        _queues.pop(session_id, None)
    logger.debug("feedback: cleaned up session %s", session_id)


def has_pending_slot(session_id: str) -> bool:
    """Return True if there is an active (unfilled) feedback slot."""
    with _lock:
        q = _queues.get(session_id)
    return q is not None and q.empty()


def wait_for_feedback(session_id: str, timeout: int = 600) -> str:
    """Block the calling thread until frontend delivers feedback for *session_id*.

    Unlike submit_feedback this is safe to call from ANY thread — it only
    needs the session_id, not thread-local state.
    Returns the feedback text, or ``"approve"`` on timeout.
    """
    with _lock:
        q = _queues.get(session_id)
    if q is None:
        logger.warning("wait_for_feedback: no slot for session %s; defaulting to approve", session_id)
        return "approve"
    logger.info("feedback: blocking on queue for session %s (timeout=%ds)", session_id, timeout)
    try:
        text = q.get(timeout=timeout)
        logger.info("feedback: received text for session %s", session_id)
        return text
    except queue.Empty:
        logger.warning("feedback: timeout for session %s; defaulting to approve", session_id)
        return "approve"


# ---------------------------------------------------------------------------
# Monkey-patch builtins.input — installed once at module import time
# ---------------------------------------------------------------------------

def _patched_input(prompt: object = "") -> str:
    """Replacement for built-in input().

    When called from a flow thread that registered a session, blocks on the
    per-session Queue and returns whatever text the frontend submitted.
    Falls back to the original input() for all other callers.
    """
    session_id: str | None = getattr(_local, "session_id", None)
    if session_id is not None:
        with _lock:
            q = _queues.get(session_id)
        if q is not None:
            logger.info("feedback: flow thread blocked, waiting for session %s", session_id)
            try:
                text = q.get(timeout=600)  # wait up to 10 minutes
                logger.info("feedback: received text for session %s", session_id)
                return text
            except queue.Empty:
                logger.warning(
                    "feedback: 10-minute timeout for session %s; using default 'approve'",
                    session_id,
                )
                return "approve"
    return _real_input(prompt)


# Patch once at import time so all subsequent calls to input() go through here.
builtins.input = _patched_input
