"""Run a generator in a persistent worker subprocess with a wall-clock
timeout, cleanly killing and respawning the worker when a timeout fires.

Why not `ProcessPoolExecutor`: its `shutdown(wait=False)` does not
forcibly kill a stuck child; on Windows, LFR-style silent hangs leave
zombie workers behind and subsequent pool spawns slow the host down
until the next spawn itself times out. We need `Process.terminate()`
semantics, so this module talks to a single spawned worker via request
and response queues.

Protocol:
    parent -> worker:  (generator_name, n, seed)  OR  None (sentinel to stop)
    worker -> parent:  ("ready",) on startup; ("ok", (G, params)) on success;
                       ("exc", exception) on failure

On timeout the parent calls `Process.terminate()` (plus `.kill()` if
still alive) and discards the worker; the next `run()` spawns a fresh
one. Exception types are pickled across the queue boundary; NetworkX
errors survive the round-trip.
"""

from __future__ import annotations

import multiprocessing as mp
import queue
from typing import Any, Dict, Optional, Tuple

import networkx as nx
import numpy as np


_WARMUP_TIMEOUT_S = 30.0


class GuardedRunner:
    """Single persistent worker with controllable lifecycle."""

    def __init__(self) -> None:
        self._ctx = mp.get_context("spawn")
        self._proc: Optional[mp.process.BaseProcess] = None
        self._req_q: Optional[mp.Queue] = None
        self._resp_q: Optional[mp.Queue] = None

    # ---------- lifecycle ----------

    def _ensure_worker(self) -> None:
        if self._proc is not None and self._proc.is_alive():
            return
        self._force_kill()  # clean up any partial state
        self._req_q = self._ctx.Queue()
        self._resp_q = self._ctx.Queue()
        self._proc = self._ctx.Process(
            target=_worker_loop,
            args=(self._req_q, self._resp_q),
            daemon=True,
        )
        self._proc.start()
        # Wait for readiness signal so the first real call doesn't pay
        # module-import cost inside a user-facing timeout window.
        try:
            signal = self._resp_q.get(timeout=_WARMUP_TIMEOUT_S)
        except queue.Empty:
            self._force_kill()
            raise RuntimeError(
                f"guarded worker did not warm up in {_WARMUP_TIMEOUT_S}s"
            )
        if signal != "ready":
            self._force_kill()
            raise RuntimeError(f"guarded worker sent unexpected startup signal: {signal!r}")

    def _force_kill(self) -> None:
        if self._proc is not None:
            if self._proc.is_alive():
                self._proc.terminate()
                self._proc.join(2.0)
            if self._proc.is_alive():
                self._proc.kill()
                self._proc.join(1.0)
            try:
                self._proc.close()
            except (ValueError, AttributeError):
                pass
        self._proc = None
        self._req_q = None
        self._resp_q = None

    def close(self) -> None:
        if self._proc is not None and self._proc.is_alive() and self._req_q is not None:
            try:
                self._req_q.put(None)  # graceful sentinel
                self._proc.join(2.0)
            except Exception:
                pass
        self._force_kill()

    # ---------- main entry ----------

    def run(
        self,
        generator_name: str,
        n: int,
        seed: int,
        timeout_s: float,
    ) -> Tuple[nx.Graph, Dict[str, Any]]:
        self._ensure_worker()
        assert self._req_q is not None and self._resp_q is not None

        self._req_q.put((generator_name, n, seed))
        try:
            kind, payload = self._resp_q.get(timeout=timeout_s)
        except queue.Empty:
            self._force_kill()
            raise RuntimeError(
                f"generator {generator_name!r} exceeded {timeout_s}s timeout"
            )

        if kind == "ok":
            return payload
        if kind == "exc":
            # re-raise with original type
            raise payload
        # programmer error
        raise RuntimeError(f"unexpected worker response: {kind!r}")


def _worker_loop(req_q: "mp.Queue", resp_q: "mp.Queue") -> None:
    # warm the module chain so the first real call is fast
    from graph_generation.generators import REGISTRY  # noqa: F401
    resp_q.put("ready")

    while True:
        try:
            req = req_q.get()
        except (EOFError, OSError):
            break
        if req is None:
            break
        generator_name, n, seed = req
        try:
            gen = next(g for g in REGISTRY if g.name == generator_name)
            rng = np.random.default_rng(seed)
            G, params = gen.generate(n, rng)
            resp_q.put(("ok", (G, params)))
        except BaseException as e:  # anything — send it back
            try:
                resp_q.put(("exc", e))
            except Exception:
                # if the exception can't cross the queue, at least report something
                resp_q.put(("exc", RuntimeError(f"worker: {type(e).__name__}: {e}")))


# ---------- singleton convenience ----------

_runner = GuardedRunner()


def guarded_generate(
    generator_name: str,
    n: int,
    seed: int,
    timeout_s: float = 5.0,
) -> Tuple[nx.Graph, Dict[str, Any]]:
    return _runner.run(generator_name, n, seed, timeout_s)


def close_guarded_pool() -> None:
    _runner.close()
