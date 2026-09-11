# Multiwfn Source Mirror

An unofficial mirror of Multiwfn source updates, preserving imported snapshots
in Git history. The build configuration and CI workflows are provided for
personal use and reference.

Multiwfn is developed by Tian Lu. See the [official website](http://sobereva.com/multiwfn)
for the manual and official downloads.

## Source synchronization

The daily workflow imports the
[latest upstream archive](http://sobereva.com/multiwfn/misc/Multiwfn_latest_src_Linux.zip)
into `src/` without local modifications and records updates as Git commits.
`upstream.json` stores the source version, download URL, archive size, and
locally calculated SHA-256 fingerprint.

## Building

CMake builds either `Multiwfn` (GUI) or `Multiwfn_noGUI` (no-GUI), selected
with `MULTIWFN_BUILD_GUI`. Both require CMake 3.24 or newer, C and Fortran
compilers, BLAS, and LAPACK. No-GUI builds also require Python 3 for tests.
For a no-GUI build, run from the repository root:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DMULTIWFN_BUILD_GUI=OFF
cmake --build build --parallel
ctest --test-dir build --output-on-failure
cmake --install build --prefix package
```

Fractional derivatives are disabled by default. Enable them with
`-DMULTIWFN_WITH_FD=ON`, using `pkg-config` and development files for FLINT 3
or newer, GMP, and MPFR. The FLINT installation must provide `flint.pc`;
Arb is included in FLINT.

For GUI builds, set `-DMULTIWFN_BUILD_GUI=ON` and
`-DMULTIWFN_DISLIN_LIBRARY=/path/to/library` to a platform-compatible DISLIN
library. Linux and macOS also require X11, Xt, Motif, and OpenGL development
files. Platform setup examples are in the [CI workflows](.github/workflows/);
upstream build instructions remain in [src/COMPILATION_METHOD.txt](src/COMPILATION_METHOD.txt).

The CMake installation includes the executable, settings, license, and build
metadata. CI packaging also bundles runtime libraries and GUI resources.

## CI packages

GUI and no-GUI packages for Linux, macOS, and Windows are available from
[GitHub Releases](https://github.com/chloranthia/multiwfn-source-mirror/releases)
and [Actions artifacts](https://github.com/chloranthia/multiwfn-source-mirror/actions).
Linux no-GUI packages also include a Rocky Linux 8 build for glibc 2.28.
All CI packages enable fractional derivatives and include build metadata;
each release also provides `SHA256SUMS.txt`.

Run `Multiwfn_noGUI` or `Multiwfn` (`.exe` on Windows); for Linux and macOS GUI
packages, use the `Multiwfn` launcher. GUI packages need a running X11 display
on Linux and XQuartz on macOS. Configure `Multiwfnpath`, `PATH`, and
`OMP_STACKSIZE` as described in the official manual.

## License and citation

See [LICENSE.txt](LICENSE.txt) for the upstream license terms and required
scientific citations.
