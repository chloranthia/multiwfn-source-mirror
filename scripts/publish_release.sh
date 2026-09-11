#!/usr/bin/env bash
set -euo pipefail

assets=(release-assets/*)
api="${GITHUB_API_URL}/repos/${GITHUB_REPOSITORY}/releases/tags/${RELEASE_TAG}"
status="$(curl --silent --show-error --retry 3 \
  --output "$RUNNER_TEMP/release.json" --write-out '%{http_code}' \
  --header 'Accept: application/vnd.github+json' \
  --header "Authorization: Bearer ${GH_TOKEN}" \
  "$api")"
case "$status" in
  200)
    gh release upload "$RELEASE_TAG" "${assets[@]}" --clobber
    gh release edit "$RELEASE_TAG" \
      --title "$RELEASE_TITLE" \
      --notes-file release-notes.md
    ;;
  404)
    gh release create "$RELEASE_TAG" "${assets[@]}" \
      --title "$RELEASE_TITLE" \
      --notes-file release-notes.md \
      --latest \
      --target "$TARGET_SHA"
    ;;
  *)
    cat "$RUNNER_TEMP/release.json" >&2
    echo "GitHub returned HTTP ${status} while checking releases." >&2
    exit 1
    ;;
esac

expected="$(printf '%s\n' "${assets[@]##*/}" | LC_ALL=C sort)"
actual="$(gh release view "$RELEASE_TAG" --json assets --jq '.assets[].name' | LC_ALL=C sort)"
while IFS= read -r asset; do
  [[ -n "$asset" ]] || continue
  if ! grep -Fxq -- "$asset" <<<"$expected"; then
    gh release delete-asset "$RELEASE_TAG" "$asset" --yes
  fi
done <<<"$actual"
actual="$(gh release view "$RELEASE_TAG" --json assets --jq '.assets[].name' | LC_ALL=C sort)"
if [[ "$actual" != "$expected" ]]; then
  printf 'Expected release assets:\n%s\nActual release assets:\n%s\n' "$expected" "$actual" >&2
  exit 1
fi
