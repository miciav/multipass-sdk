from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class VmState(Enum):
    RUNNING = "Running"
    STOPPED = "Stopped"
    DELETED = "Deleted"
    SUSPENDED = "Suspended"
    STARTING = "Starting"
    RESTARTING = "Restarting"
    UNKNOWN = "Unknown"

    @classmethod
    def _missing_(cls, value: object) -> "VmState":
        return cls.UNKNOWN


@dataclass
class VmInfo:
    name: str
    state: VmState
    ipv4: list[str]
    image: str
    image_hash: str
    cpus: int
    memory_total: str
    memory_used: str
    disk_total: str
    disk_used: str
    mounts: dict[str, str]

    @classmethod
    def from_info_json(cls, data: dict, name: str) -> "VmInfo":
        vm = data["info"][name]
        disks = vm.get("disks", {})
        first_disk = next(iter(disks.values()), {})
        memory = vm.get("memory", {})
        return cls(
            name=name,
            state=VmState(vm.get("state", "Unknown")),
            ipv4=vm.get("ipv4", []),
            image=vm.get("image_release", ""),
            image_hash=vm.get("image_hash", ""),
            cpus=int(vm.get("cpu_count", 1)),
            memory_total=str(memory.get("total", 0)),
            memory_used=str(memory.get("used", 0)),
            disk_total=str(first_disk.get("total", "0")),
            disk_used=str(first_disk.get("used", "0")),
            mounts={
                target: mount_data.get("source_path", "")
                for target, mount_data in vm.get("mounts", {}).items()
            },
        )

    @classmethod
    def from_list_json(cls, data: dict) -> list["VmInfo"]:
        return [
            cls(
                name=item["name"],
                state=VmState(item.get("state", "Unknown")),
                ipv4=item.get("ipv4", []),
                image=item.get("release", ""),
                image_hash="",
                cpus=0,
                memory_total="",
                memory_used="",
                disk_total="",
                disk_used="",
                mounts={},
            )
            for item in data.get("list", [])
        ]


@dataclass
class ImageInfo:
    aliases: list[str]
    os: str
    release: str
    remote: str
    version: str

    @classmethod
    def from_find_json(cls, data: dict) -> list["ImageInfo"]:
        return [
            cls(
                aliases=img.get("aliases", []),
                os=img.get("os", ""),
                release=img.get("release", ""),
                remote=img.get("remote", ""),
                version=img.get("version", ""),
            )
            for img in data.get("images", {}).values()
        ]


@dataclass
class NetworkInfo:
    name: str
    type: str
    description: str

    @classmethod
    def from_networks_json(cls, data: dict) -> list["NetworkInfo"]:
        return [
            cls(
                name=item["name"],
                type=item.get("type", ""),
                description=item.get("description", ""),
            )
            for item in data.get("list", [])
        ]


@dataclass
class VersionInfo:
    multipass: str
    multipassd: str

    @classmethod
    def from_json(cls, data: dict) -> "VersionInfo":
        return cls(
            multipass=data.get("multipass", ""),
            multipassd=data.get("multipassd", ""),
        )


@dataclass
class AliasInfo:
    alias: str
    instance: str
    command: str
    working_directory: str

    @classmethod
    def from_aliases_json(cls, data: dict) -> list["AliasInfo"]:
        return [
            cls(
                alias=item["alias"],
                instance=item.get("instance", ""),
                command=item.get("command", ""),
                working_directory=item.get("working-directory", ""),
            )
            for item in data.get("aliases", [])
        ]


@dataclass
class SnapshotInfo:
    name: str
    comment: str
    created: str
    parent: str | None
    instance: str

    @classmethod
    def from_snapshots_json(cls, data: dict) -> list["SnapshotInfo"]:
        return [
            cls(
                name=item["name"],
                comment=item.get("comment", ""),
                created=item.get("created", ""),
                parent=item.get("parent"),
                instance=item.get("instance", ""),
            )
            for item in data.get("list", [])
        ]
