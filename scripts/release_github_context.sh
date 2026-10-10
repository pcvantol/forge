#!/usr/bin/env bash
# Owning Forge production-release boundary; never infer from cwd or GH_REPO.
if [[ "${GITHUB_REPOSITORY:-}" != pcvantol/forge || "${GITHUB_SERVER_URL:-}" != https://github.com ]]; then
  echo 'FORGE_RELEASE_CONTEXT_REFUSED: expected owning pcvantol/forge on https://github.com' >&2
  return 1
fi
export GH_HOST=github.com
FORGE_RELEASE_REPOSITORY=github.com/pcvantol/forge

# Distinguish absent receipt from failed readback; retain immutable exact bytes.
forge_retain_release_receipt() {
  local tag="$1" receipt="$2" readback assets
  test "$(gh release view "$tag" --repo "$FORGE_RELEASE_REPOSITORY" --json targetCommitish --jq .targetCommitish)" = "$SOURCE_SHA" || return 1
  assets="$(gh release view "$tag" --repo "$FORGE_RELEASE_REPOSITORY" --json assets --jq '.assets[].name')" || return 1
  readback="$(mktemp -d "$RUNNER_TEMP/forge-receipt-readback-XXXXXX")" || return 1
  if ! printf '%s\n' "$assets" | grep -Fxq -- "$receipt"; then
    gh release upload "$tag" "$receipt" --repo "$FORGE_RELEASE_REPOSITORY" || return 1
  fi
  gh release download "$tag" --repo "$FORGE_RELEASE_REPOSITORY" --pattern "$receipt" --dir "$readback" || return 1
  cmp "$receipt" "$readback/$receipt" || return 1
  rm -rf -- "$readback"
  test ! -e "$readback" && test ! -L "$readback"
}
