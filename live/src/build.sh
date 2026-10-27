#!/usr/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Turns the Tessera image into the live system for the USB. Adapted from the Bazzite example in
# Universal Blue's Titanoboa (Apache-2.0, https://github.com/ublue-os/titanoboa).
set -exo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$(realpath /root)"

### A kernel the firmware trusts out of the box
# Bazzite's kernel is signed with Universal Blue's key, which a new machine doesn't know yet, so with
# Secure Boot on it wouldn't boot from the USB. The live system uses Fedora's signed kernel instead;
# the installed system gets Bazzite's kernel, and the installer queues Universal Blue's key for it.
kernel_pkgs=(kernel kernel-core kernel-devel kernel-devel-matched kernel-modules kernel-modules-core kernel-modules-extra)
dnf -y versionlock delete "${kernel_pkgs[@]}" || :
dnf --setopt=protect_running_kernel=False -y remove "${kernel_pkgs[@]}" || :
(cd /usr/lib/modules && rm -rf -- ./*)
dnf -y --repo fedora,updates --setopt=tsflags=noscripts install kernel kernel-core kernel-modules kernel-modules-extra
kernel=$(find /usr/lib/modules -maxdepth 1 -mindepth 1 -type d -printf '%P\n' | head -1)
depmod "$kernel"
dnf install -yq nvidia-gpu-firmware || :

### Boot from the USB
dnf install -y dracut-live livesys-scripts grub2-efi-x64-cdboot
DRACUT_NO_XATTR=1 dracut -v --force --zstd --reproducible --no-hostonly \
  --add "dmsquash-live dmsquash-live-autooverlay" "/usr/lib/modules/${kernel}/initramfs.img" "${kernel}"
sed -i "s/^livesys_session=.*/livesys_session=kde/" /etc/sysconfig/livesys
systemctl enable livesys.service livesys-late.service
mkdir -p /boot/efi
cp -av /usr/lib/efi/*/*/EFI /boot/efi/
cp -v /boot/efi/EFI/fedora/grubx64.efi /boot/efi/EFI/BOOT/fbx64.efi
mkdir -p /usr/lib/bootc-image-builder
cp "$SRC/iso.yaml" /usr/lib/bootc-image-builder/iso.yaml

### The install engine: Anaconda, driven by a kickstart from live-install
dnf install -y --allowerasing anaconda-live libblockdev-{btrfs,lvm,dm} mokutil openssl
# Anaconda ignores a kickstart given with --kickstart when it runs on a live system (--liveinst), and
# only uses interactive-defaults.ks, which can't run unattended. The Install Tessera screens have
# already asked everything, so let a live install take the kickstart: a one-line change, checked so
# the build stops if Anaconda ever changes there.
ana=$(python3 -c 'import os, pyanaconda; print(os.path.dirname(pyanaconda.__file__))')/startup_utils.py
grep -q 'if options.ksfile and not options.liveinst:' "$ana" || { echo "Anaconda's kickstart selection changed: check $ana" >&2; exit 1; }
sed -i 's/if options.ksfile and not options.liveinst:/if options.ksfile:  # Tessera: live installs take a kickstart too/' "$ana"
rm -rf "$(dirname "$ana")/__pycache__/startup_utils."*
mkdir -p /etc/anaconda/profile.d /usr/libexec/tessera /usr/share/tessera-install
cp "$SRC/anaconda-profile.conf" /etc/anaconda/profile.d/tessera.conf
install -m 0755 "$SRC/live-install" /usr/libexec/tessera/live-install
install -m 0440 "$SRC/sudoers" /etc/sudoers.d/tessera-live-install
# Universal Blue's Secure Boot key: queued for enrollment so the installed system's kernel and drivers can boot.
cp /etc/pki/akmods/certs/akmods-ublue.der /usr/share/tessera-install/secure-boot-key.der 2>/dev/null ||
  curl --retry 3 -fLo /usr/share/tessera-install/secure-boot-key.der https://github.com/ublue-os/akmods/raw/main/certs/public_key.der

### Start into Tessera, in installer mode
mkdir -p /etc/tessera
touch /etc/tessera/live-installer            # the launcher shows Install Tessera instead of the first-run setup
echo liveuser > /etc/tessera/autologin-user  # livesys creates this user at boot
mkdir -p /etc/systemd/system/tessera-autologin.service.d
printf '[Unit]\nAfter=livesys.service\n' > /etc/systemd/system/tessera-autologin.service.d/live.conf
install -m 0755 "$SRC/tessera-live-session" /usr/libexec/tessera/tessera-live-session
install -m 0755 "$SRC/live-session-run" /usr/libexec/tessera/live-session-run
sed -i 's|^Exec=.*|Exec=/usr/libexec/tessera/live-session-run|' /usr/share/wayland-sessions/tessera.desktop
install -m 0755 "$SRC/tessera-live-debug" /usr/libexec/tessera/tessera-live-debug
install -m 0644 "$SRC/tessera-live-debug.service" /etc/systemd/system/tessera-live-debug.service
systemctl enable tessera-live-debug.service
install -m 0644 "$SRC/tessera-live-session.service" /etc/systemd/system/tessera-live-session.service
systemctl enable tessera-live-session.service
# In desktop mode (or if the Tessera session can't start), Install Tessera opens as a window by itself.
mkdir -p /etc/skel/.config/autostart
cp "$SRC/install-tessera.desktop" /etc/skel/.config/autostart/install-tessera.desktop
# Fedora's own "Install to Hard Drive" would install the wrong thing, and Bazzite's welcome window
# doesn't belong on an installer USB.
rm -f /usr/share/applications/liveinst.desktop /etc/xdg/autostart/liveinst-setup.desktop
for f in /etc/xdg/autostart/*.desktop /usr/share/autostart/*.desktop /etc/skel/.config/autostart/*.desktop; do
  [ -f "$f" ] && grep -qiE '^(Name|Exec)=.*(bazzite[- ]portal|yafti)' "$f" && rm -f "$f"
done
# A shortcut on the desktop, too.
install -m 0644 "$SRC/install-tessera.desktop" /usr/share/applications/install-tessera.desktop
mkdir -p /etc/skel/Desktop
cp /usr/share/applications/install-tessera.desktop /etc/skel/Desktop/
chmod +x /etc/skel/Desktop/install-tessera.desktop

### Live-only tweaks
for s in rpm-ostreed-automatic.timer uupd.timer bootloader-update.service bazzite-hardware-setup.service \
         ublue-system-setup.service check-sb-key.service rpm-ostree-countme.service brew-setup.service \
         brew-update.timer brew-upgrade.timer tailscaled.service ublue-os-media-automount.service; do
  systemctl disable "$s" 2>/dev/null || :
done
for s in ublue-flatpak-manager.service podman-auto-update.timer ublue-user-setup.service; do
  systemctl --global disable "$s" 2>/dev/null || :
done
rm -f /etc/localtime
systemd-firstboot --timezone UTC
# ostree needs room in /var/tmp while installing; the live overlay under /run is small.
rm -rf /var/tmp || :
mkdir -p /var/tmp
cat >/etc/systemd/system/var-tmp.mount <<'UNIT'
[Unit]
Description=Larger tmpfs for /var/tmp on the live system
[Mount]
What=tmpfs
Where=/var/tmp
Type=tmpfs
Options=size=50%%,nr_inodes=1m
[Install]
WantedBy=local-fs.target
UNIT
systemctl enable var-tmp.mount
mkdir -p /etc/skel/.config
printf '[Wallet]\nEnabled=false\n' > /etc/skel/.config/kwalletrc
# An install takes a while: the live desktop must never lock (nobody knows the live user's password)
# or turn the screen off.
printf '[Daemon]\nAutolock=false\nLockOnResume=false\nTimeout=0\n' > /etc/skel/.config/kscreenlockerrc
for p in AC Battery LowBattery; do
  printf '[%s][Display]\nDimDisplayWhenIdle=false\nTurnOffDisplayWhenIdle=false\n\n[%s][SuspendAndShutdown]\nAutoSuspendAction=0\n\n' "$p" "$p"
done > /etc/skel/.config/powerdevilrc
dnf clean all
