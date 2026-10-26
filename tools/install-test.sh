#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# End-to-end test of the Tessera USB in a virtual machine: boots the ISO, drives Install Tessera with
# the keyboard (through QEMU's monitor) to install onto an empty virtual disk, then boots the installed
# system. Screenshots of every step and the serial console go to install-test/.
#   tools/install-test.sh path/to/Tessera-Live.iso
# Env: BOOT_ARGS (extra kernel arguments for the live boot), INSTALL_MINUTES (default 40)
set -euo pipefail
ISO=$(realpath "$1")
OUT=$(realpath -m install-test); mkdir -p "$OUT"; rm -f "$OUT"/*
work=$(mktemp -d)
xorriso -osirrox on -indev "$ISO" -extract /images/pxeboot/vmlinuz "$work/vmlinuz" -extract /images/pxeboot/initrd.img "$work/initrd.img" >/dev/null 2>&1
CODE=""; VARS=""
for f in /usr/share/OVMF/OVMF_CODE_4M.fd /usr/share/OVMF/OVMF_CODE.fd; do [ -f "$f" ] && { CODE=$f; break; }; done
for f in /usr/share/OVMF/OVMF_VARS_4M.fd /usr/share/OVMF/OVMF_VARS.fd; do [ -f "$f" ] && { VARS=$f; break; }; done
cp "$VARS" "$work/vars.fd"
accel=tcg; [ -w /dev/kvm ] && accel=kvm
truncate -s 100G "$work/disk.img"
n=0
shot() { n=$((n + 1)); echo "screendump $OUT/$(printf %02d $n)-$1.ppm" | socat - unix-connect:"$work/mon" >/dev/null || :; sleep 1; }
key() { for k in "$@"; do echo "sendkey $k" | socat - unix-connect:"$work/mon" >/dev/null || :; sleep 0.25; done; }
typetext() { local s=$1 i c; for ((i = 0; i < ${#s}; i++)); do c=${s:i:1}; case $c in ' ') key spc ;; *) key "$c" ;; esac; done; }
vm() { # vm NAME [extra qemu args...]
  local name=$1; shift
  qemu-system-x86_64 -machine q35,accel=$accel -cpu max -smp 4 -m 8192 \
    -drive if=pflash,format=raw,readonly=on,file="$CODE" -drive if=pflash,format=raw,file="$work/vars.fd" \
    -drive file="$work/disk.img",format=raw,if=virtio \
    -device virtio-vga -display none -serial file:"$OUT/serial-$name.log" \
    -monitor unix:"$work/mon",server,nowait -daemonize -pidfile "$work/pid" "$@"
}
stop() { kill "$(cat "$work/pid")" 2>/dev/null || :; sleep 3; }
alive() { kill -0 "$(cat "$work/pid")" 2>/dev/null; }

echo "== live boot ($accel)"
vm live -kernel "$work/vmlinuz" -initrd "$work/initrd.img" \
  -append "root=live:CDLABEL=Tessera-Live rd.live.image enforcing=0 console=tty0 console=ttyS0,115200 ${BOOT_ARGS:-}" \
  -drive file="$ISO",media=cdrom,readonly=on
sleep 150; shot welcome
key ret; sleep 20; shot disk                 # Install Tessera
key ret; sleep 4; shot graphics              # the only disk
key ret; sleep 3; shot name                  # the recommended build
typetext "tess tester"; key ret; sleep 3; shot account
key ret; sleep 3; shot password              # keep the suggested user name
typetext "tessera1"; key ret; sleep 2
typetext "tessera1"; key ret; sleep 3; shot timezone
key ret; sleep 3; shot secureboot            # the current region (UTC)
key ret; sleep 3; shot summary               # set it up for me
key up ret; sleep 15; shot installing        # Erase and install (the cursor starts on Go back)
end=$((SECONDS + ${INSTALL_MINUTES:-40} * 60))
i=0
while [ $SECONDS -lt $end ] && alive; do
  sleep 60; i=$((i + 1)); shot "install-${i}m"
  # Done when the serial console or the screen says so; the screen is checked by the person looking.
  grep -aqE "tessera-install: (done|error|refused)" "$OUT/serial-live.log" 2>/dev/null && { sleep 20; shot install-end; break; }
done
cp /run/tessera-install/state.json "$OUT/" 2>/dev/null || :
stop

echo "== first boot from the disk"
vm installed
for t in 60 120 180 240 300; do sleep 60; shot "firstboot-${t}s"; done
stop
for f in "$OUT"/*.ppm; do [ -f "$f" ] && convert "$f" "${f%.ppm}.png" && rm -f "$f"; done
ls -la "$OUT"
