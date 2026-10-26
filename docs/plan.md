# Mortar: the plan

## Goals

- **Offline first.** Once the USB is made, it installs Tessera on any Bazzite-compatible machine with no network. A network is optional, used only for things like updates or online Extras.
- **Detect on the target.** Hardware detection runs on the machine being installed to, not on the computer that made the USB.
- **Controller-first,** like Tessera: the installer is driven with a gamepad, and a keyboard and mouse work too.
- **Nothing forced.** Extras are offered, never pre-installed without asking.

## The pieces

### 1. The USB

```
USB
├── boot system        a live Tessera that boots on UEFI machines (Secure Boot via shim)
├── images/            one OCI image layout holding all Tessera builds; shared layers stored once
│     tessera, tessera-nvidia, tessera-nvidia-open
├── extras/            optional add-ons, each with a manifest (what it needs, what it does)
└── mortar.json        what the USB holds, made by Mortar (versions, checksums, preselected Extras)
```

### 2. Install Tessera (runs from the live USB)

Steps:
1. **Welcome.** Try Tessera, or Install.
2. **Disk.** Pick the target disk; it gets erased (dual-boot comes later).
3. **Graphics.** "Detected: GeForce GTX 1050 → NVIDIA, GTX 900–1000 build". The rules are the same as Tessera's `gpu-match.js`, and you can change the choice.
4. **Secure Boot.**
   - *Set it up for me* (default): queue the Universal Blue key with `mokutil` and show the walkthrough (password `universalblue`, US keyboard layout).
   - *I'll handle it*: skip, and explain `ujust enroll-secure-boot-key`.
   - Either way, say whether Secure Boot is on right now and why games with anti-cheat may want it.
5. **Extras.** Each Extra decides whether it's offered, offered with a warning, or hidden, from the hardware (for example, the Xbox add-on's `vmOffer()`).
6. **Install.** `bootc install to-disk` from the image on the USB, then point the installed system at its registry image (`ghcr.io/herbalchemist/tessera…:latest`) so updates work once it's online.
7. **Restart,** remembering the Secure Boot walkthrough. Tessera's first-run setup and tour take over from there.

### 3. Mortar (the USB maker)

- Windows and Linux first; macOS later, once code signing makes sense.
- It downloads the boot system from GitHub Releases and pulls the Tessera images straight from the image registry (no size limits, always the newest), verifies checksums and signatures, and writes the USB.
- **Every build** (default, for any PC) or **only this PC** (a smaller USB).
- Optional preselection of Extras, saved to `mortar.json` on the USB.
- It can refresh an existing Tessera USB with the newest builds.

## Order of work

1. ✅ Measure the image sizes (`tools/measure-images.py`), to know what USB size to ask for.
2. 🧪 Live USB plus the installer: disk, graphics, Secure Boot, install. Built by GitHub and boot-tested in a VM; next comes testing on real hardware.
3. Extras, starting with Xbox app compatibility.
4. The Mortar app for Windows and Linux.

## How it's built

| Piece | Where |
|---|---|
| Install Tessera screens | the Tessera launcher (`renderer.js` `flowInstaller`, `main.js` `installerOp`), active only on the USB (`/etc/tessera/live-installer`) |
| Root helper: probe, checks, kickstart, Anaconda | `live/src/live-install` (tests in `tests/`, kickstarts checked with Fedora's `ksvalidator`) |
| Live system | `live/Containerfile` + `live/src/build.sh`: Tessera with Fedora's signed kernel, dracut live boot, Anaconda, the Secure Boot key |
| The builds on the USB | `tools/fetch-images.sh`: one OCI image layout, `/tessera-images` on the ISO |
| ISO | `tools/build-iso.sh` (adapted from Titanoboa) |
| Smoke test | `tools/boot-test.sh`: boots the ISO in QEMU; screenshots land on the `boot-test` branch |
| Releases | `.github/workflows/build-live.yml`: a pre-release, split into parts under GitHub's 2 GB limit |

## Measured sizes (2026-10-26)

From the published images' manifests (compressed, as they'd sit on the USB):

| Build | Size |
|---|---|
| `tessera` (AMD / Intel) | 5.24 GB |
| `tessera-nvidia` | 5.85 GB |
| `tessera-nvidia-open` | 5.81 GB |
| **All three, shared layers once** | **11.77 GB** (16.90 GB without sharing) |

With the live boot system (a few GB) and Extras, an **every-build USB needs 32 GB**, and an
**only-this-PC USB fits on 16 GB**. All three images are public, so Mortar can pull them without logging in.

Sharing is only about 30%, because each build is chunked on its own. Two ways to shrink it later:
- Boot the live USB from the standard build itself, so the system on the USB doubles as one of the three images (saves about 5 GB).
- Chunk the three builds so their common parts land in identical layers.

## Open questions

- The base for the live boot system: build it from the Tessera image itself (most consistent) or from a minimal Fedora live image (smallest).
- Dual-boot support in the installer.
