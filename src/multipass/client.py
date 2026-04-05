from __future__ import annotations

import json

from haikunator import Haikunator

from ._backend import CommandBackend, CommandResult, SubprocessBackend
from .exceptions import MultipassCommandError
from .models import AliasInfo, ImageInfo, NetworkInfo, VmInfo, VersionInfo
from .vm import MultipassVM


def _check(result: CommandResult) -> None:
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

    def _run(self, *args: str) -> CommandResult:
        result = self._backend.run([self._cmd, *args])
        _check(result)
        return result

    def _run_json(self, *args: str) -> dict:
        return json.loads(self._run(*args).stdout)

    def get_vm(self, name: str) -> MultipassVM:
        return MultipassVM(name, self._cmd, self._backend)

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
        cmd = ["launch", "-n", name, "-c", str(cpus), "-m", memory, "-d", disk]
        if cloud_init:
            cmd += ["--cloud-init", cloud_init]
        if image and image != "ubuntu-lts":
            cmd.append(image)
        self._run(*cmd)
        return MultipassVM(name, self._cmd, self._backend)

    def list(self) -> list[VmInfo]:
        return VmInfo.from_list_json(self._run_json("list", "--format", "json"))

    def find(self) -> list[ImageInfo]:
        return ImageInfo.from_find_json(self._run_json("find", "--format", "json"))

    def purge(self) -> None:
        self._run("purge")

    def networks(self) -> list[NetworkInfo]:
        return NetworkInfo.from_networks_json(self._run_json("networks", "--format", "json"))

    def version(self) -> VersionInfo:
        return VersionInfo.from_json(self._run_json("version", "--format", "json"))

    def get(self, key: str) -> str:
        return self._run("get", key).stdout.strip()

    def set(self, key: str, value: str) -> None:
        self._run("set", f"{key}={value}")

    def aliases(self) -> list[AliasInfo]:
        return AliasInfo.from_aliases_json(self._run_json("aliases", "--format", "json"))

    def alias(self, name: str, vm: str, command: str) -> None:
        self._run("alias", f"{vm}:{command}", name)

    def unalias(self, name: str) -> None:
        self._run("unalias", name)
