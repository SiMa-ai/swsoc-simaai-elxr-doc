#!/bin/sh
# Generate /etc/buildinfo inside the image rootfs at image-creation time.
#
# Same format as /etc/packageinfo, which the SiMa.ai packages write at package-build
# time; the final line differs: SIMA_BUILD_VERSION here, SIMA_PACKAGE_VERSION there.
build_file=$1
platform=$2
version=$3
build=$4
codename=$5
branch=$(git -C "$(dirname "$0")" rev-parse --abbrev-ref HEAD 2>/dev/null || echo cib)

cat > "$build_file" <<EOF
-----------------------
Build Configuration:  |
-----------------------
DISTRO = eLxr
DISTRO_VERSION = $version
CODENAME = $codename
MACHINE = $platform
$(date +'DATE = %Y%m%d%nTIME = %H%M%S')
SIMA_BUILD_VERSION = ${version}_${branch}_B${build}
EOF
