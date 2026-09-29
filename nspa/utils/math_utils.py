"""通用数学/格式/统计工具。

涵盖：
  - interpolate  : 拉格朗日插值（局部最多 8 节点）
  - am2hms       : 赤经赤纬角分 → 时分秒/度分秒
  - initial_stats: O-C 残差的原始均值/标准差
  - sigma_clip_oc: 迭代剔除 O-C 野值
"""

import math


def interpolate(x, y, n, t):
    """拉格朗日插值。

    在 t 附近最多取 8 个相邻节点做局部 Lagrange，避免全表大阶次振荡。
    """
    if n <= 0:
        return 0.0
    if n == 1:
        return float(y[0])
    if n == 2:
        return (y[0] * (t - x[1]) - y[1] * (t - x[0])) / (x[0] - x[1])

    i = 1
    while i < n and x[i] < t:
        i += 1
    k = max(0, i - 4)
    m = min(n - 1, i + 3)

    z = 0.0
    for i in range(k, m + 1):
        s = 1.0
        for j in range(k, m + 1):
            if j != i:
                s *= (t - x[j]) / (x[i] - x[j])
        z += s * y[i]
    return z


def am2hms(ra_arcmin, de_arcmin):
    """赤经赤纬（角分）→ (hh, mm, ss, sign, ddd, dmm, dss)。"""
    hh = int(ra_arcmin / 60.0 / 15.0)
    mm = int((ra_arcmin - hh * 900.0) / 15.0)
    ss = (ra_arcmin - hh * 900.0 - mm * 15.0) * 4.0

    sign = '+' if de_arcmin >= 0 else '-'
    de1 = abs(de_arcmin)
    ddd = int(de1 / 60.0)
    dmm = int(de1 - ddd * 60.0)
    dss = (de1 - ddd * 60.0 - dmm) * 60.0
    return hh, mm, ss, sign, ddd, dmm, dss


def initial_stats(res_ra, res_de):
    """O-C 残差的原始均值/标准差。样本数 < 2 时一律返回 999.999 占位。"""
    n = len(res_ra)
    if n < 2:
        return 999.999, 999.999, 999.999, 999.999
    m_ra = sum(res_ra) / n
    m_de = sum(res_de) / n
    s_ra = math.sqrt(sum((v - m_ra) ** 2 for v in res_ra) / (n - 1))
    s_de = math.sqrt(sum((v - m_de) ** 2 for v in res_de) / (n - 1))
    return m_ra, m_de, s_ra, s_de


def sigma_clip_oc(res_ra, res_de, lines, oc_limit, mean_limit, eps):
    """迭代剔除 O-C 野值。

    剔除策略：
      - oc_limit > 0：|data - mean| < oc_limit * sigma 且 |data| < eps；
      - oc_limit == 0：|data - mean| < mean_limit。
    返回 (new_lines, new_ra, new_de, mean_ra, mean_de, std_ra, std_de, iloop)。
    """
    cur_ra = list(res_ra)
    cur_de = list(res_de)
    cur_lines = list(lines)
    iloop = 0

    def _stats(ra_arr, de_arr):
        k = len(ra_arr)
        if k == 0:
            return 0.0, 0.0, 0.0, 0.0
        m_ra = sum(ra_arr) / k
        m_de = sum(de_arr) / k
        if k > 1:
            s_ra = math.sqrt(sum((v - m_ra) ** 2 for v in ra_arr) / (k - 1))
            s_de = math.sqrt(sum((v - m_de) ** 2 for v in de_arr) / (k - 1))
        else:
            s_ra = s_de = 0.0
        return m_ra, m_de, s_ra, s_de

    mean_ra, mean_de, std_ra, std_de = _stats(cur_ra, cur_de)

    while True:
        iloop += 1
        new_ra, new_de, new_lines = [], [], []

        for i in range(len(cur_ra)):
            ra_i, de_i = cur_ra[i], cur_de[i]
            if oc_limit > 0.0:
                keep = (abs(ra_i - mean_ra) < oc_limit * std_ra and
                        abs(de_i - mean_de) < oc_limit * std_de and
                        abs(ra_i) < eps and abs(de_i) < eps)
            else:
                keep = (abs(ra_i - mean_ra) < mean_limit and
                        abs(de_i - mean_de) < mean_limit)
            if keep:
                new_ra.append(ra_i)
                new_de.append(de_i)
                new_lines.append(cur_lines[i])

        mean_ra, mean_de, std_ra, std_de = _stats(new_ra, new_de)

        if len(new_ra) >= len(cur_ra):   # 无变化，收敛
            break
        cur_ra, cur_de, cur_lines = new_ra, new_de, new_lines

    return new_lines, new_ra, new_de, mean_ra, mean_de, std_ra, std_de, iloop
