"""Hard wall-time cap on a single layout call.

Some layout backends can wedge in ways ``signal.alarm`` cannot break:
OGDF holds the GIL inside C++ for the duration of a call (so a Python
signal handler never runs), and HOLA shells out to a binary whose own
timeout we've seen ignored. The only reliable cap is to run the call
in a child process and ``terminate()``/``kill()`` it on overrun.

We use a forked context — cheap on Linux (~5ms) and, crucially, the
child inherits the parent's already-JIT'd cppyy/OGDF state via COW.
:func:`prewarm` runs once per layout in the parent before the per-graph
loop so that inheritance actually buys us anything: without it, every
forked child would re-pay the ~5s cppyy compile cost.

Result is sent back over a ``Pipe`` as ``("ok", payload)`` or
``("exc", BaseException)`` so the parent re-raises the same exception
type the in-process call would have raised — preserving e.g.
``NotApplicable`` semantics.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import signal
from typing import Any, Tuple

import networkx as nx


class LayoutTimeout(Exception):
    """Raised when a layout call exceeds its ``timeout_s`` budget."""


_PREWARM_TIMEOUT_S = 30.0
_warmed: set[str] = set()


def prewarm(layout) -> None:
    """Warm the layout's backend state in the parent process so per-call
    forks inherit it via copy-on-write.

    No-op for layouts without ``timeout_s`` set (no fork overhead to
    amortise) and for layouts already warmed in this process. Best-
    effort: any exception (NotApplicable, missing binary, etc.) is
    swallowed — per-graph calls will surface real failures.
    """
    if layout.timeout_s is None or layout.name in _warmed:
        return
    _warmed.add(layout.name)
    G = nx.complete_graph(4)
    if not layout.applies_to(G):
        return
    # Cap the warmup so a buggy backend can't wedge the whole stage
    # before any per-graph timeout has a chance to fire. SIGALRM is
    # main-thread-only; that matches where _run_layout runs.
    def _on_alarm(*_: Any) -> None:
        raise TimeoutError(f"warmup exceeded {_PREWARM_TIMEOUT_S}s")
    old = signal.signal(signal.SIGALRM, _on_alarm)
    signal.alarm(int(_PREWARM_TIMEOUT_S))
    try:
        layout.fn(G, 0)
    except Exception:
        pass
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def _worker(conn, fn, G: nx.Graph, seed: int) -> None:
    # Become our own session/process-group leader. The parent kills the
    # whole group on timeout, which catches grandchildren that the
    # layout fn might have spawned (HOLA's hola_cli, dot-ortho's dot
    # binary, etc.) — without this, terminating the worker leaves those
    # binaries orphaned to init, where we've seen them sit at 100% CPU
    # for an hour after their parent layout call timed out.
    try:
        os.setsid()
    except OSError:
        pass
    try:
        result = fn(G, seed)
    except BaseException as e:  # noqa: BLE001 — re-raise in parent
        try:
            conn.send(("exc", e))
        except Exception:
            # If pickling the exception itself fails, send a stand-in so
            # the parent doesn't hang on recv().
            conn.send(("exc", RuntimeError(
                f"{type(e).__name__}: {e}")))
    else:
        try:
            conn.send(("ok", result))
        except Exception as e:
            conn.send(("exc", RuntimeError(
                f"result not picklable: {type(e).__name__}: {e}")))
    finally:
        conn.close()


def _killpg(pid: int, sig: int) -> None:
    """Best-effort ``killpg`` — silent if the group has already exited."""
    try:
        os.killpg(pid, sig)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def call_with_timeout(fn, G: nx.Graph, seed: int,
                       timeout_s: float) -> Tuple[Any, Any]:
    """Run ``fn(G, seed)`` in a forked subprocess, killing it on overrun.

    Re-raises any exception ``fn`` raised. Raises :class:`LayoutTimeout`
    if the wall clock exceeds ``timeout_s``. Returns whatever ``fn``
    returned otherwise (typically ``(positions, bends)``).
    """
    ctx = mp.get_context("fork")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    p = ctx.Process(target=_worker,
                     args=(child_conn, fn, G, seed))
    p.start()
    # Close the child end in the parent so recv() unblocks if the child
    # exits without sending (e.g. SIGKILL'd before send()).
    child_conn.close()
    p.join(timeout_s)
    if p.is_alive():
        # Signal the whole process group, not just the worker pid,
        # so any subprocess the layout fn spawned (hola_cli, dot, etc.)
        # dies with it. The worker called os.setsid() so its pid is
        # also its pgid.
        _killpg(p.pid, signal.SIGTERM)
        p.join(1.0)
        if p.is_alive():
            _killpg(p.pid, signal.SIGKILL)
            p.join()
        try:
            parent_conn.close()
        except Exception:
            pass
        raise LayoutTimeout(
            f"layout exceeded {timeout_s:.1f}s budget")
    try:
        if parent_conn.poll(0):
            kind, payload = parent_conn.recv()
        else:
            raise RuntimeError(
                f"worker exited rc={p.exitcode} without sending a result")
    finally:
        parent_conn.close()
    if kind == "exc":
        raise payload
    return payload
