#!/bin/sh
# A/B update hook for the boot A/B + LVM eMMC layout.
#
# The rootfs slots are the rootfs.A/rootfs.B logical volumes in the LVM
# container on mmcblk0p3; the boot slots are the raw GPT partitions
# mmcblk0p1 (boot.A) and mmcblk0p2 (boot.B); tRoot keeps its own A/B
# slots in the boot flash, managed through simaai-trootctl over HPI.
# The kernel maps the active rootfs slot through dm-init, so the running
# slot is identified by its fixed per-slot UUID (stamped by the image
# build, restored by this script after an update rewrites a slot).
#
# One global A/B slot covers the whole chain - the tRoot firmware slot,
# the boot partition tRoot hands U-Boot, and thereby the rootfs. The
# bundle installs by collection (swupdate -e update,<mode>):
#
#   full     - tRoot slot image + boot fs + rootfs
#   firmware - the tRoot slot image only (reuses the OS already in the
#              target slot)
#   os       - boot fs + rootfs only (reuses the tRoot already in the
#              target slot)
#
# postinst keys off what each collection stages - a boot0.be rawfile
# marks the firmware part, a swu-os-marker rawfile marks the OS part -
# and installs whichever are present. The single switch-slot at the end
# flips the one slot regardless of which parts changed, so partial
# updates deliberately pair a new tier with whatever the other tier
# already holds in that slot (a developer flow; production ships full).
#
# preinst resolves the inactive slot and leaves /dev/rootpart and
# /dev/bootpart symlinks for the sw-description image entries to write
# through. postinst finishes each part and only when all of it succeeded
# activates the slot with switch-slot, arming the watchdog rollback until
# a healthy boot confirms via simaai-trootctl-bootgood.

set -e

# LVM tools warn about every inherited descriptor when spawned from
# swupdate, and swupdate surfaces all script stderr as ERROR lines;
# suppress the known-harmless noise so real errors stay visible.
export LVM_SUPPRESS_FD_WARNINGS=1

BOOTPART=/dev/bootpart
ROOTPART=/dev/rootpart
BOOT0=/tmp/swupdate-boot0.be
OSMARK=/tmp/swupdate.os

# Fixed per-slot identities; must match image-params.yaml. The boot
# partitions are vfat: their identity is the 32-bit FAT volume id.
ROOT_UUID_A=740d31f2-aa09-56e0-9c6e-ee357eb533d0
ROOT_UUID_B=905013a4-b365-5e4a-8ded-0f223098085a
BOOT_ID_A=EAF6D693
BOOT_ID_B=0ACF4014

# Work out which slot is running and which one an update targets, into the
# globals the hooks below use.
#
# Every step says what it could not determine, and the whole thing returns
# non-zero rather than exiting. Both are for the operator's benefit: under
# 'set -e' a failing discovery command takes the script down with nothing
# but its exit status, which swupdate reports as a bare "command returned
# <n>" naming none of these; and postfailure has to be able to attempt its
# cleanup even on a board this cannot identify.
resolve_slots() {
	# The dm-init mapping carries no /dev/mapper/rootfs node on the
	# running system (udev creates nodes only for devices it saw events
	# for), so resolve the root device from the mount table instead - it
	# is the dm-init device whatever it is called.
	rootdev=$(findmnt -no SOURCE /) || rootdev=
	if [ -z "$rootdev" ]; then
		echo "Cannot tell what / is mounted from" >&2
		return 1
	fi
	if [ ! -b "$rootdev" ]; then
		# Not a block device means the board booted with the rootfs
		# overlay (init=/usr/sbin/simaai-overlay-init): / is an
		# overlayfs mount, whose source is the literal string
		# "overlay", stacked on the real rootfs as its lower layer.
		# root= on the kernel command line names the device the kernel
		# actually mounted, whether or not something was later stacked
		# over it, so the slot identity is still available there.
		#
		# This is the ordinary case rather than an exception: the
		# overlay is on unless a boot was told otherwise, so most
		# updates run from an overlay boot. The writable layer lives on
		# the data volume, which neither slot owns, so it is meant to
		# be stacked over whichever slot is running - including the one
		# this update installs.
		cmdline_root=$(tr ' ' '\n' < /proc/cmdline |
			sed -n 's/^root=//p' | head -1)
		if [ -z "$cmdline_root" ] || [ ! -b "$cmdline_root" ]; then
			echo "/ is mounted from '$rootdev', which is not a" \
			     "block device, and root= on the kernel command" \
			     "line ('$cmdline_root') is not one either, so" \
			     "the running slot cannot be identified" >&2
			return 1
		fi
		echo "/ is '$rootdev': the rootfs overlay is active, so the" \
		     "running slot comes from root=$cmdline_root"
		rootdev=$cmdline_root
	fi

	# The boot medium's PV is the dm-init rootfs device's own backing
	# partition. Every LVM command below is scoped to it with --devices,
	# because "the board carries exactly one volume group" is only true
	# of the boot medium: a stray second group - an old install left on
	# an NVMe or SD card, or the same image flashed to two media - would
	# otherwise leak into the unscoped output (two-line vg name, wrong
	# group picked) and fail the update on that one board.
	dmname=${rootdev#/dev/}
	slave=
	if [ -d "/sys/block/$dmname/slaves" ]; then
		slave=$(ls "/sys/block/$dmname/slaves" | head -1)
	fi
	if [ -z "$slave" ]; then
		echo "The running rootfs $rootdev has no backing partition," \
		     "so this board is not running the boot A/B + LVM layout" \
		     "and has no slots to update" >&2
		return 1
	fi
	pv=/dev/$slave

	# The volume group name is flavour-dependent (simaai_<flavor>) and
	# nothing on the board depends on it, so discover it - from the boot
	# medium's PV alone, which carries exactly one.
	vg=$(vgs --devices "$pv" --noheadings -o vg_name 2>/dev/null |
		tr -d ' ') || vg=
	if [ -z "$vg" ]; then
		echo "No LVM volume group on $pv, so this board is not running" \
		     "the boot A/B + LVM layout and has no slots to update" >&2
		return 1
	fi

	active_uuid=$(blkid -s UUID -o value "$rootdev") || active_uuid=
	if [ -z "$active_uuid" ]; then
		echo "No file system UUID on the running rootfs $rootdev" >&2
		return 1
	fi

	# The boot slots are partitions 1 and 2 of the SAME medium the board
	# booted from, not of mmcblk0: an SD-booted board updates the SD's
	# boot partitions. simaai.bootdev= names the booted boot partition
	# (the boot script passes it, and simaai-mount-boot already trusts
	# it), so the inactive one is its sibling with the slot digit
	# swapped.
	bootdev=$(tr ' ' '\n' < /proc/cmdline |
		sed -n 's/^simaai\.bootdev=//p' | head -1)
	if [ -z "$bootdev" ] || [ ! -b "$bootdev" ]; then
		echo "simaai.bootdev= on the kernel command line" \
		     "('$bootdev') does not name the booted boot partition," \
		     "so the boot slot partitions cannot be located" >&2
		return 1
	fi

	case "$active_uuid" in
	"$ROOT_UUID_A")
		active=A
		inactive=B
		inactive_boot=${bootdev%1}2
		inactive_uuid=$ROOT_UUID_B
		inactive_boot_id=$BOOT_ID_B
		;;
	"$ROOT_UUID_B")
		active=B
		inactive=A
		inactive_boot=${bootdev%2}1
		inactive_uuid=$ROOT_UUID_A
		inactive_boot_id=$BOOT_ID_A
		;;
	*)
		echo "Cannot identify the running rootfs slot: $rootdev has" \
		     "UUID '$active_uuid', which is neither slot's" >&2
		return 1
		;;
	esac
	if [ ! -b "$inactive_boot" ]; then
		echo "The inactive boot partition derived from" \
		     "simaai.bootdev=$bootdev ('$inactive_boot') is not a" \
		     "block device" >&2
		return 1
	fi
	inactive_root=/dev/$vg/rootfs.$inactive
}

# The rootfs overlay's writable layer (the data volume's overlay/upper)
# belongs to neither slot, so this update does not touch it -- and after
# the reboot it keeps shadowing the updated slot's own files, a stale
# package database being the classic case. That is the
# overlay doing its job, but silently; say what is retained so the
# operator knows the local state is theirs to manage.
#
# Informational only: never fails the update, never writes the overlay.
# Cleaning it from here would break the update's atomicity -- the upper
# is shared by both slots, so no rollback could undo the write.
warn_overlay_upper() {
	upper=/data/overlay/upper
	[ -d "$upper" ] || return 0
	# Non-directory entries are the retained state: files and symlinks
	# shadow the new slot's copies, character devices are overlayfs
	# whiteouts marking local deletions.
	retained=$(find "$upper" ! -type d 2>/dev/null | wc -l) || return 0
	[ "$retained" -gt 0 ] || return 0
	echo "WARNING: the rootfs overlay retains $retained local" \
	     "modification(s) under $upper. They are outside the A/B slots:" \
	     "this update leaves them in place, and on the next overlay" \
	     "boot they keep shadowing the updated slot's own files. This" \
	     "local state is yours to review and clean up, or rerun with" \
	     "SWUPDATE_CLEAN_OVERLAY=1 to discard it with the update ('c'" \
	     "entries are local deletions):"
	find "$upper" ! -type d -printf '  %y %P\n' 2>/dev/null || true
}

# Unmount what is still mounted from the inactive boot partition, so a retry cannot write under it.
release_boot() {
	for m in $(findmnt -rn -S "$inactive_boot" -o TARGET); do
		umount "$m" || echo "could not unmount $m ($inactive_boot);" \
			"unmount it before retrying the update" >&2
		case "$m" in /tmp/tmp.*) rmdir "$m" 2>/dev/null ;; esac
	done
}

echo "== Start $1 =="

case "$1" in
preinst)
	# A stale boot0 or OS marker in /tmp must not be taken as part of this bundle.
	rm -f "$BOOT0" "$OSMARK"
	resolve_slots || exit 1
	cat /etc/buildinfo
	echo "Running slot $active, updating slot $inactive"
	warn_overlay_upper

	# An image that populates slot A only ships without a volume for the
	# other slot; simaai-growlvm reserves one on first boot. Say so
	# plainly rather than letting lvchange fail on a volume that is
	# missing for a reason a bare LVM error would not name.
	if ! lvs --devices "$pv" "$vg/rootfs.$inactive" >/dev/null 2>&1; then
		echo "No $vg/rootfs.$inactive volume to update into." \
		     "simaai-growlvm reserves the inactive slot on first" \
		     "boot; check 'systemctl status simaai-growlvm' and" \
		     "run it again before retrying this update" >&2
		exit 1
	fi

	# The rootfs slots are activation-skipped (only dm-init maps the
	# active one), so bring the target volume up explicitly. preinst runs
	# before the payload is installed, so it cannot yet tell an OS update
	# from a firmware-only one; it prepares for OS writes unconditionally
	# and postinst tears the volume back down when no OS part arrived.
	lvchange --devices "$pv" -K -ay "$vg/rootfs.$inactive"

	ln -sf "$inactive_root" $ROOTPART
	ln -sf "$inactive_boot" $BOOTPART
	echo "Partitions to update:"
	ls -l $ROOTPART $BOOTPART
	;;

postinst)
	resolve_slots || exit 1

	# What this collection staged: boot0.be marks a firmware (tRoot)
	# part, the swu-os-marker rawfile marks an OS (boot fs + rootfs) part.
	has_fw=0; [ -f "$BOOT0" ] && has_fw=1
	has_os=0; [ -f "$OSMARK" ] && has_os=1
	if [ "$has_fw" = 0 ] && [ "$has_os" = 0 ]; then
		echo "Update carries neither a tRoot nor an OS part" >&2
		exit 1
	fi

	if [ "$has_os" = 1 ]; then
		# The payloads are the shared build images: grow the rootfs to
		# this slot's volume and restore both slots' own identities,
		# exactly as the image build does after writing a slot. The file
		# systems were just written from clean mke2fs images, so tune2fs
		# can rewrite the metadata checksums without an fsck first.
		# resize2fs prints its version banner to stderr, which swupdate
		# surfaces as an ERROR line even on success: keep it quiet unless
		# the resize actually fails.
		out=$(resize2fs "$inactive_root" 2>&1) || { echo "$out" >&2; exit 1; }
		tune2fs -L "ROOT_$inactive" -U "$inactive_uuid" "$inactive_root"

		# The slot's dm-init table, from the volume's real extents while
		# it is still active: the shared boot image carries no
		# dm-table.env (each boot partition describes only its own slot),
		# so the freshly written boot file system gets one generated here.
		# Reading the geometry from the device mapper rather than shipping
		# numbers keeps the table right even if this board's volumes were
		# ever moved or resized.
		dm=$(dmsetup table "$(echo "$vg" | sed 's/-/--/g')-rootfs.$inactive")
		dmlen=$(echo "$dm" | awk '{print $2}')
		dmoff=$(echo "$dm" | awk '{print $5}')
		# dm-table.env holds one linear target; a split volume cannot be described.
		echo "$dm" | awk 'END { exit !(NR == 1 && $3 == "linear") }' ||
			{ echo "rootfs.$inactive is not one linear segment" >&2; exit 1; }
		lvchange --devices "$pv" -an "$vg/rootfs.$inactive"

		# Finish the boot slot: mount the inactive partition (the one
		# place a running system may write), drop the slot's dm table in,
		# then restamp the FAT label and volume id, exactly as the image
		# build stamps a flashed slot.
		# Unmount on any failure below; a retry raw-writes this partition.
		bootmnt=$(mktemp -d)
		trap 'release_boot; rmdir "$bootmnt" 2>/dev/null' EXIT
		mount "$inactive_boot" "$bootmnt"
		printf 'dm_name=rootfs\ndm_flags=rw\ndmoff=%s\ndmlen=%s\n' \
			"$dmoff" "$dmlen" > "$bootmnt/dm-table.env"

		# The running slot's U-Boot environment is retained by default:
		# uboot.env is developer-writable state (saveenv targets the
		# active partition), and an update should not silently reset it.
		# To start the new slot from the image's pristine environment
		# instead, run swupdate with SWUPDATE_CLEAN_UBOOT_ENV=1 in its
		# environment (scripts inherit it), or touch
		# /tmp/swupdate.clean-uboot-env for a daemon-mode swupdate whose
		# environment cannot be set per run.
		clean_env=${SWUPDATE_CLEAN_UBOOT_ENV:-0}
		[ -f /tmp/swupdate.clean-uboot-env ] && clean_env=1
		if [ "$clean_env" != 1 ] && [ -f /boot/uboot.env ]; then
			cp /boot/uboot.env "$bootmnt/uboot.env"
			echo "Retained uboot.env from the running slot"
		fi

		# DDR training data is dropped by default: the values were
		# captured by the outgoing boot stack, and the new slot retrains
		# itself on its first cold boot. To carry them over and skip that
		# retraining, run swupdate with SWUPDATE_KEEP_DDR_TRAIN=1, or
		# touch /tmp/swupdate.keep-ddr-train for daemon mode.
		keep_ddr=${SWUPDATE_KEEP_DDR_TRAIN:-0}
		[ -f /tmp/swupdate.keep-ddr-train ] && keep_ddr=1
		if [ "$keep_ddr" = 1 ] && [ -f /boot/DDR_TRAI.BIN ]; then
			cp /boot/DDR_TRAI.BIN "$bootmnt/DDR_TRAI.BIN"
			echo "Retained DDR_TRAI.BIN from the running slot"
		fi

		umount "$bootmnt"
		rmdir "$bootmnt"
		trap - EXIT
		fatlabel "$inactive_boot" "BOOT_$inactive"
		fatlabel -i "$inactive_boot" "$inactive_boot_id"
	else
		# Firmware-only: no OS part in this bundle. Drop the inactive
		# rootfs volume preinst brought up for the (absent) image writes.
		lvchange --devices "$pv" -an "$vg/rootfs.$inactive"
	fi

	if [ "$has_fw" = 1 ]; then
		# Flash the shipped tRoot slot image to the inactive tRoot slot.
		# A pre-A/B tRoot rejects the command without erasing anything,
		# so the update fails here - before any activation - on firmware
		# that cannot take it. trootctl writes the slot tRoot itself is
		# NOT running, so require tRoot's notion of the running slot to
		# match the rootfs': they only diverge after manual slot surgery,
		# and flashing then would put the new firmware in the wrong slot.
		troot_slot=$(simaai-trootctl get-active-slot \
			| sed -n 's/.*running slot[[:space:]]*:\{0,1\}[[:space:]]*\([AaBb]\).*/\1/p' \
			| head -n1 | tr 'ab' 'AB')

		if [ -z "$troot_slot" ]; then
			echo "could not determine tRoot running slot" >&2
			exit 1
		fi

		if [ "$troot_slot" != "$active" ]; then
			echo "tRoot runs slot $troot_slot but the rootfs is slot" \
				"$active; refusing to flash tRoot out of step" >&2
			exit 1
		fi
		simaai-trootctl upgrade $BOOT0
		rm -f $BOOT0
	fi

	rm -f $ROOTPART $BOOTPART $OSMARK

	# The rootfs overlay is retained by default: its writable layer is
	# the operator's local state, and an update should not silently
	# reset it (preinst lists what it holds). To hand the new slot a
	# pristine overlay instead, run swupdate with
	# SWUPDATE_CLEAN_OVERLAY=1 in its environment, or touch
	# /tmp/swupdate.clean-overlay for a daemon-mode swupdate whose
	# environment cannot be set per run.
	#
	# This is the one deliberate exception to the update's atomicity:
	# the overlay upper lives on the data volume, shared
	# by both slots and outside the A/B transaction, so no rollback can
	# undo the clean -- a development-platform knob, never the
	# production path. Rename first, delete after: each rename is
	# atomic, so a power cut at any instant leaves the next boot
	# composing a fresh, empty overlay (overlay-init recreates the
	# directories, and the kernel clears a stale workdir on mount); an
	# interrupted delete only strands a .discarded directory, removed
	# by the next clean. The running system keeps its overlay mount --
	# it pins the renamed directories -- and is one reboot from
	# retirement anyway. Runs before switch-slot so a clean cut short
	# leaves the update unactivated rather than half-honored.
	clean_overlay=${SWUPDATE_CLEAN_OVERLAY:-0}
	[ -f /tmp/swupdate.clean-overlay ] && clean_overlay=1
	if [ "$clean_overlay" = 1 ] && [ -d /data/overlay ]; then
		rm -rf /data/overlay/upper.discarded /data/overlay/work.discarded
		[ -d /data/overlay/upper ] &&
			mv /data/overlay/upper /data/overlay/upper.discarded
		[ -d /data/overlay/work ] &&
			mv /data/overlay/work /data/overlay/work.discarded
		rm -rf /data/overlay/upper.discarded /data/overlay/work.discarded
		echo "Overlay cleaned: the new slot starts from pristine state"
	fi

	# Everything is in place: activate the updated slot. tRoot owns slot
	# selection for the whole chain (its own firmware slot, the boot
	# partition it hands U-Boot, and thereby the rootfs). switch-slot
	# also sets upgrade_available, arming the watchdog rollback until a
	# healthy boot confirms with boot-good.
	simaai-trootctl switch-slot "$(echo "$inactive" | tr 'AB' 'ab')"
	echo "Slot $inactive activated; reboot to apply"

	# The update leaves the reboot to the caller by default: a bundle can
	# be installed now and the switch taken in a maintenance window, and a
	# scripted caller stays in control. To reboot automatically once the
	# update is committed, run swupdate with SWUPDATE_AUTO_REBOOT=1 in its
	# environment, or touch /tmp/swupdate.auto-reboot for a daemon-mode
	# swupdate whose environment cannot be set per run (sima-cli's --reboot
	# sets it).
	#
	# The reboot is DETACHED into a unit of its own: rebooting inline here
	# would take the board down mid-postinst, before swupdate reports the
	# result to whoever asked for the update. What that unit waits for is
	# swupdate exiting, not a fixed delay -- swupdate unlinks its control
	# socket as the very last thing it does, so the socket going away is
	# the moment the caller has its exit status, and the reboot follows a
	# tenth of a second later.
	#
	# It is a transient *service*, started at once, and not the transient
	# timer this used to arm: systemd-run gives a timer AccuracySec=1min,
	# so a nominal 5s delay was free to land anywhere in the minute after
	# it (~14s in practice) -- an unexplained pause with the prompt already
	# back, which reads as if the update had finished and left the board
	# alone.
	auto_reboot=${SWUPDATE_AUTO_REBOOT:-0}
	[ -f /tmp/swupdate.auto-reboot ] && auto_reboot=1
	if [ "$auto_reboot" = 1 ]; then
		# Resolve the socket here, while swupdate still holds it, and
		# hand the helper nothing if it is not where swupdate's default
		# puts it -- watching a path that is already gone would reboot
		# immediately, which is the one thing detaching is meant to
		# avoid. That case keeps a short fixed wait instead.
		ctrl=${TMPDIR:-/tmp}/sockinstctrl
		[ -S "$ctrl" ] || ctrl=

		helper=/tmp/swupdate-auto-reboot.sh
		cat > "$helper" <<-EOF
			#!/bin/sh
			# Written by update_modalix.sh postinst.
			ctrl='$ctrl'
			n=0
			if [ -n "\$ctrl" ]; then
				# Capped: swupdate is expected to be gone in
				# milliseconds, but a wedged one must not keep
				# an activated slot waiting for its reboot.
				while [ -e "\$ctrl" ] && [ "\$n" -lt 300 ]; do
					sleep 0.1
					n=\$((n + 1))
				done
			else
				sleep 2
			fi
			exec systemctl reboot
		EOF

		# Through the interpreter, not as an executable: /tmp is the
		# one directory this script can be sure of writing to, and it
		# is also the one a hardened board is most likely to mount
		# noexec -- which would leave the update finished and the board
		# never rebooting.
		echo "SWUPDATE_AUTO_REBOOT set; rebooting as soon as swupdate exits"
		if ! systemd-run --collect --quiet --unit=swupdate-auto-reboot \
			--description="Reboot after a completed SWUpdate" \
			/bin/sh "$helper"; then
			# No systemd-run, or no system bus to reach it on. Run
			# the same helper detached from this script instead, and
			# say so: swupdate's stderr carries systemd-run's reason
			# just above, and a board that lands here is one to look
			# at, not one to leave quietly unrebooted.
			echo "systemd-run could not arm the reboot;" \
			     "falling back to a detached helper" >&2
			/bin/sh "$helper" >/dev/null 2>&1 &
		fi
	fi
	;;

postfailure)
	# Undo what preinst left behind, so a retry starts from the board
	# state the first attempt found rather than inheriting an activated
	# target volume and stale symlinks.
	#
	# Best effort throughout: this runs because something has already
	# gone wrong, and the one thing worse than an incomplete cleanup is
	# a cleanup that fails and buries the error that caused it. A board
	# whose slots cannot be resolved has nothing this script activated,
	# so the volume step is simply skipped there.
	if resolve_slots; then
		# A killed postinst never ran its own cleanup of the boot mount.
		release_boot
		# An interrupted install leaves the target slot half-written yet
		# deceptively healthy-looking: the image's ext4 head lands first,
		# so the slot mounts and even reports the new build's version
		# while its tail is still whatever was there before - and a user
		# who trusts that and switches to it gets a board that hangs in
		# boot. A completed install is stamped with the
		# slot's fixed UUID at the very end of postinst, so a different
		# UUID proves this failure struck after image writes began: wipe
		# the first MiB so the slot reads as what it is - empty,
		# unmountable, nothing to switch to - instead of an invitation.
		# No UUID at all means the volume was never written (or not
		# activated); an intact fallback keeps its stamp and is left
		# untouched.
		got=$(blkid -s UUID -o value "$inactive_root" 2>/dev/null) || got=
		if [ -n "$got" ] && [ "$got" != "$inactive_uuid" ]; then
			echo "wiping half-written $inactive_root: its UUID" \
			     "'$got' is not the slot's '$inactive_uuid'," \
			     "so the interrupted install had already begun" \
			     "overwriting it" >&2
			dd if=/dev/zero of="$inactive_root" bs=1M count=1 \
				conv=fsync 2>/dev/null || true
		fi
		lvchange --devices "$pv" -an "$vg/rootfs.$inactive" 2>/dev/null ||
			echo "Note: $vg/rootfs.$inactive is still active" >&2
	fi
	rm -f $ROOTPART $BOOTPART $OSMARK $BOOT0
	;;
esac

echo "== Finish $1 =="
