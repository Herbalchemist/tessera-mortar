#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""How big would an offline Tessera USB be?

Reads the registry manifests of the Tessera builds (no image download needed) and adds up their
layers: once per build, and once for all builds together with shared layers counted a single time,
which is how they'd sit on the USB (an OCI image layout stores each layer blob once).

  python3 tools/measure-images.py ghcr.io/herbalchemist/tessera:latest ghcr.io/herbalchemist/tessera-nvidia:latest ...

Needs `skopeo`. Prints a Markdown report (also written to $GITHUB_STEP_SUMMARY when set) and
writes sizes.json.
"""
import json
import os
import subprocess
import sys

GB = 1000 ** 3


def raw(ref):
    r = subprocess.run(["skopeo", "inspect", "--raw", f"docker://{ref}"], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "skopeo failed")
    return json.loads(r.stdout)


def manifest(ref):
    m = raw(ref)
    if "manifests" in m:  # an index: take linux/amd64
        pick = next((x for x in m["manifests"] if x.get("platform", {}).get("architecture") == "amd64"), m["manifests"][0])
        base = ref.split("@", 1)[0]
        if ":" in base.rsplit("/", 1)[-1]:  # drop the tag, keep a registry port
            base = base.rsplit(":", 1)[0]
        m = raw(f"{base}@{pick['digest']}")
    return m


def main(refs):
    rows, everything, results = [], {}, {}
    for ref in refs:
        try:
            m = manifest(ref)
        except Exception as e:  # noqa: BLE001 - report and carry on
            rows.append(f"| `{ref}` | — | — | could not read: {e} |")
            results[ref] = {"error": str(e)}
            continue
        layers = {l["digest"]: l["size"] for l in m.get("layers", [])}
        size = sum(layers.values())
        everything.update(layers)
        results[ref] = {"layers": len(layers), "bytes": size}
        rows.append(f"| `{ref}` | {len(layers)} | {size / GB:.2f} GB | |")
    ok = [r for r in refs if "bytes" in results.get(r, {})]
    total_separate = sum(results[r]["bytes"] for r in ok)
    total_shared = sum(everything.values())
    lines = [
        "## Tessera image sizes (compressed, as stored on a USB)",
        "",
        "| Image | Layers | Size | Note |",
        "|---|---|---|---|",
        *rows,
        "",
        f"- **All {len(ok)} readable images, shared layers stored once:** {total_shared / GB:.2f} GB",
        f"- Stored separately (no sharing): {total_separate / GB:.2f} GB",
        f"- Sharing saves: {(total_separate - total_shared) / GB:.2f} GB",
        "",
        "A USB also needs the live system that boots and runs the installer (a few GB) plus room for Extras.",
    ]
    report = "\n".join(lines)
    print(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(report + "\n")
    with open("sizes.json", "w") as f:
        json.dump({"images": results, "sharedBytes": total_shared, "separateBytes": total_separate}, f, indent=2)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
