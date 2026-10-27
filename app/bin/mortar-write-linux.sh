#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Mortar's Linux writer, run as root through pkexec: writes an image to a USB drive, then reads it
# back so Mortar can check it. Prints progress lines Mortar reads:
#   PHASE write|verify  /  BYTES n  /  SHA <hex>  /  ERROR <text>
#   mortar-write-linux.sh IMAGE DEVICE [SIZE]   (SIZE: the drive's size in bytes when it was picked)
set -u
IMG=$1 DEV=$2 WANT=${3:-}
fail() { echo "ERROR $*"; exit 1; }
[ "$(id -u)" = 0 ] || fail "needs to run as root"
[ -f "$IMG" ] || fail "image not found"
case "$DEV" in
  /dev/sd[a-z]|/dev/sd[a-z][a-z]|/dev/nvme[0-9]n[0-9]|/dev/nvme[0-9][0-9]n[0-9]|/dev/mmcblk[0-9]|/dev/vd[a-z]) ;;
  *) [ -n "${MORTAR_TEST_TARGET:-}" ] && [ "$DEV" = "$MORTAR_TEST_TARGET" ] || fail "not a whole-disk device: $DEV" ;;
esac
if [ -b "$DEV" ]; then
  # Only removable or USB drives, and never one holding the running system (checked again here, as root).
  rm=$(lsblk -dn -o RM "$DEV" 2>/dev/null | tr -d ' ')
  hp=$(lsblk -dn -o HOTPLUG "$DEV" 2>/dev/null | tr -d ' ')
  tran=$(lsblk -dn -o TRAN "$DEV" 2>/dev/null | tr -d ' ')
  [ "$rm" = 1 ] || [ "$hp" = 1 ] || [ "$tran" = usb ] || fail "not a removable or USB drive" 
  if lsblk -nr -o MOUNTPOINTS "$DEV" | grep -qE '^/(boot|usr|home|var|sysroot)?$'; then fail "this drive holds the running system"; fi
  # Still the drive that was picked (a different stick can get the same name), and not in use as swap.
  if [ -n "$WANT" ] && [ "$(blockdev --getsize64 "$DEV" 2>/dev/null)" != "$WANT" ]; then fail "the drive changed since it was picked: choose it again"; fi
  for p in $(lsblk -nr -o PATH "$DEV"); do
    if swapon --show=NAME --noheadings 2>/dev/null | grep -qx "$p"; then fail "this drive is in use as swap"; fi
  done
  for p in $(lsblk -nr -o PATH "$DEV" | tail -n +2); do umount "$p" 2>/dev/null; done
  umount "$DEV" 2>/dev/null
fi
SIZE=$(stat -c %s "$IMG")
echo "PHASE write"
dd if="$IMG" of="$DEV" bs=4M iflag=fullblock oflag=direct conv=fsync status=progress 2>&1 |
  tr '\r' '\n' | while read -r n _; do case "$n" in ''|*[!0-9]*) ;; *) echo "BYTES $n" ;; esac; done
sync
[ -b "$DEV" ] && blockdev --flushbufs "$DEV" 2>/dev/null
echo "PHASE verify"
[ -b "$DEV" ] && echo 3 > /proc/sys/vm/drop_caches 2>/dev/null
tmp=$(mktemp)
{ dd if="$DEV" bs=4M count="$SIZE" iflag=count_bytes status=progress | sha256sum > "$tmp"; } 2>&1 |
  tr '\r' '\n' | while read -r n _; do case "$n" in ''|*[!0-9]*) ;; *) echo "BYTES $n" ;; esac; done
SHA=$(cut -d' ' -f1 < "$tmp"); rm -f "$tmp"
[ -n "$SHA" ] || fail "couldn't read the drive back"
echo "SHA $SHA"
