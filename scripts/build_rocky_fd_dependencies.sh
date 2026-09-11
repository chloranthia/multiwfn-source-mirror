#!/usr/bin/env bash
set -euo pipefail

fd_prefix=/opt/multiwfn-fd
fd_source_dir="$(mktemp -d)"
trap 'rm -rf "$fd_source_dir"' EXIT
mkdir -p "$fd_prefix"

curl -fL --retry 3 \
  https://ftp.gnu.org/gnu/gmp/gmp-6.3.0.tar.xz \
  -o "$fd_source_dir/gmp-6.3.0.tar.xz"
tar -xJf "$fd_source_dir/gmp-6.3.0.tar.xz" -C "$fd_source_dir"
(
  cd "$fd_source_dir/gmp-6.3.0"
  ./configure --prefix="$fd_prefix" --libdir="$fd_prefix/lib" \
    --enable-shared --disable-static --enable-fat
  make -j4
  make install
)
export PKG_CONFIG_PATH="$fd_prefix/lib/pkgconfig:$fd_prefix/lib64/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
export LD_LIBRARY_PATH="$fd_prefix/lib:$fd_prefix/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

curl -fL --retry 3 \
  https://www.mpfr.org/mpfr-4.2.2/mpfr-4.2.2.tar.xz \
  -o "$fd_source_dir/mpfr-4.2.2.tar.xz"
tar -xJf "$fd_source_dir/mpfr-4.2.2.tar.xz" -C "$fd_source_dir"
(
  cd "$fd_source_dir/mpfr-4.2.2"
  ./configure --prefix="$fd_prefix" --libdir="$fd_prefix/lib" \
    --with-gmp="$fd_prefix" --enable-shared --disable-static
  make -j4
  make install
)

curl -fL --retry 3 \
  https://flintlib.org/download/flint-3.0.1.tar.gz \
  -o "$fd_source_dir/flint-3.0.1.tar.gz"
tar -xzf "$fd_source_dir/flint-3.0.1.tar.gz" -C "$fd_source_dir"
(
  cd "$fd_source_dir/flint-3.0.1"
  ./configure --prefix="$fd_prefix" --libdir="$fd_prefix/lib" \
    --with-gmp="$fd_prefix" --with-mpfr="$fd_prefix" \
    --disable-static
  make -j4
  make install
)
