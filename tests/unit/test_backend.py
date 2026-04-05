import pytest
from multipass._backend import CommandResult, FakeBackend


def test_command_result_success():
    result = CommandResult(args=["multipass", "list"], returncode=0, stdout="ok", stderr="")
    assert result.success is True


def test_command_result_failure():
    result = CommandResult(args=["multipass", "info"], returncode=1, stdout="", stderr="not found")
    assert result.success is False


def test_fake_backend_records_calls():
    backend = FakeBackend()
    ok = CommandResult(args=[], returncode=0, stdout="", stderr="")
    backend.set_default(ok)
    backend.run(["multipass", "list"])
    backend.run(["multipass", "info", "my-vm"])
    assert backend.calls == [
        ["multipass", "list"],
        ["multipass", "info", "my-vm"],
    ]


def test_fake_backend_returns_configured_response():
    expected = CommandResult(
        args=["multipass", "list", "--format", "json"],
        returncode=0,
        stdout='{"list":[]}',
        stderr="",
    )
    backend = FakeBackend(
        responses={("multipass", "list", "--format", "json"): expected}
    )
    result = backend.run(["multipass", "list", "--format", "json"])
    assert result.stdout == '{"list":[]}'


def test_fake_backend_raises_on_unconfigured_call():
    backend = FakeBackend()
    with pytest.raises(KeyError):
        backend.run(["multipass", "unknown"])


def test_fake_backend_last_call():
    backend = FakeBackend()
    ok = CommandResult(args=[], returncode=0, stdout="", stderr="")
    backend.set_default(ok)
    backend.run(["multipass", "start", "vm1"])
    assert backend.last_call() == ["multipass", "start", "vm1"]
