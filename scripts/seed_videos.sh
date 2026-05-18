#!/usr/bin/env bash
# seed_videos.sh — instructions for fetching public test videos for the ML
# pipeline. This script is intentionally a NO-OP: it only prints the
# commented commands you would run on a developer machine. We do this on
# purpose so that:
#   * the repo never carries large binaries,
#   * the repo never silently downloads gigabytes during CI,
#   * licensing of every clip stays reviewable per item.
#
# To actually fetch data, copy/paste the commands below into a shell or
# uncomment them locally. Do NOT commit the downloaded files.
#
# All listed sources are public, free-for-research, with attribution where
# required. Verify checksums before using them in benchmarks.
#
# Layout produced (after manual download):
#   data/videos/cam_A_in.mp4
#   data/videos/cam_A_out.mp4
#   data/videos/cam_B_in.mp4
#   data/videos/cam_B_out.mp4
#   data/videos/CHECKSUMS.sha256
set -euo pipefail

DATA_DIR="${DATA_DIR:-data/videos}"
echo "Target directory: ${DATA_DIR}"
echo
echo "This script is a documented NO-OP. Read it, then run the commands you want."
echo

cat <<'EOF'
# ---------------------------------------------------------------------------
# 1) UA-DETRAC test sequences (vehicle detection/tracking, free for research)
#    https://detrac-db.rit.albany.edu/   (registration may be required)
#    Pick a daytime highway sequence (e.g., MVI_40171) and rename to cam_A_in.mp4
# ---------------------------------------------------------------------------
# mkdir -p "${DATA_DIR}"
# # Replace <URL> with the direct mirror you have access to.
# # curl -L --output "${DATA_DIR}/cam_A_in.mp4" "<URL_TO_MVI_40171>"
# # sha256: <fill-after-download>

# ---------------------------------------------------------------------------
# 2) MIO-TCD localisation challenge (CC-BY)
#    https://tcd.miovision.com/
#    Use a clip that shows traffic from a fixed CCTV angle.
# ---------------------------------------------------------------------------
# # curl -L --output "${DATA_DIR}/cam_A_out.mp4" "<URL_TO_MIO_TCD_CLIP>"
# # sha256: <fill-after-download>

# ---------------------------------------------------------------------------
# 3) AI City Challenge sample (track 1 / 4) — academic use
#    https://www.aicitychallenge.org/
#    Useful for the "opposite direction" cameras (cam_B_*).
# ---------------------------------------------------------------------------
# # curl -L --output "${DATA_DIR}/cam_B_in.mp4" "<URL_TO_AICITY_SAMPLE>"
# # sha256: <fill-after-download>

# ---------------------------------------------------------------------------
# 4) Pexels traffic free clips — quick demo data, CC0
#    https://www.pexels.com/search/videos/traffic/
#    Pick a fixed-cam highway clip and rename it.
# ---------------------------------------------------------------------------
# # curl -L --output "${DATA_DIR}/cam_B_out.mp4" "<URL_TO_PEXELS_CLIP>"
# # sha256: <fill-after-download>

# ---------------------------------------------------------------------------
# After downloading, regenerate checksums:
# ---------------------------------------------------------------------------
# (cd "${DATA_DIR}" && sha256sum cam_*.mp4 > CHECKSUMS.sha256)
# cat "${DATA_DIR}/CHECKSUMS.sha256"
EOF

echo
echo "No files were downloaded. Edit this script if you want to enable downloads locally."
exit 0
