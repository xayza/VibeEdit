"""Vision analysis for the Windows port: OCR, face detection, cutout.

Windows equivalents of the original macOS vision plugin
(``VibeEdit/Plugins/vision``), which used Apple Vision on macOS:
``VNDetectFaceRectanglesRequest`` / ``VNDetectHumanRectanglesRequest``
(faces), ``VNRecognizeTextRequest`` (text) and
``VNGenerateForegroundInstanceMaskRequest`` (cutout). Apple Vision does
not exist on Windows, so the Windows backends are:

- OCR: the Tesseract binary (``shutil.which("tesseract")``).
- Faces: OpenCV Haar cascades (``cv2``), when installed.
- Cutout: OpenCV grabCut (``cv2``), when installed.

Rules, enforced by the tests:

- ``cv2`` / Tesseract are optional runtime-only dependencies. Neither
  is imported at module top level, so importing this module never
  fails when they are absent.
- No bundled binaries and no model files are referenced: nothing here
  points at a model file that does not exist in the repo.
- Every function returns real results or raises — never a fake
  detection. In particular, when the backend is absent the function
  raises :class:`VisionUnavailable` (it must NOT return an empty face
  list or empty text as if a scan had run).
- A better cutout than grabCut (e.g. a learned person-segmentation
  model, the way Apple Vision's foreground-instance mask works) is
  REMAINING work: it would need a model file the user downloads
  separately, and no such model is shipped or referenced here.
"""

from __future__ import annotations

import os
import shutil
import subprocess


class VisionUnavailable(Exception):
    """A vision backend is missing on this machine.

    The message always names the missing binary/package and how to
    install it, so the UI can show an actionable error instead of a
    silent empty result.
    """


def _require_file(path):
    if not os.path.isfile(path):
        raise FileNotFoundError("No such image file: %s" % (path,))
    return path


def _require_cv2():
    try:
        import cv2  # noqa: F401  (optional runtime dependency)
    except ImportError:
        raise VisionUnavailable(
            "OpenCV (cv2) is not installed. Install it with "
            "'pip install opencv-python-headless' (or 'opencv-python' "
            "for the full package), then retry."
        )
    return cv2


def ocr_image(path, languages=None):
    """Return on-screen text in an image, via Tesseract if present.

    Returns ``{"text": str, "lines": [str, ...], "backend": "tesseract"}``
    where ``lines`` are the non-empty text lines, top to bottom.
    ``languages`` is a list of Tesseract language codes (default
    ``["eng"]``); they are joined with ``+`` for Tesseract's ``-l``.

    Raises VisionUnavailable when the ``tesseract`` binary is absent
    or when Tesseract itself fails on the file.
    """
    _require_file(path)
    tesseract = shutil.which("tesseract")
    if tesseract is None:
        raise VisionUnavailable(
            "Tesseract binary 'tesseract' not found on PATH. Install it "
            "to enable OCR: Windows: download the installer from the "
            "UB-Mannheim tesseract builds and add it to PATH; "
            "Ubuntu/Debian: 'sudo apt install tesseract-ocr'."
        )
    langs = "+".join(languages) if languages else "eng"
    proc = subprocess.run(
        [tesseract, path, "stdout", "-l", langs],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=120,
    )
    if proc.returncode != 0:
        raise VisionUnavailable(
            "Tesseract failed on %s: %s"
            % (path, (proc.stderr or "").strip() or "unknown error")
        )
    text = proc.stdout or ""
    lines = [ln for ln in (line.strip() for line in text.splitlines()) if ln]
    return {"text": text, "lines": lines, "backend": "tesseract"}


def detect_faces(path):
    """Return face boxes in an image, via OpenCV Haar cascades.

    Returns ``{"faces": [{"x", "y", "width", "height"}], "count": int,
    "backend": "opencv-haar"}`` with boxes in pixels from the top left
    of the image (the original reports shares of the picture; pixel
    boxes are returned here so callers need no image size, and shares
    can be derived by dividing by the image dimensions). An empty
    ``faces`` list here means a real scan ran and found nothing.

    Raises VisionUnavailable when OpenCV or its Haar cascade is
    absent, ValueError when the image cannot be decoded.
    """
    _require_file(path)
    cv2 = _require_cv2()
    cascade_path = os.path.join(
        cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
    if not os.path.isfile(cascade_path):
        raise VisionUnavailable(
            "OpenCV Haar cascade not found at %s. Reinstall "
            "opencv-python-headless; the cascade ships with the package."
            % (cascade_path,)
        )
    image = cv2.imread(path)
    if image is None:
        raise ValueError("Could not decode image file: %s" % (path,))
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    cascade = cv2.CascadeClassifier(cascade_path)
    rects = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
    faces = [{"x": int(x), "y": int(y), "width": int(w), "height": int(h)}
             for (x, y, w, h) in rects]
    return {"faces": faces, "count": len(faces), "backend": "opencv-haar"}


def cutout(path, output_path=None):
    """Cut the foreground subject out of an image via OpenCV grabCut.

    Writes a PNG with an alpha channel (foreground opaque, background
    transparent) and returns ``{"output_path": str,
    "foreground_share": float, "backend": "opencv-grabcut"}`` where
    ``foreground_share`` is the fraction of pixels kept. When
    ``output_path`` is omitted, ``<stem>_cutout.png`` next to the
    source is used.

    grabCut is seeded with a rectangle inset 10% from each border, so
    it works best when the subject does not touch the frame edge; a
    learned segmentation model would do better and remains future
    work (see the module docstring — no model file is referenced).

    Raises VisionUnavailable when OpenCV is absent, ValueError when
    the image cannot be decoded or grabCut finds no foreground.
    """
    _require_file(path)
    cv2 = _require_cv2()
    image = cv2.imread(path, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not decode image file: %s" % (path,))
    height, width = image.shape[:2]
    inset_x, inset_y = max(1, width // 10), max(1, height // 10)
    rect = (inset_x, inset_y, width - 2 * inset_x, height - 2 * inset_y)
    # numpy is a hard dependency of cv2 itself, so importing it here
    # is safe whenever cv2 imported above succeeded.
    import numpy as np
    mask = np.zeros((height, width), np.uint8)
    bgd = np.zeros((1, 65), np.float64)
    fgd = np.zeros((1, 65), np.float64)
    cv2.grabCut(image, mask, rect, bgd, fgd, 5, cv2.GC_INIT_WITH_RECT)
    keep = ((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD)).astype("uint8")
    foreground_share = float(keep.mean()) if keep.size else 0.0
    if foreground_share <= 0.0:
        raise ValueError(
            "grabCut found no foreground subject in %s (subject may "
            "touch the frame edge or fill the whole frame)" % (path,))
    if output_path is None:
        stem, _ = os.path.splitext(path)
        output_path = stem + "_cutout.png"
    bgra = cv2.cvtColor(image, cv2.COLOR_BGR2BGRA)
    bgra[:, :, 3] = keep * 255
    if not cv2.imwrite(output_path, bgra):
        raise ValueError("Could not write cutout PNG: %s" % (output_path,))
    return {"output_path": output_path,
            "foreground_share": foreground_share,
            "backend": "opencv-grabcut"}
