# Recovery: the plan

A second, small Tessera that can't be broken by the main one, for when Tessera won't start. It opens
Tessera's own screens, so a controller works (the boot menu itself needs a keyboard). It is the same
live system as the Tessera USB, so it boots on everything the USB boots on, and the USB gets every
recovery tool too.

## Where it lives

| | How you reach it | Survives |
|---|---|---|
| **The Tessera USB** (every USB Mortar makes) | Welcome › **Recover**, or Settings › Recover | anything but a dead USB; an offline USB also reinstalls with no internet |
| **Its own partition** (new installs) | Boot options › **Recovery** | a broken system, broken updates, a damaged main file system |
| **A file on the main disk** (machines installed before it existed) | Boot options › **Recovery** | a broken system and broken updates; not damage to the main file system itself |

It carries the tools and reinstalls online (about 6 GB). A Tessera USB made with the builds on it is
the offline way to reinstall. No separate "recovery USB" is needed: every Tessera USB is one.

## Who may do what

Looking and making a report need nothing. Every change needs the password of an administrator
account of the Tessera being repaired, checked against its own password file. Having the USB, or
reaching Boot options, is never enough to change anything.

## The tools

| Tool | What it does | Stage |
|---|---|---|
| What's wrong | Versions, sign-in at boot, space, file system and disk health, errors from the last start, shards | ✅ 1 |
| Problem report | The above, scrubbed of names and addresses, saved in the install's Tessera/Reports | ✅ 1 |
| Start in Tessera at boot again | Turns the automatic sign-in back on (the "stuck at a text screen" case) | ✅ 1 |
| Remove the admin PIN | For a forgotten PIN (and its waiting time) | ✅ 1 |
| Turn off all shards | In case an add-on stops Tessera from starting | ✅ 1 |
| Versions | Start or make default any kept version; keep the original install for good; undo the last update | ✅ 2 |
| Back up to a USB drive | One person's home folder: "my files" (all but installed games and caches; saves kept) or everything. In the background with progress; links and 4 GB+ files a FAT drive can't hold are listed in "not copied.txt" | ✅ 2 |
| Free up space | What uses the disk per person; clear caches, shader caches and the trash (games and files never) | ✅ 2 |
| Check and repair the disk | File system check and repair, the drive's health, said plainly | 2 |
| Repair the boot menu | When Windows or a firmware update broke it: puts the installed version's own boot loader back (bootupd) and makes Tessera first in the firmware's list; other systems stay | 2 (VM-tested by breaking it) |
| Graphics and how it starts | Finds the wrong build for this machine's graphics card; switches to the right one at the next start, once online (the install does it: Recover can't download it); the next start only with safe settings, at the login screen or in a text repair console | ✅ 2 |
| Network | Wi-Fi and wired, for downloads | 2 (the USB has it already) |
| Files | Copy files to or from a USB drive | 2 |
| Terminal | For experts, after the administrator password | 2 |
| Undo for files | Put a home folder (or one file) back the way it was: Tessera keeps read-only snapshots of the home folder on a schedule (btrfs, cheap), and Recover, or Settings, lists them by date. An idea from CachyOS's snapshots | 2 |
| Reset Tessera | One person's or everyone's: Tessera's settings (PIN, theme, shards, calibration), or also its layout and game list. Games, saves and other files stay; the old files move to ~/Tessera/Reset <date>, nothing is deleted | ✅ 2 |
| Reinstall, keep my stuff | A fresh system, keeping the home folder | 2 |
| Factory reset | Erase everything and start fresh | 2 |

## Order of work

1. ✅ **Recover on the Tessera USB**: `live/src/live-recover` (root helper, `tests/test_live_recover.py`),
   the Recover screens in the Tessera launcher (`renderer/recovery.js`, `main/recovery.js`,
   `qa/recovery.cjs`). The VM install test boots the USB again with the installed disk and records
   what Recover finds (`install-test/recover.txt`).
2. **The tools**, safest first.
3. **On the machine**: the recovery files from the online USB's live system (kernel, initrd,
   `LiveOS/squashfs.img`), kept current by a Tessera service; a partition made by the installer on
   new installs, a file on existing ones; **Recovery** in Boot options.
