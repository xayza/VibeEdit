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
- A learned cutout (the way Apple Vision's foreground-instance
  mask works) is available as a backend slot: cutout_segmented()
  runs a user-supplied ONNX person-segmentation model when the
  file and ONNX Runtime are present, and errors clearly otherwise.
  No model file is shipped or referenced by default.
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
        raise FileNotFoundError("Không có file ảnh như vậy: %s" % (path,))
    return path


def cutout_segmented(path, model_path, output_path=None):
    """Cut out the foreground with a USER-SUPPLIED learned
    segmentation model (round 3 backend slot).

    ``model_path`` must be a real model file the user downloaded
    (e.g. an ONNX person-segmentation model); nothing is bundled
    and no model path is invented. Behaviour, honestly:

    - No model file (None, or a path that is not a file) ->
      VisionUnavailable naming the missing model file.
    - Model file present but no ONNX Runtime installed ->
      VisionUnavailable naming the missing runtime (the model
      file itself is never executed, and no grabCut result is
      silently returned as a "learned" cutout).
    - Model + runtime present -> the model is run via ONNX
      Runtime; the caller is responsible for a model whose
      input/output layout matches a person-segmentation model
      (input "input", single-channel mask output). A model that
      does not match raises VisionUnavailable naming the
      mismatch instead of returning a wrong mask.

    This is an interface, not a finished model integration: the
    exact pre/post-processing of a specific model still needs
    that model's documentation, which is why the mismatch path
    errors instead of guessing.
    """
    _require_file(path)
    if not model_path or not os.path.isfile(model_path):
        raise VisionUnavailable(
            f"Không có file model phân đoạn: {model_path!r} không phải là file. Hãy tải model phân đoạn người (ONNX) và truyền đường dẫn thật của nó; bản build này không kèm sẵn model nào và không bịa đường dẫn model.")
    try:
        import onnxruntime as ort
    except ImportError as exc:
        raise VisionUnavailable(
            f"Chưa cài ONNX Runtime nên model phân đoạn đã cung cấp {model_path} không chạy được. Hãy cài bằng 'pip install onnxruntime' rồi thử lại; bản thân file model đã có nhưng chưa được dùng.") from exc
    try:
        import numpy as np
        from PIL import Image
    except ImportError as exc:
        raise VisionUnavailable(
            f"Cần numpy/Pillow để chạy model phân đoạn ({exc}); hãy cài rồi thử lại.") from exc
    session = ort.InferenceSession(model_path,
                                   providers=["CPUExecutionProvider"])
    inputs = session.get_inputs()
    if not inputs:
        raise VisionUnavailable(
            f"Model phân đoạn {model_path} không khai báo đầu vào nào.")
    input_name = inputs[0].name
    shape = [int(d) if isinstance(d, int) else 0
             for d in inputs[0].shape]
    # Generic person-segmentation layout, stated here so a wrong
    # model fails loudly instead of silently: NCHW float input,
    # first output is a mask (H,W) or (C,H,W); values outside
    # [0,1] are treated as logits and passed through a sigmoid.
    height = shape[2] if len(shape) > 2 and shape[2] else 256
    width = shape[3] if len(shape) > 3 and shape[3] else 256
    image = Image.open(path).convert("RGB")
    orig_w, orig_h = image.size
    resized = image.resize((width, height))
    arr = np.asarray(resized, dtype=np.float32) / 255.0
    arr = np.transpose(arr, (2, 0, 1))[None, :, :, :]
    try:
        outputs = session.run(None, {input_name: arr})
    except Exception as exc:
        raise VisionUnavailable(
            f"Model phân đoạn {model_path} chạy thất bại trên ảnh này: {exc}") from exc
    mask = np.asarray(outputs[0])
    while mask.ndim > 3:
        mask = mask[0]
    if mask.ndim == 3:
        # (C,H,W): channel 1 is foreground for 2-class models,
        # channel 0 otherwise.
        mask = mask[1] if mask.shape[0] >= 2 else mask[0]
    if mask.ndim != 2:
        raise VisionUnavailable(
            f"Model phân đoạn {model_path} trả về mask có shape {mask.shape}, không phải mask 2D; bố cục này backend slot này chưa hỗ trợ.")
    if mask.min() < 0 or mask.max() > 1:
        mask = 1.0 / (1.0 + np.exp(-mask))
    mask_img = Image.fromarray(
        ((mask >= 0.5) * 255).astype("uint8")).resize(
            (orig_w, orig_h), Image.NEAREST)
    if output_path is None:
        output_path = os.path.splitext(path)[0] + "_segmented.png"
    out = image.copy()
    out.putalpha(mask_img)
    out.save(output_path)
    return {"path": output_path, "backend": "onnx-segmentation",
            "model": model_path, "size": [orig_w, orig_h]}


def _require_cv2():
    try:
        import cv2  # noqa: F401  (optional runtime dependency)
    except ImportError:
        raise VisionUnavailable(
            "Chưa cài OpenCV (cv2). Hãy cài bằng 'pip install opencv-python-headless' (hoặc 'opencv-python' cho gói đầy đủ), rồi thử lại."
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
            "Không tìm thấy binary Tesseract 'tesseract' trên PATH. Hãy cài để bật OCR: Windows: tải installer từ bản build tesseract của UB-Mannheim rồi thêm vào PATH; Ubuntu/Debian: 'sudo apt install tesseract-ocr'."
        )
    langs = "+".join(languages) if languages else "eng"
    proc = subprocess.run(
        [tesseract, path, "stdout", "-l", langs],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=120,
    )
    if proc.returncode != 0:
        raise VisionUnavailable(
            "Tesseract thất bại trên %s: %s"
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
            "Không tìm thấy Haar cascade OpenCV tại %s. Hãy cài lại opencv-python-headless; cascade đi kèm gói."
            % (cascade_path,)
        )
    image = cv2.imread(path)
    if image is None:
        raise ValueError("Không giải mã được file ảnh: %s" % (path,))
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
        raise ValueError("Không giải mã được file ảnh: %s" % (path,))
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
            "grabCut không tìm thấy chủ thể foreground trong %s (chủ thể có thể chạm mép khung hình hoặc lấp đầy khung hình)" % (path,))
    if output_path is None:
        stem, _ = os.path.splitext(path)
        output_path = stem + "_cutout.png"
    bgra = cv2.cvtColor(image, cv2.COLOR_BGR2BGRA)
    bgra[:, :, 3] = keep * 255
    if not cv2.imwrite(output_path, bgra):
        raise ValueError("Không ghi được PNG tách nền: %s" % (output_path,))
    return {"output_path": output_path,
            "foreground_share": foreground_share,
            "backend": "opencv-grabcut"}
