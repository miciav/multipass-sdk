"""End-to-end verification: create VM(s), verify readiness, execute a command,
delete the VM(s).

Prerequisites:
    Multipass installed and running

Usage:
    uv run multipass-vm-e2e
    uv run multipass-vm-e2e --name my-test-vm --cpus 2 --memory 4G --disk 10G
    uv run multipass-vm-e2e --count 3
    uv run multipass-vm-e2e --count 2 --name worker --cpus 1
    uv run multipass-vm-e2e --configs '[{"name":"web","cpus":2},{"name":"db","cpus":4}]'
    uv run multipass-vm-e2e --list-images
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import fields

from .client import MultipassClient
from .exceptions import MultipassError
from .models import VmConfig
from .vm import MultipassVM


def _plural_label(names: list[str], actual_count: int | None = None) -> str:
    """Return 'VM 'name'' for a single VM, or 'N VMs' for multiple."""
    count = actual_count if actual_count is not None else len(names)
    if count == 1:
        return f"VM '{names[0]}'"
    return f"{count} VMs"


def _verify_vm(vm: MultipassVM, idx: int, total: int, timeout: float) -> int:
    """Run SSH/exec checks on a single VM. Returns 0 on success, 1 on failure."""
    label = f"  [{idx}/{total}] {vm.name}"

    print(f"{label}: waiting for SSH ...")
    t0 = time.monotonic()
    try:
        ip = vm.wait_ready(timeout=timeout, port=22)
    except MultipassError as exc:
        print(f"{label}: SSH timeout — {exc}", file=sys.stderr)
        return 1
    print(f"{label}: got IP {ip}, SSH ready in {time.monotonic() - t0:.1f}s")

    print(f"{label}: running verification command ...")
    result = vm.exec(["uname", "-a"])
    print(f"{label}: exit={result.returncode}  stdout={result.stdout.strip()}")
    if result.stderr:
        print(f"{label}: stderr={result.stderr.strip()}")
    if not result.success:
        print(f"{label}: FAILED — non-zero exit code", file=sys.stderr)
        return 1

    info = vm.info()
    print(
        f"{label}: state={info.state.value}  image={info.image}  "
        f"cpus={info.cpus}  memory={info.memory_total}"
    )
    return 0


def _check_mutually_exclusive(args: argparse.Namespace) -> None:
    if not args.configs:
        return
    conflicts = []
    if args.count != 1:
        conflicts.append("--count")
    if args.name is not None:
        conflicts.append("--name")
    if args.cpus != 1:
        conflicts.append("--cpus")
    if args.memory != "1G":
        conflicts.append("--memory")
    if args.disk != "5G":
        conflicts.append("--disk")
    if args.image is not None:
        conflicts.append("--image")
    if conflicts:
        raise SystemExit(
            f"--configs is mutually exclusive with: {', '.join(conflicts)}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="End-to-end VM lifecycle test (create, verify, delete)."
    )
    parser.add_argument(
        "--name", default=None,
        help="VM name; used as prefix when --count > 1 (auto-generated if omitted).",
    )
    parser.add_argument(
        "--cpus", type=int, default=1,
        help="Number of CPUs (default: 1).",
    )
    parser.add_argument(
        "--memory", default="1G",
        help="Memory size (default: 1G).",
    )
    parser.add_argument(
        "--disk", default="5G",
        help="Disk size (default: 5G).",
    )
    parser.add_argument(
        "--image", default=None,
        help="Ubuntu image (default: latest LTS).",
    )
    parser.add_argument(
        "--timeout", type=float, default=300,
        help="Max seconds to wait for SSH readiness (default: 300).",
    )
    parser.add_argument(
        "--count", type=int, default=1,
        help="Number of identical VMs to create in parallel (default: 1).",
    )
    parser.add_argument(
        "--configs",
        help=(
            "JSON array of VmConfig objects, e.g. "
            "'[{\"name\":\"web\",\"cpus\":2},{\"name\":\"db\",\"cpus\":4}]'. "
            "Mutually exclusive with --name/--cpus/--memory/--disk/--image/--count."
        ),
    )
    parser.add_argument(
        "--list-images", action="store_true",
        help="List available images and exit.",
    )
    args = parser.parse_args()

    _check_mutually_exclusive(args)

    if args.count < 1:
        raise SystemExit("--count must be at least 1")

    client = MultipassClient()

    if args.list_images:
        images = client.find()
        print(f"{'Aliases':<30} {'OS':<12} {'Release':<16} {'Version':<12}")
        print("-" * 70)
        for img in images:
            print(f"{','.join(img.aliases):<30} {img.os:<12} {img.release:<16} {img.version:<12}")
        raise SystemExit(0)

    if args.configs:
        try:
            raw = json.loads(args.configs)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"--configs: invalid JSON — {exc}") from exc
        if not isinstance(raw, list) or not raw:
            raise SystemExit("--configs: expected a non-empty JSON array")
        valid_fields = {f.name for f in fields(VmConfig)}
        configs = []
        for i, item in enumerate(raw):
            unknown = set(item) - valid_fields
            if unknown:
                raise SystemExit(f"--configs[{i}]: unknown fields {sorted(unknown)}")
            configs.append(VmConfig(**item))
    else:
        prefix = args.name or f"e2e-{int(time.time())}"
        if args.count == 1:
            configs = [VmConfig(
                name=prefix, image=args.image,
                cpus=args.cpus, memory=args.memory, disk=args.disk,
            )]
        else:
            configs = [
                VmConfig(
                    name=f"{prefix}-{i}", image=args.image,
                    cpus=args.cpus, memory=args.memory, disk=args.disk,
                )
                for i in range(args.count)
            ]

    names = [cfg.name for cfg in configs]
    num_vms = len(configs)
    vms: list[MultipassVM] = []
    exit_code = 0

    try:
        if num_vms == 1:
            cfg = configs[0]
            print(f"[1/3] Launching VM '{names[0]}' (cpus={cfg.cpus}, memory={cfg.memory}, disk={cfg.disk}) ...")
        else:
            cfg0 = configs[0]
            print(f"[1/3] Launching {num_vms} VMs in parallel (cpus={cfg0.cpus}, memory={cfg0.memory}, disk={cfg0.disk}) ...")
            for name in names:
                print(f"       - {name}")
        t0 = time.monotonic()
        vms = client.launch_many(configs)
        dt = time.monotonic() - t0
        verb = "launch" if num_vms == 1 else f"all {num_vms} launches"
        print(f"       {verb} completed in {dt:.1f}s")

        print(f"[2/3] Verifying {num_vms} VM(s) ...")
        for i, vm in enumerate(vms, start=1):
            rc = _verify_vm(vm, i, num_vms, args.timeout)
            if rc != 0:
                exit_code = 1

    except MultipassError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        exit_code = 2
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        exit_code = 130

    if vms:
        label = _plural_label(names, len(vms))
        print(f"[3/3] Deleting {label} ...")
        try:
            for vm in vms:
                vm.delete(purge=True)
            print("       done.")
        except MultipassError as exc:
            print(f"       cleanup failed: {exc}", file=sys.stderr)
            exit_code = 3
    elif exit_code != 130:
        print("[3/3] No VMs to clean up.")

    print()
    label = _plural_label(names, len(vms))
    if exit_code == 0:
        print(f"SUCCESS — {label} completed full lifecycle.")
    else:
        print(f"FAILURE (exit code {exit_code}) — see errors above.")

    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
