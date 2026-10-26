#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Boots the Tessera USB image in a virtual machine (UEFI, KVM) and takes screenshots, to check that it
# starts into the installer. The serial console goes to boot-test/serial.log.
#   tools/boot-test.sh path/to/Tessera-Live.iso [seconds]
set -euo pipefail
ISO=$(realpath "$1"); WAIT=${2:-240}
OUT=$(realpath -m boot-test); mkdir -p "$OUT"; rm -f "$OUT"/*
work=$(mktemp -d)
# The kernel and initramfs from the ISO, so the test can add a serial console.
xorriso -osirrox on -indev "$ISO" -extract /images/pxeboot/vmlinuz "$work/vmlinuz" -extract /images/pxeboot/initrd.img "$work/initrd.img" >/dev/null 2>&1
OVMF=""
for f in /usr/share/OVMF/OVMF_CODE_4M.fd /usr/share/OVMF/OVMF_CODE.fd /usr/share/edk2/ovmf/OVMF_CODE.fd; do [ -f "$f" ] && { OVMF=$f; break; }; done
accel=tcg; [ -w /dev/kvm ] && accel=kvm
truncate -s 80G "$work/disk.img"
qemu-system-x86_64 -machine q35,accel=$accel -cpu max -smp 4 -m 8192 \
  ${OVMF:+-drive if=pflash,format=raw,readonly=on,file=$OVMF} \
  -kernel "$work/vmlinuz" -initrd "$work/initrd.img" \
  -append "root=live:CDLABEL=Tessera-Live rd.live.image enforcing=0 console=tty0 console=ttyS0,115200 ${BOOT_ARGS:-}" \
  -drive file="$ISO",media=cdrom,readonly=on -drive file="$work/disk.img",format=raw,if=virtio \
  -device virtio-vga -display none -serial file:"$OUT/serial.log" \
  -monitor unix:"$work/mon",server,nowait -daemonize -pidfile "$work/pid"
shot() { echo "screendump $OUT/$1.ppm" | socat - unix-connect:"$work/mon" >/dev/null; sleep 1; }
for t in 60 120 180 $WAIT; do
  [ "$t" -le "$WAIT" ] || continue
  sleep $((t - ${prev:-0})); prev=$t
  shot "at-${t}s"
done
kill "$(cat "$work/pid")" 2>/dev/null || :
for f in "$OUT"/*.ppm; do [ -f "$f" ] && (convert "$f" "${f%.ppm}.png" 2>/dev/null || pnmtopng "$f" > "${f%.ppm}.png") && rm -f "$f"; done
echo "accel=$accel"; ls -la "$OUT"
