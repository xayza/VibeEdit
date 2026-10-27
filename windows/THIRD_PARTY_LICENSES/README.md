# Third-party licences bundled with the Windows build

## What is in this folder

- `GPLv3.txt` — the full text of the GNU General Public License, version 3
  (29 June 2007), copyright Free Software Foundation, Inc.
  - Source: the official GNU page, `http://www.gnu.org/licenses/gpl-3.0.html`,
    read with a browser on 2026-10-27.
  - The file itself is kept as pure licence text: no provenance header
    was prepended to it, because the licence forbids changing the
    document. This README carries the provenance instead.
  - Transcription note: the text was taken from the HTML rendering of
    that page, so HTML heading markup was stripped and the two link
    artifacts were normalised to plain URLs
    (`<https://fsf.org/>`, `<https://www.gnu.org/licenses/>`,
    `<https://www.gnu.org/licenses/why-not-lgpl.html>`). Wording and
    section order are unchanged; line wrapping follows the rendering.

## Why it is here

The Windows artifact bundles FFmpeg and FFprobe binaries. The CI build
downloads the gyan.dev `ffmpeg-release-essentials` static build, which
is a GPLv3 build, and the artifact must never be described as LGPL.
Distributing those binaries therefore
requires the GPLv3 text plus a corresponding-source offer to travel
with them (GPLv3 section 6).

At packaging time, `scripts/package_licenses.py` (wrapped by
`scripts/package_licenses.bat`) copies this file into
`dist\VibeEdit\THIRD_PARTY_LICENSES\` and generates, next to it:

- `SOURCE_OFFER.txt` — the written offer required by GPLv3 section 6b,
  generated from the ffmpeg/ffprobe binaries actually present in that
  build (their real `-version` first lines and the bundle URL, when one
  was used). Version lines are never hand-written in advance.
- `THIRD_PARTY_NOTICE.txt` — a short summary naming what is GPLv3
  (the bundled FFmpeg/FFprobe binaries) and what is not (VibeEdit's own
  code, which follows the original BashCut MIT licence).

## Rules for distributors

- Never ship `dist\VibeEdit` publicly without the
  `THIRD_PARTY_LICENSES\` folder inside it. The CI workflow verifies
  all three files exist in the artifact and fails the run if any is
  missing; see `windows/CHECK_WINDOWS.md` for the pre-distribution
  checklist.
- Never describe the bundled FFmpeg build as LGPL. It is GPLv3.
- Patent and codec notes are jurisdiction-dependent; nothing here is
  legal advice. A real legal review is still required before a public
  release that bundles codecs.
