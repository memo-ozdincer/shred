"""Persistent client for the pinned Lean REPL.

The upstream REPL flushes promptly on a terminal but buffers when connected to
ordinary pipes. A private pseudo-terminal supplies terminal semantics without
changing Lean or the verifier package.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import pty
import resource
import select
import signal
import subprocess
import termios
import tempfile
import time
from typing import Any


class ReplError(RuntimeError):
    """Raised when the REPL process or protocol fails."""


class ReplTimeout(ReplError):
    """Raised when Lean does not answer within the configured deadline."""


@dataclass(frozen=True)
class ReplResult:
    response: dict[str, Any]
    wall_seconds: float
    cpu_seconds: float | None
    peak_rss_kib: int | None


def heartbeat_count(response: dict[str, Any]) -> int | None:
    """Return the count emitted by `count_heartbeats`, if it completed."""
    values: list[int] = []
    for message in response.get("messages", []):
        if message.get("severity") != "info":
            continue
        data = str(message.get("data", "")).strip()
        if data.isdigit():
            values.append(int(data))
    return values[-1] if values else None


def heartbeat_wrapper(tactic: str) -> str:
    """Measure a tactic under C0's unlimited-heartbeat option."""
    indented = "\n".join(f"    {line}" for line in tactic.splitlines())
    return f"set_option maxHeartbeats 0 in\n  count_heartbeats\n{indented}"


def _proc_cpu_seconds(pid: int) -> float | None:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()
        ticks = int(fields[13]) + int(fields[14])
        return ticks / os.sysconf("SC_CLK_TCK")
    except (FileNotFoundError, IndexError, OSError, ValueError):
        return None


def _proc_peak_rss_kib(pid: int) -> int | None:
    try:
        for line in Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmHWM:"):
                return int(line.split()[1])
    except (FileNotFoundError, IndexError, OSError, ValueError):
        return None
    return None


def _proc_rss_kib(pid: int) -> int:
    try:
        for line in Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except (FileNotFoundError, IndexError, OSError, ValueError):
        pass
    return -1


def _largest_descendant(root_pid: int) -> int:
    """Find the memory-owning process beneath the short-lived `lake env` wrapper."""
    discovered = [root_pid]
    index = 0
    while index < len(discovered):
        pid = discovered[index]
        index += 1
        try:
            children = Path(f"/proc/{pid}/task/{pid}/children").read_text().split()
        except OSError:
            continue
        discovered.extend(int(child) for child in children if int(child) not in discovered)
    return max(discovered, key=_proc_rss_kib)


class LeanRepl:
    """One persistent, single-request-at-a-time Lean REPL process."""

    def __init__(
        self,
        workspace: Path,
        *,
        executable: Path = Path(".lake/packages/REPL/.lake/build/bin/repl"),
        lake: str = "lake",
        timeout_seconds: float = 300.0,
        memory_limit_bytes: int | None = 24 * 1024**3,
    ) -> None:
        self.workspace = workspace.resolve()
        self.executable = (
            executable if executable.is_absolute() else self.workspace / executable
        ).resolve()
        self.timeout_seconds = timeout_seconds
        self.lake = lake
        self.memory_limit_bytes = memory_limit_bytes
        self._process: subprocess.Popen[bytes] | None = None
        self._master_fd: int | None = None
        self._buffer = b""
        self._stderr = None

    def __enter__(self) -> "LeanRepl":
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @property
    def pid(self) -> int:
        if self._process is None:
            raise ReplError("REPL has not been started")
        return self._process.pid

    def start(self) -> None:
        if self._process is not None:
            raise ReplError("REPL is already running")
        if not self.executable.is_file():
            raise ReplError(f"REPL executable does not exist: {self.executable}")
        master_fd, slave_fd = pty.openpty()
        attributes = termios.tcgetattr(slave_fd)
        # Non-canonical mode avoids the terminal driver's ~4 KiB input-line
        # limit; generated theorem/proof JSON can be substantially longer.
        attributes[3] &= ~(termios.ECHO | termios.ECHONL | termios.ICANON)
        attributes[6][termios.VMIN] = 1
        attributes[6][termios.VTIME] = 0
        termios.tcsetattr(slave_fd, termios.TCSANOW, attributes)
        self._stderr = tempfile.TemporaryFile(mode="w+b")

        def apply_limits() -> None:
            if self.memory_limit_bytes is not None:
                resource.setrlimit(
                    resource.RLIMIT_AS,
                    (self.memory_limit_bytes, self.memory_limit_bytes),
                )
        try:
            try:
                self._process = subprocess.Popen(
                    [self.lake, "env", str(self.executable)],
                    cwd=self.workspace,
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=self._stderr,
                    close_fds=True,
                    start_new_session=True,
                    preexec_fn=apply_limits,
                )
            except BaseException:
                os.close(master_fd)
                self._stderr.close()
                self._stderr = None
                raise
        finally:
            os.close(slave_fd)
        self._master_fd = master_fd

    def close(self) -> None:
        process = self._process
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        if self._master_fd is not None:
            os.close(self._master_fd)
        if self._stderr is not None:
            self._stderr.close()
        self._process = None
        self._master_fd = None
        self._stderr = None
        self._buffer = b""

    def _read_response(self, deadline: float) -> dict[str, Any]:
        if self._master_fd is None or self._process is None:
            raise ReplError("REPL is not running")
        while True:
            normalized = self._buffer.replace(b"\r\n", b"\n")
            boundary = normalized.find(b"\n\n")
            if boundary >= 0:
                payload = normalized[:boundary]
                self._buffer = normalized[boundary + 2 :]
                try:
                    response = json.loads(payload)
                except json.JSONDecodeError as error:
                    raise ReplError(f"invalid REPL JSON: {error}: {payload[:500]!r}") from error
                if not isinstance(response, dict):
                    raise ReplError(f"REPL returned non-object JSON: {type(response).__name__}")
                return response

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ReplTimeout(f"Lean REPL request exceeded {self.timeout_seconds} seconds")
            if self._process.poll() is not None:
                detail = ""
                if self._stderr is not None:
                    self._stderr.seek(0)
                    detail = self._stderr.read().decode("utf-8", errors="replace")[-4096:]
                raise ReplError(
                    f"Lean REPL exited with status {self._process.returncode}: {detail}"
                )
            readable, _, _ = select.select([self._master_fd], [], [], min(remaining, 1.0))
            if readable:
                try:
                    self._buffer += os.read(self._master_fd, 1024 * 1024)
                except OSError as error:
                    raise ReplError(f"failed reading Lean REPL: {error}") from error

    def request(self, request: dict[str, Any]) -> ReplResult:
        if self._master_fd is None or self._process is None:
            raise ReplError("REPL is not running")
        payload = json.dumps(request, ensure_ascii=False, separators=(",", ":")) + "\n\n"
        measured_pid_before = _largest_descendant(self._process.pid)
        cpu_before = _proc_cpu_seconds(measured_pid_before)
        started = time.monotonic()
        try:
            remaining = memoryview(payload.encode("utf-8"))
            while remaining:
                written = os.write(self._master_fd, remaining)
                remaining = remaining[written:]
            response = self._read_response(started + self.timeout_seconds)
        except ReplTimeout:
            self.close()
            raise
        wall_seconds = time.monotonic() - started
        measured_pid_after = _largest_descendant(self._process.pid)
        cpu_after = _proc_cpu_seconds(measured_pid_after)
        cpu_seconds = (
            cpu_after - cpu_before
            if (
                measured_pid_before == measured_pid_after
                and cpu_before is not None
                and cpu_after is not None
            )
            else None
        )
        return ReplResult(
            response=response,
            wall_seconds=wall_seconds,
            cpu_seconds=cpu_seconds,
            peak_rss_kib=_proc_peak_rss_kib(measured_pid_after),
        )

    def initialize(self, code: str) -> ReplResult:
        return self.request(
            {
                "cmd": code,
                "allTactics": False,
                "ast": False,
                "tactics": False,
                "premises": False,
            }
        )

    def elaborate(self, code: str, *, env: int, all_tactics: bool = False) -> ReplResult:
        return self.request(
            {
                "cmd": code,
                "env": env,
                "allTactics": all_tactics,
                "ast": False,
                "tactics": False,
                "premises": False,
            }
        )

    def proof_step(
        self,
        proof_state: int,
        tactic: str,
        *,
        count_heartbeats: bool = True,
        decl_name: str | None = None,
    ) -> ReplResult:
        source = heartbeat_wrapper(tactic) if count_heartbeats else tactic
        request: dict[str, Any] = {"proofState": proof_state, "tactic": source}
        if decl_name is not None:
            request["declName"] = decl_name
        return self.request(request)
