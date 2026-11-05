#!/bin/sh
# Common rootfs customization. $1 = rootfs directory.
# Parameters via environment: PLATFORM, VERSION, CODENAME, BUILD, BUILD_TYPE,
# CURRENT_DIR.
# Consumed by the mmdebstrap customize hooks (image-params.yaml).
set -e
chroot "$1" groupadd sima
chroot "$1" groupadd -f tracing
chroot "$1" groupadd -f i2c
chroot "$1" useradd -m -g sima -G sudo,audio,video,tracing,i2c sima
# root and sima passwords: crypt hashes, one user:hash line each, from outside the repo.
# Without them both stay locked, as the base system and useradd leave them.
if [ -n "${CIB_CREDENTIALS:-}" ]; then
	chroot "$1" chpasswd -e < "$CIB_CREDENTIALS"
fi
chroot "$1" usermod -a -G sima root
chroot "$1" usermod -s /bin/bash sima
echo "${PLATFORM}" > "$1/etc/hostname"
# The rootfs is a logical volume in the "Boot A/B + LVM" layout, so the
# spare eMMC space goes to the data volume instead of to /. elxr-growfs walks
# the block device hierarchy below / and bails out on anything that is not a
# partition, so it cannot be used here.
systemctl enable --root="$1" simaai-growlvm
# One boot file system per A/B slot means /boot cannot be a static fstab entry;
# this mounts the slot the board booted from, read-only.
systemctl enable --root="$1" simaai-mount-boot
# The U-Boot environment lives on that same per-slot boot file system, but is a
# separate question from where this boot's kernel came from -- it is still on
# the eMMC when the board boots from USB, SD or the network. It gets a mount of
# its own, which is what lets /etc/fw_env.config be a static file.
systemctl enable --root="$1" simaai-mount-uboot-env
systemctl enable --root="$1" simaai-hwrevision
# Each board makes its own SSH host keys on first boot; the build's are removed at the end.
systemctl enable --root="$1" simaai-ssh-hostkeys
# The overlay pre-init activates the volume group before udev exists, so the
# data volume never gets its udev links. This replays that activation once
# udev is up, or /dev/disk/by-label/data never appears and the /data entry
# in fstab waits out its device timeout on every boot.
systemctl enable --root="$1" simaai-overlay-udev-replay
# Updates run swupdate one-shot (swupdate -i <bundle> -e update,<mode>, with
# the key /etc/swupdate.cfg names), so no daemon is needed. The swupdate deb, built for signed images,
# enables a daemon that then exits "provide a public key file" and systemd
# restart-loops it every 20s. Neutralise the daemon-mode units: mask the
# service and its socket (the masked service also blocks socket activation, and
# freeing /run/swupdate/* lets a one-shot run bind its own sockets), and disable
# the progress helper (it only watches a daemon install and reboots after it).
systemctl --root="$1" mask swupdate.service swupdate.socket
systemctl disable --root="$1" swupdate-progress.service
# e2scrub takes a snapshot to check a mounted file system, and growlvm hands
# every spare extent to data, so there is never room for one.
systemctl disable --root="$1" e2scrub_reap.service
systemctl disable --root="$1" e2scrub_all.timer
chroot "$1" chown -R sima /home/sima
# Mount point for the persistent data logical volume, which every flavor's
# fstab now carries.
mkdir -p "$1/data"
sh "${CURRENT_DIR}/scripts/build_scripts/prepare_buildinfo.sh" "$1/etc/buildinfo" "${PLATFORM}" "${VERSION}" "${BUILD:-0}" "${CODENAME}"
# Drop the build-time local package repository from the image's apt config.
# It is reachable only while the image is being built (localhost, forwarded
# to the build host's reprepro); left in place it makes `apt update` on the
# flashed board fail with a connection refused to localhost:80. Sources may
# be one-line (*.list, /etc/apt/sources.list) or deb822 (*.sources, the
# trixie default); handle both, and never fail when a file is absent.
prune_localhost() {
	f="$1"
	[ -f "$f" ] || return 0
	case "$f" in
	*.sources)
		# deb822: drop whole stanzas (blank-line separated) pointing at the build-time repo (//localhost/).
		awk 'BEGIN { RS = ""; ORS = "\n\n" } !/\/\/localhost\//' "$f" > "$f.pruned"
		mv "$f.pruned" "$f"
		;;
	*)
		sed -i '\#//localhost/#d' "$f"
		;;
	esac
}
prune_localhost "$1/etc/apt/sources.list"
for src in "$1"/etc/apt/sources.list.d/*.list "$1"/etc/apt/sources.list.d/*.sources; do
	prune_localhost "$src"
done
# The SiMa.ai source line stays in the image and names this keyring as its
# signed-by; only the build container has it, so apt on a board needs a copy.
install -D -m 644 /usr/share/keyrings/simaai-public.gpg "$1/usr/share/keyrings/simaai-public.gpg"
# Drop the build-time dpkg options too (force-confdef, force-confold in
# image-stages.yaml). They exist so a conffile the overlay already wrote
# cannot stop the build with a prompt no one is there to answer, which is a
# property of the build and not of the board: on a running system the same
# options would silently discard every updated conffile an upgrade ships.
# mmdebstrap keeps this file rather than treating it as temporary, so removing
# it is on us. Every package is configured by the time customize hooks run,
# and no later hook installs one, so nothing still needs the options.
rm -f "$1/etc/dpkg/dpkg.cfg.d/99mmdebstrap"
# Drop the host keys openssh-server made, or every board would share them.
rm -f "$1"/etc/ssh/ssh_host_*
