"""assert checks for cib.cli; run: python3 cib/test_cli.py (host, no container)."""
import os, re, subprocess, sys, tempfile, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cib.cli as c

def dies(fn, *a, **k):
    try:
        fn(*a, **k)
    except SystemExit as e:
        return str(e.code)
    raise AssertionError("did not die")

# built()/discard(): stem anchoring
with tempfile.TemporaryDirectory() as t:
    out = Path(t)
    names = ["elxr-minimal-modalix-3.0.0.1-agate-arm64-boot0.be",
             "elxr-minimal-modalix-3.0.0.1-agate-arm64.swu",
             "elxr-minimal-modalix-3.0.0.1-agate-arm64.img",
             "elxr-palette-modalix-3.0.0.1-agate-arm64-boot0.be",      # other flavor, same version
             "elxr-minimal-modalix-3.0.0.1-dev-agate-arm64-boot0.be",  # dev build
             "elxr-minimal-modalix-3.0.0.1-dev-agate-arm64.swu",
             "elxr-minimal-modalix-3.0.0.10-agate-arm64-boot0.be",     # longer build number
             "SHA256SUMS"]
    for n in names: (out / n).write_text("x")
    (out / "elxr-minimal-modalix-3.0.0.1-agate-arm64-dir").mkdir()
    stem = "elxr-minimal-modalix-3.0.0.1-"
    assert [p.name for p in c.built(out, stem, r"-boot0\.be")] == [names[0]]
    assert [p.name for p in c.built(out, stem, r"\.swu")] == [names[1]]
    assert [p.name for p in c.built(out, "elxr-minimal-modalix-3.0.0.1-dev-", r"\.swu")] == [names[5]]
    assert c.built(out, "elxr-minimal-modalix-9.9.9.9-", r"\.swu") == []
    (out / "elxr-minimal-modalix-3.0.0.1-agate-arm64.unsigned.swu").write_text("x")
    (out / "elxr-minimal-modalix-3.0.0.1-agate-arm64.img.gz").write_text("x")
    (out / "elxr-minimal-modalix-3.0.0.1-agate-arm64-boot.vfat").write_text("x")
    (out / "elxr-minimal-modalix-3.0.0.1-agate-arm64-boot.vfat.gz").write_text("x")
    assert [p.name for p in c.built(out, stem, r"\.swu")] == [names[1]], "unsigned.swu is not .swu"
    assert len(c.built(out, stem)) == 7, [p.name for p in c.built(out, stem)]
    c.write_sums(out)
    assert "boot.vfat" in (out / "SHA256SUMS").read_text()
    c.discard(out, stem)
    sums = (out / "SHA256SUMS").read_text()
    assert stem + "agate" not in sums and "elxr-palette-modalix-3.0.0.1-agate-arm64-boot0.be" in sums, sums
    left = sorted(p.name for p in out.iterdir())
    assert left == sorted([names[3], names[4], names[5], names[6], "SHA256SUMS",
                           "elxr-minimal-modalix-3.0.0.1-agate-arm64-dir"]), left
    c.discard(out, "nomatch-"); assert sorted(p.name for p in out.iterdir()) == left
    c.discard(out, "elxr-minimal-modalix-3.0.0.1-dev-")
    assert sorted(p.name for p in out.iterdir()) == sorted([names[3], names[6], "SHA256SUMS",
                           "elxr-minimal-modalix-3.0.0.1-agate-arm64-dir"])

# subj(): CN with / or \ refused, plain CN accepted
assert c.subj("Acme Ltd", "SWU CA") == "/CN=Acme Ltd SWU CA"
assert "must not contain" in dies(c.subj, "Acme/Products", "SWU CA")
assert "must not contain" in dies(c.subj, "Acme\\x", "SWU CA")
assert "must not contain" in dies(c.subj, "a+b", "SWU CA")
assert c.subj("", "SWU CA") == "/CN= SWU CA"

# load_config(): type message names text for str fields; version rule unchanged
with tempfile.TemporaryDirectory() as t:
    ws = Path(t)
    (ws / "image.yaml").write_text("base: 1\ntarget: modalix\nrelease: 3.0.0\nversion: 3.0.0.1\n")
    assert dies(c.load_config, ws) == "cib: image.yaml: base must be text"
    (ws / "image.yaml").write_text("base: minimal\ntarget: modalix\nrelease: 3.0.0\nversion: 3.0.0.1\nhooks: x\n")
    assert dies(c.load_config, ws) == "cib: image.yaml: hooks must be a list"
    (ws / "image.yaml").write_text("base: minimal\ntarget: modalix\nrelease: 3.0.0\nversion: 3.0.0.1\nslots: [a]\n")
    assert dies(c.load_config, ws) == "cib: image.yaml: slots must be text or a number"
    (ws / "image.yaml").write_text("base: minimal\ntarget: modalix\nrelease: 3.0.0\nversion: 3.0.0.1\ntroot: {boot0: b}\n")
    assert dies(c.load_config, ws) == "cib: image.yaml: unknown field troot", "troot override is gone"
    (ws / "image.yaml").write_text("base: minimal\ntarget: modalix\nrelease: 3.0.0\nversion: 3.0.0.1\n")
    os.environ.pop("SIMA_RELEASE", None)
    assert c.load_config(ws)["version"] == "3.0.0.1"

# cmd_init(): --release validated; --configs copies the named directory itself
import argparse
with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    cfgdir = t / "mycfgs"                      # not named "configs"
    (cfgdir / "images").mkdir(parents=True)
    (cfgdir / "images/image-minimal-modalix.yaml").write_text("version: 3.0.0\n")
    (cfgdir / "images/marker").write_text("mine")
    os.environ.pop("SIMA_RELEASE", None); os.environ.pop("CIB_UID", None); os.environ.pop("CIB_GID", None)
    a = argparse.Namespace(dir=str(t / "ws"), flavor="minimal", target="modalix",
                           release="3.0", configs=str(cfgdir))
    assert "must be numeric" in dies(c.cmd_init, a)
    a.release = "3.0.0a"; assert "must be numeric" in dies(c.cmd_init, a)
    a.release = None; assert "is required" in dies(c.cmd_init, a)
    a.release = "3.0.0"
    import io, contextlib
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        c.cmd_init(a)
    assert (t / "ws/configs/images/marker").read_text() == "mine", "copied the named configs dir"
    assert (t / "ws/image.yaml").read_text().startswith("base: minimal")
    assert "image.yaml exists" in dies(c.cmd_init, a)
    # --configs pointing at a dir named configs still works
    a2 = argparse.Namespace(dir=str(t / "ws2"), flavor="minimal", target="modalix", release="3.0.0",
                            configs=str(t / "repo/configs"))
    (t / "repo/configs/images").mkdir(parents=True)
    (t / "repo/configs/images/image-minimal-modalix.yaml").write_text("version: 3.0.0\n")
    with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
        c.cmd_init(a2)
    assert (t / "ws2/configs/images/image-minimal-modalix.yaml").is_file()
    assert "reference config" in dies(c.cmd_init, argparse.Namespace(
        dir=str(t / "ws3"), flavor="palette", target="modalix", release="3.0.0", configs=str(cfgdir)))

# cmd_verify --manifest error paths need a bundle; covered in the container run.


# chown(): a file already owned by CIB_UID/GID is left alone, so its setuid bit survives
with tempfile.TemporaryDirectory() as d:
    f = Path(d) / "helper"; f.write_text("x"); f.chmod(0o4755)
    os.environ["CIB_UID"], os.environ["CIB_GID"] = str(os.getuid()), str(os.getgid())
    c.chown(d)
    assert f.stat().st_mode & 0o4000, "setuid bit lost"
    del os.environ["CIB_UID"], os.environ["CIB_GID"]
# read_yaml / load_config: bad YAML, non-mapping, trailing newline, non-text hooks
with tempfile.TemporaryDirectory() as d:
    ws = Path(d)
    for body, msg in (("base: [", "not valid YAML"), ("- a\n", "must hold a mapping")):
        (ws / "image.yaml").write_text(body)
        assert msg in dies(c.load_config, ws), body
    good = "base: minimal\ntarget: modalix\nrelease: 3.0.0\n"
    (ws / "image.yaml").write_text(good + 'version: "3.0.0.1\\n"\n')
    assert "must be 3.0.0.<build>" in dies(c.load_config, ws), "trailing newline accepted"
    (ws / "image.yaml").write_text(good + "version: 3.0.0.1\nhooks: [1]\n")
    assert "hooks must be a list of script file names" in dies(c.load_config, ws)

# strip_comments / artifacts: comments ignored, // inside a string kept
desc = ('software = { version = "3.0.0.1"; images = (\n'
        '  { filename = "a.img"; sha256 = "AA"; },  // { filename = "gone"; sha256 = "x"; }\n'
        '  # { filename = "gone2"; sha256 = "x"; }\n'
        '  { filename = "http://h/b.img"; sha256 = "bb"; } ); }')
assert list(c.artifacts(desc)) == [("a.img", "aa"), ("http://h/b.img", "bb")], list(c.artifacts(desc))

# components(): source packages in an SBOM are not installed packages
with tempfile.TemporaryDirectory() as d:
    f = Path(d) / "s.cdx.json"
    f.write_text(json.dumps({"components": [
        {"name": "bash", "version": "5", "purl": "pkg:deb/debian/bash@5?arch=arm64"},
        {"name": "bash", "version": "5", "purl": "pkg:deb/debian/bash@5?arch=source"},
        {"name": "src-only", "version": "1", "purl": "pkg:deb/debian/src-only@1?arch=source"}]}))
    assert c.components(f) == {"bash": "5"}, c.components(f)

# check_issued: a missing file is named, not blamed on the CA
assert "nope.crt not found" in dies(c.check_issued, "nope.crt", "nope.crt")

# sign / verify round trip, tampering, -dev suffix, missing bundle
import argparse, subprocess
with tempfile.TemporaryDirectory() as d:
    t = Path(d); here = os.getcwd(); os.chdir(t)
    try:
        c.gen_keys(t / "keys", algo="ec", cn="T")
        assert (t / "keys/ca.key").stat().st_mode & 0o777 == 0o600
        c.gen_deb_key(t / "keys")
        assert (t / "keys/debs-signing.secret.asc").stat().st_mode & 0o777 == 0o600
        src = t / "src"; src.mkdir()
        (src / "boot0.be").write_text("b")
        (src / "sw-description").write_text(
            'software = { version = "3.0.0.1"; hardware-compatibility = ["1"];\n'
            f' images = ( {{ filename = "boot0.be"; sha256 = "{c.sha256(src / "boot0.be")}"; }} ); }}')
        c.write_swu(["sw-description", "boot0.be"], src, t / "u.swu")
        def sign(swu, out, dev=False, encrypt=False, aes=None):
            c.cmd_sign(argparse.Namespace(swu=str(swu), out=str(out), dev=dev, key=str(t / "keys/swu-signing.key"),
                                          cert=str(t / "keys/swu-signing.crt"), pkcs11=None,
                                          encrypt=encrypt, aes_key=aes))
        def version(swu):
            with tempfile.TemporaryDirectory() as x:
                c.read_swu(swu, x)
                return __import__("re").search(r'version = "([^"]*)"', (Path(x) / "sw-description").read_text())[1]
        def verify(swu, **k):
            c.cmd_verify(argparse.Namespace(swu=str(swu), ca=str(t / "keys/ca.crt"), manifest=k.get("manifest")))
        sign(t / "u.swu", t / "s.swu")
        verify(t / "s.swu")
        sign(t / "u.swu", t / "d1.swu", dev=True); sign(t / "d1.swu", t / "d2.swu", dev=True)
        assert version(t / "d1.swu") == version(t / "d2.swu") == "3.0.0.1-dev", version(t / "d2.swu")
        assert "not found" in dies(sign, t / "missing.swu", t / "x.swu")
        # payload encryption: key file checks, round trip, sha256 over the ciphertext, no double encryption
        c.gen_payload_key(t / "keys")
        assert (t / "keys/payload.key").stat().st_mode & 0o777 == 0o600
        assert "exists" in dies(c.gen_payload_key, t / "keys")
        (t / "bad.key").write_text("nothex\n")
        assert "must hold" in dies(c.read_aes_key, t / "bad.key")
        assert "not found" in dies(c.read_aes_key, t / "none.key")
        assert "has none of" in dies(sign, t / "u.swu", t / "e0.swu", encrypt=True, aes=str(t / "keys/payload.key"))
        (src / "rootfs.ext4.gz").write_bytes(os.urandom(1000))
        (src / "boot.vfat.gz").write_bytes(os.urandom(37))
        (src / "sw-description").write_text(
            'software = { version = "3.0.0.1"; hardware-compatibility = ["1"]; update = { full = { images = (\n'
            + "".join(f' {{\n\t\tfilename = "{n}";\n\t\tsha256 = "{c.sha256(src / n)}";\n }},\n'
                      for n in ("rootfs.ext4.gz", "boot.vfat.gz"))
            + f' {{ filename = "boot0.be"; sha256 = "{c.sha256(src / "boot0.be")}"; }} ); }}; }}; }}')
        plain_rootfs = (src / "rootfs.ext4.gz").read_bytes()
        c.write_swu(["sw-description", "boot0.be", "rootfs.ext4.gz", "boot.vfat.gz"], src, t / "p.swu")
        sign(t / "p.swu", t / "e.swu", encrypt=True, aes=str(t / "keys/payload.key"))
        verify(t / "e.swu")
        with tempfile.TemporaryDirectory() as x:
            c.read_swu(t / "e.swu", x)
            desc = (Path(x) / "sw-description").read_text()
            assert desc.count("encrypted = true;") == 2 and desc.count("ivt = ") == 2, desc
            ivt = re.search(r'filename = "rootfs.ext4.gz";\s*encrypted = true;\s*ivt = "([0-9a-f]{32})"', desc)[1]
            assert (Path(x) / "boot0.be").read_text() == "b", "boot0.be must stay plain"
            enc = Path(x) / "rootfs.ext4.gz"
            assert enc.read_bytes() != plain_rootfs
            dec = subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-K", c.read_aes_key(t / "keys/payload.key"),
                                  "-iv", ivt, "-in", enc], capture_output=True, check=True).stdout
            assert dec == plain_rootfs, "round trip"
        assert "already encrypted" in dies(sign, t / "e.swu", t / "e2.swu", encrypt=True, aes=str(t / "keys/payload.key"))
        with tempfile.TemporaryDirectory() as x:   # a changed member no longer matches the signed sha256
            c.read_swu(t / "s.swu", x); (Path(x) / "boot0.be").write_text("evil")
            c.write_swu(["sw-description", "sw-description.sig", "boot0.be"], x, t / "bad.swu")
        assert "does not match its signed sha256" in dies(verify, t / "bad.swu")
    finally:
        os.chdir(here)
# check_debs: a customer atf-* or troot-* package is refused, kernel and U-Boot pass
with tempfile.TemporaryDirectory() as d:
    ws = Path(d); (ws / c.DEBS).mkdir()
    deb = ws / c.DEBS / "x.deb"; deb.write_text("x")
    cfg = {"target": "modalix", "debs": {"key": "k"}}
    real = c.check_deb_signature, c.run
    try:
        c.check_deb_signature = lambda *a: None
        for pkg, msg in (("atf-modalix", "ATF comes from SiMa"), ("atf-modalix-secure", "ATF comes from SiMa"),
                         ("troot-modalix", "tRoot comes from SiMa")):
            c.run = lambda cmd, **k: {"Architecture": "arm64", "Package": pkg, "Version": "9"}[cmd[-1]]
            assert msg in dies(c.check_debs, ws, cfg), pkg
        c.run = lambda cmd, **k: {"Architecture": "arm64", "Package": "u-boot-modalix", "Version": "9"}[cmd[-1]]
        assert c.check_debs(ws, cfg) == [("u-boot-modalix", "9")]
    finally:
        c.check_deb_signature, c.run = real
# kernel FIT signature: a FIT made and signed by mkimage, checked against the key mkimage wrote
import shutil
if all(shutil.which(x) for x in ("mkimage", "dtc", "openssl")):
    with tempfile.TemporaryDirectory() as d:
        t = Path(d); (t / "keys").mkdir(); (t / "k.bin").write_bytes(os.urandom(5000))
        def sh(*cmd):
            subprocess.run(cmd, cwd=t, check=True, capture_output=True)
        def make(hint, *opts):
            if not (t / f"keys/{hint}.key").exists():
                sh("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", f"keys/{hint}.key",
                   "-out", f"keys/{hint}.crt", "-subj", "/CN=t", "-days", "1")
            (t / "t.its").write_text('/dts-v1/; / { description = "t"; #address-cells = <1>;\n'
                ' images { kernel { description = "k"; data = /incbin/("k.bin"); type = "kernel"; arch = "arm64";\n'
                '  os = "linux"; compression = "none"; load = <0x80000>; entry = <0x80000>; hash-1 { algo = "sha256"; }; }; };\n'
                ' configurations { default = "conf"; conf { description = "c"; kernel = "kernel";\n'
                '  signature-1 { algo = "sha256,rsa2048"; key-name-hint = "%s"; sign-images = "kernel"; }; }; }; };\n' % hint)
            (t / "e.dts").write_text("/dts-v1/; / { };\n")
            sh("dtc", "-O", "dtb", "-o", f"{hint}.dtb", "e.dts")
            sh("mkimage", *opts, "-f", "t.its", "-k", "keys", "-K", f"{hint}.dtb", "-r", f"{hint}.itb")
            return (t / f"{hint}.itb").read_bytes(), c.required_keys(b"junk" + (t / f"{hint}.dtb").read_bytes())
        fit, keys = make("prod")
        assert [h for h, _ in keys.values()] == ["prod"], keys
        c.fit_check(fit, keys)                                   # inline data
        ext, _ = make("prod", "-E")
        c.fit_check(ext, keys)                                   # external data (data-offset)
        bad = bytearray(fit); bad[fit.find(b"c\0", fit.find(b"conf"))] ^= 1
        assert "not signed by" in dies(c.fit_check, bytes(bad), keys), "changed configuration"
        j = fit.find((t / "k.bin").read_bytes()[:64]); bad = bytearray(fit); bad[j + 9] ^= 1
        assert "does not match its sha256 hash" in dies(c.fit_check, bytes(bad), keys), "changed kernel"
        _, other = make("other")
        assert "not signed by U-Boot's required key 'other'" in dies(c.fit_check, fit, other)
        # a signature over the kernel only: the configuration's fdt image could be swapped
        (t / "cov.its").write_text('/dts-v1/; / { description = "t"; #address-cells = <1>;\n images {\n'
            ' kernel { data = /incbin/("k.bin"); type = "kernel"; arch = "arm64"; os = "linux"; compression = "none";\n'
            '  load = <0x80000>; entry = <0x80000>; hash-1 { algo = "sha256"; }; };\n'
            ' fdt-1 { data = /incbin/("e.dts"); type = "flat_dt"; arch = "arm64"; compression = "none"; hash-1 { algo = "sha256"; }; }; };\n'
            ' configurations { default = "conf"; conf { kernel = "kernel"; fdt = "fdt-1";\n'
            '  signature-1 { algo = "sha256,rsa2048"; key-name-hint = "prod"; sign-images = "kernel"; }; }; }; };\n')
        sh("dtc", "-O", "dtb", "-o", "cov.dtb", "e.dts")
        sh("mkimage", "-f", "cov.its", "-k", "keys", "-K", "cov.dtb", "-r", "cov.itb")
        assert dies(c.fit_check, (t / "cov.itb").read_bytes(), c.required_keys((t / "cov.dtb").read_bytes())) == \
            "cib: the kernel FIT signature does not cover /images/fdt-1, /images/fdt-1/hash-1"
        assert "not a FIT" in dies(c.fit_check, b"junk" * 20, keys)
        def fdt(conf, hashes):   # unsigned: no keys, so only the configuration and image hashes are checked
            (t / "x.dts").write_text('/dts-v1/; / { images { kernel { data = [00]; %s }; };\n'
                                     ' configurations { default = "conf"; conf { %s }; }; };\n' % (hashes, conf))
            sh("dtc", "-O", "dtb", "-o", "x.dtb", "x.dts"); return (t / "x.dtb").read_bytes()
        H0 = 'hash-1 { algo = "sha256"; value = [%s]; };' % c.hashlib.sha256(b"\0").hexdigest()
        c.fit_check(fdt('kernel = "kernel";', H0), {})
        assert "has no kernel" in dies(c.fit_check, fdt('fdt = "kernel";', H0), {})
        assert "has no kernel" in dies(c.fit_check, fdt('kernel = "gone";', H0), {})
        for bad in ("", 'hash-1 { algo = "crc32"; value = <0>; };', 'hash-1 { algo = "sha256"; };'):
            assert "has no hash that can be checked" in dies(c.fit_check, fdt('kernel = "kernel";', bad), {}), bad
        c.fit_check(fdt('kernel = "kernel";', 'hash-1 { algo = "crc32"; value = <0>; };' + H0.replace("hash-1", "hash-2")), {})
        assert "does not match its sha256 hash" in dies(c.fit_check, fdt('kernel = "kernel";', H0.replace("[6e", "[6f")), {})
        assert c.required_keys(b"no trees here") == {}
        # check_secure_boot: no key, the development key without --dev, and with it
        devfit, _ = make("dev")
        boot = t / "root/boot"; boot.mkdir(parents=True)
        (boot / "fitImage").write_bytes(devfit); (boot / "fip.bin").write_bytes(b"x")
        (boot / "u-boot.bin").write_bytes(b"x")
        assert "no required FIT key" in dies(c.check_secure_boot, t / "root", False)
        (boot / "u-boot.bin").write_bytes(b"pad" + (t / "dev.dtb").read_bytes())
        assert "need --dev" in dies(c.check_secure_boot, t / "root", False)
        c.check_secure_boot(t / "root", True)
        (boot / "fitImage").write_bytes(fit)                    # signed by prod, U-Boot wants dev
        assert "not signed by" in dies(c.check_secure_boot, t / "root", True)
else:
    FIT_SKIPPED = True
# fip_bl33 / check_fip_uboot: the U-Boot inside fip.bin must be /boot/u-boot.bin
import struct
def fip(*entries, magic=0xAA640001, end=True):
    toc = [(u, d) for u, d in entries] + ([(bytes(16), b"")] if end else [])
    pos, head, body = 16 + 40 * len(toc), struct.pack("<IIQ", magic, 0, 0), b""
    for u, d in toc:
        head += struct.pack("<16sQQQ", u, pos + len(body) if d else 0, len(d), 0); body += d
    return head + body
OTHER, UB = bytes(range(1, 17)), b"u-boot" * 100
assert c.fip_bl33(fip((OTHER, b"bl31"), (c.BL33_UUID, UB), (OTHER, b"cert"))) == UB, "middle entry"
assert c.fip_bl33(fip((c.BL33_UUID, UB))) == UB, "only entry"
assert c.fip_bl33(fip((c.BL33_UUID, b""))) == b"", "empty U-Boot entry"
assert c.fip_bl33(fip((OTHER, b"bl31"))) is None, "no U-Boot entry"
assert c.fip_bl33(fip((OTHER, b"x"), (c.BL33_UUID, UB), end=False)) == UB, "no end marker"
assert c.fip_bl33(fip((OTHER, b"x"), end=False)) is None, "no end marker, no U-Boot"
assert c.fip_bl33(fip((c.BL33_UUID, UB), magic=0xAA640002)) is None, "wrong magic"
assert c.fip_bl33(fip() + struct.pack("<16sQQQ", c.BL33_UUID, 0, 4, 0)) is None, "entry after the end"
assert all(c.fip_bl33(b) is None for b in (b"", b"x", fip((c.BL33_UUID, UB))[:55])), "too short"
assert c.fip_bl33(fip((c.BL33_UUID, UB))[:-1]) is None, "cut payload"
assert c.fip_bl33(fip((c.BL33_UUID, b""), end=False)) == b"", "table ends at end of file"
assert c.fip_bl33(fip((c.BL33_UUID, b"first"), (c.BL33_UUID, b"second"))) == b"first", "first entry wins"
assert c.BL33_UUID == bytes.fromhex("d6d0eea7fcead54b97829934f234b6e4"), "TF-A's BL33 UUID"
with tempfile.TemporaryDirectory() as t:
    boot = Path(t) / "boot"; boot.mkdir()
    (boot / "fip.bin").write_bytes(fip((OTHER, b"bl31"), (c.BL33_UUID, UB)))
    (boot / "u-boot.bin").write_bytes(UB)
    c.check_fip_uboot(t)
    for other in (UB[:-1], UB + b"x", UB.replace(b"u", b"v", 1), b""):
        (boot / "u-boot.bin").write_bytes(other)
        assert "not the U-Boot inside /boot/fip.bin" in dies(c.check_fip_uboot, t), other[:8]
    (boot / "u-boot.bin").write_bytes(UB)
    for bad in (b"junk" * 20, fip((OTHER, UB)), fip((c.BL33_UUID, UB))[:-1]):
        (boot / "fip.bin").write_bytes(bad)
        assert "not the U-Boot inside /boot/fip.bin" in dies(c.check_fip_uboot, t)
    (boot / "fip.bin").write_bytes(fip((c.BL33_UUID, UB))[:-1]); (boot / "u-boot.bin").write_bytes(UB[:-1])
    assert "not the U-Boot inside /boot/fip.bin" in dies(c.check_fip_uboot, t), "both cut alike"
    # the check runs in cmd_finish, after the boot files are known to exist
    (boot / "fip.bin").write_bytes(fip((c.BL33_UUID, UB))); (boot / "fitImage").write_bytes(b"f")
    (Path(t) / "lib/linux-image-6-m").mkdir(parents=True)
    (Path(t) / "var/lib/dpkg").mkdir(parents=True); (Path(t) / "var/lib/apt/lists").mkdir(parents=True)
    (Path(t) / "var/lib/dpkg/status").write_text("".join(
        f"Package: {p}\nStatus: install ok installed\nVersion: 1\n\n"
        for p in ("linux-image-6-m", "u-boot-m", "atf-m")))
    (Path(t) / "var/lib/apt/lists/repo.sima.ai_dists_x_Packages").write_text(
        "".join(f"Package: {p}\nVersion: 1\n\n" for p in ("linux-image-6-m", "u-boot-m", "atf-m")))
    (Path(t) / "policy.json").write_text(json.dumps(
        {"own_sources": False, "base": "minimal", "dev": False}))
    fin = argparse.Namespace(root=t, build=t, target="m")
    assert "not the U-Boot inside /boot/fip.bin" in dies(c.cmd_finish, fin), "cmd_finish refuses"
    (boot / "u-boot.bin").write_bytes(UB)
    c.cmd_finish(fin)
    assert [p["name"] for p in json.loads((Path(t) / "packages.json").read_text())] == \
        ["atf-m", "linux-image-6-m", "u-boot-m"], "cmd_finish passes with the matching U-Boot"
# cib init writes a .gitignore that keeps secrets and output out of git, and keeps an existing one
with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    (t / "cfg/images").mkdir(parents=True)
    (t / "cfg/images/image-minimal-modalix.yaml").write_text("version: 3.0.0\n")
    for name in ("ws", "ws3"):
        (t / name).mkdir()
    (t / "ws3/.gitignore").write_text("mine\n")
    for name in ("ws", "ws3"):
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            c.cmd_init(argparse.Namespace(dir=str(t / name), flavor="minimal", target="modalix",
                                          release="3.0.0", configs=str(t / "cfg")))
    assert (t / "ws/.gitignore").read_text() == c.GITIGNORE and "keys/*.key" in c.GITIGNORE
    assert (t / "ws3/.gitignore").read_text() == "mine\n", "existing .gitignore kept"

# gen_leaf: a failed certificate swap restores the old key; a good renew changes both
with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    c.gen_keys(t, "ecdsa-p384", "T")
    k0, c0 = (t / "swu-signing.key").read_bytes(), (t / "swu-signing.crt").read_bytes()
    real = os.replace
    for exc in (OSError("disk full"), KeyboardInterrupt()):
        def flaky(s, d):
            if str(d).endswith("swu-signing.crt"):
                raise exc
            real(s, d)
        os.replace = flaky
        try:
            c.gen_leaf(t, "ecdsa-p384", "T"); raise AssertionError("did not fail")
        except type(exc):
            pass
        finally:
            os.replace = real
        assert (t / "swu-signing.key").read_bytes() == k0 and (t / "swu-signing.crt").read_bytes() == c0, exc
    def late(s, d):
        real(s, d)
        if str(d).endswith("swu-signing.crt"):
            raise KeyboardInterrupt
    os.replace = late
    try:
        c.gen_leaf(t, "ecdsa-p384", "T"); raise AssertionError("did not fail")
    except KeyboardInterrupt:
        pass
    finally:
        os.replace = real
    c.check_issued(t / "swu-signing.crt", t / "ca.crt")
    pair = [subprocess.run(["openssl", k, "-in", t / f, "-noout", "-pubkey"] if k == "x509" else
                           ["openssl", "pkey", "-in", t / f, "-pubout"], capture_output=True, check=True).stdout
            for k, f in (("x509", "swu-signing.crt"), ("pkey", "swu-signing.key"))]
    assert pair[0] == pair[1], "key and certificate match after a late interrupt"
    k0, c0 = (t / "swu-signing.key").read_bytes(), (t / "swu-signing.crt").read_bytes()
    c.gen_leaf(t, "ecdsa-p384", "T")
    assert (t / "swu-signing.key").read_bytes() != k0 and (t / "swu-signing.crt").read_bytes() != c0
    c.check_issued(t / "swu-signing.crt", t / "ca.crt")
# gen_leaf: no key copy outlives the run; a leftover from a SIGKILL is swept; signal handlers come back
import signal
with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    c.gen_keys(t, "ecdsa-p384", "T")
    (t / ".cib-renew-dead").mkdir(); (t / ".cib-renew-dead/old.key").write_text("old secret")
    (t / "keep.me").write_text("x")
    before = signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGHUP)
    c.gen_leaf(t, "ecdsa-p384", "T")
    assert not list(t.glob(".cib-renew-*")), "stale and own work dirs removed"
    assert (t / "keep.me").read_text() == "x" and (t / "ca.key").is_file()
    assert (signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGHUP)) == before, "handlers restored"
    k0, c0 = (t / "swu-signing.key").read_bytes(), (t / "swu-signing.crt").read_bytes()
    code = ("import os, signal, sys; sys.path.insert(0, %r); import cib.cli as c; from pathlib import Path\n"
            "real = os.replace\n"
            "def hit(s, d):\n"
            "    os.kill(os.getpid(), signal.SIGTERM); real(s, d)\n"
            "os.replace = hit\n"
            "c.gen_leaf(Path(%r), 'ecdsa-p384', 'T')\n") % (str(Path(c.__file__).parent.parent), str(t))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 128 + signal.SIGTERM, (r.returncode, r.stderr)
    assert not list(t.glob(".cib-renew-*")), "SIGTERM mid-swap leaves no key copy"
    assert (t / "swu-signing.key").read_bytes() == k0 and (t / "swu-signing.crt").read_bytes() == c0, "old pair intact"
assert "keys/.cib-renew-*/" in c.GITIGNORE
# update_modalix.sh: the inactive boot partition is unmounted when postinst fails, and by postfailure
src = (Path(__file__).resolve().parent.parent / "configs/images/files/update_modalix.sh").read_text()
snip = src[src.index("\t\tbootmnt=$(mktemp -d)"):src.index("\t\tfatlabel ")]
func = src[src.index("release_boot() {"):src.index('echo "== Start $1 =="')]
STUBS = (  # a mount is a marker file M; findmnt lists the last mount point while M exists
    'mount() {{ echo mount >> $LOG; touch $D/M; }}\n'
    'umount() {{ echo umount >> $LOG; {ufail} rm -f $D/M "$1"/*; }}\n'
    'findmnt() {{ [ -f $D/M ] && cat $D/last; return 0; }}\n'
    'mktemp() {{ d=$(command mktemp -d); echo "$d" > $D/last; {chmod} echo "$d"; }}\n')
def run_boot(body, fail=False, ufail=False):
    with tempfile.TemporaryDirectory() as t:
        D = Path(t)
        script = (f'set -e\nLOG={D}/log\nD={t}\n: > $LOG\n' + STUBS.format(chmod='ln -s /dev/full "$d/dm-table.env";' if fail else "",
                  ufail="return 1;" if ufail else "") + 'inactive_boot=/dev/x dmoff=1 dmlen=2 clean_env=1 keep_ddr=0\n'
                  + func + body + 'echo done >> $LOG\n')
        r = subprocess.run(["sh", "-c", script], capture_output=True, text=True)
        last = (D / "last").read_text().strip() if (D / "last").exists() else ""
        return r.returncode, (D / "log").read_text().split(), r.stderr, last
rc, steps, err, last = run_boot(snip)
assert (rc, steps) == (0, ["mount", "umount", "done"]), "clean run unmounts once and clears the trap"
assert not os.path.exists(last)
rc, steps, err, last = run_boot(snip, fail=True)
assert rc != 0 and steps == ["mount", "umount"], (rc, steps)  # a failed write still unmounts
assert not os.path.exists(last), "and removes the mount point"
rc, steps, err, last = run_boot(snip, fail=True, ufail=True)
assert rc != 0 and "could not unmount" in err and "before retrying" in err, err  # a busy mount is reported
# postfailure: whatever is still mounted from the inactive boot partition is unmounted first
fail_part = src[src.index("postfailure)"):]
assert fail_part.index("\t\trelease_boot\n") < fail_part.index("dd if=/dev/zero"), "postfailure calls release_boot"
rc, steps, err, last = run_boot('d=$(mktemp -d); mount /dev/x "$d"\nrelease_boot\n')
assert steps == ["mount", "umount", "done"], steps
rc, steps, err, last = run_boot("release_boot\n")
assert (rc, steps) == (0, ["done"]), "nothing mounted: nothing to do"
# postinst refuses a rootfs slot that is not exactly one linear dm segment
dmsnip = src[src.index("\t\tdm=$(dmsetup"):src.index("\t\tlvchange", src.index("\t\tdm=$(dmsetup"))]
for table, ok in (("0 8 linear 179:2 2048", True), ("0 8 linear 179:2 2048\n8 8 linear 179:2 9000", False),
                  ("0 8 striped 2 128 179:2 0 179:3 0", False), ("", False)):
    r = subprocess.run(["sh", "-c", 'set -e\nvg=v inactive=B\ndmsetup() { printf "%s" "$DM"; }\n' + dmsnip + 'echo "$dmoff $dmlen"'],
                       env={**os.environ, "DM": table}, capture_output=True, text=True)
    assert (r.returncode == 0) == ok and (r.stdout == "2048 8\n" if ok else "not one linear segment" in r.stderr), (table, r)
# CIB_CREDENTIALS: optional, validated up front, mounted by host/cib, read by base.sh with chpasswd -e
H = "$6$salt$" + "a" * 20
def cred(text, name="credentials"):
    d = tempfile.mkdtemp(); f = Path(d) / name; f.write_text(text); os.environ["CIB_CREDENTIALS"] = str(f); return f
os.environ.pop("CIB_CREDENTIALS", None)
import contextlib, io
with contextlib.redirect_stderr(io.StringIO()) as e:
    assert c.check_credentials() is None
assert e.getvalue().startswith("cib: no CIB_CREDENTIALS: root and sima are locked") and e.getvalue().count("\n") == 1, e.getvalue()
os.environ["CIB_CREDENTIALS"] = "/nonexistent/credentials"; assert "not found" in dies(c.check_credentials)
LINE, ONE = ":{} must be root:<hash> or sima:<hash> with a $id$ crypt hash, not a password", " must hold exactly one root and one sima line"
for bad, want in ((f"root:root\nsima:{H}\n", LINE.format(1)), (f"root:{H}\n", ONE), (f"sima:{H}\n", ONE),
                  (f"root:{H}\nroot:{H}\nsima:{H}\n", ONE), (f"root:{H}\nsima:{H}\nbob:{H}\n", LINE.format(3)),
                  (f"root:!\nsima:{H}\n", LINE.format(1)), (f"root:{H}\n\nsima:{H}\n", LINE.format(2)),
                  (f"root:{H} \nsima:{H}\n", LINE.format(1)), ("", ONE)):
    f = cred(bad); assert dies(c.check_credentials) == f"cib: {f}{want}", (bad, dies(c.check_credentials))
cred(f"root:{H}\nsima:{H}\n"); c.check_credentials()
cred(f"sima:{H}\nroot:{H}", "a b"); assert "paths used in hooks" in dies(c.check_credentials), "space in path"
os.environ.pop("CIB_CREDENTIALS", None)
# host/cib mounts the file read-only and passes the container path, not the content
with tempfile.TemporaryDirectory() as t:
    t = Path(t); (t / "bin").mkdir(); (t / "keys").mkdir()
    (t / "bin/docker").write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n'); (t / "bin/docker").chmod(0o755)
    (t / "keys/cred.txt").write_text("secret\n")
    r = subprocess.run([str(Path(__file__).resolve().parent.parent / "host/cib"), "build"], cwd=t,
                       env={**os.environ, "PATH": f"{t}/bin:{os.environ['PATH']}", "CIB_CREDENTIALS": str(t / "keys/cred.txt")},
                       capture_output=True, text=True)
    args = r.stdout.split("\n")
    assert f"{t}/keys/cred.txt:/keys/CIB_CREDENTIALS:ro" in args and "CIB_CREDENTIALS=/keys/CIB_CREDENTIALS" in args, args
    assert "secret" not in r.stdout and not any(a.startswith(f"{t}/keys:") for a in args), "only the file is mounted"
    for missing in (t / "keys/none", t / "keys"):
        r = subprocess.run([str(Path(__file__).resolve().parent.parent / "host/cib"), "sign"], cwd=t, capture_output=True, text=True,
                           env={**os.environ, "PATH": f"{t}/bin:{os.environ['PATH']}", "SWU_SIGNING_KEY": str(missing)})
        assert r.returncode == 1 and r.stdout == "" and f"SWU_SIGNING_KEY: {missing} is not a file" in r.stderr, r
hook = (Path(__file__).resolve().parent.parent / "configs/images/hooks/base.sh").read_text()
assert all(" chpasswd" not in ln or "chpasswd -e" in ln for ln in hook.splitlines()), "no password in the hook"
snip = hook[hook.index("if [ -n \"${CIB_CREDENTIALS"):hook.index("chroot \"$1\" usermod -a -G sima root")].replace('"$1"', "/r")
def hook_run(env):
    return subprocess.run(["sh", "-c", 'chroot() { echo "chroot $*"; cat; }\nset -e\n' + snip + 'echo reached'],
                          env={"PATH": os.environ["PATH"], **env}, stdin=subprocess.DEVNULL, capture_output=True, text=True)
r = hook_run({})
assert r.returncode == 0 and r.stdout == "reached\n", r
f = cred(f"root:{H}\nsima:{H}\n"); os.environ.pop("CIB_CREDENTIALS")
r = hook_run({"CIB_CREDENTIALS": str(f)})
assert r.returncode == 0 and r.stdout.split("\n")[0] == "chroot /r chpasswd -e" and f"root:{H}" in r.stdout, r
# SSH: no root password login, no host keys in the image, each board makes its own on first boot
base = (Path(__file__).resolve().parent.parent / "configs/images/hooks/base.sh").read_text()
unit = (Path(__file__).resolve().parent.parent / "configs/images/overlay/simaai/usr/lib/systemd/system/simaai-ssh-hostkeys.service").read_text()
assert "PermitRootLogin yes" not in base, "root keeps the default prohibit-password"
assert base.rstrip().endswith('rm -f "$1"/etc/ssh/ssh_host_*'), "host keys removed last, after every package is configured"
assert 'systemctl enable --root="$1" simaai-ssh-hostkeys' in base
assert "Before=ssh.service" in unit and "ExecStart=/usr/bin/ssh-keygen -A" in unit and "WantedBy=ssh.service" in unit
# entrypoint: only "cib build" and a shell get the build set-up; other cib commands run at once
ep = (Path(__file__).resolve().parent.parent / "entrypoint.sh").read_text()
case = ep[ep.index('case "${1:-} ${2:-}" in'):ep.index("# --- arm64 emulation")]
with tempfile.TemporaryDirectory() as t:
    (Path(t) / "cib").write_text('#!/bin/sh\necho "ran $*"\n'); (Path(t) / "cib").chmod(0o755)
    for argv, want in ((["cib", "sign", "x"], "ran sign x\n"), (["cib", "verify"], "ran verify\n"),
                       (["cib", "build", "--dev"], "setup\n"), (["cib", "build"], "setup\n"), (["bash"], "setup\n"),
                       (["bash", "-c", "x"], "setup\n"), (["cib", "builder"], "ran builder\n")):
        r = subprocess.run(["bash", "-c", case + "echo setup", "ep", *argv], capture_output=True, text=True,
                           env={"PATH": f"{t}:{os.environ['PATH']}"})
        assert r.stdout == want, (argv, r.stdout, r.stderr)
# update_modalix.sh: preinst drops a boot0.be or OS marker left in /tmp before swupdate writes this bundle's
pre = src[src.index("preinst)\n"):src.index("postinst)\n")]
assert pre.index('rm -f "$BOOT0" "$OSMARK"') < pre.index("resolve_slots"), "cleared first"
with tempfile.TemporaryDirectory() as t:
    b0, osm = Path(t) / "boot0.be", Path(t) / "os"; b0.write_text("stale"); osm.write_text("stale")
    r = subprocess.run(["sh", "-c", f'BOOT0={b0} OSMARK={osm}\n' + pre.split("\n", 3)[2] + "\n"], capture_output=True, text=True)
    assert r.returncode == 0 and not b0.exists() and not osm.exists(), r
# a missing input file ends in one cib: line, not a traceback
with tempfile.TemporaryDirectory() as d:
    for argv in (["verify", "--ca", f"{d}/ca.crt", f"{d}/no.swu"], ["diff", "--against", f"{d}/no.json", "--image", f"{d}/no.cdx.json"]):
        try:
            c.main(argv)
            raise AssertionError(argv)
        except SystemExit as e:
            assert str(e.code).startswith("cib: ") and "No such file or directory" in str(e.code), e.code
# cib sign with no SWU: the image.yaml version's bundle, not whatever else out/ still holds
import argparse, contextlib, io
with tempfile.TemporaryDirectory() as t:
    here = os.getcwd(); os.chdir(t); (Path(t) / "out").mkdir()
    real_rs, real_gk = c.read_swu, c.gen_keys
    picked = []
    def pick(swu, d): picked.append(str(swu)); raise StopIteration
    def sign(ver):
        y = Path("image.yaml")
        y.unlink(missing_ok=True)
        if ver: y.write_text(f"base: minimal\ntarget: modalix\nversion: {ver}\n")
        with contextlib.redirect_stderr(io.StringIO()):
            try: c.cmd_sign(argparse.Namespace(swu=None, out=None, dev=True, key=None, cert=None, pkcs11=None, encrypt=False, aes_key=None))
            except StopIteration: return picked.pop()
            except SystemExit as e: return str(e.code)
    N = "out/elxr-minimal-modalix-{}-agate-arm64.{}swu"
    for v, k in (("3.0.0.1", "unsigned."), ("3.0.0.1", ""), ("3.0.0.10", "unsigned."), ("3.0.0.2", "unsigned.")):
        Path(N.format(v, k)).write_text("x")
    try:
        c.read_swu, c.gen_keys = pick, lambda *a, **k: None
        assert sign("3.0.0.2") == N.format("3.0.0.2", "unsigned.")
        assert sign("3.0.0.1") == N.format("3.0.0.1", "unsigned."), "not 3.0.0.10, not the signed one"
        assert sign(None) == "cib: name the .swu to sign (out/ holds 3)", "no image.yaml: every unsigned bundle"
        assert sign("3.0.0.3") == "cib: name the .swu to sign (out/ holds 0)"
        Path(N.format("3.0.0.1", "unsigned.")).unlink()
        assert sign("3.0.0.1") == N.format("3.0.0.1", ""), "only the signed one left: re-sign it"
    finally:
        c.read_swu, c.gen_keys = real_rs, real_gk; os.chdir(here)
if "FIT_SKIPPED" in globals():
    sys.exit("the FIT asserts did not run: mkimage, dtc or openssl missing; the other asserts passed")
print("ALL CLI ASSERTS PASSED")
