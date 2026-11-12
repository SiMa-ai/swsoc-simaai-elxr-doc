#!/bin/bash
#
# Copyright (c) 2026 SiMa.ai Technologies, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# Customer Image Builder container entrypoint.
#
# For "cib build" and a shell, prepares what "rs build" expects from its
# surroundings, then runs the given command (bash when none); other cib commands run directly:
#   - a check for the host's arm64 binfmt handler, so mmdebstrap can run arm64 maintainer
#     scripts under qemu-user-static on an x86-64 host
#   - a local apt repo at http://localhost/deb/custom holding every .deb in
#     /workspace/custom-debs, signed with a key made for this run alone; the
#     image's apt pinning ranks it above SiMa.ai's repo, so a customer
#     kernel or U-Boot replaces SiMa.ai's
#
# Inputs (environment):
#   CIB_CODENAME     - suite the repo publishes (set by the Dockerfile)
#   SWU_SIGNING_KEY,
#   SWU_SIGNING_CERT - used by "cib sign" only; "cib build" never needs them
set -eo pipefail

# Other cib commands need none of the set-up below.
case "${1:-} ${2:-}" in
    "cib build" | bash*) ;;
    cib\ *) exec "$@" ;;
esac

DEBS=/workspace/custom-debs
REPO_DIR=/var/www/html/deb/custom
KEY_UID="CIB local repo <cib-local-repo@localhost>"

# --- arm64 emulation ----------------------------------------------------------
# The host must provide the arm64 binfmt handler; mounting binfmt_misc only shows the host's entries.
if [ ! -e /proc/sys/fs/binfmt_misc/register ]; then
    mount -t binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc 2>/dev/null || true
fi
if [ "$(uname -m)" != "aarch64" ]; then
    case "$(head -n1 /proc/sys/fs/binfmt_misc/qemu-aarch64 2>/dev/null)" in
        enabled) ;;
        disabled) echo "cib: the host's qemu-aarch64 binfmt handler is disabled;" \
                       "enable it on the host" >&2; exit 1 ;;
        *) echo "cib: no arm64 binfmt handler; install qemu-user-static on the host" >&2; exit 1 ;;
    esac
fi
# Without the F flag the interpreter must exist at its registered path inside
# the container (and any chroot); with it, the kernel already holds it open.
if [ "$(uname -m)" != "aarch64" ]; then
    entry=/proc/sys/fs/binfmt_misc/qemu-aarch64
    interp="$(sed -n 's/^interpreter //p' "$entry")"
    case "$(sed -n 's/^flags: //p' "$entry")" in
        *F*) ;;
        *) [ -x "$interp" ] || { echo "cib: the host's arm64 binfmt handler" \
               "has no F flag and $interp is not in the container;" \
               "re-register it with the F flag (qemu-user-static)" >&2; exit 1; } ;;
    esac
fi

# --- local repo signing key ---------------------------------------------------
# Made fresh for each container run in a temporary directory: the repo below
# is rebuilt on every start, so nothing needs the key afterwards, and no
# private key reaches the workspace or an image layer.
GNUPGHOME="$(mktemp -d)"
export GNUPGHOME
gpg --batch --passphrase '' --quick-gen-key "$KEY_UID" rsa3072 sign never 2>/dev/null || {
    echo "cib: cannot create the local repo signing key" >&2; exit 1; }
gpg --batch --export "$KEY_UID" > /usr/share/keyrings/custom-repo.gpg

# --- local repo contents ------------------------------------------------------
# Rebuilt from $DEBS on every start, so the repo holds exactly what the
# directory holds now. An empty repo is still exported: the image configs
# always list it.
rm -rf "$REPO_DIR/db" "$REPO_DIR/dists" "$REPO_DIR/pool"
reprepro -b "$REPO_DIR" export "$CIB_CODENAME"
shopt -s nullglob
# With a workspace image.yaml, only .debs signed by the customer's key
# (debs.key) may enter the local repo. cib build checks them itself; a shell does not.
if [ -f image.yaml ] && [ -n "$(echo "$DEBS"/*.deb)" ] && [ "${1:-}" != cib ]; then
    cib verify-debs
fi
for deb in "$DEBS"/*.deb; do
    arch="$(dpkg-deb -f "$deb" Architecture)"
    case "$arch" in
        arm64|all) ;;
        *) echo "cib: $deb is for $arch, not arm64" >&2; exit 1 ;;
    esac
    echo "cib: adding $(dpkg-deb -f "$deb" Package) $(dpkg-deb -f "$deb" Version)"
    # reprepro refuses a .deb without Section/Priority; default only those.
    defaults=()
    [ -n "$(dpkg-deb -f "$deb" Section)" ] || defaults+=(-S misc)
    [ -n "$(dpkg-deb -f "$deb" Priority)" ] || defaults+=(-P optional)
    reprepro -b "$REPO_DIR" -C non-free "${defaults[@]}" includedeb "$CIB_CODENAME" "$deb"
done
shopt -u nullglob
# The signing key is not needed past this point: stop the agent and drop the key.
gpgconf --kill all 2>/dev/null || true
rm -rf "$GNUPGHOME"
unset GNUPGHOME

if ! pgrep -x nginx >/dev/null 2>&1; then
    nginx
fi

exec "$@"
