# Customer guide

How to build, sign and ship your own image and update bundle (`.swu`) with PIB.
The command reference and the `image.yaml` options are in the [README](../README.md);
this guide covers what you need to know around them.

## Prerequisites

- A Linux host with Docker that allows privileged containers. The build uses loop
  devices, LVM and, on an x86-64 host, an arm64 binfmt handler (qemu-user-static installed on the host).
- Network access to the Debian, eLxr and SiMa.ai package repositories, or your own
  mirrors named in `sources` and `sima_source`. There is no offline mode.
- Time and space: a minimal image build took about 25 minutes and left 3.5 GB in
  `out/` (the raw image is a 4 GB sparse file). The rootfs tree (up to 1.5 GB for
  minimal and 5.6 GB for palette, the slot sizes) is built inside the container, so
  Docker's storage location
  needs that space too. Keep 10 GB free for minimal and 20 GB for palette.
- To build the container yourself: a PIB checkout (it carries the pasha wheel SiMa.ai
  packs for the release) and access to gitlab.com. The image configs ship in
  it and in the container.

## Workflow

Create a workspace, make keys, sign your debs, edit `image.yaml`, then `pib build`,
`pib sign`, `pib verify` and install. The steps are in the README. Two properties
matter for how you organise it:

- `pib build` never needs your signing key. It builds with a throwaway key and removes
  that signature, so the build host can be an ordinary CI machine.
- `pib sign` needs only the unsigned `.swu` and your key (a PEM file or an HSM/token via
  PKCS#11), so signing can run on a separate, locked-down host.

## Keys and who holds them

| File | What it is | Keep it |
|---|---|---|
| `keys/ca.key` | Your CA private key | Offline; only needed to issue a new signing leaf |
| `keys/ca.crt` | Your CA certificate | Public. Installed in every image as `/etc/swupdate/swupdate.crt` |
| `keys/swu-signing.key`, `.crt` | The leaf that signs bundles | On the signing host only |
| `keys/debs-signing.secret.asc`, `.asc` | gpg key for custom `.deb` files | Secret key on the build side; the public key is checked at build time |

`pib keys init` writes the private keys without a passphrase, mode 600: only file
permissions and where you keep them protect them. Keep the signing key in an HSM or token
(`pib sign --pkcs11`) if the signing host is shared. The CA is valid for 10 years and the
signing leaf for 825 days; renew the leaf (below) before it expires.

A board trusts what is in `/etc/swupdate/swupdate.crt`. You can rotate the signing leaf
without touching boards, as long as the new leaf is issued by the same CA: put `ca.key`
back in `keys/`, run `pib keys renew`, and move `ca.key` offline again. Changing the
CA means shipping a bundle signed under the old CA whose image carries the new
`ca.crt`: build with `signing.ca` pointing at the new CA, then set `signing.ca` back
to the old CA before `pib sign`, which checks the leaf against it (or name the
bundle and sign with `--key`/`--cert` from a directory holding neither `image.yaml`
nor `keys/ca.crt`).

## Encrypted bundles

`pib sign --encrypt` encrypts the rootfs and boot payloads of a bundle with AES-256-CBC,
each with its own IV recorded in the signed `sw-description`. `boot0.be`, the SBOM and the update
script stay in the clear. To use it:

1. `pib keys payload` writes `keys/payload.key` (the key and a default IV, in the
   format `swupdate -K` reads).
2. Set `encryption: {key: keys/payload.key}` in `image.yaml` and build. The image then
   holds the key as `/etc/swupdate/aes.key`, readable by root only, and
   `/etc/swupdate.cfg` names it.
3. `pib sign --encrypt` (or `--aes-key <file>` on a signing host without `image.yaml`).

A board installs an encrypted bundle only if its running image already holds the key.
For the first one, install an unencrypted bundle of an image built with
`encryption.key`, or pass the key by hand: `swupdate -i <bundle> -K payload.key ...`.

This keeps the image contents confidential in transit and on update servers. It does
not protect against anyone who can read a board's root filesystem, because the key is
stored there. The `.img` and `.img.gz` files in `out/` are never encrypted and contain
the key.

## Moving a board to your keys

A board running a SiMa.ai image does not trust your CA yet. Install your first bundle
with the CA given explicitly:

```bash
swupdate -i your.swu -k ca.crt -e update,full
```

That image carries `ca.crt` and `/etc/swupdate.cfg`, so every later update needs no
`-k`: `simaai-update your-next.swu -e update,full` (or plain `swupdate -i`, which reads
`/etc/swupdate.cfg` by default).

**Root caveat.** `-k` stays available: anyone with root on the board can install any
bundle that verifies against a CA they supply. Signatures protect delivery, not the
board against its own root user.

## Version rule

The version is `<SiMa.ai release>.<your build>`, all numeric: `3.0.0.4`. Your build is
1 to 65535. Each image refuses to install a bundle older than itself (its
`no-downgrading` setting is its own version), and an equal version installs.

It must be numeric because the board's `swupdate` compares versions as semantic versions
only when they are digits and dots; `3.0.0-pib.1` sorts as older than `3.0.0`, so a
board running `3.0.0` would refuse it. `pib build` rejects anything else.

## Installing and rollback

`swupdate -e update,full` writes tRoot, the boot partition and the rootfs into the
inactive slot, switches the next-boot slot and arms the watchdog. It does not reboot.
After a reboot a healthy boot confirms the new slot. A slot that does not come up is
rolled back to the other slot by the watchdog, and the board reports "rolled back".
In testing, a slot whose root filesystem was destroyed and a slot whose kernel image
(`fitImage`) was damaged so that U-Boot could not boot it both fell back to the other
slot after about six to seven minutes. The failed slot is then retired: a full update
(`update,full`, which rewrites the slot's tRoot) re-arms it, and an `update,os` into it
fails at the slot switch.

`update,os` and `update,firmware` install only part of that and are for development.

The board's writable overlay survives updates by default, and files in it shadow the new
image. `SWUPDATE_CLEAN_OVERLAY=1` gives the new slot a pristine overlay and deletes
local changes under `/data/overlay`; it cannot be rolled back.

## tRoot (boot firmware)

Bundles carry SiMa.ai's `boot0.be` from the release's `troot-*` package. tRoot
is SiMa.ai's and cannot be replaced through PIB. The build refuses a `troot-*` package
in `custom-debs/`, checks that the package came from SiMa.ai's repository (unless you
use your own mirror), and fails with `md5 check failed for boot0.be` unless the bundle's
file has the md5 SiMa.ai lists for `boot/Release/boot0.be` in the release tRoot package
the image installs (`troot-modalix`, or `troot-modalix-secure` for `securepalette`).
The check downloads that package and needs network access.
A board does not refuse a bad `boot0.be` before the slot switch, and a tRoot slot that never
starts is not rolled back: a corrupted tRoot image in the inactive slot leaves the board
unable to boot.

## Boot chain you supply

You can replace the kernel with your own `.deb` file in `custom-debs/`.
ATF and tRoot hold the root of trust and come from SiMa.ai: the build refuses an
`atf-*` or `troot-*` package in `custom-debs/`. It also refuses `u-boot-modalix`:
the board boots the U-Boot inside `/boot/fip.bin`, which the ATF package carries and
PIB does not rebuild.
Keep SiMa.ai's kernel package name (`linux-image-6.18.3-modalix`) with a higher version. The flavor's package list installs
`linux-image-6.18.3-modalix*`, so a kernel with another name is either not installed
or (if it matches that pattern or is listed in `packages.add`) a second one.
The image must end up with exactly one kernel, U-Boot and ATF package, with `/boot/fip.bin`, `/boot/u-boot.bin`
and `/boot/fitImage` present and a single `lib/linux-image-*` directory. Your debs are
pinned so `apt upgrade` on a board leaves them alone.

PIB does not sign kernels: signing belongs to the package build. On
`securepalette`, where U-Boot enforces the kernel FIT signature, the build checks that
the image's `fitImage` verifies against the keys its U-Boot requires, and fails
instead of producing a bundle that will not boot. SiMa.ai's release packages are
signed with a development key named `dev`; a `securepalette` build that still trusts
it is refused unless you pass `--dev`, and a `--dev` bundle cannot be signed for shipping.
A shippable `securepalette` needs packages signed with a production key. Fused boards have
not been tested.

## What the image does with SWUpdate

The image's `swupdate.service` and `swupdate.socket` are masked, so there is no daemon:
updates run one-shot from the command line (the masking is done by the SiMa.ai image
hook `base.sh`). Updates arrive over `scp` and `simaai-update`, or your own tooling.

## Host side effects

Building changes things on the host outside the workspace:

- `binfmt_misc`: the container does not register anything. On an x86-64 host the arm64
  handler (qemu-user-static) must already be installed and enabled, or the container
  stops at start.
- Loop devices and LVM: the build attaches the image to a loop device and creates a
  volume group. An interrupted build can leave both behind; `pib clean` lists them and
  `pib clean --yes` removes them. It matches every `elxr-*-<target>-*.img` loop device on the
  host, not only this workspace's: do not run it while any build on the host is running.
- The container is started `--privileged` with the host's `/dev` mounted.

## Defaults you should change before shipping

The repository holds no password. Without `PIB_CREDENTIALS`, `root` and `sima` are locked
in the image. With it, their passwords come from that file: one `root:<hash>` and one
`sima:<hash>` line, hashes made with `openssl passwd -6`; a plain-text password is refused.
Keep the file outside the workspace.

`root` cannot log in over SSH with a password (`PermitRootLogin prohibit-password`); add
your public key in `overlay/root/.ssh/authorized_keys` (`chmod 700` the `.ssh` directory and
`600` the file: sshd ignores a key file others can write), or log in as `sima` and use
`sudo`. The image holds no SSH host keys: `simaai-ssh-hostkeys.service` makes them on
first boot, before `ssh.service`, so each board has its own. On a board that boots
without the rootfs overlay they are made again after every update, because the new
rootfs holds none. With the overlay they live in it and survive updates, but
`SWUPDATE_CLEAN_OVERLAY=1` discards them: the board makes new ones, and every SSH client
that knew the old ones warns that the host key changed.

A board whose passwords were changed on the board keeps them through an update: the
changed `/etc/shadow` lives in the rootfs overlay. The image's accounts, locked or from
`PIB_CREDENTIALS`, reach a freshly flashed board, a board whose passwords were never
changed, and any board after `SWUPDATE_CLEAN_OVERLAY=1`; without `PIB_CREDENTIALS`
such a board needs an SSH key in `overlay/`.

The update script (`configs/images/files/update_modalix.sh`) has four known limitations
in release 3.0.0:

- It reads its control files (`swupdate.clean-overlay`, `swupdate.auto-reboot`,
  `swupdate.clean-uboot-env`, `swupdate.keep-ddr-train`) from world-writable `/tmp`, and
  writes `/tmp/swupdate-auto-reboot.sh`, so any local account can set them. Do not give
  untrusted users or services a login on the board.
- `SWUPDATE_CLEAN_OVERLAY=1` deletes the overlay's upper and work directories while the
  running system still has them mounted. Reboot soon after such an update.
- A bundle that holds only firmware (no rootfs or boot partition) still switches to the
  other slot, pairing the new firmware with whatever that slot already holds. Ship full
  bundles.
- If an install fails part-way, `postfailure` does not invalidate the half-written boot
  partition of the target slot. Do not switch to that slot by hand; reinstall first.
