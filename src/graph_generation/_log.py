"""Shared timing + progress helpers used across stages.

The stages are noisy on purpose — corpus runs take hours and going
silent for any single span > a few minutes is what makes failures hard
to diagnose. Use :func:`stopwatch` for elapsed measurement and
:func:`fmt_dur` for the consistent ``Xh Ym Zs`` rendering everywhere.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Callable, Iterator


def fmt_dur(seconds: float) -> str:
    """Render a duration in the format used by every stage's logs.

    < 0.1s → milliseconds; < 60s → fractional seconds; minutes/hours
    otherwise. The compact form keeps log lines aligned even when
    durations span 5 orders of magnitude.
    """
    if seconds < 0.1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m{s:02d}s"


@contextmanager
def stopwatch() -> Iterator[Callable[[], float]]:
    """Context manager yielding an ``elapsed()`` callable.

    Usage::

        with stopwatch() as elapsed:
            do_work()
        print(f"done in {fmt_dur(elapsed())}")

    Reading ``elapsed()`` after the block ends still returns the final
    duration — handy when you want to log after the work returns.
    """
    t0 = time.perf_counter()
    final: list[float] = []
    def elapsed() -> float:
        return final[0] if final else time.perf_counter() - t0
    try:
        yield elapsed
    finally:
        final.append(time.perf_counter() - t0)
