# multipass-sdk

Unofficial Python SDK for [Canonical Multipass](https://multipass.run). Wraps the Multipass CLI to manage Ubuntu VMs programmatically.

- Full coverage of the Multipass CLI (launch, list, find, exec, transfer, mount, snapshot, clone, …)
- Testable without Multipass installed — inject a `FakeBackend` in unit tests
- Typed exception hierarchy, dataclass models, no external runtime dependencies beyond `haikunator`

---

## Installation

### From GitHub (recommended for internal projects)

```bash
uv add git+https://github.com/miciav/multipass-sdk.git
```

To pin to a specific commit or tag:

```bash
uv add git+https://github.com/miciav/multipass-sdk.git@v0.3.0
```

Multipass itself must be installed on the machine where the SDK is used at runtime. It is **not** required for unit tests.

---

## Quick start

```python
from multipass import MultipassClient

client = MultipassClient()

# Launch a VM (name is auto-generated if omitted)
vm = client.launch(name="my-vm", cpus=2, memory="1G", disk="10G", image="22.04")

# Wait until SSH is reachable, then connect
ip = vm.wait_ready(timeout=180, port=22)
print(f"VM ready at {ip}")

# Run a command
result = vm.exec(["uname", "-r"])
print(result.stdout)

# Lifecycle
vm.stop()
vm.start()
vm.suspend()
vm.restart()

# Cleanup
vm.delete(purge=True)
```

---

## API reference

### `MultipassClient`

```python
client = MultipassClient(cmd="multipass")   # cmd: path to the CLI binary
```

| Method | Description |
|--------|-------------|
| `launch(name, image, *, cpus, memory, disk, cloud_init, cloud_init_config) → MultipassVM` | Launch a new VM |
| `ensure_running(name, image, *, cpus, memory, disk, cloud_init, cloud_init_config) → MultipassVM` | Idempotent: launch, start, or no-op so the VM ends up Running |
| `get_vm(name) → MultipassVM` | Get a VM object by name |
| `list() → list[VmInfo]` | List all VMs |
| `find() → list[ImageInfo]` | List available images |
| `purge()` | Permanently delete all soft-deleted VMs |
| `networks() → list[NetworkInfo]` | List available networks |
| `version() → VersionInfo` | Multipass and multipassd versions |
| `get(key) → str` | Read a Multipass setting |
| `set(key, value)` | Write a Multipass setting |
| `aliases() → list[AliasInfo]` | List all aliases |
| `alias(name, vm, command)` | Create an alias |
| `unalias(name)` | Remove an alias |

### `MultipassVM`

| Method | Description |
|--------|-------------|
| `info() → VmInfo` | Get current VM state and metadata |
| `start()` | Start the VM |
| `stop(*, force, time)` | Stop the VM |
| `restart()` | Restart the VM |
| `suspend()` | Suspend the VM |
| `recover()` | Recover a VM in error state |
| `delete(*, purge)` | Delete the VM (soft or permanent) |
| `exec(command: list[str]) → CommandResult` | Run a command in the VM |
| `transfer(source, dest)` | Transfer files between host and VM (recursive) |
| `mount(source, target, *, mount_type, uid_map, gid_map)` | Mount a host directory |
| `unmount(mount)` | Unmount a directory |
| `snapshots() → list[SnapshotInfo]` | List snapshots |
| `snapshot(name, *, comment) → SnapshotInfo` | Create a snapshot (VM must be stopped) |
| `restore(snapshot, *, destructive)` | Restore a snapshot |
| `clone(new_name) → MultipassVM` | Clone the VM (VM must be stopped) |
| `wait_for_ip(timeout, *, interval) → str` | Poll until the VM has an IPv4 address |
| `wait_ready(timeout, port, *, interval) → str` | Poll until the VM has an IP and a TCP port is reachable |

### `wait_for_ip` / `wait_ready`

These methods make the common "launch → SSH" pattern reliable:

```python
vm = client.launch(name="worker", disk="10G")

# Returns the first IPv4 address once assigned
ip = vm.wait_for_ip(timeout=120)

# Returns the IP once the given TCP port is reachable (default: 22)
ip = vm.wait_ready(timeout=180, port=22)
```

Both raise `MultipassTimeoutError` if the deadline is exceeded.

### File transfer

Use `instance-name:/path` notation for VM paths, plain paths for host paths:

```python
vm.transfer("/host/file.txt", "my-vm:/home/ubuntu/file.txt")
vm.transfer("my-vm:/home/ubuntu/output.txt", "/host/dest/")
```

### Snapshots

```python
vm.stop()
snap = vm.snapshot("snap1", comment="before upgrade")
vm.start()

# restore (--destructive consumes the snapshot)
vm.stop()
vm.restore("snap1", destructive=True)
vm.start()
```

### cloud-init

Pass a file path, a YAML string, or a dict — the SDK handles the rest.

**File path** (you manage the file):

```python
vm = client.launch(name="my-vm", cloud_init="/home/user/cloud-init.yaml")
```

**Inline dict** (serialized to JSON, which cloud-init accepts natively):

```python
vm = client.launch(
    name="my-vm",
    cloud_init_config={
        "packages": ["git", "curl"],
        "runcmd": ["apt-get upgrade -y"],
    }
)
```

**Inline YAML string**:

```python
vm = client.launch(
    name="my-vm",
    cloud_init_config="""
#cloud-config
packages:
  - git
  - curl
runcmd:
  - apt-get upgrade -y
"""
)
```

When `cloud_init_config` is used, the SDK writes a temporary file to the user's home directory (not `/tmp`) so that Multipass installed via snap can read it. The file is deleted automatically after launch.

#### Custom user and SSH key

```python
from pathlib import Path

ssh_key = Path("~/.ssh/id_rsa.pub").expanduser().read_text().strip()

vm = client.launch(
    name="my-vm",
    cloud_init_config={
        "users": [
            {
                "name": "michele",
                "groups": ["sudo"],
                "shell": "/bin/bash",
                "sudo": "ALL=(ALL) NOPASSWD:ALL",
                "ssh_authorized_keys": [ssh_key],
            }
        ]
    }
)
```

To keep the default `ubuntu` user alongside your custom one, add `"default"` as the first entry in the `users` list:

```python
"users": ["default", {"name": "michele", ...}]
```

### SSH key injection helper

`find_ssh_public_key()` returns the content of the first SSH public key found in
`~/.ssh/` (priority: ed25519 → rsa → ecdsa → dsa), or `None` if none exists.
Combine it with `cloud_init_config` to make new VMs immediately accessible:

```python
from multipass import MultipassClient, find_ssh_public_key

client = MultipassClient()
pub_key = find_ssh_public_key()

vm = client.ensure_running(
    "my-vm",
    cloud_init_config={"ssh_authorized_keys": [pub_key]} if pub_key else None,
)
ip = vm.wait_ready(timeout=180)
```

---

## Exceptions

All exceptions inherit from `MultipassError`.

| Exception | When raised |
|-----------|-------------|
| `MultipassCommandError` | CLI exits with non-zero status |
| `MultipassNotInstalledError` | `multipass` binary not found |
| `MultipassTimeoutError` | `wait_for_ip` / `wait_ready` deadline exceeded |
| `VmNotFoundError` | VM does not exist |
| `VmAlreadyRunningError` | Operation requires stopped VM |
| `VmNotRunningError` | Operation requires running VM |
| `VmAlreadySuspendedError` | VM is already suspended |

---

## Testing without Multipass

Inject a `FakeBackend` to unit-test code that uses the SDK:

```python
import json
from multipass import MultipassClient, FakeBackend, CommandResult

backend = FakeBackend({
    ("multipass", "list", "--format", "json"): CommandResult(
        args=[], returncode=0,
        stdout=json.dumps({"list": []}),
        stderr="",
    )
})
client = MultipassClient(backend=backend)
vms = client.list()   # no Multipass required
```

`FakeBackend` also supports queued responses for polling scenarios:

```python
backend = FakeBackend()
backend.push("multipass", "info", "my-vm", "--format", "json",
             result=CommandResult(..., stdout=info_no_ip))
backend.push("multipass", "info", "my-vm", "--format", "json",
             result=CommandResult(..., stdout=info_with_ip))
```

---

## Running the tests

```bash
# Setup
uv sync --extra dev

# Unit tests (no Multipass required)
uv run pytest tests/unit/ -v

# Integration tests (require Multipass installed and running)
uv run pytest -m integration -v
```

The integration test suite covers: full VM lifecycle, resources, soft delete + purge, `wait_for_ip`, `wait_ready` + SSH, suspend/resume, file transfer, snapshot/restore, clone, cloud-init, and error handling.

---

## Contributing

Send a pull request. Unit tests must pass; integration tests are welcome but not required in CI.
