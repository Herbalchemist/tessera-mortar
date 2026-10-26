# SPDX-License-Identifier: GPL-3.0-or-later
"""Prints the kickstarts live-install writes (both Secure Boot choices), for ksvalidator."""
import importlib.machinery
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_live_install as t  # noqa: E402

li = t.li
out = sys.argv[1]
for sb in ("auto", "manual"):
    c = li.check({**t.GOOD, "secureBoot": sb}, t.OFFERED)
    with open(os.path.join(out, f"tessera-{sb}.ks"), "w") as f:
        f.write(li.kickstart(c, t.OFFERED["imagesDir"], "$6$salt$hash", sb_key="/k.der"))
