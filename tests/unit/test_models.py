from multipass.models import (
    VmInfo, VmState, ImageInfo, NetworkInfo, VersionInfo, AliasInfo, SnapshotInfo
)

INFO_JSON = {
    "errors": [],
    "info": {
        "my-vm": {
            "cpu_count": "2",
            "disks": {"sda1": {"total": "5368709120", "used": "1234567890"}},
            "image_hash": "abc123",
            "image_release": "22.04 LTS",
            "ipv4": ["192.168.64.2"],
            "memory": {"total": 1073741824, "used": 123456789},
            "mounts": {},
            "state": "Running",
        }
    },
}

LIST_JSON = {
    "list": [
        {"ipv4": ["192.168.64.2"], "name": "my-vm", "release": "22.04 LTS", "state": "Running"}
    ]
}


def test_vminfo_from_info_json():
    info = VmInfo.from_info_json(INFO_JSON, "my-vm")
    assert info.name == "my-vm"
    assert info.state == VmState.RUNNING
    assert info.ipv4 == ["192.168.64.2"]
    assert info.cpus == 2
    assert info.image == "22.04 LTS"
    assert info.image_hash == "abc123"


def test_vminfo_from_list_json():
    items = VmInfo.from_list_json(LIST_JSON)
    assert len(items) == 1
    assert items[0].name == "my-vm"
    assert items[0].state == VmState.RUNNING
    assert items[0].ipv4 == ["192.168.64.2"]


def test_vmstate_unknown_falls_back():
    info = VmInfo.from_info_json(
        {"errors": [], "info": {"x": {**INFO_JSON["info"]["my-vm"], "state": "Weird"}}}, "x"
    )
    assert info.state == VmState.UNKNOWN


def test_imageinfo_from_json():
    data = {
        "errors": [],
        "images": {
            "22.04": {
                "aliases": ["jammy", "lts"],
                "os": "Ubuntu",
                "release": "22.04 LTS",
                "remote": "",
                "version": "20230801",
            }
        },
    }
    images = ImageInfo.from_find_json(data)
    assert len(images) == 1
    assert "jammy" in images[0].aliases
    assert images[0].os == "Ubuntu"


def test_version_info_from_json():
    v = VersionInfo.from_json({"multipass": "1.13.0", "multipassd": "1.13.0"})
    assert v.multipass == "1.13.0"
    assert v.multipassd == "1.13.0"


def test_network_info_from_json():
    data = {"list": [{"description": "Wi-Fi", "name": "en0", "type": "wifi"}]}
    nets = NetworkInfo.from_networks_json(data)
    assert len(nets) == 1
    assert nets[0].name == "en0"


def test_alias_info_from_json():
    data = {
        "aliases": [
            {"alias": "myalias", "command": "ls", "instance": "myvm", "working-directory": "default"}
        ]
    }
    aliases = AliasInfo.from_aliases_json(data)
    assert len(aliases) == 1
    assert aliases[0].alias == "myalias"
    assert aliases[0].instance == "myvm"


def test_snapshot_info_from_json():
    data = {
        "list": [
            {
                "comment": "Before upgrade",
                "created": "2023-08-15T10:30:00.000Z",
                "instance": "my-vm",
                "name": "snapshot1",
                "parent": None,
            }
        ]
    }
    snaps = SnapshotInfo.from_snapshots_json(data)
    assert len(snaps) == 1
    assert snaps[0].name == "snapshot1"
    assert snaps[0].parent is None
