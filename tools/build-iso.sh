#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Makes the Tessera USB image (an ISO you write to a USB drive): the live system from a container
# image, plus the Tessera builds as an OCI image layout next to it, so it installs with no network.
# Adapted from Universal Blue's Titanoboa build_iso.sh (Apache-2.0, https://github.com/ublue-os/titanoboa),
# which follows the container-native ISO contract (https://github.com/ondrejbudai/bootc-isos).
#
#   sudo tools/build-iso.sh LIVE_IMAGE IMAGES_DIR OUTPUT_DIR
#     LIVE_IMAGE  the live system, in the local container storage (e.g. localhost/tessera-live:latest)
#     IMAGES_DIR  an OCI image layout with the builds (see tools/fetch-images.sh); goes on the ISO as /tessera-images
#     OUTPUT_DIR  where the ISO is written
set -euo pipefail
LIVE_IMAGE=$1 IMAGES_DIR=$(realpath "$2") OUT=$(realpath -m "$3")
mkdir -p "$OUT"
podman run --rm -i --cap-add sys_admin --security-opt label=disable -e SQUASH_LEVEL="${SQUASH_LEVEL:-19}" \
  --mount type=image,source="$LIVE_IMAGE",dst=/rootfs \
  -v "$IMAGES_DIR":/tessera-images:ro -v "$OUT":/output \
  quay.io/fedora/fedora:latest bash -euxo pipefail -s <<'INNER'
dnf install -y -q squashfs-tools xorriso yq mtools dosfstools
mkdir -p /work/iso-root/boot/grub2 /work/iso-root/images/pxeboot /work/iso-root/LiveOS
cd /work
mksquashfs /rootfs /work/iso-root/LiveOS/squashfs.img -all-root -noappend -e sysroot -e ostree -comp zstd -Xcompression-level "${SQUASH_LEVEL:-19}" -quiet
conf=/rootfs/usr/lib/bootc-image-builder/iso.yaml
label=$(yq '.label' <"$conf")
cp -av /rootfs/usr/lib/modules/*/initramfs.img /work/iso-root/images/pxeboot/initrd.img
cp -av /rootfs/usr/lib/modules/*/vmlinuz /work/iso-root/images/pxeboot/vmlinuz
[ -d /rootfs/usr/lib/grub/i386-pc ] && cp -avT /rootfs/usr/lib/grub/i386-pc /work/iso-root/boot/grub2/i386-pc
cp -avT /rootfs/boot/efi/EFI /work/EFI
{
  echo "set timeout=$(yq '.grub2.timeout // 10' <"$conf")"
  echo "set default=\"$(yq '.grub2.default // 0' <"$conf")\""
  echo 'set menu_auto_hide=false'
  echo 'insmod all_video'
  echo 'set gfxpayload=keep'
  echo 'insmod gzio'
  echo 'insmod part_gpt'
  echo "search --no-floppy --set=root -l '$label'"
  for i in $(yq '.grub2.entries | keys | .[]' <"$conf"); do
    echo "menuentry '$(yq ".grub2.entries[$i].name" <"$conf")' {"
    echo "  linux $(yq ".grub2.entries[$i].linux" <"$conf")"
    echo "  initrd $(yq ".grub2.entries[$i].initrd" <"$conf")"
    echo "}"
  done
} > /work/grub.cfg
for dir in /work/EFI/* /work/iso-root/boot/grub2; do cp /work/grub.cfg "$dir/grub.cfg"; done
cp -avT /work/EFI /work/iso-root/EFI
truncate -s 100M /work/uefi.img
mkfs.fat -F32 /work/uefi.img
mcopy -i /work/uefi.img -s /work/EFI ::
xorriso -as mkisofs -R -V "$label" \
  -partition_offset 16 -appended_part_as_gpt \
  -append_partition 2 C12A7328-F81F-11D2-BA4B-00A0C93EC93B ./uefi.img \
  -iso_mbr_part_type EBD0A0A2-B9E5-4433-87C0-68B6B72699C7 \
  -e --interval:appended_partition_2:all:: -no-emul-boot -iso-level 3 \
  -graft-points -o "/output/$label.iso" iso-root /tessera-images=/tessera-images
ls -la /output
INNER
