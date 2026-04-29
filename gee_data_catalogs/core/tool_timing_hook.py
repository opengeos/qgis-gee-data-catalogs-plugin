"""Per-step wall-clock timing hook for the AI Assistant.

Registers with the underlying Strands agent's hook registry to capture the
duration of every model (LLM) call AND every tool call in chronological
order. Each completion is logged to the QGIS Log Messages panel so users
can see exactly where the seconds in a long chat turn went, and the same
data is exposed as a list the AI Assistant panel renders next to the total
elapsed time.

The breakdown distinguishes "LLM call" entries (one per round-trip to the
provider) from tool entries, so you can tell whether a slow turn is many
fast LLM calls, one slow LLM call, or actual tool work.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from qgis.core import Qgis, QgsMessageLog
from strands.hooks import HookProvider, HookRegistry
from strands.hooks.events import (
    AfterModelCallEvent,
    AfterToolCallEvent,
    BeforeModelCallEvent,
    BeforeToolCallEvent,
)

PLUGIN_NAME = "GEE Data Catalogs"


def _tool_use_id(use: Any) -> Optional[str]:
    """Return the tool_use_id from a Strands tool_use dict, if present."""
    if not isinstance(use, dict):
        return None
    return use.get("toolUseId") or use.get("tool_use_id")


class ToolTimingHookProvider(HookProvider):
    """Strands hook provider that records per-step wall-clock durations.

    Captures both tool calls and LLM round-trips. Each completed step is
    appended to ``timings`` in chronological order with a ``kind`` field
    (``"tool"`` or ``"model"``) so callers can render a clear breakdown.
    """

    def __init__(self) -> None:
        self._tool_starts: Dict[str, float] = {}
        self._model_start: Optional[float] = None
        self._model_call_count: int = 0
        self.timings: List[Dict[str, Any]] = []

    def register_hooks(
        self, registry: HookRegistry, **kwargs: Any
    ) -> None:  # noqa: ARG002
        """Register before/after callbacks for tool and model events."""
        registry.add_callback(BeforeToolCallEvent, self._before_tool)
        registry.add_callback(AfterToolCallEvent, self._after_tool)
        registry.add_callback(BeforeModelCallEvent, self._before_model)
        registry.add_callback(AfterModelCallEvent, self._after_model)

    def _before_tool(self, event: BeforeToolCallEvent) -> None:
        """Record a monotonic start time keyed by tool_use_id."""
        use = event.tool_use
        tool_use_id = _tool_use_id(use)
        if tool_use_id is None:
            return
        self._tool_starts[tool_use_id] = time.monotonic()

    def _after_tool(self, event: AfterToolCallEvent) -> None:
        """Compute the elapsed time, log it, and append a timing record."""
        use = event.tool_use
        tool_use_id = _tool_use_id(use)
        name = str(use.get("name", "")) if isinstance(use, dict) else ""

        started = self._tool_starts.pop(tool_use_id, None) if tool_use_id else None
        elapsed = time.monotonic() - started if started is not None else None

        failed = event.exception is not None
        record: Dict[str, Any] = {
            "kind": "tool",
            "name": name,
            "duration": elapsed,
            "failed": failed,
        }
        self.timings.append(record)

        if elapsed is None:
            return

        if failed:
            QgsMessageLog.logMessage(
                f"Tool '{name}' failed after {elapsed:.2f}s: {event.exception}",
                PLUGIN_NAME,
                Qgis.MessageLevel.Warning,
            )
        else:
            QgsMessageLog.logMessage(
                f"Tool '{name}' completed in {elapsed:.2f}s",
                PLUGIN_NAME,
                Qgis.MessageLevel.Info,
            )

    def _before_model(self, event: BeforeModelCallEvent) -> None:  # noqa: ARG002
        """Record the start of an LLM round-trip."""
        self._model_start = time.monotonic()

    def _after_model(self, event: AfterModelCallEvent) -> None:
        """Compute LLM round-trip duration, log it, and append a record."""
        started = self._model_start
        self._model_start = None
        elapsed = time.monotonic() - started if started is not None else None

        self._model_call_count += 1
        name = f"LLM call #{self._model_call_count}"
        failed = event.exception is not None

        record: Dict[str, Any] = {
            "kind": "model",
            "name": name,
            "duration": elapsed,
            "failed": failed,
        }
        self.timings.append(record)

        if elapsed is None:
            return

        if failed:
            QgsMessageLog.logMessage(
                f"{name} failed after {elapsed:.2f}s: {event.exception}",
                PLUGIN_NAME,
                Qgis.MessageLevel.Warning,
            )
        else:
            QgsMessageLog.logMessage(
                f"{name} completed in {elapsed:.2f}s",
                PLUGIN_NAME,
                Qgis.MessageLevel.Info,
            )


def format_tool_timings(
    timings: List[Dict[str, Any]],
    total_elapsed: Optional[float] = None,
) -> str:
    """Render a per-step timing breakdown for the chat panel.

    Renders entries in chronological order (the order they completed) with
    LLM round-trips and tool calls interleaved so users can see whether a
    slow turn is dominated by model latency, by tool execution, or by
    framework overhead.

    Args:
        timings: List of {kind, name, duration, failed} records from
            :class:`ToolTimingHookProvider`.
        total_elapsed: Optional total chat turn duration in seconds. When
            provided, a final "Other" line is added showing the residual
            time inside ``agent.chat()`` that was not spent in any
            recorded step (typically Strands framework overhead).

    Returns:
        A multi-line string suitable for appending to the chat reply.
    """
    if not timings:
        return ""

    lines = ["Per-step timing:"]
    accounted = 0.0
    have_durations = False
    for record in timings:
        name = record.get("name") or "(unknown)"
        duration = record.get("duration")
        failed = record.get("failed")
        if duration is None:
            lines.append(f"  - {name}: n/a")
            continue
        have_durations = True
        accounted += duration
        suffix = " [failed]" if failed else ""
        lines.append(f"  - {name}: {duration:.2f}s{suffix}")

    if (
        total_elapsed is not None
        and have_durations
        and total_elapsed > accounted + 0.05
    ):
        other = total_elapsed - accounted
        lines.append(f"  - Other: {other:.2f}s")

    return "\n".join(lines)
