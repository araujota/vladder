#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX="${HOME}/.local/share/vladder"
SKILL_DIR="${CODEX_HOME:-${HOME}/.codex}/skills"
PACKAGE_SOURCE="${ROOT_DIR}"
INSTALL_SYSTEM=1
INSTALL_ALIVE2=1
DRY_RUN=0
ALIVE2_COMMIT="c0f5434f402ad91714ee0952f686cd0f524920ad"

usage() {
  printf '%s\n' "Usage: scripts/install.sh [options]"
  printf '%s\n' "  --prefix PATH              installation prefix (default: ${PREFIX})"
  printf '%s\n' "  --skill-dir PATH           parent directory for the vladder skill"
  printf '%s\n' "  --package PATH             source tree, sdist, or wheel to install"
  printf '%s\n' "  --no-system-packages       reuse existing system tools"
  printf '%s\n' "  --without-alive2           do not build Alive2 when alive-tv is absent"
  printf '%s\n' "  --dry-run                  print planned commands without executing"
}

while (($#)); do
  case "$1" in
    --prefix) PREFIX="$2"; shift 2 ;;
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    --package) PACKAGE_SOURCE="$2"; shift 2 ;;
    --no-system-packages) INSTALL_SYSTEM=0; shift ;;
    --without-alive2) INSTALL_ALIVE2=0; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

run() {
  printf '+'
  printf ' %q' "$@"
  printf '\n'
  if ((DRY_RUN == 0)); then
    "$@"
  fi
}

if ((INSTALL_SYSTEM)); then
  if command -v apt-get >/dev/null 2>&1; then
    SUDO=()
    if ((EUID != 0)); then
      command -v sudo >/dev/null 2>&1 || { printf '%s\n' "sudo is required for system packages" >&2; exit 1; }
      SUDO=(sudo)
    fi
    run "${SUDO[@]}" apt-get update
    run "${SUDO[@]}" apt-get install -y \
      build-essential ca-certificates cmake curl git ninja-build pkg-config \
      python3 python3-pip python3-venv clang-20 llvm-20 llvm-20-dev llvm-20-tools \
      lld-20 z3 libz3-dev linux-tools-common binutils
  else
    printf '%s\n' "No apt-get found; validating an existing toolchain instead."
  fi
fi

run mkdir -p "${PREFIX}/bin" "${PREFIX}/src" "${PREFIX}/build"
run python3 -m venv "${PREFIX}/venv"
run "${PREFIX}/venv/bin/python" -m pip install --upgrade pip setuptools wheel
run "${PREFIX}/venv/bin/python" -m pip install "${PACKAGE_SOURCE}"
run ln -sfn "${PREFIX}/venv/bin/vladder" "${PREFIX}/bin/vladder"
run ln -sfn "${PREFIX}/venv/bin/silicontune" "${PREFIX}/bin/silicontune"

export PATH="${PREFIX}/bin:${PATH}"

if ! command -v alive-tv >/dev/null 2>&1 && ((INSTALL_ALIVE2)); then
  ALIVE_SOURCE="${PREFIX}/src/alive2"
  ALIVE_BUILD="${PREFIX}/build/alive2"
  if [[ ! -d "${ALIVE_SOURCE}/.git" ]]; then
    run git clone https://github.com/AliveToolkit/alive2.git "${ALIVE_SOURCE}"
  fi
  run git -C "${ALIVE_SOURCE}" fetch --tags origin
  run git -C "${ALIVE_SOURCE}" checkout --detach "${ALIVE2_COMMIT}"
  run cmake -S "${ALIVE_SOURCE}" -B "${ALIVE_BUILD}" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release -DBUILD_TV=ON -DLLVM_DIR="$(llvm-config-20 --cmakedir)"
  run cmake --build "${ALIVE_BUILD}" --target alive-tv
  run ln -sfn "${ALIVE_BUILD}/alive-tv" "${PREFIX}/bin/alive-tv"
fi

run "${PREFIX}/bin/vladder" skill install --target "${SKILL_DIR}" --force
if ((INSTALL_ALIVE2)); then
  run "${PREFIX}/bin/vladder" doctor --strict
else
  run "${PREFIX}/bin/vladder" doctor
fi

printf '%s\n' "vLadder installed under ${PREFIX}."
printf '%s\n' "Add ${PREFIX}/bin to PATH to use the release."
