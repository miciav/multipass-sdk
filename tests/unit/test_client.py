import json
import pytest
from multipass._backend import CommandResult, FakeBackend
from multipass.client import MultipassClient
from multipass.exceptions import MultipassCommandError
from multipass.models import VmState
from multipass.vm import MultipassVM

LIST_JSON = json.dumps({
    "list": [
        {"ipv4": ["192.168.64.2"], "name": "vm1", "release": "22.04 LTS", "state": "Running"},
        {"ipv4": [], "name": "vm2", "release": "22.04 LTS", "state": "Stopped"},
    ]
})

FIND_JSON = json.dumps({
    "errors": [],
    "images": {
        "22.04": {
            "aliases": ["jammy", "lts"],
            "os": "Ubuntu",
            "release": "22.04 LTS",
            "remote": "",
            "version": "20230801",
        }
    },
})

NETWORKS_JSON = json.dumps({
    "list": [{"description": "Wi-Fi", "name": "en0", "type": "wifi"}]
})

VERSION_JSON = json.dumps({"multipass": "1.13.0", "multipassd": "1.13.0"})

ALIASES_JSON = json.dumps({
    "aliases": [{"alias": "myalias", "command": "ls", "instance": "vm1", "working-directory": "default"}]
})


def make_ok(stdout: str = "") -> CommandResult:
    return CommandResult(args=[], returncode=0, stdout=stdout, stderr="")


def make_err(stderr: str = "error") -> CommandResult:
    return CommandResult(args=[], returncode=1, stdout="", stderr=stderr)


def test_list_returns_vm_info_list():
    backend = FakeBackend(
        {("multipass", "list", "--format", "json"): make_ok(LIST_JSON)}
    )
    client = MultipassClient(backend=backend)
    vms = client.list()
    assert len(vms) == 2
    assert vms[0].name == "vm1"
    assert vms[0].state == VmState.RUNNING
    assert vms[1].name == "vm2"


def test_find_returns_image_list():
    backend = FakeBackend(
        {("multipass", "find", "--format", "json"): make_ok(FIND_JSON)}
    )
    client = MultipassClient(backend=backend)
    images = client.find()
    assert len(images) == 1
    assert "jammy" in images[0].aliases


def test_get_vm_returns_multipass_vm():
    client = MultipassClient(backend=FakeBackend())
    vm = client.get_vm("my-vm")
    assert isinstance(vm, MultipassVM)
    assert vm.name == "my-vm"


def test_launch_default_name_generates_name():
    backend = FakeBackend()
    backend.set_default(make_ok())
    client = MultipassClient(backend=backend)
    vm = client.launch()
    assert vm.name
    assert backend.calls[0][0] == "multipass"
    assert backend.calls[0][1] == "launch"


def test_launch_with_explicit_name_and_resources():
    backend = FakeBackend()
    backend.set_default(make_ok())
    client = MultipassClient(backend=backend)
    vm = client.launch(name="test-vm", cpus=4, memory="8G", disk="30G")
    assert vm.name == "test-vm"
    call = backend.last_call()
    assert "test-vm" in call
    assert "4" in call
    assert "8G" in call
    assert "30G" in call


def test_launch_with_cloud_init():
    backend = FakeBackend()
    backend.set_default(make_ok())
    client = MultipassClient(backend=backend)
    client.launch(name="test-vm", cloud_init="/tmp/cloud-init.yaml")
    call = backend.last_call()
    assert "--cloud-init" in call
    assert "/tmp/cloud-init.yaml" in call


def test_launch_raises_on_failure():
    backend = FakeBackend()
    backend.set_default(make_err("launch failed"))
    client = MultipassClient(backend=backend)
    with pytest.raises(MultipassCommandError):
        client.launch(name="bad-vm")


def test_purge_sends_correct_command():
    backend = FakeBackend()
    backend.set_default(make_ok())
    client = MultipassClient(backend=backend)
    client.purge()
    assert backend.last_call() == ["multipass", "purge"]


def test_networks_returns_list():
    backend = FakeBackend(
        {("multipass", "networks", "--format", "json"): make_ok(NETWORKS_JSON)}
    )
    client = MultipassClient(backend=backend)
    nets = client.networks()
    assert len(nets) == 1
    assert nets[0].name == "en0"


def test_version_returns_version_info():
    backend = FakeBackend(
        {("multipass", "version", "--format", "json"): make_ok(VERSION_JSON)}
    )
    client = MultipassClient(backend=backend)
    v = client.version()
    assert v.multipass == "1.13.0"


def test_get_returns_value():
    backend = FakeBackend(
        {("multipass", "get", "local.bridged-network"): make_ok("eth0\n")}
    )
    client = MultipassClient(backend=backend)
    assert client.get("local.bridged-network") == "eth0"


def test_set_sends_correct_command():
    backend = FakeBackend()
    backend.set_default(make_ok())
    client = MultipassClient(backend=backend)
    client.set("local.driver", "qemu")
    assert backend.last_call() == ["multipass", "set", "local.driver=qemu"]


def test_aliases_returns_list():
    backend = FakeBackend(
        {("multipass", "aliases", "--format", "json"): make_ok(ALIASES_JSON)}
    )
    client = MultipassClient(backend=backend)
    aliases = client.aliases()
    assert len(aliases) == 1
    assert aliases[0].alias == "myalias"


def test_alias_sends_correct_command():
    backend = FakeBackend()
    backend.set_default(make_ok())
    client = MultipassClient(backend=backend)
    client.alias("myalias", "vm1", "ls")
    assert backend.last_call() == ["multipass", "alias", "vm1:ls", "myalias"]


def test_unalias_sends_correct_command():
    backend = FakeBackend()
    backend.set_default(make_ok())
    client = MultipassClient(backend=backend)
    client.unalias("myalias")
    assert backend.last_call() == ["multipass", "unalias", "myalias"]


def test_custom_multipass_cmd():
    backend = FakeBackend()
    backend.set_default(make_ok(LIST_JSON))
    client = MultipassClient(cmd="/usr/local/bin/multipass", backend=backend)
    client.list()
    assert backend.calls[0][0] == "/usr/local/bin/multipass"


def test_public_api_importable():
    from multipass import (
        MultipassClient,
        MultipassVM,
        MultipassError,
        MultipassCommandError,
        MultipassNotInstalledError,
        VmNotFoundError,
        VmAlreadyRunningError,
        VmNotRunningError,
        VmAlreadySuspendedError,
        VmInfo,
        VmState,
        ImageInfo,
        NetworkInfo,
        VersionInfo,
        AliasInfo,
        SnapshotInfo,
        CommandResult,
        FakeBackend,
        SubprocessBackend,
    )
    assert MultipassClient is not None
