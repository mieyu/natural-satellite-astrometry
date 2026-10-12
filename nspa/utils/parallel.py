"""Conservative process counts for image stages with large temporary arrays."""

import math
import os

import psutil
from astropy.io import fits


def image_worker_limit(requested, n_files, image_paths=(), bytes_per_pixel=192):
    """0 selects at most two workers; explicit limits also obey the RAM budget.

    Reserve half of currently available memory for the UI, parent process and
    other applications. Pixel costs include temporary arrays; the fixed cost
    covers Python, imported libraries and JIT compilation. These are estimates,
    not an allocation guarantee. Unknown memory or image sizes use one worker.
    """
    cap = max(1, min(n_files, os.cpu_count() or 1, requested or 2))
    if cap == 1:
        return 1
    try:
        largest = 0
        for path in image_paths:
            header = fits.getheader(path)
            largest = max(largest, math.prod(
                int(header[f"NAXIS{i}"]) for i in range(1, int(header["NAXIS"]) + 1)
            ))
        if largest <= 0:
            return 1
        per_worker = 384 * 1024**2 + largest * bytes_per_pixel
        budget = int(psutil.virtual_memory().available * 0.5)
        return max(1, min(cap, budget // per_worker))
    except (OSError, ValueError, KeyError, psutil.Error):
        return 1
