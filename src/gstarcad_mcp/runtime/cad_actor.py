"""Dedicated COM actor: one Windows thread owns all COM access (guideline 10)."""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any

from gstarcad_mcp.errors import (
    CAD_NOT_RESPONDING,
    CAD_OPERATION_TIMEOUT,
    CAD_QUEUE_FULL,
    INTERNAL_ERROR,
    ExpectedCadError,
)
from gstarcad_mcp.runtime.command import CadCommand
from gstarcad_mcp.runtime.health import RuntimeState
from gstarcad_mcp.util.json import assert_wire_safe

logger = logging.getLogger(__name__)

_STOP = object()


@dataclass
class WorkItem:
    command: CadCommand
    result_future: Future
    cancel_requested: threading.Event


class ActorRuntimeState:
    """Actor-thread-owned state: the Gcad session plus the registry."""

    def __init__(self, cad: Any, registry: Any, config: Any, extras: dict[str, Any] | None = None):
        self.cad = cad
        self.registry = registry
        self.config = config
        self.extras = extras or {}


class CadActor:
    def __init__(
        self,
        config: Any,
        dispatcher: Any = None,
        *,
        cad_factory: Callable[[], Any] | None = None,
        registry: Any | None = None,
        runtime_state_factory: Callable[[Any, Any, Any], ActorRuntimeState] | None = None,
    ) -> None:
        self._config = config
        self._dispatcher = dispatcher
        self._cad_factory = cad_factory
        self._registry = registry
        self._runtime_state_factory = runtime_state_factory
        max_depth = getattr(config, "max_queue_depth", 128)
        self._queue: queue.Queue = queue.Queue(maxsize=max_depth)
        self._thread: threading.Thread | None = None
        self._startup: Future = Future()
        self._state_lock = threading.Lock()
        self._state = RuntimeState.NEW
        self._runtime: ActorRuntimeState | None = None
        self.queue_wait_count = 0
        self.executed_count = 0
        self.error_count = 0

    # -- state observation -------------------------------------------------

    @property
    def state(self) -> RuntimeState:
        with self._state_lock:
            return self._state

    def _set_state(self, state: RuntimeState) -> None:
        with self._state_lock:
            self._state = state
        logger.info("CAD actor state -> %s", state.value)

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    @property
    def runtime(self) -> ActorRuntimeState | None:
        return self._runtime

    # -- lifecycle ----------------------------------------------------------

    async def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._thread_main, name="gstarcad-com-actor", daemon=False
        )
        self._thread.start()
        await asyncio.wrap_future(self._startup)

    async def close(self) -> None:
        thread = self._thread
        if thread is None:
            return
        self._set_state(RuntimeState.STOPPING)
        try:
            self._queue.put_nowait(_STOP)
        except queue.Full:
            pass
        timeout = getattr(self._config, "shutdown_timeout_seconds", 10.0)
        await asyncio.to_thread(thread.join, timeout)
        if thread.is_alive():
            logger.error("CAD actor thread did not stop within %.1fs", timeout)
            self._set_state(RuntimeState.FAILED)
        else:
            self._set_state(RuntimeState.STOPPED)

    # -- execution ----------------------------------------------------------

    async def execute(self, command: CadCommand) -> Any:
        state = self.state
        if state in (RuntimeState.STOPPING, RuntimeState.STOPPED, RuntimeState.FAILED):
            raise ExpectedCadError(
                CAD_QUEUE_FULL if state == RuntimeState.FAILED else CAD_NOT_RESPONDING,
                f"CAD actor is {state.value}; the command was rejected.",
            )
        future: Future = Future()
        item = WorkItem(command=command, result_future=future, cancel_requested=threading.Event())
        try:
            self._queue.put_nowait(item)
        except queue.Full as exc:
            raise ExpectedCadError(CAD_QUEUE_FULL, "CAD operation queue is full.") from exc
        try:
            return await asyncio.wrap_future(future)
        except asyncio.CancelledError:
            item.cancel_requested.set()
            future.cancel()
            raise

    # -- actor thread ---------------------------------------------------------

    def _thread_main(self) -> None:
        cad: Any = None
        try:
            self._set_state(RuntimeState.STARTING)
            factory = self._cad_factory or self._default_cad_factory
            cad = factory()
            registry = self._registry
            if self._runtime_state_factory is not None:
                runtime = self._runtime_state_factory(cad, registry, self._config)
            else:
                runtime = ActorRuntimeState(cad, registry, self._config)
            self._runtime = runtime
            self._set_state(RuntimeState.READY)
            self._startup.set_result(None)

            while True:
                item = self._queue.get()
                if item is _STOP:
                    break
                self._run_item(runtime, item)
        except BaseException as exc:  # startup or fatal loop failure
            self._set_state(RuntimeState.FAILED)
            if not self._startup.done():
                self._startup.set_exception(exc)
            logger.exception("GstarCAD COM actor failed")
            self._fail_queued_items(exc)
        finally:
            closer = getattr(cad, "close", None)
            if callable(closer):
                try:
                    closer()
                except Exception:
                    logger.exception("Error closing Gcad session")
            if self.state != RuntimeState.FAILED:
                self._set_state(RuntimeState.STOPPED)

    def _default_cad_factory(self) -> Any:
        from pygcadwin import Gcad

        cfg = self._config
        kwargs: dict[str, Any] = {
            "create_if_missing": getattr(cfg, "create_if_missing", True),
            "visible": getattr(cfg, "visible", True),
            "startup_wait": getattr(cfg, "startup_wait_seconds", 20.0),
        }
        prog_id = getattr(cfg, "prog_id", "auto")
        if prog_id and prog_id.strip().lower() != "auto":
            kwargs["prog_id"] = prog_id
        cad = Gcad(**kwargs)
        cad.connect()
        return cad

    def _run_item(self, runtime: ActorRuntimeState, item: WorkItem) -> None:
        command = item.command
        if item.cancel_requested.is_set() or item.result_future.cancelled():
            return
        if command.deadline_monotonic is not None and time.monotonic() > command.deadline_monotonic:
            item.result_future.set_exception(
                ExpectedCadError(CAD_OPERATION_TIMEOUT, "Command expired before execution began.")
            )
            return
        started = time.monotonic()
        try:
            if self._dispatcher is None:
                raise ExpectedCadError(
                    INTERNAL_ERROR,
                    "CAD actor has no command dispatcher configured; cannot execute work.",
                )
            result = self._dispatcher.dispatch(runtime, command)
            result = assert_wire_safe(result)
        except BaseException as exc:
            self.error_count += 1
            if not item.result_future.cancelled():
                item.result_future.set_exception(exc)
        else:
            self.executed_count += 1
            elapsed = time.monotonic() - started
            warn_after = getattr(self._config, "operation_warning_seconds", 30.0)
            if elapsed > warn_after:
                logger.warning("Slow CAD command %s took %.1fs", command.name, elapsed)
            if not item.result_future.cancelled():
                item.result_future.set_result(result)

    def _fail_queued_items(self, exc: BaseException) -> None:
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return
            if item is _STOP:
                continue
            if not item.result_future.done():
                item.result_future.set_exception(exc)
