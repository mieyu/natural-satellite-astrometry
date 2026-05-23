"""DS9 region 文件适配器。"""

from adias.domain.models import DetectedStar
from adias.domain.matching import match_result_to_legacy
from adias.io.text_io import read_reg_file, write_ref_file, write_reg_file


def read_detection_region(regfile):
    return read_reg_file(regfile)


def write_reference_region(filename, result):
    return write_ref_file(filename, match_result_to_legacy(result))


def read_detected_stars(regfile):
    det_x, det_y, det_flux, det_snr = read_reg_file(regfile)
    return [
        DetectedStar(x=x, y=y, flux=flux, snr=snr)
        for x, y, flux, snr in zip(det_x, det_y, det_flux, det_snr)
    ]


def write_detected_region(reg_path, stars, bkgd, bkgdsigma, snr_threshold):
    legacy = [
        {
            "starx": s.x,
            "stary": s.y,
            "sumi": s.flux,
            "snr": s.snr,
            "star_id": s.star_id,
            "star_pix": s.pixel_count,
            "overflag": 1 if s.saturated else 0,
        }
        for s in stars
    ]
    return write_reg_file(reg_path, legacy, bkgd, bkgdsigma, snr_threshold)
