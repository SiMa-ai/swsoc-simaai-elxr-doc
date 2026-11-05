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

echo "-----------------------" > $build_file
echo "Build Configuration:  |" >> $build_file
echo "-----------------------" >> $build_file
echo "DISTRO = eLxr" >> $build_file
echo "DISTRO_VERSION = $version" >> $build_file
echo "CODENAME = $codename" >> $build_file
echo "MACHINE = $platform" >> $build_file
echo "DATE = $(date +%Y%m%d)" >> $build_file
echo "TIME = $(date +%H%M%S)" >> $build_file
echo "SIMA_BUILD_VERSION = ${version}_${branch}_B${build}" >> $build_file
