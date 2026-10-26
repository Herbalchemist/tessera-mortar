# Tessera Mortar

**The media creation tool for [Tessera](https://github.com/Herbalchemist/tessera)**, the
controller-first gaming OS built on Bazzite. Mortar is what holds the tiles together.

> **Status: testing.** The bootable Tessera USB is being tested on real hardware; the Mortar app itself comes next. The plan is in [docs/plan.md](docs/plan.md).

## What it will do

1. **Make a Tessera USB** from Windows or Linux. Pick a USB drive and Mortar downloads the newest Tessera pieces, checks them, and writes a bootable drive.
2. **Install anywhere, offline.** The USB carries every Tessera build (AMD / Intel, older NVIDIA, newer NVIDIA), so it installs with no internet on any machine Bazzite supports.
3. **Detect the hardware on the machine being installed to.** The installer picks the build for that machine's graphics card, and you can change its choice.
4. **Try it before installing.** The USB boots into a live Tessera with a controller-friendly **Install Tessera** app, like Ubuntu's "try or install".
5. **Make Secure Boot simple.** "Set it up for me" (the default) or "I'll handle it", with a clear walkthrough of the one confirmation screen firmware always shows.
6. **Offer optional Extras, never force them.** For example, Xbox app compatibility, offered only where the hardware can run it.

## Platforms

| Making the USB on | Status |
|---|---|
| Linux | Planned, first |
| Windows | Planned, first. Mortar isn't code-signed yet, so Windows shows an "unknown publisher" warning: choose *More info › Run anyway*. |
| macOS | Not yet. Signing costs money, so until then Mac users can make the USB from Windows (Boot Camp works) or Linux. |

## Try the test USB (for testers)

GitHub builds a test image of the USB after every change: see [Releases](https://github.com/Herbalchemist/tessera-mortar/releases). It's about 17 GB, so it comes in parts.

1. Download every `Tessera-Live.iso.partNN` file and `Tessera-Live.iso.sha256` from the newest release.
2. Join the parts into one file:
   - **Linux:** `cat Tessera-Live.iso.part* > Tessera-Live.iso`
   - **Windows (Command Prompt):** `copy /b Tessera-Live.iso.part00+Tessera-Live.iso.part01+… Tessera-Live.iso`, listing every part in order.
3. Check the file: `sha256sum -c Tessera-Live.iso.sha256` on Linux, or compare against `certutil -hashfile Tessera-Live.iso SHA256` on Windows.
4. Write it to a **32 GB or larger** USB drive with balenaEtcher, Fedora Media Writer, Rufus (in DD mode) or `dd`. Everything on the drive is erased.
5. Boot the target PC from the USB (UEFI). The boot menu has three entries:
   - **Try or install Tessera:** the normal one, starting into Install Tessera.
   - **Safe graphics:** for screens that stay black.
   - **Desktop mode:** the KDE desktop, with Install Tessera in a window.

**The install erases the disk you pick.** Use a spare disk or machine while this is in testing.

## Tools that work today

- `tools/measure-images.py`: how big an offline USB needs to be. It reads the published Tessera images' manifests and adds up their layers, counting layers the builds share only once. It also runs on GitHub (Actions › *Measure images*).

## License

GPL-3.0-or-later, like Tessera.
