# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

An unofficial Python SDK that wraps the Multipass CLI to manage Ubuntu VMs programmatically. Full coverage of every Multipass CLI command. Designed to be imported by other projects (e.g. nanofaas) — it has no dependencies on them.

## Setup

```bash
uv sync --extra dev
```

Requires [uv](https://docs.astral.sh/uv/). Multipass itself is NOT required for unit tests.

## Running Tests

```bash
# Unit tests only (no Multipass required)
uv run pytest tests/unit/ -v

# Single test
uv run pytest tests/unit/test_vm.py::test_exec_builds_command_from_list -v

# Integration tests (requires Multipass installed)
uv run pytest -m integration -v
```

## Architecture

`src/multipass/` contains five modules:

- `_backend.py` — `CommandResult` dataclass, `CommandBackend` protocol, `SubprocessBackend` (real CLI), `FakeBackend` (for tests). All subprocess calls go through the backend.
- `exceptions.py` — Typed exception hierarchy rooted at `MultipassError`.
- `models.py` — Dataclasses (`VmInfo`, `VmState`, `ImageInfo`, etc.) with `from_*_json()` class methods that parse the actual Multipass CLI JSON output.
- `vm.py` — `MultipassVM`: per-VM operations (info, start, stop, restart, suspend, delete, recover, exec, transfer, mount, unmount, snapshot, restore, clone).
- `client.py` — `MultipassClient`: global operations (launch, list, find, purge, networks, version, get, set, aliases).

`MultipassClient` creates `MultipassVM` instances and passes its backend down to them. Unit tests inject a `FakeBackend` configured with pre-built `CommandResult` responses.
