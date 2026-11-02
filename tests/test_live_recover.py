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


class Backup(Stand):
    def setUp(self):
        super().setUp()
        self.old_mnt = lr.MNT
        lr.MNT = self.tmp
        os.environ["TESSERA_RECOVER_FOREGROUND"] = "1"
        write(os.path.join(self.home, "Pictures", "a.png"), "png")
        write(os.path.join(self.home, ".cache", "junk"), "x")
        write(os.path.join(self.home, ".local", "share", "Steam", "steamapps", "common", "Game", "big.bin"), "game")
        write(os.path.join(self.home, ".local", "share", "Steam", "steamapps", "compatdata", "1", "save.dat"), "save")
        write(os.path.join(self.home, "Games", "Heroic", "Prefixes", "x", "save.sav"), "heroic save")
        os.symlink("Pictures/a.png", os.path.join(self.home, "link.png"))
        lsblk = {"blockdevices": [
            {"name": "nvme0n1", "path": "/dev/nvme0n1", "type": "disk", "rm": False, "tran": "nvme", "size": 1000, "children": [
                {"name": "nvme0n1p3", "path": "/dev/nvme0n1p3", "pkname": "nvme0n1", "type": "part", "fstype": "btrfs", "uuid": "1234-abcd", "size": 900}]},
            {"name": "sdb", "path": "/dev/sdb", "type": "disk", "rm": True, "tran": "usb", "model": "SanDisk ", "size": 64, "children": [
                {"name": "sdb1", "path": "/dev/sdb1", "pkname": "sdb", "type": "part", "fstype": "exfat", "uuid": "AB12-CD34", "label": "STICK", "size": 64}]},
            {"name": "sdc", "path": "/dev/sdc", "type": "disk", "rm": True, "tran": "usb", "size": 64, "children": [
                {"name": "sdc1", "path": "/dev/sdc1", "pkname": "sdc", "type": "part", "fstype": "ext4", "uuid": "eeee-ffff", "size": 64}]}]}
        write(os.path.join(self.tmp, "lsblk.json"), json.dumps(lsblk))
        os.environ["TESSERA_RECOVER_LSBLK"] = os.path.join(self.tmp, "lsblk.json")

    def tearDown(self):
        lr.MNT = self.old_mnt
        os.environ.pop("TESSERA_RECOVER_FOREGROUND", None)
        os.environ.pop("TESSERA_RECOVER_LSBLK", None)
        super().tearDown()

    def copied(self, uuid):
        top = os.path.join(self.tmp, "usb-" + uuid)
        (folder,) = [f for f in os.listdir(top) if f.startswith("Tessera backup ")]
        return os.path.join(top, folder)

    def test_only_usb_drives_are_offered(self):
        self.assertEqual([(d["uuid"], d["label"], d["model"]) for d in lr.drives([self.inst])], [("AB12-CD34", "STICK", "SanDisk"), ("eeee-ffff", "", "")])

    def test_a_tessera_on_an_external_drive_is_never_offered(self):
        external = dict(self.inst, disk={"name": "sdc"})
        self.assertEqual([d["uuid"] for d in lr.drives([external])], ["AB12-CD34"])

    def test_my_files_leave_out_games_and_caches_but_keep_saves(self):
        r = lr.start_backup(self.inst, {"who": "alex", "drive": "AB12-CD34", "what": "mine"})
        self.assertTrue(r["ok"])
        st = lr.load_json(lr.state_file())
        self.assertEqual(st["phase"], "done")
        out = os.path.join(self.copied("AB12-CD34"), "alex")
        self.assertTrue(os.path.exists(os.path.join(out, "Pictures", "a.png")))
        self.assertTrue(os.path.exists(os.path.join(out, ".local", "share", "Steam", "steamapps", "compatdata", "1", "save.dat")))
        self.assertTrue(os.path.exists(os.path.join(out, "Games", "Heroic", "Prefixes", "x", "save.sav")))
        self.assertFalse(os.path.exists(os.path.join(out, ".cache")))
        self.assertFalse(os.path.exists(os.path.join(out, ".local", "share", "Steam", "steamapps", "common")))
        # exFAT holds no links: listed, not copied
        self.assertFalse(os.path.lexists(os.path.join(out, "link.png")))
        with open(os.path.join(self.copied("AB12-CD34"), "not copied.txt")) as f:
            self.assertIn("link.png", f.read())
        self.assertEqual(st["skipped"], 1)

    def test_everything_keeps_games_and_links_on_a_linux_drive(self):
        lr.start_backup(self.inst, {"who": "alex", "drive": "eeee-ffff", "what": "all"})
        out = os.path.join(self.copied("eeee-ffff"), "alex")
        self.assertTrue(os.path.exists(os.path.join(out, ".local", "share", "Steam", "steamapps", "common", "Game", "big.bin")))
        self.assertEqual(os.readlink(os.path.join(out, "link.png")), "Pictures/a.png")
        self.assertFalse(os.path.exists(os.path.join(out, ".cache")))
        mode = stat.S_IMODE(os.stat(os.path.join(out, ".local", "share", "tessera", "settings.json")).st_mode)
        self.assertEqual(mode, 0o600)

    def test_wrong_choices_are_refused(self):
        self.assertFalse(lr.start_backup(self.inst, {"who": "nobody", "drive": "AB12-CD34", "what": "mine"})["ok"])
        self.assertFalse(lr.start_backup(self.inst, {"who": "alex", "drive": "1234-abcd", "what": "mine"})["ok"])  # the install's own disk
        self.assertFalse(lr.start_backup(self.inst, {"who": "alex", "drive": "AB12-CD34", "what": "../x"})["ok"])

    def test_a_backup_can_be_stopped(self):
        open(os.path.join(self.tmp, "backup.stop"), "w").close()
        orig = lr.backup_job
        # the stop file is cleared when a job starts, so set it again just after
        def job(*a):
            real_copy = lr.copy_tree
            lr.copy_tree = lambda *x: real_copy(*x[:4], x[4], lambda: True)
            try:
                orig(*a)
            finally:
                lr.copy_tree = real_copy
        lr.backup_job = job
        try:
            lr.start_backup(self.inst, {"who": "alex", "drive": "eeee-ffff", "what": "mine"})
        finally:
            lr.backup_job = orig
        self.assertEqual(lr.load_json(lr.state_file())["phase"], "canceled")

    def test_backup_needs_the_administrator_password(self):
        import io, sys
        old = sys.stdin, sys.stdout
        sys.stdin, sys.stdout = io.StringIO(json.dumps({"user": "alex", "password": "nope", "who": "alex", "drive": "AB12-CD34", "what": "mine"})), io.StringIO()
        find, lr.find = lr.find, lambda i: self.inst
        try:
            lr.main(["backup", self.inst["id"]])
            out = json.loads(sys.stdout.getvalue())
        finally:
            sys.stdin, sys.stdout = old
            lr.find = find
        self.assertEqual(out.get("needPassword"), True)
        self.assertFalse(os.path.exists(lr.state_file()))


class FreeUpSpace(Stand):
    def setUp(self):
        super().setUp()
        write(os.path.join(self.home, ".cache", "thumbs", "a"), "x" * 5000)
        write(os.path.join(self.home, ".local", "share", "Trash", "files", "old.txt"), "y" * 5000)
        write(os.path.join(self.home, ".local", "share", "Steam", "steamapps", "shadercache", "1", "s.bin"), "z" * 5000)
        write(os.path.join(self.home, ".local", "share", "Steam", "steamapps", "common", "G", "g.bin"), "g" * 5000)
        self.keep = os.path.join(self.tmp, "outside", "precious.txt")
        write(self.keep, "keep")
        os.symlink(os.path.dirname(self.keep), os.path.join(self.home, ".cache", "link-out"))

    def test_what_uses_the_disk_per_person(self):
        u = lr.space_use(self.inst)
        alex = next(p for p in u["people"] if p["name"] == "alex")
        for k in ("caches", "trash", "shaders", "games"):
            self.assertGreater(alex[k], 0, k)
        self.assertEqual(u["versions"], 2)

    def test_only_the_chosen_things_are_cleared_and_links_are_not_followed(self):
        done = lr.fix_clean(self.inst, {"what": ["caches", "trash", "nonsense"]})
        self.assertTrue(done[0].startswith("alex: "))
        self.assertEqual(os.listdir(os.path.join(self.home, ".cache")), [])
        self.assertEqual(os.listdir(os.path.join(self.home, ".local", "share", "Trash")), [])
        self.assertTrue(os.path.exists(self.keep))  # what a link in the cache pointed at stays
        self.assertTrue(os.path.exists(os.path.join(self.home, ".local", "share", "Steam", "steamapps", "shadercache", "1", "s.bin")))
        self.assertTrue(os.path.exists(os.path.join(self.home, ".local", "share", "Steam", "steamapps", "common", "G", "g.bin")))
        self.assertTrue(os.path.exists(os.path.join(self.home, ".local", "share", "tessera", "settings.json")))
        self.assertEqual(lr.fix_clean(self.inst, {"what": ["caches", "trash"]}), ["There was nothing to clear."])

    def test_a_choice_is_needed(self):
        with self.assertRaises(RuntimeError):
            lr.fix_clean(self.inst, {"what": ["games"]})


class DiskCheck(Stand):
    """Check and repair the disk, with stand-ins for smartctl, fsck.fat, e2fsck, btrfs and dmesg that
    answer from files and record how they were called."""

    def setUp(self):
        super().setUp()
        self.old_mnt, lr.MNT = lr.MNT, self.tmp
        os.environ["TESSERA_RECOVER_FOREGROUND"] = "1"
        self.bin = os.path.join(self.tmp, "bin")
        self.calls = os.path.join(self.tmp, "calls")
        for tool in ("smartctl", "fsck.fat", "e2fsck", "btrfs", "dmesg"):
            write(os.path.join(self.bin, tool), f"""#!/bin/sh
echo "{tool} $*" >> {self.calls}
key=$(echo "{tool} $1 $2" | tr ' ./-' '____')
[ -f "{self.tmp}/out.$key" ] && cat "{self.tmp}/out.$key"
[ -f "{self.tmp}/out.{tool}" ] && cat "{self.tmp}/out.{tool}"
exit $(cat "{self.tmp}/rc.{tool}" 2>/dev/null || echo 0)
""", 0o755)
        self.old_path = os.environ["PATH"]
        os.environ["PATH"] = self.bin + os.pathsep + self.old_path
        self.inst["disk"] = {"name": "nvme0n1"}
        self.inst["boot"] = {"device": "/dev/nvme0n1p2", "path": self.boot, "uuid": "b"}
        lsblk = {"blockdevices": [{"name": "nvme0n1", "path": "/dev/nvme0n1", "type": "disk", "children": [
            {"name": "nvme0n1p1", "path": "/dev/nvme0n1p1", "pkname": "nvme0n1", "type": "part", "fstype": "vfat", "uuid": "E"},
            {"name": "nvme0n1p2", "path": "/dev/nvme0n1p2", "pkname": "nvme0n1", "type": "part", "fstype": "ext4", "uuid": "b"},
            {"name": "nvme0n1p3", "path": "/dev/nvme0n1p3", "pkname": "nvme0n1", "type": "part", "fstype": "btrfs", "uuid": "1234-abcd"}]}]}
        write(os.path.join(self.tmp, "lsblk.json"), json.dumps(lsblk))
        os.environ["TESSERA_RECOVER_LSBLK"] = os.path.join(self.tmp, "lsblk.json")
        self.answer("smartctl", json.dumps({"smart_status": {"passed": True}, "nvme_smart_health_information_log": {"critical_warning": 0, "media_errors": 0, "percentage_used": 3}}))
        self.scrub_says("finished", {})

    def tearDown(self):
        lr.MNT = self.old_mnt
        os.environ["PATH"] = self.old_path
        for k in ("TESSERA_RECOVER_FOREGROUND", "TESSERA_RECOVER_LSBLK"):
            os.environ.pop(k, None)
        super().tearDown()

    def answer(self, tool, text, rc=0):
        write(os.path.join(self.tmp, f"out.{tool}"), text)
        write(os.path.join(self.tmp, f"rc.{tool}"), str(rc))

    def scrub_says(self, status, counts):
        body = f"UUID: x\nStatus: {status}\n" + "".join(f"\t{k}: {v}\n" for k, v in {"data_bytes_scrubbed": 100, "tree_bytes_scrubbed": 10, **counts}.items())
        write(os.path.join(self.tmp, "out.btrfs_scrub_status"), body)

    def called(self):
        with open(self.calls) as f:
            return f.read().splitlines()

    def result(self):
        return lr.load_json(lr.state_file())

    def test_a_healthy_disk_is_checked_read_only(self):
        self.assertTrue(lr.start_check(self.inst, False)["ok"])
        st = self.result()
        self.assertEqual((st["phase"], st["healthy"], st["repair"]), ("done", True, False))
        self.assertEqual([r["text"] for r in st["results"]], [
            "The drive reports good health.", "The start-up (EFI) partition: no problems.",
            "The boot partition: no problems.", "The main file system: every block checked, no damage."])
        calls = self.called()
        self.assertIn("fsck.fat -n -w /dev/nvme0n1p1", calls)
        self.assertIn("e2fsck -f -n /dev/nvme0n1p2", calls)
        self.assertIn(f"btrfs scrub start -r {self.mnt}", calls)
        self.assertFalse(any(c.startswith(("fsck.fat -a", "e2fsck -f -p", "btrfs check")) or c == f"btrfs scrub start {self.mnt}" for c in calls))

    def test_repair_uses_only_the_safe_repairs(self):
        lr.start_check(self.inst, True)
        calls = self.called()
        self.assertIn("fsck.fat -a -w /dev/nvme0n1p1", calls)
        self.assertIn("e2fsck -f -p /dev/nvme0n1p2", calls)
        self.assertIn(f"btrfs scrub start {self.mnt}", calls)
        self.assertFalse(any(c.startswith("btrfs check") for c in calls))

    def test_damage_without_a_second_copy_names_the_files(self):
        self.scrub_says("finished", {"csum_errors": 2, "uncorrectable_errors": 2})
        write(os.path.join(self.tmp, "out.dmesg"), "[1.0] BTRFS warning (device nvme0n1p3): checksum error at logical 1 on dev /dev/nvme0n1p3, physical 2, root 5, inode 257, offset 0, length 4096, links 1 (path: alex/Games/big.bin)\n")
        lr.start_check(self.inst, True)
        st = self.result()
        self.assertFalse(st["healthy"])
        self.assertEqual(st["files"], ["alex/Games/big.bin"])
        self.assertIn("2 damaged blocks with no second copy", st["results"][-1]["text"])

    def test_a_failing_drive_is_said_plainly(self):
        self.answer("smartctl", json.dumps({"smart_status": {"passed": True}, "ata_smart_attributes": {"table": [{"id": 5, "raw": {"value": 12}}, {"id": 197, "raw": {"value": 3}}]}}))
        ok, text = lr.drive_health("sda")
        self.assertFalse(ok)
        self.assertIn("12 worn-out sectors replaced; 3 sectors waiting to be replaced", text)
        self.answer("smartctl", json.dumps({"smart_status": {"passed": False}}))
        self.assertIn("failing", lr.drive_health("sda")[1])
        self.answer("smartctl", "not json")
        self.assertIsNone(lr.drive_health("sda")[0])

    def test_boot_partition_problems_too_deep_for_automatic_repair(self):
        def fake(cmd, timeout=0):
            return lr.subprocess.CompletedProcess(cmd, 4 if cmd[0] == "e2fsck" else 0, "", "")
        orig, lr.run_tool = lr.run_tool, fake
        try:
            self.assertEqual(lr.check_partition("The boot partition", "/dev/x", "ext4", False), (False, "The boot partition: problems found (Repair can try to fix them)."))
            self.assertIn("not safe to repair automatically", lr.check_partition("The boot partition", "/dev/x", "ext4", True)[1])
        finally:
            lr.run_tool = orig

    def test_repair_needs_the_password_but_looking_does_not(self):
        import io, sys
        find, lr.find = lr.find, lambda i: self.inst
        old = sys.stdin, sys.stdout
        try:
            sys.stdin, sys.stdout = io.StringIO(json.dumps({"user": "alex", "password": "nope"})), io.StringIO()
            lr.main(["check", self.inst["id"], "--repair"])
            self.assertTrue(json.loads(sys.stdout.getvalue()).get("needPassword"))
            self.assertFalse(os.path.exists(self.calls))
            sys.stdin, sys.stdout = io.StringIO(""), io.StringIO()
            lr.main(["check", self.inst["id"]])
            self.assertTrue(json.loads(sys.stdout.getvalue())["ok"])
        finally:
            sys.stdin, sys.stdout = old
            lr.find = find
        self.assertEqual(self.result()["repair"], False)


class BootMenu(Stand):
    """Repair the boot menu, with stand-ins for efibootmgr, bootupctl and mount."""
    PU = "5b0c6a1e-0001-4c3a-9e6e-aaaaaaaaaaaa"

    def setUp(self):
        super().setUp()
        self.old_mnt, lr.MNT = lr.MNT, self.tmp
        self.bin = os.path.join(self.tmp, "bin")
        self.calls = os.path.join(self.tmp, "calls")
        self.order = os.path.join(self.tmp, "order")
        write(self.order, "0000,0003")
        # efibootmgr: lists entries from files; -o rewrites the order; -c adds entry 0005 for us
        write(os.path.join(self.bin, "efibootmgr"), f"""#!/bin/sh
printf '%s\\n' "efibootmgr $*" >> {self.calls}
case "$1" in
  -o) echo "$2" > {self.order}; exit 0 ;;
  -c) printf 'Boot0005* Tessera\tHD(1,GPT,{self.PU},0x800,0x12c000)/\\EFI\\fedora\\shimx64.efi\n' >> {self.tmp}/entries; o=$(cat {self.order}); echo "0005,$o" > {self.order}; exit 0 ;;
esac
echo "BootCurrent: 0000"
echo "BootOrder: $(cat {self.order})"
cat {self.tmp}/entries
""", 0o755)
        write(os.path.join(self.bin, "bootupctl"), f"""#!/bin/sh
echo "bootupctl $*" >> {self.calls}
exit $(cat {self.tmp}/rc.bootupctl 2>/dev/null || echo 0)
""", 0o755)
        write(os.path.join(self.bin, "mount"), "#!/bin/sh\nexit 1\n", 0o755)
        self.entries(windows_first=True, ours=True)
        self.old_path = os.environ["PATH"]
        os.environ["PATH"] = self.bin + os.pathsep + self.old_path
        os.environ["TESSERA_RECOVER_BOOTUPCTL"] = os.path.join(self.bin, "bootupctl")
        lr.BOOTUPCTL = os.environ["TESSERA_RECOVER_BOOTUPCTL"]
        self.inst["disk"] = {"name": "nvme0n1"}
        self.inst["boot"] = {"device": "/dev/nvme0n1p2", "path": self.boot, "uuid": "bbbb-boot"}
        lsblk = {"blockdevices": [{"name": "nvme0n1", "path": "/dev/nvme0n1", "type": "disk", "children": [
            {"name": "nvme0n1p1", "path": "/dev/nvme0n1p1", "pkname": "nvme0n1", "type": "part", "fstype": "vfat", "uuid": "E5P", "partuuid": self.PU},
            {"name": "nvme0n1p2", "path": "/dev/nvme0n1p2", "pkname": "nvme0n1", "type": "part", "fstype": "ext4", "uuid": "bbbb-boot"}]}]}
        write(os.path.join(self.tmp, "lsblk.json"), json.dumps(lsblk))
        os.environ["TESSERA_RECOVER_LSBLK"] = os.path.join(self.tmp, "lsblk.json")
        self.esp = os.path.join(self.tmp, "esp-E5P")
        for rel in ("EFI/fedora/shimx64.efi", "EFI/fedora/grubx64.efi", "EFI/BOOT/BOOTX64.EFI"):
            write(os.path.join(self.esp, rel), "x")
        write(os.path.join(self.esp, "EFI/fedora/grub.cfg"), "search --no-floppy --fs-uuid --set=dev bbbb-boot\n")
        write(os.path.join(self.boot, "grub2", "grub.cfg"), "# static\n")
        os.makedirs(os.path.join(self.inst["deployments"][0]["dir"], "usr", "lib", "bootupd", "updates", "EFI"))

    def tearDown(self):
        lr.MNT = self.old_mnt
        os.environ["PATH"] = self.old_path
        for k in ("TESSERA_RECOVER_LSBLK", "TESSERA_RECOVER_BOOTUPCTL"):
            os.environ.pop(k, None)
        super().tearDown()

    def entries(self, windows_first, ours):
        lines = ["Boot0000* Windows Boot Manager\tHD(1,GPT,ffff0000-0000-0000-0000-000000000000,0x800,0x32000)/\\EFI\\Microsoft\\Boot\\bootmgfw.efi"]
        if ours:
            lines.append(f"Boot0003* Fedora\tHD(1,GPT,{self.PU},0x800,0x12c000)/\\EFI\\fedora\\shimx64.efi")
        write(os.path.join(self.tmp, "entries"), "\n".join(lines) + "\n")
        write(self.order, "0000,0003" if windows_first else "0003,0000")

    def called(self):
        return open(self.calls).read().splitlines() if os.path.exists(self.calls) else []

    def keys(self):
        return {f["key"]: f["text"] for f in lr.boot_findings(lr.boot_state(self.inst))}

    def test_a_healthy_boot_menu_has_no_findings(self):
        self.entries(windows_first=False, ours=True)
        self.assertEqual(self.keys(), {})

    def test_windows_first_and_a_missing_entry_are_found(self):
        self.assertIn("Windows Boot Manager", self.keys()["firmware"])
        self.entries(windows_first=True, ours=False)
        self.assertIn("no entry to start Tessera", self.keys()["firmware"])

    def test_missing_files_and_a_wrong_pointer_are_found(self):
        os.remove(os.path.join(self.esp, "EFI/BOOT/BOOTX64.EFI"))
        write(os.path.join(self.esp, "EFI/fedora/grub.cfg"), "search --fs-uuid --set=dev 0000-old\n")
        t = self.keys()["bootmenu"]
        self.assertIn("EFI/BOOT/BOOTX64.EFI", t)
        self.assertIn("pointer to the boot partition is wrong", t)

    def test_repair_reinstalls_from_the_installed_version_and_puts_tessera_first(self):
        done = lr.fix_boot(self.inst)
        calls = self.called()
        d = self.inst["deployments"][0]["dir"]
        self.assertIn(f"bootupctl backend install --src-root {d} --device /dev/nvme0n1 --component EFI --write-uuid --update-firmware {self.inst['sysroot']}", calls)
        self.assertEqual(open(self.order).read().strip(), "0003,0000")
        self.assertTrue(any("starts first again" in x for x in done))

    def test_repair_adds_a_firmware_entry_when_there_is_none(self):
        self.entries(windows_first=True, ours=False)
        lr.fix_boot(self.inst)
        self.assertIn("efibootmgr -c -d /dev/nvme0n1 -p 1 -L Tessera -l \\EFI\\fedora\\shimx64.efi", self.called())
        self.assertEqual(open(self.order).read().strip().split(",")[0], "0005")

    def test_a_failed_reinstall_changes_nothing_else(self):
        write(os.path.join(self.tmp, "rc.bootupctl"), "1")
        with self.assertRaises(RuntimeError):
            lr.fix_boot(self.inst)
        self.assertFalse(any(c.startswith("efibootmgr -o") for c in self.called()))


if __name__ == "__main__":
    unittest.main()
