#!/usr/bin/env bash
# Install ffmpeg + ffprobe on a GitHub Actions Ubuntu runner.
#
# Tries static builds first, then apt. Each download is checked with `xz -t`
# before it is unpacked: johnvansickle.com has started answering with an HTTP
# 200 "One moment, please..." bot-check page instead of the archive, which wget
# counts as a success and tar then chokes on.
#
# Sources, in order:
#   1. johnvansickle.com static release (historical default)
#   2. BtbN/FFmpeg-Builds on GitHub Releases (GitHub-hosted, so it is up
#      whenever the runner can reach GitHub at all)
#   3. apt (pulls in the multimedia stack; broke once when libcaca0 was
#      yanked from noble-updates, hence last)
set -uo pipefail

SOURCES=(
  "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
  "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz"
)

SUDO=""
[ "$(id -u)" -ne 0 ] && SUDO="sudo"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

try_static() {
  local url="$1" archive="$work/ffmpeg.tar.xz" attempt
  for attempt in 1 2 3; do
    rm -f "$archive"
    if wget -q --tries=1 --timeout=60 "$url" -O "$archive" && xz -t "$archive" 2>/dev/null; then
      rm -rf "$work/x" && mkdir -p "$work/x"
      tar -xJf "$archive" -C "$work/x" || return 1
      local ffmpeg ffprobe
      ffmpeg="$(find "$work/x" -type f -name ffmpeg | head -n1)"
      ffprobe="$(find "$work/x" -type f -name ffprobe | head -n1)"
      [ -n "$ffmpeg" ] && [ -n "$ffprobe" ] || return 1
      $SUDO install -m 755 "$ffmpeg" "$ffprobe" /usr/local/bin/ || return 1
      return 0
    fi
    echo "  attempt ${attempt}: download failed or was not an xz archive; retrying in $((attempt * 5))s"
    sleep $((attempt * 5))
  done
  return 1
}

installed=""
for url in "${SOURCES[@]}"; do
  echo "Trying ffmpeg static build: $url"
  if try_static "$url"; then
    installed="$url"
    break
  fi
  echo "  gave up on this source."
done

if [ -z "$installed" ]; then
  echo "No static build worked; falling back to apt."
  $SUDO apt-get update && $SUDO apt-get install -y ffmpeg || exit 1
fi

ffmpeg -version | head -n1 && ffprobe -version | head -n1
