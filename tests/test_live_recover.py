# SPDX-License-Identifier: GPL-3.0-or-later
# live-recover against a stand-in installed Tessera: an ostree sysroot with two versions, boot
# entries, a home folder with Tessera's settings, /etc/passwd, /etc/group and /etc/shadow.
import ctypes
import ctypes.util
import importlib.machinery
import importlib.util
import json
import os
import shutil
import stat
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
loader = importlib.machinery.SourceFileLoader("live_recover", os.path.join(HERE, "..", "live", "src", "live-recover"))
spec = importlib.util.spec_from_loader("live_recover", loader)
lr = importlib.util.module_from_spec(spec)
loader.exec_module(lr)

# the stand-in person: whoever runs the tests (so chown works), or 1000 when that is root
UID, GID = (os.getuid(), os.getgid()) if os.getuid() >= 1000 else (1000, 1000)


def sha512(password, salt="saltsalt"):
    lib = ctypes.CDLL(ctypes.util.find_library("crypt"))
    lib.crypt.restype = ctypes.c_char_p
    lib.crypt.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    return lib.crypt(password.encode(), f"$6${salt}$".encode()).decode()


def write(path, text, mode=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    if mode is not None:
        os.chmod(path, mode)


class Stand(unittest.TestCase):
    """A file system as Anaconda leaves it after installing Tessera (btrfs top level)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["TESSERA_RECOVER_MNT"] = self.tmp  # repairs don't remount in tests
        self.mnt = os.path.join(self.tmp, "fs")
        self.boot = os.path.join(self.tmp, "boot")
        sysroot = os.path.join(self.mnt, "root")
        base = os.path.join(sysroot, "ostree", "deploy", "default", "deploy")
        for name, ver, image in (("aaa.0", "43.20261101.0", "ghcr.io/herbalchemist/tessera:latest"), ("bbb.0", "43.20261031.0", "ghcr.io/herbalchemist/tessera:latest")):
            d = os.path.join(base, name)
            write(os.path.join(d, "usr", "lib", "os-release"), f'NAME="Tessera"\nVERSION="{ver}"\nPRETTY_NAME="Tessera {ver}"\n')
            write(os.path.join(base, name + ".origin"), f"[origin]\ncontainer-image-reference=ostree-image-signed:docker://{image}\n")
            etc = os.path.join(d, "etc")
            write(os.path.join(etc, "passwd"), f"root:x:0:0:root:/root:/bin/bash\nalex:x:{UID}:{GID}:Alex:/var/home/alex:/bin/bash\nkid:x:1001:1001:Kid:/var/home/kid:/bin/bash\nsddm:x:978:978::/var/lib/sddm:/sbin/nologin\n")
            write(os.path.join(etc, "group"), "wheel:x:10:alex\n")
            write(os.path.join(etc, "shadow"), f"root:!:19000::::::\nalex:{sha512('tessera1')}:19000:0:99999:7:::\nkid:{sha512('kidpass', 'kidsalts')}:19000:0:99999:7:::\n", 0o600)
            write(os.path.join(etc, "hostname"), "alex-pc\n")
        # boot entries: the newest is (ostree:0)
        for n, (title, boot_n, name) in enumerate((("Tessera 43.20261101.0 (ostree:0)", "1", "aaa.0"), ("Tessera 43.20261031.0 (ostree:1)", "1", "bbb.0"))):
            link_dir = os.path.join(sysroot, "ostree", f"boot.{boot_n}", "default", "csum")
            os.makedirs(link_dir, exist_ok=True)
            os.symlink(f"../../../deploy/default/deploy/{name}", os.path.join(link_dir, str(n)))
            write(os.path.join(self.boot, "loader", "entries", f"ostree-{n + 1}-default.conf"), f"title {title}\nversion {n + 1}\noptions root=UUID=x rw ostree=/ostree/boot.{boot_n}/default/csum/{n}\n")
        # home folders on the 'home' subvolume
        self.home = os.path.join(self.mnt, "home", "alex")
        write(os.path.join(self.home, ".local", "share", "tessera", "settings.json"), json.dumps({"pin": {"hash": "x", "salt": "y"}, "codeAddons": {"enabled": ["xbox", "other"], "allowUnverified": True}, "theme": {"active": "stock"}}), 0o600)
        write(os.path.join(self.home, ".local", "state", "tessera", "pin-tries.json"), "{}")
        os.makedirs(os.path.join(self.mnt, "home", "kid"))
        self.inst = lr.find_installs(self.mnt, self.boot, {"device": "/dev/nvme0n1p3", "uuid": "1234-abcd", "type": "btrfs"})[0]
        self.inst.update(id="1234abcd-0000:default", mount=self.mnt, disk={"name": "nvme0n1"})

    def tearDown(self):
        shutil.rmtree(self.tmp)
        os.environ.pop("TESSERA_RECOVER_MNT", None)

    def settings(self):
        with open(os.path.join(self.home, ".local", "share", "tessera", "settings.json")) as f:
            return json.load(f)


class Finding(Stand):
    def test_finds_the_install_versions_in_boot_order_and_people(self):
        i = self.inst
        self.assertEqual([d["version"] for d in i["deployments"]], ["43.20261101.0", "43.20261031.0"])
        self.assertEqual([d["index"] for d in i["deployments"]], [0, 1])
        self.assertEqual([(u["name"], u["admin"]) for u in i["users"]], [("alex", True), ("kid", False)])
        self.assertEqual(i["users"][0]["path"], self.home)
        self.assertEqual(i["hostname"], "alex-pc")

    def test_other_systems_are_not_tessera(self):
        other = os.path.join(self.tmp, "other")
        write(os.path.join(other, "ostree", "deploy", "fedora", "deploy", "c.0", "usr", "lib", "os-release"), 'NAME="Fedora Linux"\n')
        self.assertEqual(lr.find_installs(other, None, {}), [])

    def test_the_screens_see_no_paths(self):
        p = json.dumps(lr.public(self.inst))
        self.assertNotIn(self.tmp, p)
        self.assertIn("43.20261101.0", p)

    def test_ids_are_checked_before_anything_is_looked_up(self):
        for bad in ("", "../etc", "1234:default;rm", "x" * 100, None):
            self.assertIsNone(lr.find(bad))


class Diagnosing(Stand):
    def test_sign_in_off_and_shards_on_are_found_with_their_fixes(self):
        d = lr.diagnose(self.inst)
        keys = {f["key"]: f["fix"] for f in d["findings"]}
        self.assertEqual(keys.get("signin"), "signin")
        self.assertEqual(keys.get("shards"), "shards")
        self.assertIn("versions", keys)

    def test_report_is_scrubbed_and_saved_in_the_persons_tessera_folder(self):
        text = lr.report_text(self.inst, lr.diagnose(self.inst))
        self.assertNotIn("alex-pc", text)
        self.assertNotIn("alex", text.lower().replace("[user]", ""))
        saved = lr.save_report(self.inst, text)
        self.assertTrue(saved.startswith("~/Tessera/Reports/tessera-recovery-report-"))
        files = os.listdir(os.path.join(self.home, "Tessera", "Reports"))
        self.assertEqual(len(files), 1)


class Passwords(Stand):
    def test_only_an_administrators_right_password(self):
        self.assertTrue(lr.password_ok(self.inst, "alex", "tessera1"))
        self.assertFalse(lr.password_ok(self.inst, "alex", "wrong"))
        self.assertFalse(lr.password_ok(self.inst, "kid", "kidpass"))  # not an administrator
        self.assertFalse(lr.password_ok(self.inst, "root", ""))
        self.assertFalse(lr.password_ok(self.inst, "nobody", "x"))
        self.assertFalse(lr.password_ok(self.inst, "alex", None))


class Repairs(Stand):
    def test_sign_in_is_turned_back_on_in_every_version(self):
        off = os.path.join(self.inst["deployments"][0]["dir"], "etc", "tessera", "no-autologin")
        write(off, "")
        done = lr.fix_signin(self.inst)
        for d in self.inst["deployments"]:
            link = os.path.join(d["dir"], "etc", "systemd", "system", "multi-user.target.wants", "tessera-autologin.service")
            self.assertEqual(os.readlink(link), "/usr/lib/systemd/system/tessera-autologin.service")
        self.assertFalse(os.path.exists(off))
        self.assertTrue(any("no-autologin" in x for x in done))
        self.assertEqual(lr.fix_signin(self.inst), ["It was already on."])
        self.assertTrue(lr.diagnose(self.inst)["signin"]["enabled"])

    def test_pin_removed_with_its_tries_and_the_file_keeps_owner_and_mode(self):
        p = os.path.join(self.home, ".local", "share", "tessera", "settings.json")
        before = os.stat(p)
        self.assertEqual(lr.fix_pin(self.inst), ["alex: the admin PIN was removed"])
        s = self.settings()
        self.assertNotIn("pin", s)
        self.assertEqual(s["theme"], {"active": "stock"})  # nothing else touched
        after = os.stat(p)
        self.assertEqual((after.st_uid, after.st_gid, stat.S_IMODE(after.st_mode)), (before.st_uid, before.st_gid, 0o600))
        self.assertFalse(os.path.exists(os.path.join(self.home, ".local", "state", "tessera", "pin-tries.json")))
        self.assertEqual(lr.fix_pin(self.inst), ["No admin PIN was set."])

    def test_shards_all_off_and_the_safety_setting_kept(self):
        self.assertEqual(lr.fix_shards(self.inst), ["alex: 2 shards turned off"])
        self.assertEqual(self.settings()["codeAddons"], {"enabled": [], "allowUnverified": True})


class CommandLine(Stand):
    def test_unknown_commands_and_installs_are_refused(self):
        self.assertEqual(lr.main(["nope"]), 2)


if __name__ == "__main__":
    unittest.main()


class Layouts(Stand):
    def test_home_folders_in_a_var_subvolume_are_found(self):
        shutil.move(os.path.join(self.mnt, "home"), os.path.join(self.tmp, "home-moved"))
        os.makedirs(os.path.join(self.mnt, "var"))
        shutil.move(os.path.join(self.tmp, "home-moved"), os.path.join(self.mnt, "var", "home"))
        inst = lr.find_installs(self.mnt, self.boot, {})[0]
        self.assertEqual(inst["users"][0]["path"], os.path.join(self.mnt, "var", "home", "alex"))

    def test_the_journal_is_found_in_a_var_subvolume(self):
        j = os.path.join(self.mnt, "var", "log", "journal", "0123abcd")
        os.makedirs(j)
        self.assertEqual(lr.journal_dir(self.inst), j)

    def test_version_names_without_the_edition(self):
        d = os.path.join(self.mnt, "root", "ostree", "deploy", "default", "deploy", "aaa.0", "usr", "lib", "os-release")
        write(d, 'NAME="Tessera"\nVERSION="44.20261026.0 (Kinoite)"\nOSTREE_VERSION=\'44.20261026.0\'\n')
        inst = lr.find_installs(self.mnt, self.boot, {})[0]
        self.assertEqual(inst["deployments"][0]["version"], "44.20261026.0")


class Versions(Stand):
    def setUp(self):
        super().setUp()
        self.calls = os.path.join(self.tmp, "ostree-calls")
        fake = os.path.join(self.tmp, "ostree")
        write(fake, f'#!/bin/sh\necho "$@" >> {self.calls}\n', 0o755)
        lr.OSTREE = fake
        write(os.path.join(self.mnt, "root", "ostree", "repo", "config"), "[core]\nrepo_version=1\n[sysroot]\nbootloader=none\n")
        self.inst["boot"] = {"path": self.boot, "device": "/dev/nvme0n1p2"}

    def test_default_keep_and_unkeep_run_ostree_on_the_install(self):
        sysroot = os.path.join(self.mnt, "root")
        self.assertEqual(lr.fix_version(self.inst, {"action": "default", "index": 1}), ["43.20261031.0 now starts by default"])
        self.assertIn("kept for good", lr.fix_version(self.inst, {"action": "keep", "index": 0})[0])
        lr.fix_version(self.inst, {"action": "unkeep", "index": 0})
        with open(self.calls) as f:
            self.assertEqual(f.read().splitlines(), [f"admin --sysroot={sysroot} set-default 1", f"admin --sysroot={sysroot} pin 0", f"admin --sysroot={sysroot} pin --unpin 0"])

    def test_bad_requests_change_nothing(self):
        for req in ({"action": "rm", "index": 0}, {"action": "default", "index": "0"}, {"action": "default", "index": True}, {"action": "default", "index": 7}):
            with self.assertRaises(RuntimeError):
                lr.fix_version(self.inst, req)
        self.assertFalse(os.path.exists(self.calls))

    def test_a_boot_menu_ostree_would_rewrite_is_left_alone(self):
        write(os.path.join(self.mnt, "root", "ostree", "repo", "config"), "[sysroot]\nbootloader=grub2\n")
        with self.assertRaises(RuntimeError):
            lr.fix_version(self.inst, {"action": "default", "index": 1})

    def test_kept_versions_are_shown(self):
        base = os.path.join(self.mnt, "root", "ostree", "deploy", "default", "deploy")
        with open(os.path.join(base, "bbb.0.origin"), "a") as f:
            f.write("\n[libostree-transient]\npinned=true\n")
        inst = lr.find_installs(self.mnt, self.boot, {})[0]
        inst.update(id=self.inst["id"])
        self.assertEqual([v["kept"] for v in lr.public(inst)["versions"]], [False, True])
