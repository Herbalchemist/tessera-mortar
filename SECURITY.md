# Security

## Reporting a problem

Please report security problems privately, not in a public issue: on GitHub, open the
**Security** tab of this repository and choose **Report a vulnerability**.

## Our standards

Tessera Mortar follows Tessera's security standards; the full list, and what each one means for
a project with no server or database, is in [Tessera's SECURITY.md](https://github.com/Herbalchemist/tessera/blob/main/SECURITY.md).
`tools/security-check.cjs` checks them on every push and pull request (`.github/workflows/test.yml`).
For Mortar in particular:

- **The drive to erase** is re-checked in the main process against a fresh list of drives, which
  never includes the system or boot disk. Nothing on the screen can point Mortar at another device.
- **Images are verified**: a downloaded image must match its release's SHA-256 before it is
  written, a file from disk is used only if it was picked in Mortar's own file dialog, and the USB
  is checked after writing.
- **Writing needs permission**: on Linux through `pkexec` (the system's password prompt), on
  Windows as administrator. Mortar itself never runs as root.
- **The window is locked down**: sandboxed, isolated, no Node in the page, a strict
  Content-Security-Policy, no navigation or new windows, developer tools off in released builds,
  and every request checked for coming from Mortar's own page.
- **No secrets**: Mortar ships no keys or tokens; `.gitignore` keeps key and environment files out.
- **Dependencies**: Dependabot keeps Electron, the build tools and the workflows' actions up to
  date; actions are pinned to a commit. Pull requests are reviewed by Claude Code's security
  review once the `CLAUDE_API_KEY` secret is added.
