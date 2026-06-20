"""No-reference image-quality metrics (pure numpy/opencv). Lifted verbatim from cull_server.py."""
import cv2
import numpy as np


def lapvar(gray):
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def exposure_metrics(gray):
    """(mean 0..1, highlight-clip frac, shadow-clip frac) on a 0..255 gray region."""
    y = gray.astype(np.float64)
    return float(y.mean()) / 255.0, float((gray >= 250).mean()), float((gray <= 5).mean())


def contrast_rms(gray):
    return float(gray.astype(np.float64).std() / 255.0)


def dynamic_range(gray):
    p1, p99 = np.percentile(gray, [1, 99])
    return float((p99 - p1) / 255.0)


def colorfulness(rgb):
    """Hasler & Suesstrunk (2003) colorfulness; ~0 for black & white."""
    R, G, B = (rgb[:, :, i].astype(np.float64) for i in range(3))
    rg = np.abs(R - G)
    yb = np.abs(0.5 * (R + G) - B)
    return float(np.sqrt(rg.std() ** 2 + yb.std() ** 2)
                 + 0.3 * np.sqrt(rg.mean() ** 2 + yb.mean() ** 2))


def wb_cast(rgb):
    """Gray-world color-cast magnitude in LAB (0 = neutral, larger = stronger tint)."""
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float64)
    return float(np.sqrt((lab[:, :, 1].mean() - 128) ** 2 + (lab[:, :, 2].mean() - 128) ** 2))
