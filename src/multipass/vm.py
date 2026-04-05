from __future__ import annotations

import json

from .exceptions import MultipassCommandError, VmNotFoundError
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

    # ------------------------------------------------------------------ info

    def info(self) -> VmInfo:
        result = self._backend.run([self._cmd, "info", self.name, "--format", "json"])
        _raise_for_result(result, self.name)
        return VmInfo.from_info_json(json.loads(result.stdout), self.name)

    # ------------------------------------------------------------ lifecycle

    def start(self) -> None:
        result = self._backend.run([self._cmd, "start", self.name])
        _raise_for_result(result, self.name)

    def stop(self, *, force: bool = False, time: int | None = None) -> None:
        cmd = [self._cmd, "stop", self.name]
        if force:
            cmd.append("--force")
        if time is not None:
            cmd += ["--time", str(time)]
        result = self._backend.run(cmd)
        _raise_for_result(result, self.name)

    def restart(self) -> None:
        result = self._backend.run([self._cmd, "restart", self.name])
        _raise_for_result(result, self.name)

    def suspend(self) -> None:
        result = self._backend.run([self._cmd, "suspend", self.name])
        _raise_for_result(result, self.name)

    def delete(self, *, purge: bool = False) -> None:
        cmd = [self._cmd, "delete", self.name]
        if purge:
            cmd.append("--purge")
        result = self._backend.run(cmd)
        _raise_for_result(result, self.name)

    def recover(self) -> None:
        result = self._backend.run([self._cmd, "recover", self.name])
        _raise_for_result(result, self.name)

    # -------------------------------------------------------------- exec

    def exec(self, command: list[str]) -> CommandResult:
        """Execute a command in the VM. command must be a list of args (no shell splitting)."""
        cmd = [self._cmd, "exec", self.name, "--"] + command
        result = self._backend.run(cmd)
        _raise_for_result(result, self.name)
        return result

    # ------------------------------------------------------------ transfer

    def transfer(self, source: str, dest: str) -> None:
        """Transfer files between host and VM.

        Use 'vm-name:/path' notation for VM paths, plain paths for host.
        Always recursive (-r).
        """
        result = self._backend.run([self._cmd, "transfer", "-r", source, dest])
        _raise_for_result(result, self.name)

    # -------------------------------------------------------------- mount

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
        result = self._backend.run(cmd)
        _raise_for_result(result, self.name)

    def unmount(self, mount: str) -> None:
        result = self._backend.run([self._cmd, "umount", mount])
        _raise_for_result(result, self.name)

    # ---------------------------------------------------------- snapshots

    def snapshots(self) -> list[SnapshotInfo]:
        result = self._backend.run(
            [self._cmd, "list", "--snapshots", "--format", "json"]
        )
        _raise_for_result(result, self.name)
        return SnapshotInfo.from_snapshots_json(json.loads(result.stdout))

    def snapshot(self, name: str, *, comment: str | None = None) -> SnapshotInfo:
        cmd = [self._cmd, "snapshot", self.name, "--name", name]
        if comment:
            cmd += ["--comment", comment]
        result = self._backend.run(cmd)
        _raise_for_result(result, self.name)
        all_snaps = self.snapshots()
        for snap in all_snaps:
            if snap.name == name:
                return snap
        raise MultipassCommandError(cmd, 0, "", f"Snapshot '{name}' not found after creation")

    def restore(self, snapshot: str, *, destructive: bool = False) -> None:
        cmd = [self._cmd, "restore", f"{self.name}.{snapshot}"]
        if destructive:
            cmd.append("--destructive")
        result = self._backend.run(cmd)
        _raise_for_result(result, self.name)

    # --------------------------------------------------------------- clone

    def clone(self, new_name: str) -> "MultipassVM":
        cmd = [self._cmd, "clone", self.name, "--name", new_name]
        result = self._backend.run(cmd)
        _raise_for_result(result, self.name)
        return MultipassVM(new_name, self._cmd, self._backend)
