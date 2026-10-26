# Tessera Mortar

**The media creation tool for [Tessera](https://github.com/Herbalchemist/tessera)**, the
controller-first gaming OS built on Bazzite. Mortar is what holds the tiles together.

> **Status: early design.** Nothing here is ready to use yet. The plan is in [docs/plan.md](docs/plan.md).

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

## Tools that work today

- `tools/measure-images.py`: how big an offline USB needs to be. It reads the published Tessera images' manifests and adds up their layers, counting layers the builds share only once. It also runs on GitHub (Actions › *Measure images*).

## License

GPL-3.0-or-later, like Tessera.
