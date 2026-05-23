"""object_N.out 与 O-C 文本产物适配器。"""

import os

from adias.domain.models import ObjectObservation, OCStats
from adias.io.text_io import (
    read_object_out,
    sort_output_file,
    write_comoc_lines,
    write_object_result,
    write_oc_stat,
)


def read_object_residuals(filepath):
    return read_object_out(filepath)


def sort_object_output(filepath):
    return sort_output_file(filepath)


def open_object_output_files(out_directory, obj_total):
    return {
        obj: open(
            os.path.join(out_directory, f"object_{obj}.out"), "w", encoding="utf-8"
        )
        for obj in range(1, obj_total + 1)
    }


def close_object_output_files(object_out_files):
    for f in object_out_files.values():
        f.close()


def sort_object_outputs(out_directory, obj_total):
    for obj in range(1, obj_total + 1):
        sort_object_output(os.path.join(out_directory, f"object_{obj}.out"))


def write_object_observation(file_handle, observation, hh, mm, ss, exptime, field_angle):
    if not isinstance(observation, ObjectObservation):
        raise TypeError("observation 必须是 ObjectObservation")
    return write_object_result(
        file_handle,
        observation.year,
        observation.month,
        observation.day_fraction,
        observation.obs_ra,
        observation.obs_de,
        observation.eph_ra,
        observation.eph_de,
        observation.sigma,
        hh,
        mm,
        ss,
        exptime,
        str(observation.fits_file),
        field_angle,
    )


def write_oc_stats(filepath, stats, oc_limit, mean_limit):
    if not isinstance(stats, OCStats):
        raise TypeError("stats 必须是 OCStats")
    return write_oc_stat(
        filepath,
        stats.raw_count,
        stats.raw_mean_ra,
        stats.raw_mean_de,
        stats.raw_std_ra,
        stats.raw_std_de,
        stats.kept_count,
        stats.mean_ra,
        stats.mean_de,
        stats.std_ra,
        stats.std_de,
        stats.iterations,
        oc_limit,
        mean_limit,
    )


__all__ = [
    "read_object_residuals",
    "open_object_output_files",
    "close_object_output_files",
    "sort_object_outputs",
    "sort_object_output",
    "write_object_observation",
    "write_object_result",
    "write_oc_stat",
    "write_oc_stats",
    "write_comoc_lines",
]
