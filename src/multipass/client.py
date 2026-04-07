from __future__ import annotations

import json
import tempfile
from pathlib import Path

from haikunator import Haikunator

from ._backend import CommandBackend, CommandResult, SubprocessBackend
from .exceptions import MultipassCommandError, VmNotFoundError
from .models import AliasInfo, ImageInfo, NetworkInfo, VmInfo, VmState, VersionInfo
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
        cloud_init_config: dict | str | None = None,
    ) -> MultipassVM:
        if name is None:
            name = Haikunator().haikunate(token_length=0)
        cmd = ["launch", "-n", name, "-c", str(cpus), "-m", memory, "-d", disk]
        if cloud_init:
            cmd += ["--cloud-init", cloud_init]
        if image and image != "ubuntu-lts":
            cmd.append(image)
        if cloud_init_config is not None:
            content = (
                json.dumps(cloud_init_config, indent=2)
                if isinstance(cloud_init_config, dict)
                else cloud_init_config
            )
            tmp = tempfile.NamedTemporaryFile(
                dir=Path.home(), suffix=".yaml", delete=False, mode="w"
            )
            try:
                tmp.write(content)
                tmp.close()
                self._run(*cmd, "--cloud-init", tmp.name)
            finally:
                Path(tmp.name).unlink(missing_ok=True)
        else:
            self._run(*cmd)
        return MultipassVM(name, self._cmd, self._backend)

    def ensure_running(
        self,
        name: str,
        image: str | None = None,
        *,
        cpus: int = 1,
        memory: str = "1G",
        disk: str = "5G",
        cloud_init: str | None = None,
        cloud_init_config: dict | str | None = None,
    ) -> MultipassVM:
        """Ensure the named VM exists and is running.

        State machine:
        - Not found  → launch with provided parameters
        - Deleted    → purge *all* soft-deleted VMs (system-wide), then launch
        - Running    → no-op
        - Any other  → start (Stopped, Suspended, etc.)

        .. warning::
            When the VM is in DELETED state, ``multipass purge`` is called, which
            permanently removes **all** soft-deleted instances on the system — not
            only the target VM. Ensure no other instances in DELETED state need
            to be recovered before calling this method.

        Returns the ``MultipassVM`` object in all cases.
        """
        try:
            info = self.get_vm(name).info()
        except VmNotFoundError:
            return self.launch(
                name, image,
                cpus=cpus, memory=memory, disk=disk,
                cloud_init=cloud_init, cloud_init_config=cloud_init_config,
            )

        if info.state == VmState.RUNNING:
            return self.get_vm(name)

        if info.state == VmState.DELETED:
            self.purge()
            return self.launch(
                name, image,
                cpus=cpus, memory=memory, disk=disk,
                cloud_init=cloud_init, cloud_init_config=cloud_init_config,
            )

        # Stopped, Suspended, Starting, Restarting, Unknown → try to start
        self.get_vm(name).start()
        return self.get_vm(name)

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
