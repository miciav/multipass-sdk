import json
import pytest
from unittest.mock import MagicMock, patch
from multipass._backend import CommandResult, FakeBackend
from multipass.exceptions import MultipassCommandError, MultipassTimeoutError, VmNotFoundError
from multipass.models import VmState
from multipass.vm import MultipassVM

INFO_RESPONSE = json.dumps({
    "errors": [],
    "info": {
        "my-vm": {
            "cpu_count": "2",
            "disks": {"sda1": {"total": "5368709120", "used": "1000000000"}},
            "image_hash": "abc123",
            "image_release": "22.04 LTS",
            "ipv4": ["192.168.64.2"],
            "memory": {"total": 1073741824, "used": 123456789},
            "mounts": {},
            "state": "Running",
        }
    },
})

_VM_DATA = json.loads(INFO_RESPONSE)["info"]["my-vm"]

INFO_NO_IP = json.dumps({
    "errors": [], "info": {"my-vm": {**_VM_DATA, "ipv4": []}}
})

INFO_WITH_IP = json.dumps({
    "errors": [], "info": {"my-vm": {**_VM_DATA, "ipv4": ["192.168.64.5"]}}
})

SNAPSHOTS_JSON = json.dumps({
    "errors": [],
    "info": {
        "my-vm": {
            "snap1": {
                "comment": "Before upgrade",
                "created": "2023-08-15T10:30:00.000Z",
                "parent": "",
            }
        }
    }
})


def make_ok(stdout: str = "") -> CommandResult:
    return CommandResult(args=[], returncode=0, stdout=stdout, stderr="")


def make_err(stderr: str, returncode: int = 1) -> CommandResult:
    return CommandResult(args=[], returncode=returncode, stdout="", stderr=stderr)


# ------------------------------------------------------------------ info

def test_info_returns_vm_info():
    backend = FakeBackend(
        {("multipass", "info", "my-vm", "--format", "json"): make_ok(INFO_RESPONSE)}
    )
    vm = MultipassVM("my-vm", "multipass", backend)
    info = vm.info()
    assert info.name == "my-vm"
    assert info.state == VmState.RUNNING
    assert info.ipv4 == ["192.168.64.2"]


def test_info_raises_vm_not_found():
    backend = FakeBackend(
        {("multipass", "info", "ghost", "--format", "json"): make_err('instance "ghost" does not exist')}
    )
    vm = MultipassVM("ghost", "multipass", backend)
    with pytest.raises(VmNotFoundError):
        vm.info()


def test_info_raises_command_error_on_generic_failure():
    backend = FakeBackend(
        {("multipass", "info", "my-vm", "--format", "json"): make_err("some unexpected error")}
    )
    vm = MultipassVM("my-vm", "multipass", backend)
    with pytest.raises(MultipassCommandError):
        vm.info()


# ------------------------------------------------------------ lifecycle

def test_start_sends_correct_command():
    backend = FakeBackend()
    backend.set_default(make_ok())
    vm = MultipassVM("my-vm", "multipass", backend)
    vm.start()
    assert backend.last_call() == ["multipass", "start", "my-vm"]


def test_stop_sends_correct_command():
    backend = FakeBackend()
    backend.set_default(make_ok())
    vm = MultipassVM("my-vm", "multipass", backend)
    vm.stop()
    assert backend.last_call() == ["multipass", "stop", "my-vm"]


def test_stop_force_adds_flag():
    backend = FakeBackend()
    backend.set_default(make_ok())
    vm = MultipassVM("my-vm", "multipass", backend)
    vm.stop(force=True)
    assert "--force" in backend.last_call()


def test_restart_sends_correct_command():
    backend = FakeBackend()
    backend.set_default(make_ok())
    vm = MultipassVM("my-vm", "multipass", backend)
    vm.restart()
    assert backend.last_call() == ["multipass", "restart", "my-vm"]


def test_suspend_sends_correct_command():
    backend = FakeBackend()
    backend.set_default(make_ok())
    vm = MultipassVM("my-vm", "multipass", backend)
    vm.suspend()
    assert backend.last_call() == ["multipass", "suspend", "my-vm"]


def test_recover_sends_correct_command():
    backend = FakeBackend()
    backend.set_default(make_ok())
    vm = MultipassVM("my-vm", "multipass", backend)
    vm.recover()
    assert backend.last_call() == ["multipass", "recover", "my-vm"]


def test_delete_sends_correct_command():
    backend = FakeBackend()
    backend.set_default(make_ok())
    vm = MultipassVM("my-vm", "multipass", backend)
    vm.delete()
    assert backend.last_call() == ["multipass", "delete", "my-vm"]


def test_delete_purge_adds_flag():
    backend = FakeBackend()
    backend.set_default(make_ok())
    vm = MultipassVM("my-vm", "multipass", backend)
    vm.delete(purge=True)
    assert "--purge" in backend.last_call()


def test_lifecycle_raises_on_failure():
    backend = FakeBackend()
    backend.set_default(make_err("not running"))
    vm = MultipassVM("my-vm", "multipass", backend)
    with pytest.raises(MultipassCommandError):
        vm.start()


# -------------------------------------------------------------- exec

def test_exec_builds_command_from_list():
    exec_result = CommandResult(
        args=["multipass", "exec", "my-vm", "--", "ls", "-la"],
        returncode=0,
        stdout="total 0\n",
        stderr="",
    )
    backend = FakeBackend(
        {("multipass", "exec", "my-vm", "--", "ls", "-la"): exec_result}
    )
    vm = MultipassVM("my-vm", "multipass", backend)
    result = vm.exec(["ls", "-la"])
    assert result.stdout == "total 0\n"
    assert result.success is True


def test_exec_raises_on_nonzero():
    backend = FakeBackend(
        {("multipass", "exec", "my-vm", "--", "false"): make_err("", returncode=1)}
    )
    vm = MultipassVM("my-vm", "multipass", backend)
    with pytest.raises(MultipassCommandError):
        vm.exec(["false"])


# ------------------------------------------------------------ transfer

def test_transfer_host_to_vm():
    backend = FakeBackend()
    backend.set_default(make_ok())
    vm = MultipassVM("my-vm", "multipass", backend)
    vm.transfer("/host/path/file.txt", "my-vm:/remote/path/")
    assert backend.last_call() == [
        "multipass", "transfer", "-r", "/host/path/file.txt", "my-vm:/remote/path/"
    ]


def test_transfer_vm_to_host():
    backend = FakeBackend()
    backend.set_default(make_ok())
    vm = MultipassVM("my-vm", "multipass", backend)
    vm.transfer("my-vm:/remote/file.txt", "/host/dest/")
    assert backend.last_call() == [
        "multipass", "transfer", "-r", "my-vm:/remote/file.txt", "/host/dest/"
    ]


# -------------------------------------------------------------- mount

def test_mount_sends_correct_command():
    backend = FakeBackend()
    backend.set_default(make_ok())
    vm = MultipassVM("my-vm", "multipass", backend)
    vm.mount("/host/dir", "my-vm:/mnt/dir")
    assert backend.last_call() == ["multipass", "mount", "/host/dir", "my-vm:/mnt/dir"]


def test_mount_with_options():
    backend = FakeBackend()
    backend.set_default(make_ok())
    vm = MultipassVM("my-vm", "multipass", backend)
    vm.mount("/host/dir", "my-vm:/mnt/dir", uid_map="1000:1000", gid_map="1000:1000")
    call = backend.last_call()
    assert "--uid-map" in call
    assert "1000:1000" in call


def test_unmount_sends_correct_command():
    backend = FakeBackend()
    backend.set_default(make_ok())
    vm = MultipassVM("my-vm", "multipass", backend)
    vm.unmount("my-vm:/mnt/dir")
    assert backend.last_call() == ["multipass", "umount", "my-vm:/mnt/dir"]


# ---------------------------------------------------------- snapshots

def test_snapshots_returns_list():
    backend = FakeBackend(
        {("multipass", "list", "--snapshots", "--format", "json"): make_ok(SNAPSHOTS_JSON)}
    )
    vm = MultipassVM("my-vm", "multipass", backend)
    snaps = vm.snapshots()
    assert len(snaps) == 1
    assert snaps[0].name == "snap1"


def test_snapshot_create_sends_correct_command():
    backend = FakeBackend()
    backend.set_default(make_ok(SNAPSHOTS_JSON))
    vm = MultipassVM("my-vm", "multipass", backend)
    vm.snapshot("snap1", comment="Before upgrade")
    calls = backend.calls
    assert any(call[:3] == ["multipass", "snapshot", "my-vm"] for call in calls)


def test_restore_sends_correct_command():
    backend = FakeBackend()
    backend.set_default(make_ok())
    vm = MultipassVM("my-vm", "multipass", backend)
    vm.restore("snap1")
    assert backend.last_call() == ["multipass", "restore", "my-vm.snap1"]


def test_restore_destructive_adds_flag():
    backend = FakeBackend()
    backend.set_default(make_ok())
    vm = MultipassVM("my-vm", "multipass", backend)
    vm.restore("snap1", destructive=True)
    assert "--destructive" in backend.last_call()


# --------------------------------------------------------------- clone

def test_clone_sends_correct_command_and_returns_vm():
    backend = FakeBackend()
    backend.set_default(make_ok())
    vm = MultipassVM("my-vm", "multipass", backend)
    new_vm = vm.clone("my-vm-clone")
    assert backend.last_call() == ["multipass", "clone", "my-vm", "--name", "my-vm-clone"]
    assert new_vm.name == "my-vm-clone"


# -------------------------------------------------------- wait_for_ip

INFO_KEY = ("multipass", "info", "my-vm", "--format", "json")


@patch("multipass.vm.time.sleep")
def test_wait_for_ip_returns_ip_when_ready(mock_sleep):
    backend = FakeBackend()
    backend.push(*INFO_KEY, result=make_ok(INFO_NO_IP))
    backend.push(*INFO_KEY, result=make_ok(INFO_WITH_IP))
    vm = MultipassVM("my-vm", "multipass", backend)
    with patch("multipass.vm.time.monotonic", side_effect=[0, 10, 20]):
        ip = vm.wait_for_ip(timeout=120, interval=2.0)
    assert ip == "192.168.64.5"
    mock_sleep.assert_called_once_with(2.0)


@patch("multipass.vm.time.sleep")
def test_wait_for_ip_raises_timeout(mock_sleep):
    backend = FakeBackend()
    backend.set_default(make_ok(INFO_NO_IP))
    vm = MultipassVM("my-vm", "multipass", backend)
    with patch("multipass.vm.time.monotonic", side_effect=[0, 130]):
        with pytest.raises(MultipassTimeoutError) as exc_info:
            vm.wait_for_ip(timeout=120)
    assert exc_info.value.name == "my-vm"
    assert exc_info.value.timeout == 120


# -------------------------------------------------------- wait_ready

@patch("multipass.vm.time.sleep")
@patch("multipass.vm.socket.create_connection")
def test_wait_ready_returns_ip_when_ssh_reachable(mock_conn, mock_sleep):
    backend = FakeBackend()
    backend.set_default(make_ok(INFO_WITH_IP))
    mock_conn.return_value.__enter__ = MagicMock(return_value=None)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)
    vm = MultipassVM("my-vm", "multipass", backend)
    with patch("multipass.vm.time.monotonic", side_effect=[0, 10]):
        ip = vm.wait_ready(timeout=120, port=22)
    assert ip == "192.168.64.5"
    mock_conn.assert_called_once_with(("192.168.64.5", 22), timeout=1)


@patch("multipass.vm.time.sleep")
@patch("multipass.vm.socket.create_connection", side_effect=OSError)
def test_wait_ready_raises_timeout_when_port_unreachable(mock_conn, mock_sleep):
    backend = FakeBackend()
    backend.set_default(make_ok(INFO_WITH_IP))
    vm = MultipassVM("my-vm", "multipass", backend)
    with patch("multipass.vm.time.monotonic", side_effect=[0, 130]):
        with pytest.raises(MultipassTimeoutError):
            vm.wait_ready(timeout=120, port=22)


@patch("multipass.vm.time.sleep")
@patch("multipass.vm.socket.create_connection")
def test_wait_ready_waits_for_ip_before_tcp(mock_conn, mock_sleep):
    backend = FakeBackend()
    backend.push(*INFO_KEY, result=make_ok(INFO_NO_IP))
    backend.push(*INFO_KEY, result=make_ok(INFO_WITH_IP))
    mock_conn.return_value.__enter__ = MagicMock(return_value=None)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)
    vm = MultipassVM("my-vm", "multipass", backend)
    with patch("multipass.vm.time.monotonic", side_effect=[0, 10, 20]):
        ip = vm.wait_ready(timeout=120, port=22)
    assert ip == "192.168.64.5"
    mock_conn.assert_called_once()  # TCP check solo quando IP disponibile
