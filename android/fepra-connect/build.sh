#!/usr/bin/env bash
set -euo pipefail
src="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
build="${FEPRA_ANDROID_BUILD_DIR:-$HOME/.cache/fepra-connect-build}"
export JAVA_HOME="${JAVA_HOME:-$(brew --prefix openjdk@17)/libexec/openjdk.jdk/Contents/Home}"
gradle_bin="${GRADLE_BIN:-$(brew --prefix gradle@8)/bin/gradle}"
mkdir -p "$build"
rsync -a --delete --exclude .gradle --exclude build "$src/" "$build/"
printf 'sdk.dir=%s\n' "${ANDROID_HOME:-$(brew --prefix)/share/android-commandlinetools}" > "$build/local.properties"
cd "$build"
"$gradle_bin" --no-daemon "$@"
