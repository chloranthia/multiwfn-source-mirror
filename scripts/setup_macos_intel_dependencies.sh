#!/usr/bin/env bash
set -euo pipefail

test "$(uname -m)" = x86_64
test "$(sw_vers -productVersion | cut -d. -f1)" = 15

macports_version=2.12.7
installer_sha256=87b2e87ed7adc4aca947b42eb7ff991614cc0edfccb486237f2bbc75f28aae63
ports_commit=1ec0f5eae9073740ad1c2974c9c03653736ffae9
ports_sha256=c857f1860babda2cbfbd306256343cd5fcadec20fee467135ef65eb1064798c0
# Runtime recipe closure for the pinned X11/Motif binaries. Keep this list in
# sync with the ports snapshot; indexing unrelated ports costs several minutes.
port_paths=(
  archivers/brotli archivers/bzip2 archivers/zlib
  devel/gettext devel/icu devel/ncurses devel/pkgconfig
  graphics/fontconfig graphics/libjpeg-turbo graphics/libpng
  print/freetype textproc/expat textproc/libiconv textproc/libxml2
  x11/Xft2 x11/motif x11/xorg-libX11 x11/xorg-libXau x11/xorg-libXcursor
  x11/xorg-libXdmcp x11/xorg-libXext x11/xorg-libXfixes x11/xorg-libXmu
  x11/xorg-libXrandr x11/xorg-libXt x11/xorg-libice x11/xorg-libsm
  x11/xorg-libxcb x11/xorg-xcb-proto x11/xorg-xorgproto x11/xpm x11/xrender
)
cache_archive="$1"
prefix=/opt/local

sudo mkdir -p "$prefix"
if test -f "$cache_archive"; then
  # The restored prefix is consumed by the build; package installation is only
  # performed on a cache miss, when the installer also creates its service user.
  sudo tar -xzf "$cache_archive" -C "$prefix"
else
  work="$(mktemp -d "$RUNNER_TEMP/macports.XXXXXX")"
  installer="MacPorts-$macports_version-15-Sequoia.pkg"
  curl -fL --retry 3 \
    "https://github.com/macports/macports-base/releases/download/v$macports_version/$installer" \
    -o "$work/$installer"
  printf '%s  %s\n' "$installer_sha256" "$work/$installer" | shasum -a 256 -c -
  curl -fL --retry 3 \
    "https://github.com/macports/macports-ports/archive/$ports_commit.tar.gz" \
    -o "$work/ports.tar.gz"
  printf '%s  %s\n' "$ports_sha256" "$work/ports.tar.gz" | shasum -a 256 -c -

  ports_tree="$prefix/var/macports/sources/pinned"
  sudo mkdir -p "$ports_tree" "$prefix/etc/macports"
  archive_root="macports-ports-$ports_commit"
  members=("$archive_root/_resources")
  for port_path in "${port_paths[@]}"; do
    members+=("$archive_root/$port_path")
  done
  sudo tar -xzf "$work/ports.tar.gz" --strip-components=1 -C "$ports_tree" "${members[@]}"
  printf 'file://%s [nosync,default]\n' "$ports_tree" \
    | sudo tee "$prefix/etc/macports/sources.conf" >/dev/null
  printf 'https://github.com/macports/macports-base/releases/tag/v%s\n' "$macports_version" \
    | sudo tee "$prefix/etc/macports/RELEASE_URL" >/dev/null
  # The official installer runs selfupdate. Keep that version check on the
  # local pinned release, and prevent ports from falling back to source builds.
  {
    echo "prefix $prefix"
    echo "portdbpath $prefix/var/macports"
    echo "sources_conf $prefix/etc/macports/sources.conf"
    echo 'buildfromsource never'
    echo "release_version_urls file://$prefix/etc/macports/RELEASE_URL"
  } | sudo tee "$prefix/etc/macports/macports.conf" >/dev/null
  sudo /usr/sbin/installer -pkg "$work/$installer" -target /
  test "$("$prefix/bin/port" version)" = "Version: $macports_version"
  (cd "$ports_tree" && sudo "$prefix/bin/portindex")
  sudo "$prefix/bin/port" -N -b install \
    pkgconfig xorg-libX11 xorg-libXt motif
fi

"$prefix/bin/pkg-config" --version
for library in libX11.dylib libXt.dylib libXm.dylib; do
  lipo "$prefix/lib/$library" -verify_arch x86_64
done

if ! test -f "$cache_archive"; then
  # Save the installed environment immediately, so a later build/test failure
  # does not force the next attempt to reinstall the same dependencies.
  sudo tar -czf "$cache_archive" -C "$prefix" \
    --exclude='./var/macports/build' \
    --exclude='./var/macports/distfiles' \
    --exclude='./var/macports/software' \
    --exclude='./var/macports/logs' .
fi
