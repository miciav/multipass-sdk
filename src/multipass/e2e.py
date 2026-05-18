"""End-to-end verification: create VM(s), verify readiness, run feature tests,
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
    uv run multipass-vm-e2e --skip transfer,clone
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from dataclasses import fields
from pathlib import Path

from .client import MultipassClient
from .exceptions import MultipassError
from .models import VmConfig, VmState
from .vm import MultipassVM

_STEPS = 5


def _plural_label(names: list[str], actual_count: int | None = None) -> str:
    count = actual_count if actual_count is not None else len(names)
    if count == 1:
        return f"VM '{names[0]}'"
    return f"{count} VMs"


def _verify_vm(vm: MultipassVM, idx: int, total: int, timeout: float) -> int:
    """Run SSH/exec checks. Returns 0 on success, 1 on failure."""
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
        raise SystemExit(f"--configs is mutually exclusive with: {', '.join(conflicts)}")


# ------------------------------------------------------------------ feature tests


def _test_exec_structured(vm: MultipassVM) -> bool:
    """Verify exec_structured with cwd and env."""
    label = f"       [{vm.name}]"
    print(f"{label} exec_structured(cwd=/tmp, env={{MSG=hello}}) ...")
    try:
        result = vm.exec_structured(
            ["sh", "-c", 'echo "cwd=$(pwd)" "MSG=$MSG"'],
            cwd="/tmp",
            env={"MSG": "hello"},
        )
    except MultipassError as exc:
        print(f"{label} exec_structured FAILED — {exc}", file=sys.stderr)
        return False
    stdout = result.stdout.strip()
    ok = "cwd=/tmp" in stdout and "MSG=hello" in stdout
    print(f"{label}   stdout: {stdout}")
    if not ok:
        print(f"{label} exec_structured FAILED — unexpected output", file=sys.stderr)
    return ok


def _test_stop_start(vm: MultipassVM, timeout: float) -> bool:
    """Stop the VM, verify state, start it, verify running + SSH."""
    label = f"       [{vm.name}]"
    print(f"{label} stop ...")
    try:
        vm.stop()
    except MultipassError as exc:
        print(f"{label} stop FAILED — {exc}", file=sys.stderr)
        return False

    info = vm.info()
    if info.state != VmState.STOPPED:
        print(f"{label} stop FAILED — expected state=Stopped, got {info.state}", file=sys.stderr)
        return False
    print(f"{label}   state={info.state.value} ✓")

    print(f"{label} start ...")
    try:
        vm.start()
    except MultipassError as exc:
        print(f"{label} start FAILED — {exc}", file=sys.stderr)
        return False

    print(f"{label}   waiting for SSH after start ...")
    try:
        vm.wait_ready(timeout=timeout, port=22)
    except MultipassError as exc:
        print(f"{label} start FAILED — SSH not reachable: {exc}", file=sys.stderr)
        return False
    print(f"{label}   SSH reachable ✓")
    return True


def _test_restart(vm: MultipassVM, timeout: float) -> bool:
    """Restart the VM and verify it comes back."""
    label = f"       [{vm.name}]"
    print(f"{label} restart ...")
    try:
        vm.restart()
    except MultipassError as exc:
        print(f"{label} restart FAILED — {exc}", file=sys.stderr)
        return False

    # VM state during restart is transient; wait for SSH
    try:
        vm.wait_ready(timeout=timeout, port=22)
    except MultipassError as exc:
        print(f"{label} restart FAILED — SSH not reachable: {exc}", file=sys.stderr)
        return False
    print(f"{label}   SSH reachable after restart ✓")
    return True


def _test_transfer(vm: MultipassVM) -> bool:
    """Transfer a file host→VM, verify, VM→host, verify round-trip."""
    label = f"       [{vm.name}]"
    print(f"{label} transfer (host → VM → host) ...")

    content = f"e2e-transfer-test-{int(time.time())}"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tf:
        tf.write(content)
        host_src = tf.name

    vm_dest = f"{vm.name}:/tmp/e2e_transfer_in.txt"
    try:
        vm.transfer(host_src, vm_dest)
    except MultipassError as exc:
        print(f"{label} transfer (host→VM) FAILED — {exc}", file=sys.stderr)
        Path(host_src).unlink(missing_ok=True)
        return False

    # Verify file arrived
    result = vm.exec(["cat", "/tmp/e2e_transfer_in.txt"])
    if result.stdout.strip() != content:
        print(f"{label} transfer (host→VM) FAILED — content mismatch", file=sys.stderr)
        print(f"{label}   expected: {content!r}")
        print(f"{label}   got:      {result.stdout.strip()!r}")
        Path(host_src).unlink(missing_ok=True)
        return False
    print(f"{label}   host→VM ✓  ({len(content)} bytes)")

    # Transfer back
    host_back = host_src + ".back"
    try:
        vm.transfer(f"{vm.name}:/tmp/e2e_transfer_in.txt", host_back)
    except MultipassError as exc:
        print(f"{label} transfer (VM→host) FAILED — {exc}", file=sys.stderr)
        Path(host_src).unlink(missing_ok=True)
        return False

    roundtrip = Path(host_back).read_text()
    Path(host_back).unlink(missing_ok=True)
    Path(host_src).unlink(missing_ok=True)

    if roundtrip != content:
        print(f"{label} transfer (VM→host) FAILED — content mismatch", file=sys.stderr)
        return False
    print(f"{label}   VM→host ✓  ({len(roundtrip)} bytes)")
    return True


def _test_clone(vm: MultipassVM, timeout: float) -> tuple[bool, MultipassVM | None]:
    """Clone the VM, verify the clone is reachable. Returns (ok, clone_vm)."""
    label = f"       [{vm.name}]"
    clone_name = f"{vm.name}-clone"
    print(f"{label} clone → {clone_name} ...")

    try:
        cloned = vm.clone(clone_name)
    except MultipassError as exc:
        print(f"{label} clone FAILED — {exc}", file=sys.stderr)
        return False, None

    try:
        cloned.wait_ready(timeout=timeout, port=22)
    except MultipassError as exc:
        print(f"{label} clone FAILED — SSH not reachable: {exc}", file=sys.stderr)
        _safe_delete(cloned)
        return False, None

    result = cloned.exec(["hostname"])
    print(f"{label}   hostname={result.stdout.strip()}  exit={result.returncode}  ✓")
    return result.success, cloned


def _test_snapshot_restore(vm: MultipassVM, timeout: float) -> bool:
    """Create snapshot, stop VM, restore, start, verify."""
    label = f"       [{vm.name}]"
    snap_name = "e2e-snap"

    print(f"{label} snapshot '{snap_name}' ...")
    try:
        vm.snapshot(snap_name, comment="e2e test snapshot")
    except MultipassError as exc:
        print(f"{label} snapshot FAILED — {exc}", file=sys.stderr)
        return False

    snaps = vm.snapshots()
    if not any(s.name == snap_name for s in snaps):
        print(f"{label} snapshot FAILED — snapshot not found in list", file=sys.stderr)
        return False
    print(f"{label}   snapshot created ✓")

    print(f"{label} stop (for restore) ...")
    try:
        vm.stop()
    except MultipassError as exc:
        print(f"{label} stop FAILED — {exc}", file=sys.stderr)
        return False

    print(f"{label} restore '{snap_name}' ...")
    try:
        vm.restore(snap_name, destructive=True)
    except MultipassError as exc:
        print(f"{label} restore FAILED — {exc}", file=sys.stderr)
        return False
    print(f"{label}   restored ✓")

    print(f"{label} start after restore ...")
    try:
        vm.start()
        vm.wait_ready(timeout=timeout, port=22)
    except MultipassError as exc:
        print(f"{label} start after restore FAILED — {exc}", file=sys.stderr)
        return False
    print(f"{label}   SSH reachable after restore ✓")
    return True


# ------------------------------------------------------------------ helpers


def _safe_delete(vm: MultipassVM) -> None:
    try:
        vm.delete(purge=True)
    except MultipassError:
        pass


def _skip_reason(feature: str, skipped: set[str], count: int) -> str | None:
    if "all" in skipped or feature in skipped:
        return "skipped by --skip"
    if count > 1 and feature != "exec_structured":
        return "skipped (--count > 1)"
    return None


# ------------------------------------------------------------------ main


def main() -> None:
    parser = argparse.ArgumentParser(
        description="End-to-end VM lifecycle test (create, verify, feature test, delete)."
    )
    parser.add_argument(
        "--name", default=None,
        help="VM name; used as prefix when --count > 1 (auto-generated if omitted).",
    )
    parser.add_argument("--cpus", type=int, default=1, help="Number of CPUs (default: 1).")
    parser.add_argument("--memory", default="1G", help="Memory size (default: 1G).")
    parser.add_argument("--disk", default="5G", help="Disk size (default: 5G).")
    parser.add_argument("--image", default=None, help="Ubuntu image (default: latest LTS).")
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
        help="JSON array of VmConfig objects. Mutually exclusive with --name/--cpus/--memory/--disk/--image/--count.",
    )
    parser.add_argument(
        "--skip", default="",
        help="Comma-separated feature names to skip: exec_structured, stop_start, restart, transfer, clone, snapshot_restore. Use 'all' to skip all feature tests.",
    )
    parser.add_argument("--list-images", action="store_true", help="List available images and exit.")
    args = parser.parse_args()

    _check_mutually_exclusive(args)

    if args.count < 1:
        raise SystemExit("--count must be at least 1")

    skipped = {s.strip() for s in args.skip.split(",") if s.strip()}

    client = MultipassClient()

    if args.list_images:
        images = client.find()
        print(f"{'Aliases':<30} {'OS':<12} {'Release':<16} {'Version':<12}")
        print("-" * 70)
        for img in images:
            print(f"{','.join(img.aliases):<30} {img.os:<12} {img.release:<16} {img.version:<12}")
        raise SystemExit(0)

    # --- build configs -------------------------------------------------------
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
    clones: list[MultipassVM] = []
    exit_code = 0
    failed_features: list[str] = []

    try:
        # ============================================================ [1/5] launch
        if num_vms == 1:
            cfg = configs[0]
            print(f"[1/{_STEPS}] Launching VM '{names[0]}' (cpus={cfg.cpus}, memory={cfg.memory}, disk={cfg.disk}) ...")
        else:
            cfg0 = configs[0]
            print(f"[1/{_STEPS}] Launching {num_vms} VMs in parallel (cpus={cfg0.cpus}, memory={cfg0.memory}, disk={cfg0.disk}) ...")
            for name in names:
                print(f"       - {name}")
        t0 = time.monotonic()
        vms = client.launch_many(configs)
        dt = time.monotonic() - t0
        verb = "launch" if num_vms == 1 else f"all {num_vms} launches"
        print(f"       {verb} completed in {dt:.1f}s")

        # ============================================================ [2/5] verify
        print(f"[2/{_STEPS}] Basic verification ({num_vms} VM(s)) ...")
        for i, vm in enumerate(vms, start=1):
            rc = _verify_vm(vm, i, num_vms, args.timeout)
            if rc != 0:
                exit_code = 1

        # ============================================================ [3/5] features
        if num_vms == 1 and "all" not in skipped:
            print(f"[3/{_STEPS}] Feature tests ...")
            primary = vms[0]

            tests = [
                ("exec_structured", lambda: _test_exec_structured(primary)),
                ("stop_start", lambda: _test_stop_start(primary, args.timeout)),
                ("restart", lambda: _test_restart(primary, args.timeout)),
                ("transfer", lambda: _test_transfer(primary)),
                ("clone", lambda: _test_clone_wrapper(primary, args.timeout, clones)),
                ("snapshot_restore", lambda: _test_snapshot_restore(primary, args.timeout)),
            ]

            for name, test_fn in tests:
                reason = _skip_reason(name, skipped, num_vms)
                if reason:
                    print(f"       ⏭  {name}: {reason}")
                    continue
                try:
                    ok = test_fn()
                except Exception as exc:
                    print(f"       ✗  {name}: unexpected error — {exc}", file=sys.stderr)
                    failed_features.append(name)
                    continue
                if ok:
                    print(f"       ✓  {name}")
                else:
                    failed_features.append(name)
                    print(f"       ✗  {name} FAILED")
        else:
            if num_vms > 1:
                print(f"[3/{_STEPS}] Feature tests skipped (--count > 1)")
            else:
                print(f"[3/{_STEPS}] Feature tests skipped (--skip all)")

    except MultipassError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        exit_code = 2
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        exit_code = 130

    # ============================================================ [4/5] cleanup clones
    print(f"[4/{_STEPS}] Cleaning up clones ({len(clones)} VM(s)) ...")
    for c in clones:
        _safe_delete(c)

    # ============================================================ [5/5] cleanup VMs
    if vms:
        label = _plural_label(names, len(vms))
        print(f"[5/{_STEPS}] Deleting {label} ...")
        try:
            for vm in vms:
                vm.delete(purge=True)
            print("       done.")
        except MultipassError as exc:
            print(f"       cleanup failed: {exc}", file=sys.stderr)
            exit_code = 3
    elif exit_code != 130:
        print(f"[5/{_STEPS}] No VMs to clean up.")

    # --------------------------------------------------------------- summary
    print()
    label = _plural_label(names, len(vms))
    if exit_code == 0 and not failed_features:
        print(f"SUCCESS — {label} completed full lifecycle, all features passed.")
    else:
        parts = []
        if exit_code != 0:
            parts.append(f"exit code {exit_code}")
        if failed_features:
            parts.append(f"features failed: {', '.join(failed_features)}")
        print(f"FAILURE ({'; '.join(parts)}) — see errors above.")
        if exit_code == 0:
            exit_code = 1

    raise SystemExit(exit_code)


def _test_clone_wrapper(vm, timeout, clones):
    ok, cloned = _test_clone(vm, timeout)
    if cloned is not None:
        clones.append(cloned)
    return ok


if __name__ == "__main__":
    main()
