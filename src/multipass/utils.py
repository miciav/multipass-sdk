from __future__ import annotations

from pathlib import Path

_KEY_NAMES = ("id_ed25519", "id_rsa", "id_ecdsa", "id_dsa")


def find_ssh_public_key() -> str | None:
    """Return the content of the first SSH public key found in ~/.ssh/, or None.

    Checks keys in priority order: ed25519, rsa, ecdsa, dsa.
    Returns the stripped key string ready for use in cloud-init
    ``ssh_authorized_keys``.
    """
    ssh_dir = Path.home() / ".ssh"
    for name in _KEY_NAMES:
        pub = ssh_dir / f"{name}.pub"
        if pub.exists():
            return pub.read_text(encoding="utf-8").strip()
    return None
