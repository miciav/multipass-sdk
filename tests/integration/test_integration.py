"""
Integration tests — require Multipass installed and running.
Run with: uv run pytest -m integration
"""
import socket as _socket
import tempfile
import textwrap
from pathlib import Path

import pytest
from multipass import MultipassClient, MultipassCommandError, VmNotFoundError, VmState


@pytest.fixture(scope="module")
def client():
    return MultipassClient()


# ------------------------------------------------------------------ read-only

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


# -------------------------------------------------------------- full lifecycle

@pytest.mark.integration
def test_vm_full_lifecycle(client):
    """Launch → info → stop → start → exec → delete."""
    vm = client.launch(name="sdk-test-vm", cpus=1, memory="512M", disk="5G", image="22.04")
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
def test_vm_info_reports_resources(client):
    """info() riporta correttamente cpu_count, memoria e disco."""
    vm = client.launch(name="sdk-resources-vm", cpus=2, memory="512M", disk="5G")
    try:
        info = vm.info()
        assert info.cpus == 2
        assert int(info.disk_total) > 0
        assert int(info.memory_total) > 0
    finally:
        vm.delete(purge=True)


# ------------------------------------------------------------- delete / purge

@pytest.mark.integration
def test_delete_soft_then_purge(client):
    """Soft delete → stato Deleted → purge globale → VM non trovata."""
    vm = client.launch(name="sdk-delete-test", cpus=1, memory="512M", disk="5G")
    vm.delete()
    info = vm.info()
    assert info.state == VmState.DELETED
    client.purge()
    with pytest.raises(VmNotFoundError):
        vm.info()


# --------------------------------------------------------------- wait helpers

@pytest.mark.integration
def test_wait_for_ip_after_launch(client):
    """wait_for_ip restituisce un IPv4 valido dopo il launch."""
    vm = client.launch(name="sdk-ip-test", cpus=1, memory="512M", disk="5G")
    try:
        ip = vm.wait_for_ip(timeout=120)
        assert ip
        assert "." in ip
    finally:
        vm.delete(purge=True)


@pytest.mark.integration
def test_wait_ready_ssh_reachable(client):
    """wait_ready attende finché la porta 22 è aperta, poi verifica con TCP diretto."""
    vm = client.launch(name="sdk-ssh-test", cpus=1, memory="512M", disk="5G")
    try:
        ip = vm.wait_ready(timeout=180, port=22)
        assert ip
        with _socket.create_connection((ip, 22), timeout=5):
            pass
    finally:
        vm.delete(purge=True)


# ------------------------------------------------------------- suspend/resume

@pytest.mark.integration
def test_suspend_and_resume(client):
    """Suspend → stato Suspended → start → stato Running."""
    vm = client.launch(name="sdk-suspend-vm", cpus=1, memory="512M", disk="5G")
    try:
        vm.suspend()
        info = vm.info()
        assert info.state == VmState.SUSPENDED

        vm.start()
        info = vm.info()
        assert info.state == VmState.RUNNING
    finally:
        vm.delete(purge=True)


# ----------------------------------------------------------- file transfer

@pytest.mark.integration
def test_transfer_host_to_vm_and_back(client):
    """Trasferisce un file host→VM, legge il contenuto con exec, trasferisce VM→host."""
    vm = client.launch(name="sdk-transfer-vm", cpus=1, memory="512M", disk="5G")
    try:
        vm.wait_ready(timeout=180, port=22)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("sdk-transfer-test\n")
            src_path = f.name

        vm.transfer(src_path, "sdk-transfer-vm:/tmp/sdk-test.txt")
        result = vm.exec(["cat", "/tmp/sdk-test.txt"])
        assert "sdk-transfer-test" in result.stdout

        with tempfile.TemporaryDirectory() as dst_dir:
            vm.transfer("sdk-transfer-vm:/tmp/sdk-test.txt", dst_dir + "/")
            content = Path(dst_dir, "sdk-test.txt").read_text()
            assert "sdk-transfer-test" in content
    finally:
        vm.delete(purge=True)


# ---------------------------------------------------------- snapshot / restore

@pytest.mark.integration
def test_snapshot_and_restore(client):
    """Crea un file, snapshot, modifica il file, restore, verifica che il file originale sia tornato."""
    vm = client.launch(name="sdk-snap-vm", cpus=1, memory="512M", disk="5G")
    try:
        vm.wait_ready(timeout=180, port=22)

        vm.exec(["bash", "-c", "echo original > /home/ubuntu/snaptest.txt"])
        vm.stop()
        snap = vm.snapshot("snap1", comment="before-change")
        assert snap.name == "snap1"

        # verifica che lo snapshot compaia nella lista mentre la VM è ferma
        snaps = vm.snapshots()
        assert any(s.name == "snap1" for s in snaps)

        vm.start()
        vm.wait_ready(timeout=120, port=22)

        vm.exec(["bash", "-c", "echo modified > /home/ubuntu/snaptest.txt"])
        result = vm.exec(["cat", "/home/ubuntu/snaptest.txt"])
        assert "modified" in result.stdout

        vm.stop()
        # --destructive consuma lo snapshot durante il restore
        vm.restore("snap1", destructive=True)
        vm.start()
        vm.wait_ready(timeout=120, port=22)

        result = vm.exec(["cat", "/home/ubuntu/snaptest.txt"])
        assert "original" in result.stdout
    finally:
        vm.delete(purge=True)


# -------------------------------------------------------------------- clone

@pytest.mark.integration
def test_clone_creates_independent_vm(client):
    """Clona una VM e verifica che il clone sia indipendente."""
    vm = client.launch(name="sdk-clone-src", cpus=1, memory="512M", disk="5G")
    clone = None
    try:
        vm.stop()
        clone = vm.clone("sdk-clone-dst")
        clone.start()
        info = clone.info()
        assert info.name == "sdk-clone-dst"
        assert info.state == VmState.RUNNING
    finally:
        vm.delete(purge=True)
        if clone:
            clone.delete(purge=True)


# ------------------------------------------------------------- cloud-init

@pytest.mark.integration
def test_cloud_init_creates_file(client):
    """cloud-init scrive un file al primo avvio; exec verifica che esista."""
    cloud_init = textwrap.dedent("""\
        #cloud-config
        write_files:
          - path: /tmp/cloud-init-marker
            content: "hello from cloud-init\n"
    """)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(cloud_init)
        ci_path = f.name

    vm = client.launch(name="sdk-cloudinit-vm", cpus=1, memory="512M", disk="5G", cloud_init=ci_path)
    try:
        vm.wait_ready(timeout=180, port=22)
        result = vm.exec(["cat", "/tmp/cloud-init-marker"])
        assert "hello from cloud-init" in result.stdout
    finally:
        vm.delete(purge=True)


# ----------------------------------------------------------- error handling

@pytest.mark.integration
def test_launch_nonexistent_image_raises(client):
    """Lanciare un'immagine inesistente solleva MultipassCommandError."""
    with pytest.raises(MultipassCommandError):
        client.launch(name="sdk-err-vm", image="this-image-does-not-exist-xyz")


@pytest.mark.integration
def test_get_nonexistent_vm_raises(client):
    """info() su una VM inesistente solleva VmNotFoundError."""
    vm = client.get_vm("sdk-ghost-vm-that-does-not-exist")
    with pytest.raises(VmNotFoundError):
        vm.info()
