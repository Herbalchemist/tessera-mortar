# SPDX-License-Identifier: GPL-3.0-or-later
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
loader = importlib.machinery.SourceFileLoader("live_install", os.path.join(HERE, "..", "live", "src", "live-install"))
spec = importlib.util.spec_from_loader("live_install", loader)
li = importlib.util.module_from_spec(spec)
loader.exec_module(li)

LSBLK = json.dumps({"blockdevices": [
    {"name": "nvme0n1", "path": "/dev/nvme0n1", "size": 1000204886016, "model": "Samsung SSD 980 1TB", "tran": "nvme", "rm": False, "type": "disk", "ro": False, "hotplug": False},
    {"name": "sda", "path": "/dev/sda", "size": 32017047552 * 4, "model": "SanDisk Ultra", "tran": "usb", "rm": True, "type": "disk", "ro": False, "hotplug": True},
    {"name": "sdb", "path": "/dev/sdb", "size": 16000000000, "model": "Tiny", "tran": "usb", "rm": True, "type": "disk", "ro": False, "hotplug": True},
    {"name": "zram0", "path": "/dev/zram0", "size": 8000000000000, "type": "disk", "ro": False},
    {"name": "sr0", "path": "/dev/sr0", "size": 100000000000, "type": "rom"},
]})

OFFERED = {"disks": li.disks(LSBLK, live="/dev/sda"), "images": ["tessera", "tessera-nvidia", "tessera-nvidia-open"],
           "imagesDir": "/run/initramfs/live/tessera-images", "timezones": ["UTC", "America/Phoenix"]}
GOOD = {"disk": "/dev/nvme0n1", "variant": "nvidia", "user": "alex", "fullName": "Alex", "password": "hunter22",
        "timezone": "America/Phoenix", "secureBoot": "auto"}


class Disks(unittest.TestCase):
    def test_only_real_big_disks_and_never_the_usb(self):
        self.assertEqual([d["path"] for d in OFFERED["disks"]], ["/dev/nvme0n1"])

    def test_without_knowing_the_usb_it_is_offered_but_marked_removable(self):
        ds = li.disks(LSBLK, live=None)
        self.assertEqual([d["path"] for d in ds], ["/dev/nvme0n1", "/dev/sda"])
        self.assertTrue(ds[1]["removable"])


# ---------------------------------------------------------------- next to other systems
MiB, GB = 1024 ** 2, 1000 ** 3
SECT = 512


def table(parts, total=1000 * GB):
    """An sfdisk --json table: parts are (node, start bytes, size bytes)."""
    return {"partitiontable": {"label": "gpt", "sectorsize": SECT, "firstlba": 2048, "lastlba": total // SECT - 34,
                               "partitions": [{"node": n, "start": a // SECT, "size": z // SECT} for n, a, z in parts]}}


WIN_PARTS = [("/dev/nvme0n1p1", MiB, 100 * MiB), ("/dev/nvme0n1p2", 101 * MiB, 16 * MiB),
             ("/dev/nvme0n1p3", 117 * MiB, 400 * GB), ("/dev/nvme0n1p4", 117 * MiB + 400 * GB, 600 * MiB)]
WIN_LSBLK = [
    {"path": "/dev/nvme0n1p1", "size": 100 * MiB, "fstype": "vfat", "parttype": li.ESP_TYPE, "parttypename": "EFI System", "type": "part"},
    {"path": "/dev/nvme0n1p2", "size": 16 * MiB, "parttypename": "Microsoft reserved", "type": "part"},
    {"path": "/dev/nvme0n1p3", "size": 400 * GB, "fstype": "ntfs", "label": "Windows", "parttypename": "Microsoft basic data", "type": "part"},
    {"path": "/dev/nvme0n1p4", "size": 600 * MiB, "fstype": "ntfs", "parttypename": "Windows recovery environment", "type": "part"},
]


def win_disk(esp=("Microsoft", "Boot"), esp_free=60 * MiB, parts=WIN_PARTS, lsblk=WIN_LSBLK):
    look = (lambda path: {"systems": [n for n in esp if n.lower() != "boot"], "free": esp_free}) if esp is not None else (lambda path: None)
    d = {"path": "/dev/nvme0n1", "size": 1000 * GB, "model": "SSD", "transport": "nvme", "removable": False, "live": False}
    return {**d, **li.disk_layout(d["path"], table=table(parts), parts=lsblk, esp_look=look)}


class Alongside(unittest.TestCase):
    def setUp(self):
        self.efi = tempfile.mkdtemp()
        li.EFI_DIR = self.efi

    def offered(self, d):
        return {**OFFERED, "disks": [d]}

    def test_free_space_is_measured_in_one_piece(self):
        d = win_disk()
        self.assertEqual(d["systems"], ["Windows"])
        self.assertTrue(d["alongside"]["ok"])
        self.assertGreater(d["free"], 590 * GB)
        self.assertLess(d["free"], 600 * GB)
        self.assertEqual(d["esp"]["path"], "/dev/nvme0n1p1")
        self.assertEqual([q["what"] for q in d["partitions"]], ["Boot partition (EFI)", "Windows", "Windows", "Windows recovery"])

    def test_next_to_windows_reuses_its_boot_partition_and_touches_nothing_else(self):
        c = li.check({**GOOD, "layout": "alongside"}, self.offered(win_disk()))
        ks = li.kickstart(c, "/imgs", "$6$x$y")
        self.assertIn("clearpart --none", ks)
        self.assertIn("part /boot/efi --onpart=nvme0n1p1 --noformat", ks)
        self.assertNotIn("zerombr", ks)
        self.assertNotIn("clearpart --all", ks)
        self.assertNotIn("autopart", ks)
        self.assertNotIn("rm -rf /mnt/sysroot/boot/efi/EFI/fedora", ks)   # other systems' boot files stay
        self.assertIn("btrfs / --subvol --name=root LABEL=tessera", ks)

    def test_erase_is_unchanged(self):
        ks = li.kickstart(li.check(GOOD, self.offered(win_disk())), "/imgs", "$6$x$y")
        self.assertIn("clearpart --all --initlabel --drives=nvme0n1", ks)
        self.assertIn("autopart --type=btrfs --noswap", ks)
        self.assertIn("rm -rf /mnt/sysroot/boot/efi/EFI/fedora", ks)

    def test_replacing_partitions(self):
        parts = WIN_PARTS[:3] + [("/dev/nvme0n1p4", 117 * MiB + 400 * GB, 300 * GB)]
        lsblk = WIN_LSBLK[:3] + [{"path": "/dev/nvme0n1p4", "size": 300 * GB, "fstype": "ext4", "parttypename": "Linux filesystem", "type": "part"}]
        d = win_disk(parts=parts, lsblk=lsblk)
        self.assertEqual(d["systems"], ["Windows", "Linux"])
        c = li.check({**GOOD, "layout": "replace", "remove": ["/dev/nvme0n1p4"]}, self.offered(d))
        ks = li.kickstart(c, "/imgs", "$6$x$y")
        self.assertIn("clearpart --list=nvme0n1p4", ks)
        self.assertNotIn("clearpart --none", ks)
        # the removed partition joins the free space after it: one bigger piece
        self.assertGreater(li.biggest_room(d["table"], ["/dev/nvme0n1p4"]), 590 * GB)

    def test_refusals(self):
        d = win_disk()
        for patch, msg in [({"layout": "shrink"}, "unknown way"), ({"layout": "replace"}, "pick the partitions"),
                           ({"layout": "replace", "remove": ["/dev/nvme0n1p1"]}, "boot partition stays"),
                           ({"layout": "replace", "remove": ["/dev/sda1"]}, "isn't on this disk"),
                           ({"layout": "replace", "remove": "/dev/nvme0n1p3"}, "pick the partitions"),
                           ({"layout": "replace", "remove": ["/dev/nvme0n1p3", "/dev/nvme0n1p3"]}, "once")]:
            with self.assertRaises(li.Bad, msg=str(patch)) as e:
                li.check({**GOOD, **patch}, self.offered(d))
            self.assertIn(msg, str(e.exception).lower())

    def test_not_enough_room(self):
        full = WIN_PARTS[:3] + [("/dev/nvme0n1p4", 117 * MiB + 400 * GB, 590 * GB)]
        with self.assertRaises(li.Bad) as e:
            li.check({**GOOD, "layout": "alongside"}, self.offered(win_disk(parts=full)))
        self.assertIn("not enough room", str(e.exception).lower())

    def test_another_fedora_on_the_disk_is_refused(self):
        d = win_disk(esp=("Microsoft", "fedora", "Boot"))
        self.assertFalse(d["alongside"]["ok"])
        self.assertIn("fedora", d["alongside"]["why"].lower())
        with self.assertRaises(li.Bad):
            li.check({**GOOD, "layout": "alongside"}, self.offered(d))

    def test_full_or_unreadable_boot_partition_is_refused(self):
        self.assertFalse(win_disk(esp_free=10 * MiB)["alongside"]["ok"])
        self.assertFalse(win_disk(esp=None)["alongside"]["ok"])

    def test_no_uefi_or_mbr_or_empty(self):
        os.rmdir(self.efi)
        self.assertIn("uefi", win_disk()["alongside"]["why"].lower())
        os.mkdir(self.efi)
        mbr = {"partitiontable": {**table(WIN_PARTS)["partitiontable"], "label": "dos"}}
        d = li.disk_layout("/dev/x", table=mbr, parts=WIN_LSBLK, esp_look=lambda p: None)
        self.assertIn("mbr", d["alongside"]["why"].lower())
        e = li.disk_layout("/dev/x", table={}, parts=[], esp_look=lambda p: None)
        self.assertIn("empty", e["alongside"]["why"].lower())

    def test_lsblk_lists_partitions_beside_the_disk(self):
        # what lsblk on the USB really answers without a NAME column (seen in the VM install test)
        flat = {"blockdevices": [{"path": "/dev/vda", "type": "disk"}, *[{**q, "path": q["path"].replace("/dev/nvme0n1p", "/dev/vda")} for q in WIN_LSBLK]]}
        tree = {"blockdevices": [{"path": "/dev/vda", "type": "disk", "children": flat["blockdevices"][1:]}]}
        for shape in (flat, tree):
            self.assertEqual([q["path"] for q in li.partitions_of("/dev/vda", shape)], ["/dev/vda1", "/dev/vda2", "/dev/vda3", "/dev/vda4"])
        self.assertEqual(li.partitions_of("/dev/vdb", flat), [])

    def test_the_whole_probe_path_finds_windows(self):
        import types
        flat = {"blockdevices": [{"path": "/dev/nvme0n1", "type": "disk"}, *WIN_LSBLK]}
        answers = {"sfdisk": json.dumps(table(WIN_PARTS)), "lsblk": json.dumps(flat)}
        real = li.run
        li.run = lambda cmd, **kw: types.SimpleNamespace(stdout=answers[cmd[0]], stderr="", returncode=0)
        try:
            d = li.disk_layout("/dev/nvme0n1", esp_look=lambda p: {"systems": ["Microsoft"], "free": 60 * MiB})
        finally:
            li.run = real
        self.assertEqual(d["esp"]["path"], "/dev/nvme0n1p1")
        self.assertEqual(d["systems"], ["Windows"])
        self.assertEqual(len(d["partitions"]), 4)
        self.assertTrue(d["alongside"]["ok"])

    def test_disagreeing_readings_leave_the_disk_alone(self):
        d = li.disk_layout("/dev/nvme0n1", table=table(WIN_PARTS), parts=WIN_LSBLK[:2], esp_look=lambda p: {"systems": ["Microsoft"], "free": 60 * MiB})
        self.assertFalse(d["alongside"]["ok"])
        self.assertIn("reliably", d["alongside"]["why"])

    def test_a_disk_without_a_boot_partition_gets_one(self):
        parts = [("/dev/sdb1", MiB, 200 * GB)]
        lsblk = [{"path": "/dev/sdb1", "size": 200 * GB, "fstype": "ntfs", "label": "Games", "parttypename": "Microsoft basic data", "type": "part"}]
        d = {**win_disk(parts=parts, lsblk=lsblk), "path": "/dev/nvme0n1"}
        self.assertIsNone(d["esp"])
        c = li.check({**GOOD, "layout": "alongside"}, self.offered(d))
        self.assertIn("part /boot/efi --fstype=efi --size=600 --ondisk=nvme0n1", li.kickstart(c, "/imgs", "$6$x$y"))


class Check(unittest.TestCase):
    def test_good(self):
        c = li.check(GOOD, OFFERED)
        self.assertEqual(c["image"], "tessera-nvidia")
        self.assertEqual(c["hostname"], "tessera")

    def test_refusals(self):
        for patch, msg in [({"disk": "/dev/sda"}, "disk"), ({"disk": "/dev/nvme0n1; rm -rf /"}, "disk"),
                           ({"variant": "evil"}, "build"), ({"user": "Root"}, "user name"), ({"user": "9lives"}, "user name"),
                           ({"user": "a b"}, "user name"), ({"password": "abc"}, "password"), ({"password": "ok\nrootpw x"}, "password"),
                           ({"timezone": "Mars/Base"}, "time zone")]:
            with self.assertRaises(li.Bad, msg=str(patch)) as e:
                li.check({**GOOD, **patch}, OFFERED)
            self.assertIn(msg, str(e.exception).lower())

    def test_missing_build_on_usb(self):
        with self.assertRaises(li.Bad):
            li.check(GOOD, {**OFFERED, "images": ["tessera"]})

    def test_full_name_cannot_break_out(self):
        c = li.check({**GOOD, "fullName": 'Al"ex\n--groups=root'}, OFFERED)
        self.assertNotIn('"', c["fullName"])
        self.assertNotIn("\n", c["fullName"])


class Kickstart(unittest.TestCase):
    def ks(self, **patch):
        return li.kickstart(li.check({**GOOD, **patch}, OFFERED), OFFERED["imagesDir"], "$6$salt$hash", sb_key="/k.der", registry="ghcr.io/herbalchemist")

    def test_contents(self):
        k = self.ks()
        self.assertIn("ostreecontainer --url=/run/initramfs/live/tessera-images:tessera-nvidia --transport=oci", k)
        self.assertIn("clearpart --all --initlabel --drives=nvme0n1", k)
        self.assertIn("ignoredisk --only-use=nvme0n1", k)
        self.assertIn("user --name=alex --groups=wheel --iscrypted --password=$6$salt$hash --gecos=\"Alex\"", k)
        self.assertIn("timezone America/Phoenix --utc", k)
        self.assertIn("ostree-image-signed:docker://ghcr.io/herbalchemist/tessera-nvidia:latest", k)
        self.assertNotIn("unverified", k)
        self.assertIn("mokutil --import /k.der", k)
        self.assertNotIn("hunter22", k)

    def test_manual_secure_boot_leaves_keys_alone(self):
        self.assertNotIn("mokutil", self.ks(secureBoot="manual"))

    def test_the_original_version_is_kept_for_good(self):
        self.assertIn("ostree admin --sysroot=/mnt/sysroot pin 0", self.ks())

    def test_every_section_closes(self):
        k = self.ks()
        self.assertEqual(k.count("\n%pre-install") + k.count("\n%post"), k.count("\n%end"))


class Online(unittest.TestCase):
    OFF = {**OFFERED, "source": "online", "imagesDir": None}

    def test_online_kickstart_pulls_from_the_registry(self):
        c = li.check(GOOD, {**self.OFF, "online": True})
        k = li.kickstart(c, None, "$6$salt$hash", sb_key="/k.der", registry="ghcr.io/herbalchemist")
        self.assertIn("ostreecontainer --url=ghcr.io/herbalchemist/tessera-nvidia:latest --transport=registry", k)
        self.assertNotIn("--transport=oci", k)

    def test_offline_online_usb_is_refused(self):
        with self.assertRaises(li.Bad) as e:
            li.check(GOOD, {**self.OFF, "online": False})
        self.assertIn("internet", str(e.exception))


class Images(unittest.TestCase):
    def test_reads_ref_names(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "index.json"), "w") as f:
                json.dump({"manifests": [{"annotations": {"org.opencontainers.image.ref.name": n}} for n in ("tessera", "tessera-nvidia", "other")]}, f)
            self.assertEqual(li.images_available(d), ["tessera", "tessera-nvidia"])


if __name__ == "__main__":
    unittest.main()
