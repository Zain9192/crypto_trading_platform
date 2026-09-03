#!/usr/bin/env bash
set -euo pipefail

CHECKSTYLE_VERSION="${CHECKSTYLE_VERSION:-14.1.0}"
CHECKSTYLE_CONFIG="${CHECKSTYLE_CONFIG:-config/checkstyle/checkstyle.xml}"

mapfile -t JAVA_FILES < <(
  find . -type f -name '*.java' \
    -not -path './.git/*' \
    -not -path './frontend/node_modules/*' \
    -not -path './frontend/dist/*' \
    -not -path './backend/.venv/*' \
    -print
)

if [[ ${#JAVA_FILES[@]} -eq 0 ]]; then
  echo "No Java source files found. Checkstyle is configured but not applicable to the current Python/TypeScript codebase."
  exit 0
fi

if ! command -v java >/dev/null 2>&1; then
  echo "Java is required to run Checkstyle." >&2
  exit 1
fi

CACHE_DIR="${RUNNER_TEMP:-/tmp}/checkstyle"
JAR_PATH="${CACHE_DIR}/checkstyle-${CHECKSTYLE_VERSION}-all.jar"
mkdir -p "${CACHE_DIR}"

if [[ ! -f "${JAR_PATH}" ]]; then
  curl -fsSL \
    "https://github.com/checkstyle/checkstyle/releases/download/checkstyle-${CHECKSTYLE_VERSION}/checkstyle-${CHECKSTYLE_VERSION}-all.jar" \
    -o "${JAR_PATH}"
fi

java -jar "${JAR_PATH}" -c "${CHECKSTYLE_CONFIG}" "${JAVA_FILES[@]}"
