#!/usr/bin/env bash
set -euo pipefail

entry_binary="$1"
shift
dependency_roots=("$@")
bundle_dir="$(dirname "$entry_binary")/lib"
mkdir -p "$bundle_dir"

processed="$(mktemp)"
diagnostics="$(mktemp)"
trap 'rm -f "$processed" "$diagnostics"' EXIT

resolve_dependency() {
  local dependency="$1"
  local binary="$2"
  local name="${dependency##*/}"
  local candidate
  local rpath
  local base
  local root
  local resolved
  case "$dependency" in
    @loader_path/*)
      candidate="$(dirname "$binary")/${dependency#@loader_path/}"
      if test -f "$candidate"; then
        printf '%s\n' "$candidate"
        return 0
      fi
      ;;
    @executable_path/*)
      candidate="$(dirname "$entry_binary")/${dependency#@executable_path/}"
      if test -f "$candidate"; then
        printf '%s\n' "$candidate"
        return 0
      fi
      ;;
    @rpath/*)
      while IFS= read -r rpath; do
        case "$rpath" in
          @loader_path/*)
            base="$(dirname "$binary")/${rpath#@loader_path/}"
            ;;
          @executable_path/*)
            base="$(dirname "$entry_binary")/${rpath#@executable_path/}"
            ;;
          *)
            base="$rpath"
            ;;
        esac
        candidate="$base/${dependency#@rpath/}"
        if test -f "$candidate"; then
          printf '%s\n' "$candidate"
          return 0
        fi
      done < <(otool -l "$binary" | awk '
        $1 == "cmd" { is_rpath = ($2 == "LC_RPATH") }
        is_rpath && $1 == "path" { print $2; is_rpath = 0 }
      ')
      ;;
    /*)
      if test -f "$dependency"; then
        printf '%s\n' "$dependency"
        return 0
      fi
      ;;
  esac
  for root in "${dependency_roots[@]}"; do
    if test -f "$root/lib/$name"; then
      printf '%s\n' "$root/lib/$name"
      return 0
    fi
    resolved="$(find -L "$root" -type f -name "$name" -print -quit 2>/dev/null || true)"
    if test -n "$resolved"; then
      printf '%s\n' "$resolved"
      return 0
    fi
  done
  return 1
}

rewrite_install_name() {
  local binary="${*: -1}"
  local signature_warning="install_name_tool: warning: changes being made to the file will invalidate the code signature in: $binary"
  local line
  local status

  # Removing a signature first can leave arm64 dylibs with an invalid __LINKEDIT.
  # The rewritten package files are signed and verified after all changes.
  if install_name_tool "$@" 2>"$diagnostics"; then
    while IFS= read -r line || [[ -n "$line" ]]; do
      case "$line" in
        "$signature_warning" | */"$signature_warning" | \
          "$signature_warning (for architecture arm64)" | \
          */"$signature_warning (for architecture arm64)") ;;
        *) printf '%s\n' "$line" >&2 ;;
      esac
    done < "$diagnostics"
  else
    status=$?
    cat "$diagnostics" >&2
    return "$status"
  fi
}

bundle_binary() {
  local binary="$1"
  local dependency
  local resolved
  local name
  local bundled
  local replacement_prefix
  if [[ "$binary" == "$entry_binary" ]]; then
    replacement_prefix='@loader_path/lib'
  else
    replacement_prefix='@loader_path'
  fi

  while IFS= read -r dependency; do
    case "$dependency" in
      # XQuartz provides these GLX libraries at runtime for macOS GUI builds.
      /usr/lib/* | /System/Library/* | /usr/X11/lib/libGL.* | /usr/X11/lib/libGLU.* | /opt/X11/lib/libGL.* | /opt/X11/lib/libGLU.*)
        continue
        ;;
    esac
    if ! resolved="$(resolve_dependency "$dependency" "$binary")"; then
      echo "Unable to resolve non-system macOS dependency: $dependency" >&2
      return 1
    fi
    name="${resolved##*/}"
    bundled="$bundle_dir/$name"
    if ! test -f "$bundled"; then
      cp -L "$resolved" "$bundled"
    fi
    if ! grep -Fqx "$bundled" "$processed" 2>/dev/null; then
      printf '%s\n' "$bundled" >>"$processed"
      rewrite_install_name -id "@loader_path/$name" "$bundled"
      bundle_binary "$bundled"
    fi
    rewrite_install_name -change "$dependency" "$replacement_prefix/$name" "$binary"
  done < <(otool -L "$binary" | tail -n +2 | awk '{print $1}')
}

bundle_binary "$entry_binary"
if otool -L "$entry_binary" "$bundle_dir"/* |
  grep -E '/opt/homebrew/|/usr/local/(Cellar|opt)/'; then
  echo 'Bundled package still refers to Homebrew paths' >&2
  exit 1
fi

while IFS= read -r bundled; do
  codesign --force --sign - "$bundled"
  codesign --verify "$bundled"
done < "$processed"
codesign --force --sign - "$entry_binary"
codesign --verify "$entry_binary"
