from pathlib import Path
import pytest
from multipass.utils import find_ssh_public_key


def test_returns_ed25519_key_content(tmp_path, monkeypatch):
    monkeypatch.setattr("multipass.utils.Path.home", lambda: tmp_path)
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir()
    (ssh_dir / "id_ed25519.pub").write_text("ssh-ed25519 AAAA... user@host\n")
    assert find_ssh_public_key() == "ssh-ed25519 AAAA... user@host"


def test_strips_trailing_whitespace(tmp_path, monkeypatch):
    monkeypatch.setattr("multipass.utils.Path.home", lambda: tmp_path)
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir()
    (ssh_dir / "id_ed25519.pub").write_text("ssh-ed25519 AAAA...  \n\n")
    assert find_ssh_public_key() == "ssh-ed25519 AAAA..."


def test_falls_back_to_rsa_when_ed25519_absent(tmp_path, monkeypatch):
    monkeypatch.setattr("multipass.utils.Path.home", lambda: tmp_path)
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir()
    (ssh_dir / "id_rsa.pub").write_text("ssh-rsa BBBB... user@host\n")
    assert find_ssh_public_key() == "ssh-rsa BBBB... user@host"


def test_key_priority_order(tmp_path, monkeypatch):
    """ed25519 is preferred over rsa when both exist."""
    monkeypatch.setattr("multipass.utils.Path.home", lambda: tmp_path)
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir()
    (ssh_dir / "id_rsa.pub").write_text("ssh-rsa BBBB...\n")
    (ssh_dir / "id_ed25519.pub").write_text("ssh-ed25519 AAAA...\n")
    assert find_ssh_public_key() == "ssh-ed25519 AAAA..."


def test_returns_none_when_no_keys_present(tmp_path, monkeypatch):
    monkeypatch.setattr("multipass.utils.Path.home", lambda: tmp_path)
    (tmp_path / ".ssh").mkdir()
    assert find_ssh_public_key() is None


def test_returns_none_when_ssh_dir_absent(tmp_path, monkeypatch):
    monkeypatch.setattr("multipass.utils.Path.home", lambda: tmp_path)
    assert find_ssh_public_key() is None


def test_importable_from_top_level():
    from multipass import find_ssh_public_key as f
    assert callable(f)
