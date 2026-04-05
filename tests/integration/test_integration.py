"""
Integration tests — require Multipass installed and running.
Run with: uv run pytest -m integration
"""
import pytest
from multipass import MultipassClient, VmState


@pytest.fixture(scope="module")
def client():
    return MultipassClient()


@pytest.mark.integration
def test_version(client):
    v = client.version()
    assert v.multipass
    assert v.multipassd


@pytest.mark.integration
def test_find_returns_images(client):
    images = client.find()
    assert len(images) > 0


@pytest.mark.integration
def test_list_returns_vms(client):
    vms = client.list()
    assert isinstance(vms, list)


@pytest.mark.integration
def test_vm_full_lifecycle(client):
    """Launch → info → stop → start → exec → delete. Requires internet access."""
    vm = client.launch(name="sdk-test-vm", cpus=1, memory="512M", disk="3G", image="22.04")
    try:
        info = vm.info()
        assert info.name == "sdk-test-vm"
        assert info.state == VmState.RUNNING

        vm.stop()
        info = vm.info()
        assert info.state == VmState.STOPPED

        vm.start()
        info = vm.info()
        assert info.state == VmState.RUNNING

        result = vm.exec(["echo", "hello"])
        assert "hello" in result.stdout
    finally:
        vm.delete(purge=True)
