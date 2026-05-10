# 功能：04comoc O-C 统计与野值剔除批处理逻辑。
# 使用：from adias.core.adias_oc_analyzer import run_comoc

import os
import math

from adias.io.adias_text_io import (read_object_out, write_oc_stat,
                                    write_comoc_lines, clean_proc_files)
from adias.utils.adias_math_utils import sigma_clip_oc


def _initial_stats(res_ra, res_de):
    """计算原始数据的均值和标准差。"""
    n = len(res_ra)
    if n == 0:
        return 999.999, 999.999, 999.999, 999.999
    m_ra = sum(res_ra) / n
    m_de = sum(res_de) / n
    if n > 1:
        s_ra = math.sqrt(sum((v - m_ra)**2 for v in res_ra) / (n - 1))
        s_de = math.sqrt(sum((v - m_de)**2 for v in res_de) / (n - 1))
    else:
        s_ra = s_de = 0.0
    if n < 2:
        return 999.999, 999.999, 999.999, 999.999
    return m_ra, m_de, s_ra, s_de


def run_comoc(config, fitspath_list):
    """
    对每个观测目录的每个目标逐日执行 O-C 野值剔除与统计汇总。

    Parameters
    ----------
    config        : dict，parse_config() 返回的参数字典
    fitspath_list : list[str]，观测目录路径列表
    """
    outdir     = config['newoutfile0']
    obj_total  = config['obj_total']
    oc_limit   = config['oc_limit']
    mean_limit = config['mean_limit']
    eps        = config['eps']
    del_flag   = config['del_flag']

    os.makedirs(outdir, exist_ok=True)

    for obj in range(1, obj_total + 1):
        obj_label = str(obj)

        oc_summary_path = os.path.join(outdir, f'00oc_{obj_label}.out')
        month_out_path  = os.path.join(outdir,
                              os.path.basename(fitspath_list[0]) + obj_label + '.dat')

        with (open(oc_summary_path, 'a', encoding='utf-8') as f_oc_summary,
              open(month_out_path,  'a', encoding='utf-8') as f_month):

            n_day = 0
            for fitspath in fitspath_list:
                n_day += 1
                print()
                print(f'{n_day:3d}-本日fits文件：{fitspath}')

                # 按需删除过程文件
                if del_flag == 1:
                    clean_proc_files(fitspath)

                # 提取日期字符串
                try:
                    fit_names = sorted(f for f in os.listdir(fitspath)
                                       if f.endswith('.fit') and not f.endswith('_n.fit'))
                    date_str = fit_names[0][:8] if fit_names else 'output'
                except Exception:
                    date_str = 'output'

                # 各输出文件路径
                objout_path = os.path.join(fitspath, f'object_{obj_label}.out')
                final_obj   = os.path.join(fitspath, f'final_object_{obj_label}.out')
                final_oc    = os.path.join(fitspath, f'final_oc_{obj_label}.out')
                day_out     = os.path.join(outdir, date_str + obj_label + '.out')
                obsdata_out = os.path.join(outdir, date_str + f'_obsdata_{obj_label}.out')
                all_out     = os.path.join(outdir, date_str + f'_all_{obj_label}.out')

                if not os.path.exists(objout_path):
                    print(f'警告: 文件不存在 {objout_path}')
                    continue

                # 读取 O-C 数据
                raw_lines, res_ra, res_de = read_object_out(objout_path)
                n_raw = len(raw_lines)

                # 写出完整行（all 文件）
                with open(all_out, 'w', encoding='utf-8') as f_all:
                    for line in raw_lines:
                        f_all.write((line[:147] if len(line) >= 147 else line) + '\n')

                # 原始统计
                mean_ra0, mean_de0, std_ra0, std_de0 = _initial_stats(res_ra, res_de)

                print('================04Comoc-Program execution summary==================')
                print('=================res数据统计结果=================')
                print(f'  原始数据数量n_obj：{n_raw:4d}')
                print(f'  原始数据均值ra,de：{mean_ra0:12.4f}{mean_de0:12.4f}')
                print(f'  原始数据方差ra,de：{std_ra0:12.4f}{std_de0:12.4f}')
                if oc_limit > 0.0:
                    print(f'*********剔除野值标准(oc_limit)：{oc_limit:5.2f}  *********')
                else:
                    print(f'*********剔除野值标准(mean_limit)：{mean_limit:5.2f}  *********')

                # 迭代野值剔除
                kept_lines, new_ra, new_de, \
                mean_ra, mean_de, std_ra, std_de, iloop = sigma_clip_oc(
                    res_ra, res_de, raw_lines, oc_limit, mean_limit, eps)
                n_new = len(kept_lines)

                # 数据量不足时置为无效值
                if n_new < 2:
                    mean_ra = mean_de = std_ra = std_de = 999.999

                print(f'  剔除野值后数据数量n_new：{n_new:4d}')
                print(f'  剔除野值后数据均值ra,de：{mean_ra:12.4f}{mean_de:12.4f}')
                print(f'  剔除野值后数据方差ra,de：{std_ra:12.4f}{std_de:12.4f}')
                print(f'  剔除野值迭代次数：{iloop:2d}')
                print(f'  残差文件输出:{oc_summary_path}')

                # 写出统计报告
                write_oc_stat(final_oc, n_raw, mean_ra0, mean_de0, std_ra0, std_de0,
                              n_new, mean_ra, mean_de, std_ra, std_de,
                              iloop, oc_limit, mean_limit)

                # 写出剔除后数据
                if std_ra < 0.3 and std_de < 0.3 and n_new > 1:
                    with (open(day_out,     'w', encoding='utf-8') as f_out,
                          open(final_obj,   'w', encoding='utf-8') as f_final,
                          open(obsdata_out, 'w', encoding='utf-8') as f_obsdata):
                        write_comoc_lines(f_out, f_final, f_obsdata, f_month, kept_lines)

                    f_oc_summary.write(
                        f'{date_str} & {n_raw:4d} & '
                        f'{mean_ra0:9.3f} & {mean_de0:9.3f} & '
                        f'{std_ra0:9.3f} & {std_de0:9.3f} & '
                        f'{n_new:4d} & '
                        f'{mean_ra:9.3f} & {mean_de:9.3f} & '
                        f'{std_ra:9.3f} & {std_de:9.3f}\n')
                else:
                    print('删除该日期数据：============')
                    print(f'{date_str}{n_raw:4d}{mean_ra0:9.4f}{mean_de0:9.4f}'
                          f'{std_ra0:9.4f}{std_de0:9.4f}{n_new:4d}'
                          f'{mean_ra:9.4f}{mean_de:9.4f}{std_ra:9.4f}{std_de:9.4f}')
                    print('================')

        print(f'   本日匹配共归算天然卫星目标个数{obj:3d}')
        print('=================================================================')

    print(f'数据统计归算结束，共处理数据天数：{len(fitspath_list):3d}')
    print('=================================================================')
    print('=====================ADIAS END======================')