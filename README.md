# SiMa.ai Customer Image Builder (CIB)

CIB builds a customer's own eLxr image and update bundle (`.swu`) for SiMa.ai
Modalix boards. It runs in a container and wraps `rs build` (rucksack). The
customer adds packages, an overlay and hooks, signs
the bundle with their own key, and boards only accept bundles signed under the
customer's CA.

This repository holds the container build context and the `cib` command, next to the
SiMa.ai SDK manual:

| Path | What it is |
|---|---|
| `Dockerfile.cib`, `entrypoint.sh`, `files/` | The container (eLxr base, rucksack, a local signed apt repo for `custom-debs/`) |
| `dist/` | Wheels the Dockerfile installs, the SiMa.ai pasha wheel included (packed and checked in for each release) |
| `cib/` | The `cib` Python package and its `pyproject.toml` |
| `host/cib` | Host shim: runs the container with the current directory as the workspace |
| `configs/images/` | Image configs for each flavor (`image-{minimal,palette,securepalette}-modalix.yaml`), with the stage list, params, hooks, overlay and SWU files they use |
| `scripts/` | The two build helper scripts the stages call |
| `UPSTREAM` | What the configs were taken from (the SiMa.ai 3.0.0 image configs, the eLxr config tool commit) and how they differ |

Only the `minimal` flavor has been built end to end. Not implemented:
payload encryption, `cib mirror`, `--offline`, `--from` (an offline build will need another
way to check the `boot0.be` md5). Secure-boot flavors and
fused boards have not been tested; for `securepalette` the kernel FIT signature is
not checked against the key in the image's U-Boot.

The base image is pinned by digest and the debsbom wheels are checked against hashes;
the pasha wheel in `dist/` and the `cib` package are installed without a hash check. The eLxr apt packages (rucksack, mmdebstrap, qemu) are whatever the eLxr
mirror serves when the image is built.

More detail: [customer guide](docs/customer-guide.md) (keys, moving a board to your
keys, version rule, rollback, host side effects) and
[identifying an image](docs/support-identification.md).

## Get the image

`host/cib` runs the container image `sima-image-builder:<release>`. Use the image SiMa.ai
provides for the release (set `CIB_IMAGE` to its full name if it is not tagged that way
locally), or build it. Building it needs `dist/pasha-<release>-py3-none-any.whl`, which
SiMa.ai packs and checks in for each release; the Dockerfile stops with that message
when the wheel is missing.

```bash
docker build -f Dockerfile.cib -t sima-image-builder:3.0.0 .
```

The Dockerfile needs BuildKit, the default builder since Docker Engine 23.0 when the
buildx plugin is installed. On older engines, set `DOCKER_BUILDKIT=1`.

The build also downloads `elxr-config` (eLxr manifests and overlay) from GitLab at
a pinned commit and checks its sha256, so it needs access to gitlab.com.

Put `host/cib` on your `PATH`. It needs Docker, runs the container with
`--privileged -v /dev:/dev` (loop devices, LVM) and mounts the current
directory at `/workspace`. `CIB_IMAGE` or `SIMA_RELEASE` choose another image tag.
`SWU_SIGNING_KEY` (a file or a `pkcs11:` URI) and `SWU_SIGNING_CERT` (a PEM file)
are passed to `cib sign`; `CIB_CREDENTIALS` (an optional file) is used by `cib build`. Each file is
mounted alone, read-only.

## Workflow

1. **Create a workspace** in any folder. The image configs ship in the container,
   and the workspace gets a copy of `configs/` and the files the hooks use:

   ```bash
   cib init my-image --flavor minimal --release 3.0.0
   cd my-image
   ```

   `cib init` also writes a `.gitignore` for `keys/*.key`, `keys/*.secret.asc`, `out/` and
   `build/`, so a workspace kept in git does not commit secrets or build output.

   To use another set of configs, export `CIB_CONFIGS=<dir>/configs`: the host shim
   mounts that directory's parent read-only (`--configs` works for a directory inside
   the workspace).

2. **Create keys** (`keys/`): a customer CA, a CA-issued SWU signing leaf, and a
   gpg key for custom debs. Keep `ca.key` offline.

   ```bash
   cib keys init
   ```

3. **Add custom packages** to `custom-debs/` and sign each one. `cib build` accepts
   only debs signed by the key in `debs.key`:

   ```bash
   cib sign-deb custom-debs/u-boot-modalix_2.2.0_arm64.deb
   ```

   This writes `<deb>.sig`. `cib verify-debs` re-checks them.

4. **Edit `image.yaml`** (see below), then **build**:

   ```bash
   export CIB_CREDENTIALS=$HOME/cib-credentials   # optional: root:<hash> and sima:<hash> lines
   cib build            # out/<image>.unsigned.swu, .img, .img.gz, -boot0.be, .cdx.json, .manifest.json, SHA256SUMS
   ```

   `CIB_CREDENTIALS` is optional: a file outside the workspace with the image's `root`
   and `sima` passwords as crypt hashes, one `user:hash` line each (make a hash with
   `openssl passwd -6`); plain-text passwords are refused. Without it both accounts are
   locked in the image: boards with a rootfs overlay keep their own passwords, and a
   freshly flashed board needs an SSH key in `overlay/`. The repository holds no password.
   The host shim mounts the file read-only, and only its path reaches the build's commands.

   `cib build` never needs the customer signing key: the bundle is built with a
   throwaway key which is then removed with its signature. `cib build --dev`
   builds a throwaway-signed bundle that no board will trust (version gets `-dev`).
   A rebuild with the same `version` replaces, and a failed one removes, every
   `out/` file of that version, a signed `.swu` included; bump `version` to keep them.
   The `palette` and `securepalette` flavors also write `simaai-image-palette.manifest`,
   `simaai-image-palette.licenses` and `du.txt` into `out/`; a failed build leaves those.

5. **Sign and verify**:

   ```bash
   cib sign             # out/<image>.swu, signed with signing.key / signing.cert
   cib verify --ca keys/ca.crt --manifest out/<image>.manifest.json out/<image>.swu
   ```

   `cib sign --pkcs11 <uri> --cert keys/swu-signing.crt` signs with a key held
   in an HSM or token through the OpenSSL PKCS#11 engine (tested with a SoftHSM
   module added to the container). The host shim mounts no token: run the container
   directly with the token's device or `pcscd` socket mounted, and set
   `PKCS11_MODULE_PATH` if the engine does not find the module. Signing can run
   on any host that only has the bundle.

6. **Other commands**: `cib diff --against <sbom-or-manifest>` lists package
   differences; `cib clean [--yes]` lists (or with `--yes` detaches) loop devices
   and volume groups left by an interrupted build. It matches every `elxr-*-<target>-*.img`
   loop device on the host, other workspaces' builds included.

## `image.yaml`

`cib init` writes the first eight rows; the rest are optional.

| Key | Meaning |
|---|---|
| `base`, `target`, `release` | Flavor (`minimal`, `palette`, `securepalette`), platform, SiMa.ai release. `release` must match the container's release. |
| `version` | `<release>.<build>`, all numeric, build 1..65535 (for example `3.0.0.4`). Boards refuse older versions. |
| `slots` | `ab` (default: `rootfs.A` and `rootfs.B`) or `a` (single slot). |
| `packages.add`, `packages.remove` | Packages added to or removed from the flavor's list. |
| `overlay` | A directory inside the workspace, copied over `/` after SiMa.ai's overlays with every file owned by root. |
| `hooks` | A list of script files in the workspace, run in order after SiMa.ai's customize hooks (paths: letters, digits and `_ . / + -` only). |
| `signing.cert`, `signing.key`, `signing.ca` | Bundle signing leaf and key; `ca` is installed in the image as `/etc/swupdate/swupdate.crt`. |
| `debs.key` | Public key that `custom-debs/*.deb` signatures must come from. |
| `vendor` | One line written to `/etc/buildinfo` as `VENDOR = ...`. |
| `swu.description`, `swu.script` | Your own `sw-description` and update script. The description must contain `@@VERSION@@`, `@@HW_COMPAT@@`, `@@<member>@@` for every hash, and install `boot0.be`. |
| `sources` | List of apt lines replacing the Debian and eLxr ones (for a mirror). |
| `sima_source` | One apt line replacing the SiMa.ai repository line. Keep `signed-by=/usr/share/keyrings/simaai-public.gpg`: it is the only keyring the image carries for it. Apt pins still match `repo.sima.ai`. |

## What the build checks and produces

- `custom-debs/` must be arm64 or all, signed by `debs.key`, hold no `troot-*`
  or `atf-*` package (tRoot and ATF are SiMa.ai's) and no second kernel or U-Boot. The image must end up with exactly one
  kernel, one U-Boot and one ATF package.
- `boot0.be` in the bundle must have the md5 listed for `boot/Release/boot0.be` in the
  `md5sums` of the tRoot package the image installs (`troot-modalix`, or
  `troot-modalix-secure` for `securepalette`; downloaded from the SiMa.ai release apt line,
  which is the `sima_source` line when you set one), or the build fails with `md5 check failed for boot0.be`. This needs network
  access to that repo.
- Custom debs are pinned (priority 1001) so `apt upgrade` leaves them alone.
- The image carries `/etc/swupdate.cfg` (`public-key-file` and
  `no-downgrading = "<version>"`) and `/usr/bin/simaai-update`, which installs a
  bundle using that config.
- `<image>.manifest.json` lists every installed package with its origin
  (`customer`, `sima`, `elxr`, `debian`, or the mirror host), the version, and
  the `boot0.be` source and sha256.
- The apt lists come from `sources`, `sima_source` and the SiMa.ai release repo;
  the build-only local repo on `localhost` is removed from the shipped image.

## Install on a board

`root` can log in over SSH with a key only (`PermitRootLogin prohibit-password`): put your
public key in `overlay/root/.ssh/authorized_keys` (`chmod 700` the `.ssh` directory and `600` the
file: sshd ignores a key file others can write), or log in as `sima` and use `sudo`.

The first install onto a board that does not yet trust your CA needs the CA file:

```bash
scp out/<image>.swu keys/ca.crt root@<board>:/tmp/
ssh root@<board> swupdate -i /tmp/<image>.swu -k /tmp/ca.crt -e update,full
ssh root@<board> reboot
```

After that the image trusts the CA itself:

```bash
ssh root@<board> simaai-update /tmp/<image>.swu -e update,full
```

`-e update,full` installs tRoot, boot and rootfs into the inactive slot, flips the
slot and arms the watchdog rollback; reboot to apply. A slot that fails to boot is
rolled back to the other slot. By default the board's writable overlay is kept; set
`SWUPDATE_CLEAN_OVERLAY=1` to give the new slot a pristine one (this deletes local
changes under `/data/overlay`).
