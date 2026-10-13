"""Rotation acquisition with a known target ephemeris and nominal plate scale.

Radial distances around each possible target are invariant under rotation.
They propose angles; unique star correspondences and an affine fit validate
them. This is an acquisition aid, not an all-sky blind plate solver.
"""

import heapq

import numpy as np
from scipy.spatial import cKDTree

from nspa.domain.astrometry import DEG2RAD, rade2ky, sol_par


def plate_orientation(par, modeltype):
    """Return clockwise angle [0, 360) and x parity at the plate origin.

    Convention: sky = R_clockwise(angle) @ diag(parity, 1) @ detector.
    Polar decomposition separates rotation from scale/shear. For polynomial
    plates this describes the local linear part at their fitted origin.
    """
    half = modeltype // 2
    matrix = np.array([[par[0], par[1]], [par[half], par[half + 1]]])
    if not np.all(np.isfinite(matrix)) or abs(np.linalg.det(matrix)) < 1e-15:
        raise ValueError("底片线性部分退化，无法提取旋转角")
    parity = 1 if np.linalg.det(matrix) > 0 else -1
    u, _, vt = np.linalg.svd(matrix @ np.diag([parity, 1]))
    rotation = u @ vt
    angle = float(np.degrees(np.arctan2(rotation[0, 1], rotation[0, 0])) % 360)
    return angle, parity


def _unique_pairs(predicted, tree, radius):
    distance, catalog = tree.query(predicted, distance_upper_bound=radius)
    # Greedy nearest correspondence: never count the same reference twice.
    used, det_ids, cat_ids = set(), [], []
    for i in np.argsort(distance):
        j = int(catalog[i])
        if np.isfinite(distance[i]) and j not in used:
            used.add(j)
            det_ids.append(i)
            cat_ids.append(j)
    return np.asarray(det_ids, dtype=int), np.asarray(cat_ids, dtype=int)


def acquire_rotation(det_x, det_y, det_flux, pscale, fl, limit_match,
                     obj_ra, obj_de, gaia_ra, gaia_de, gaia_mag, modeltype):
    """Return coarse-match dictionary, or None when no validated solution exists.

    Proposals use at most 80 bright detections and 120 bright catalog stars;
    every detection is still considered as the target. At most 128 hypotheses
    are validated against the full field. At least six unique inlier stars are
    required, with <=0.5 arcsec affine residual and sufficient model freedom.
    """
    minimum = max(6, modeltype // 2 + 1)
    det = np.column_stack([det_x, det_y]).astype(float)
    flux = np.asarray(det_flux, dtype=float)
    ra, de, mag = (np.asarray(v, dtype=float) for v in (gaia_ra, gaia_de, gaia_mag))
    if (len(det) < minimum or len(ra) < minimum or
            not np.isfinite([pscale, fl, limit_match, obj_ra, obj_de]).all() or
            pscale <= 0 or fl <= 0 or limit_match <= 0):
        return None
    valid = np.isfinite(det).all(axis=1) & np.isfinite(flux)
    det, flux = det[valid], flux[valid]
    valid = np.isfinite(ra) & np.isfinite(de) & np.isfinite(mag)
    ra, de, mag = ra[valid], de[valid], mag[valid]
    sky = np.column_stack(rade2ky(ra * DEG2RAD, de * DEG2RAD,
                                 obj_ra * DEG2RAD, obj_de * DEG2RAD))
    valid = np.isfinite(sky).all(axis=1)
    sky, ra, de, mag = sky[valid], ra[valid], de[valid], mag[valid]
    if len(det) < minimum or len(sky) < minimum:
        return None
    scale = pscale / fl
    radius = limit_match / 3600 * DEG2RAD
    bright_det = det[np.argsort(-flux, kind="stable")[:80]]
    bright_sky = sky[np.argsort(mag, kind="stable")[:120]]
    sky_r = np.linalg.norm(bright_sky, axis=1)
    sky_phi = np.arctan2(bright_sky[:, 1], bright_sky[:, 0])
    hypotheses = []
    serial = 0
    for ox, oy in det:
        relative = (bright_det - [ox, oy]) * scale
        det_r = np.linalg.norm(relative, axis=1)
        # Ignore near-origin vectors whose direction is dominated by errors.
        ii, jj = np.nonzero((np.abs(det_r[:, None] - sky_r) <= 2 * radius) &
                            (det_r[:, None] > 10 * radius))
        if len(ii) < minimum:
            continue
        for parity in (1, -1):
            phi = np.arctan2(relative[ii, 1], parity * relative[ii, 0])
            angles = np.degrees(phi - sky_phi[jj]) % 360
            bins = np.floor(angles).astype(int)
            histogram = np.bincount(bins, minlength=360)
            votes = histogram + np.roll(histogram, 1) + np.roll(histogram, -1)
            # Retain separated peaks, including peaks across 359/0 degrees.
            for _ in range(2):
                peak = int(np.argmax(votes))
                selected = np.abs((angles - (peak + 0.5) + 180) % 360 - 180) <= 1.5
                support = min(len(np.unique(ii[selected])), len(np.unique(jj[selected])))
                if support >= minimum:
                    values = angles[selected] * DEG2RAD
                    angle = float(np.arctan2(np.sin(values).mean(), np.cos(values).mean()))
                    item = (support, serial, float(ox), float(oy), parity, angle)
                    serial += 1
                    if len(hypotheses) < 128:
                        heapq.heappush(hypotheses, item)
                    elif item[0] > hypotheses[0][0]:
                        heapq.heapreplace(hypotheses, item)
                votes[(peak + np.arange(-3, 4)) % 360] = 0

    tree = cKDTree(sky)
    best = None
    for _, _, ox, oy, parity, angle in sorted(hypotheses, reverse=True):
        xy = (det - [ox, oy]) * scale
        ca, sa = np.cos(angle), np.sin(angle)
        matrix = np.array([[parity * ca, sa], [-parity * sa, ca]])
        predicted = xy @ matrix.T
        par = None
        for iteration in range(3):
            ids, cats = _unique_pairs(predicted, tree, radius * (2 if iteration == 0 else 1))
            if len(ids) < minimum:
                par = None
                break
            try:
                par, _, _ = sol_par(xy[ids, 0], xy[ids, 1], ra[cats], de[cats],
                                     len(ids), obj_ra, obj_de, 6)
            except np.linalg.LinAlgError:
                par = None
                break
            predicted = np.column_stack([xy @ par[:2] + par[2],
                                          xy @ par[3:5] + par[5]])
        if par is None:
            continue
        # Validate actual correspondences, not just the clipped fit's sigma.
        ids, cats = _unique_pairs(predicted, tree, min(radius, 0.5 / 3600 * DEG2RAD))
        if len(ids) < minimum:
            continue
        try:
            par, sigma, used = sol_par(xy[ids, 0], xy[ids, 1], ra[cats], de[cats],
                                        len(ids), obj_ra, obj_de, 6)
        except np.linalg.LinAlgError:
            continue
        sigma = sigma / DEG2RAD * 3600
        singular = np.linalg.svd(np.array([par[:2], par[3:5]]), compute_uv=False)
        if used < minimum or sigma > 0.5 or np.any(np.abs(singular - 1) > 0.1):
            continue
        if best is not None and (used, -sigma) <= (best["used"], -best["sig"]):
            continue
        best = dict(n=len(ids), used=used, sig=sigma, par=par,
                    rx=xy[ids, 0], ry=xy[ids, 1], rra=ra[cats], rde=de[cats],
                    rmag=mag[cats], ox=ox, oy=oy)
    return best
