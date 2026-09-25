#!/usr/bin/env bash
# sonar_scan.sh: ejecuta el scanner de SonarQube (docker) para las apps del monorepo.
# Uso: scripts/sonar_scan.sh [api|web|all]
# Token: se toma de $SONAR_TOKEN o de ~/.config/opencode/.env (linea SONAR_TOKEN=...).
# El servidor debe estar accesible en $SONAR_HOST_URL (default http://localhost:9000);
# por eso el contenedor del scanner corre con --network host.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SCANNER_IMAGE="sonarsource/sonar-scanner-cli:11"

target="${1:-all}"
if [[ "${target}" != "api" && "${target}" != "web" && "${target}" != "all" ]]; then
  echo "Uso: $0 [api|web|all]" >&2
  exit 1
fi

# SONAR_TOKEN: entorno > ~/.config/opencode/.env
if [[ -z "${SONAR_TOKEN:-}" && -r "${HOME}/.config/opencode/.env" ]]; then
  SONAR_TOKEN="$(grep -m1 '^SONAR_TOKEN=' "${HOME}/.config/opencode/.env" | cut -d= -f2- | tr -d '"' || true)"
  export SONAR_TOKEN
fi
if [[ -z "${SONAR_TOKEN:-}" ]]; then
  echo "Falta SONAR_TOKEN (definelo en el entorno o en ~/.config/opencode/.env)." >&2
  exit 1
fi

export SONAR_HOST_URL="${SONAR_HOST_URL:-http://localhost:9000}"

scan_app() {
  local dir="$1"
  local base="/usr/src/${dir}"
  local args=(
    "-Dproject.settings=${base}/sonar-project.properties"
    "-Dsonar.projectBaseDir=${base}"
  )

  # Coverage condicional: solo si el reporte existe realmente.
  if [[ -f "${REPO_ROOT}/${dir}/coverage.xml" ]]; then
    args+=("-Dsonar.python.coverage.reportPaths=coverage.xml")
  fi
  # Angular emite coverage/<projectName>/lcov.info; projectName = DeepBDE-web (angular.json).
  if [[ -f "${REPO_ROOT}/${dir}/coverage/DeepBDE-web/lcov.info" ]]; then
    args+=("-Dsonar.javascript.lcov.reportPaths=coverage/DeepBDE-web/lcov.info")
  elif [[ -f "${REPO_ROOT}/${dir}/coverage/lcov.info" ]]; then
    args+=("-Dsonar.javascript.lcov.reportPaths=coverage/lcov.info")
  fi

  echo "[sonar] Escaneando ${dir} -> ${SONAR_HOST_URL}"
  docker run --rm --network host \
    -e SONAR_TOKEN -e SONAR_HOST_URL \
    -v "${REPO_ROOT}:/usr/src" \
    "${SCANNER_IMAGE}" "${args[@]}"
}

case "${target}" in
  api) scan_app "apps/api" ;;
  web) scan_app "apps/web" ;;
  all) scan_app "apps/api"; scan_app "apps/web" ;;
esac

echo "[sonar] Hecho."
