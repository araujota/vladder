#!/usr/bin/env bash
set -euo pipefail

PREFIX="${HOME}/.local/share/vladder/toolchains"
ZIG_VERSION="0.16.0"
ZIG_SHA256="70e49664a74374b48b51e6f3fdfbf437f6395d42509050588bd49abe52ba3d00"
JULIA_VERSION="1.12.6"
JULIA_SHA256="bbabf3bef19421a9dbd24a767d807606ab85e444323b5a1c73ffe293fa3d079a"

usage() {
  printf '%s\n' "Usage: scripts/bootstrap_language_toolchains.sh [--prefix PATH]"
}

while (($#)); do
  case "$1" in
    --prefix) PREFIX="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
  printf '%s\n' \
    "Automatic Zig/Julia bootstrap currently supports Linux x86_64 only; install both tools manually." >&2
  exit 1
fi

mkdir -p "${PREFIX}/bin" "${PREFIX}/downloads"

if ! command -v zig >/dev/null 2>&1 && [[ ! -x "${PREFIX}/zig-${ZIG_VERSION}/zig" ]]; then
  archive="${PREFIX}/downloads/zig-x86_64-linux-${ZIG_VERSION}.tar.xz"
  extracted="${PREFIX}/zig-x86_64-linux-${ZIG_VERSION}"
  curl -fL "https://ziglang.org/download/${ZIG_VERSION}/zig-x86_64-linux-${ZIG_VERSION}.tar.xz" -o "${archive}"
  printf '%s  %s\n' "${ZIG_SHA256}" "${archive}" | sha256sum -c -
  tar -xJf "${archive}" -C "${PREFIX}"
  mv "${extracted}" "${PREFIX}/zig-${ZIG_VERSION}"
fi
if ! command -v zig >/dev/null 2>&1; then
  ln -sfn "${PREFIX}/zig-${ZIG_VERSION}/zig" "${PREFIX}/bin/zig"
fi

if ! command -v julia >/dev/null 2>&1 && [[ ! -x "${PREFIX}/julia-${JULIA_VERSION}/bin/julia" ]]; then
  archive="${PREFIX}/downloads/julia-${JULIA_VERSION}-linux-x86_64.tar.gz"
  curl -fL "https://julialang-s3.julialang.org/bin/linux/x64/1.12/julia-${JULIA_VERSION}-linux-x86_64.tar.gz" -o "${archive}"
  printf '%s  %s\n' "${JULIA_SHA256}" "${archive}" | sha256sum -c -
  tar -xzf "${archive}" -C "${PREFIX}"
fi
if ! command -v julia >/dev/null 2>&1; then
  ln -sfn "${PREFIX}/julia-${JULIA_VERSION}/bin/julia" "${PREFIX}/bin/julia"
fi

printf '%s\n' "Zig: $(command -v zig || printf '%s' "${PREFIX}/bin/zig")"
printf '%s\n' "Julia: $(command -v julia || printf '%s' "${PREFIX}/bin/julia")"
