#!/bin/sh
# Minimal-flavor customization. $1 = rootfs directory.
set -e
# Never block the boot on a file system that is not there: the minimal flavor
# is also netbooted and run from a cpio, where the eMMC volumes may be absent.
# Skip the root line -- the kernel has already mounted / by the time fstab is
# read -- and leave entries that are marked nofail already alone.
sed -i '/[[:space:]]\/[[:space:]]/!{/nofail/!s/defaults/defaults,nofail/}' "$1/etc/fstab"
