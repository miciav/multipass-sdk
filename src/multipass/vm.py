from __future__ import annotations

import json
import socket
import time

from .exceptions import MultipassCommandError, MultipassError, MultipassTimeoutError, VmNotFoundError
from .models import SnapshotInfo, VmInfo
from ._backend import CommandBackend, CommandResult

_NOT_FOUND_PHRASES = ("does not exist", "not found", "no such instance")


def _raise_for_result(result: CommandResult, vm_name: str) -> None:
    if result.success:
        return
    msg = (result.stderr or result.stdout).lower()
    if any(phrase in msg for phrase in _NOT_FOUND_PHRASES):
        raise VmNotFoundError(vm_name)
    raise MultipassCommandError(result.args, result.returncode, result.stdout, result.stderr)


class MultipassVM:
    def __init__(self, name: str, cmd: str, backend: CommandBackend) -> None:
        self.name = name
        self._cmd = cmd
        self._backend = backend

    def _run(self, cmd: list[str]) -> CommandResult:
        result = self._backend.run(cmd)
        _raise_for_result(result, self.name)
        return result

    def info(self) -> VmInfo:
        result = self._run([self._cmd, "info", self.name, "--format", "json"])
        return VmInfo.from_info_json(json.loads(result.stdout), self.name)

    def start(self) -> None:
        self._run([self._cmd, "start", self.name])

    def stop(self, *, force: bool = False, time: int | None = None) -> None:
        cmd = [self._cmd, "stop", self.name]
        if force:
            cmd.append("--force")
        if time is not None:
            cmd += ["--time", str(time)]
        self._run(cmd)

    def restart(self) -> None:
        self._run([self._cmd, "restart", self.name])

    def suspend(self) -> None:
        self._run([self._cmd, "suspend", self.name])

    def delete(self, *, purge: bool = False) -> None:
        cmd = [self._cmd, "delete", self.name]
        if purge:
            cmd.append("--purge")
        self._run(cmd)

    def recover(self) -> None:
        self._run([self._cmd, "recover", self.name])

    def exec(self, command: list[str]) -> CommandResult:
        """Execute a command in the VM. command must be a list of args (no shell splitting)."""
        return self._run([self._cmd, "exec", self.name, "--"] + command)

    def transfer(self, source: str, dest: str) -> None:
        """Transfer files between host and VM.

        Use 'vm-name:/path' notation for VM paths, plain paths for host.
        Always recursive (-r).
        """
        self._run([self._cmd, "transfer", "-r", source, dest])

    def mount(
        self,
        source: str,
        target: str,
        *,
        mount_type: str | None = None,
        uid_map: str | None = None,
        gid_map: str | None = None,
    ) -> None:
        cmd = [self._cmd, "mount", source, target]
        if mount_type:
            cmd += ["--type", mount_type]
        if uid_map:
            cmd += ["--uid-map", uid_map]
        if gid_map:
            cmd += ["--gid-map", gid_map]
        self._run(cmd)

    def unmount(self, mount: str) -> None:
        self._run([self._cmd, "umount", mount])

    def snapshots(self) -> list[SnapshotInfo]:
        result = self._run([self._cmd, "list", "--snapshots", "--format", "json"])
        return SnapshotInfo.from_snapshots_json(json.loads(result.stdout))

    def snapshot(self, name: str, *, comment: str | None = None) -> SnapshotInfo:
        cmd = [self._cmd, "snapshot", self.name, "--name", name]
        if comment:
            cmd += ["--comment", comment]
        self._run(cmd)
        return SnapshotInfo(
            name=name,
            comment=comment or "",
            created="",
            parent=None,
            instance=self.name,
        )

    def restore(self, snapshot: str, *, destructive: bool = False) -> None:
        cmd = [self._cmd, "restore", f"{self.name}.{snapshot}"]
        if destructive:
            cmd.append("--destructive")
        self._run(cmd)

    def clone(self, new_name: str) -> "MultipassVM":
        self._run([self._cmd, "clone", self.name, "--name", new_name])
        return MultipassVM(new_name, self._cmd, self._backend)

    def wait_for_ip(self, timeout: float = 120, *, interval: float = 2.0) -> str:
        """Poll info() until the VM has an IPv4 address. Returns the first IP."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                ip_list = self.info().ipv4
                if ip_list:
                    return ip_list[0]
            except MultipassError:
                pass
            time.sleep(interval)
        raise MultipassTimeoutError(self.name, timeout)

    def wait_ready(self, timeout: float = 120, port: int = 22, *, interval: float = 2.0) -> str:
        """Poll until VM has IP AND TCP port is reachable. Returns the IP."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                ip_list = self.info().ipv4
                if ip_list:
                    with socket.create_connection((ip_list[0], port), timeout=1):
                        return ip_list[0]
            except (MultipassError, OSError):
                pass
            time.sleep(interval)
        raise MultipassTimeoutError(self.name, timeout)
