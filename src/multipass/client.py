from __future__ import annotations

import json

from haikunator import Haikunator

from ._backend import CommandBackend, CommandResult, SubprocessBackend
from .exceptions import MultipassCommandError
from .models import AliasInfo, ImageInfo, NetworkInfo, VmInfo, VersionInfo
from .vm import MultipassVM


def _check(result: CommandResult) -> None:
    """Raise MultipassCommandError on non-zero exit. Used for global (non-VM) commands."""
    if not result.success:
        raise MultipassCommandError(
            result.args, result.returncode, result.stdout, result.stderr
        )


class MultipassClient:
    def __init__(
        self,
        cmd: str = "multipass",
        backend: CommandBackend | None = None,
    ) -> None:
        self._cmd = cmd
        self._backend: CommandBackend = backend or SubprocessBackend()

    # --------------------------------------------------------- VM factory

    def get_vm(self, name: str) -> MultipassVM:
        return MultipassVM(name, self._cmd, self._backend)

    # ------------------------------------------------------------- launch

    def launch(
        self,
        name: str | None = None,
        image: str | None = None,
        *,
        cpus: int = 1,
        memory: str = "1G",
        disk: str = "5G",
        cloud_init: str | None = None,
    ) -> MultipassVM:
        if name is None:
            name = Haikunator().haikunate(token_length=0)
        cmd = [
            self._cmd, "launch",
            "-n", name,
            "-c", str(cpus),
            "-m", memory,
            "-d", disk,
        ]
        if cloud_init:
            cmd += ["--cloud-init", cloud_init]
        if image and image != "ubuntu-lts":
            cmd.append(image)
        result = self._backend.run(cmd)
        _check(result)
        return MultipassVM(name, self._cmd, self._backend)

    # --------------------------------------------------------------- list

    def list(self) -> list[VmInfo]:
        result = self._backend.run([self._cmd, "list", "--format", "json"])
        _check(result)
        return VmInfo.from_list_json(json.loads(result.stdout))

    # --------------------------------------------------------------- find

    def find(self) -> list[ImageInfo]:
        result = self._backend.run([self._cmd, "find", "--format", "json"])
        _check(result)
        return ImageInfo.from_find_json(json.loads(result.stdout))

    # -------------------------------------------------------------- purge

    def purge(self) -> None:
        result = self._backend.run([self._cmd, "purge"])
        _check(result)

    # ------------------------------------------------------------ networks

    def networks(self) -> list[NetworkInfo]:
        result = self._backend.run([self._cmd, "networks", "--format", "json"])
        _check(result)
        return NetworkInfo.from_networks_json(json.loads(result.stdout))

    # ------------------------------------------------------------- version

    def version(self) -> VersionInfo:
        result = self._backend.run([self._cmd, "version", "--format", "json"])
        _check(result)
        return VersionInfo.from_json(json.loads(result.stdout))

    # ------------------------------------------------------------ get/set

    def get(self, key: str) -> str:
        result = self._backend.run([self._cmd, "get", key])
        _check(result)
        return result.stdout.strip()

    def set(self, key: str, value: str) -> None:
        result = self._backend.run([self._cmd, "set", f"{key}={value}"])
        _check(result)

    # ------------------------------------------------------------ aliases

    def aliases(self) -> list[AliasInfo]:
        result = self._backend.run([self._cmd, "aliases", "--format", "json"])
        _check(result)
        return AliasInfo.from_aliases_json(json.loads(result.stdout))

    def alias(self, name: str, vm: str, command: str) -> None:
        result = self._backend.run([self._cmd, "alias", f"{vm}:{command}", name])
        _check(result)

    def unalias(self, name: str) -> None:
        result = self._backend.run([self._cmd, "unalias", name])
        _check(result)
