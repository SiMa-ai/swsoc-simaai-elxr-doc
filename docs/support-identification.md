# Identifying a PIB image

What support can tell about an image from a board, and what needs the build outputs.

## From the board

| Question | Where to look |
|---|---|
| Which SiMa.ai release is it based on? | `DISTRO_VERSION` in `/etc/buildinfo`: the first three fields of `<release>.<build>` |
| Which customer build is it? | The fourth field of `DISTRO_VERSION` (1 to 65535) |
| Who built it? | `VENDOR = ...` in `/etc/buildinfo` (set by `vendor` in `image.yaml`; absent if not set). Also the subject of `/etc/swupdate/swupdate.crt`, the customer CA the board trusts (`CN=<cn> SWU CA`, from `pib keys init --cn`; `Customer` if none was given) |
| Is it a PIB image? | `/etc/swupdate.cfg` and `/usr/bin/simaai-update` exist; `/etc/apt/preferences.d/99pib-custom` lists the packages the customer supplied (the file exists only when the build used `custom-debs/`) |
| Is it a development (`--dev`) build? | `no-downgrading` in `/etc/swupdate.cfg` ends in `-dev`, and `/etc/swupdate/swupdate.crt` has the subject `CN=PIB dev SWU CA`. Such a board trusts a throwaway key: do not ship it |
| Which slot is running and was there a rollback? | `simaai-trootctl get-active-slot` (per-slot validity) and `simaai-trootctl rollback-status` (the rollback latch); `simaai-ab-info` prints both |
| Which downgrade floor does it enforce? | `no-downgrading` in `/etc/swupdate.cfg` (the image's own version) |
| Which packages, with licenses and source packages? | The CycloneDX SBOM in `/usr/share/doc/sbom/` (the same file as the build's `.cdx.json` and the bundle's `sbom.cdx.json`) |
| Which packages, and which did the customer supply? | `dpkg -l`; the pins in `99pib-custom`, when it exists, name the customer's packages and versions |

A SiMa.ai release image has a three-field version and no `VENDOR` line.

## From the build outputs

`<image>.manifest.json`, written next to the image by `pib build`, holds:

- `image`, `version`, `release`, `vendor` and the SBOM `supplier`;
- every installed package with its version and origin: `customer` (from `custom-debs/`),
  `sima`, `elxr`, `debian`, or the mirror's host name for a custom `sources` mirror;
- `boot0`: the tRoot source (the `troot-*` package, its version and origin) and the
  `boot0.be` sha256.

`pib verify --ca keys/ca.crt --manifest <manifest> <bundle>` checks that the bundle's
version and `boot0.be` are the ones the manifest describes. `pib diff --against
<manifest-or-sbom>` lists package
differences between two builds.

## Limits

- The tRoot source is **not** readable from a board: the manifest and the bundle record
  it, but nothing on the board does. Keep the manifest with each released build.
- The manifest is a build output; boards do not carry it. Match a board to a build by
  `DISTRO_VERSION` and `VENDOR`.
- PIB checks that the bundle's `boot0.be` has the md5 SiMa.ai lists in the release tRoot package the image installs. It does not check that the file suits a given variant or board.
