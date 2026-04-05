from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Protocol

from .exceptions import MultipassNotInstalledError


@dataclass
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.returncode == 0


class CommandBackend(Protocol):
    def run(self, args: list[str]) -> CommandResult: ...


class SubprocessBackend:
    """Real backend — invokes the Multipass CLI via subprocess."""

    def run(self, args: list[str]) -> CommandResult:
        binary = args[0] if args else "multipass"
        if not shutil.which(binary):
            raise MultipassNotInstalledError()
        try:
            proc = subprocess.run(args, capture_output=True, text=True)
        except FileNotFoundError:
            raise MultipassNotInstalledError()
        return CommandResult(
            args=args,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )


class FakeBackend:
    """Test backend — returns pre-configured responses and records all calls."""

    def __init__(
        self,
        responses: dict[tuple[str, ...], CommandResult] | None = None,
    ) -> None:
        self._responses: dict[tuple[str, ...], CommandResult] = responses or {}
        self._calls: list[list[str]] = []
        self._default: CommandResult | None = None

    def set_default(self, result: CommandResult) -> None:
        self._default = result

    def run(self, args: list[str]) -> CommandResult:
        self._calls.append(list(args))
        key = tuple(args)
        if key in self._responses:
            return self._responses[key]
        if self._default is not None:
            return self._default
        raise KeyError(f"FakeBackend: no response configured for {args!r}")

    @property
    def calls(self) -> list[list[str]]:
        return list(self._calls)

    def last_call(self) -> list[str]:
        return self._calls[-1] if self._calls else []
