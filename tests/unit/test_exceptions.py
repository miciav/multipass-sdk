from multipass.exceptions import (
    MultipassError,
    MultipassCommandError,
    MultipassNotInstalledError,
    VmNotFoundError,
    VmAlreadyRunningError,
    VmNotRunningError,
    VmAlreadySuspendedError,
)


def test_all_exceptions_are_subclasses_of_multipass_error():
    assert issubclass(MultipassCommandError, MultipassError)
    assert issubclass(MultipassNotInstalledError, MultipassError)
    assert issubclass(VmNotFoundError, MultipassError)
    assert issubclass(VmAlreadyRunningError, MultipassError)
    assert issubclass(VmNotRunningError, MultipassError)
    assert issubclass(VmAlreadySuspendedError, MultipassError)


def test_multipass_command_error_stores_fields():
    err = MultipassCommandError(["multipass", "info"], 1, "", "instance not found")
    assert err.returncode == 1
    assert err.stderr == "instance not found"
    assert "multipass" in str(err)


def test_vm_not_found_error_includes_name():
    err = VmNotFoundError("my-vm")
    assert err.name == "my-vm"
    assert "my-vm" in str(err)
