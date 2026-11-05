#!/bin/sh
# Palette/securepalette customization (identical for both). $1 = rootfs.
set -e
systemctl disable --root="$1" kea-ctrl-agent
systemctl disable --root="$1" kea-dhcp-ddns-server
systemctl disable --root="$1" kea-dhcp4-server
systemctl disable --root="$1" kea-dhcp6-server
systemctl --root="$1" mask pulseaudio.socket
# Build reports go next to the image (OUTPUT_DIR, set by cib build).
out="${OUTPUT_DIR:-$CURRENT_DIR}"
chroot "$1" dpkg-query -l > "${out}/simaai-image-palette.manifest"
# Ship the same manifest inside the image so simaai-pdiff can diff the
# packages installed on a running system against the build-time set.
cp "${out}/simaai-image-palette.manifest" "$1/etc/simaai-image-palette.manifest"
chroot "$1" /bin/bash -c "du -a --exclude=var/cache /" > "${out}/du.txt" || true
python3 "${CURRENT_DIR}/scripts/extract_licenses.py" "${out}/simaai-image-palette.manifest" "${out}/simaai-image-palette.licenses" "$1/usr/share/doc/"
