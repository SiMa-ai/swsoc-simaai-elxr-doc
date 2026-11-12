"""assert checks for cib.cli; run: python3 cib/test_cli.py (host, no container)."""
import os, sys, tempfile, json
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
        def sign(swu, out, dev=False):
            c.cmd_sign(argparse.Namespace(swu=str(swu), out=str(out), dev=dev, key=str(t / "keys/swu-signing.key"),
                                          cert=str(t / "keys/swu-signing.crt"), pkcs11=None))
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
print("ALL CLI ASSERTS PASSED")
