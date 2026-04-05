"""
Integration tests — require Multipass installed and running.
Run with: uv run pytest -m integration
"""
import socket as _socket
import pytest
from multipass import MultipassClient, VmNotFoundError, VmState


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


@pytest.mark.integration
def test_delete_soft_then_purge(client):
    """Soft delete → verifica stato Deleted → purge globale → VM non trovata."""
    vm = client.launch(name="sdk-delete-test", cpus=1, memory="512M", disk="3G")
    vm.delete()
    info = vm.info()
    assert info.state == VmState.DELETED
    client.purge()
    with pytest.raises(VmNotFoundError):
        vm.info()


@pytest.mark.integration
def test_wait_for_ip_after_launch(client):
    """wait_for_ip restituisce un IPv4 valido dopo il launch."""
    vm = client.launch(name="sdk-ip-test", cpus=1, memory="512M", disk="3G")
    try:
        ip = vm.wait_for_ip(timeout=120)
        assert ip
        assert "." in ip
    finally:
        vm.delete(purge=True)


@pytest.mark.integration
def test_wait_ready_ssh_reachable(client):
    """wait_ready attende finché la porta 22 è aperta, poi verifica con TCP diretto."""
    vm = client.launch(name="sdk-ssh-test", cpus=1, memory="512M", disk="3G")
    try:
        ip = vm.wait_ready(timeout=180, port=22)
        assert ip
        with _socket.create_connection((ip, 22), timeout=5):
            pass  # connessione TCP verificata indipendentemente dall'SDK
    finally:
        vm.delete(purge=True)
