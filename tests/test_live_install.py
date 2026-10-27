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
