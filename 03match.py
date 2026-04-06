# **********************************CCD 图像预处理与天体匹配 - 03match (Python)**********************************
# program name: 03match.py
#
# function:
#   1）读取 GAIA 星表和卫星历表；
#   2）根据星表、卫星历表位置以及 02detect 产生的星象检测结果 (*.reg)，自动确认底片旋转角度及视场中目标星坐标；
#   3）自动完成参考星匹配与底片模型参数（par）解算，归算目标星的赤经赤纬位置；
#   4）输出目标星的观测时间、位置、O–C、图像 sig0、曝光时间、图像名等信息。
#
# input:
#   0）由 02detect 程序生成的 *.reg 文件（每幅科学图像对应一个 reg 文件）；
#   1）配置文件 adias.cfg（本程序使用的关键字段示例）：
#        1.1）3tele_label       望远镜标签（如 ss156）；
#        1.2）3tele_focal       望远镜焦距（单位：mm）；
#        1.3）3ccd_scale        CCD 比例尺（单位：arcsec/pixel）；
#        1.4）3ccd_fieldsize    CCD 视场大小（角分，用于从 GAIA 星表中圈定参考星区域）；
#        1.5）3modeltype        底片模型参数个数（6 / 12 / 20 / 30）；
#        1.6）3plate_angle      底片旋转角度初始值（单位：deg）；
#        1.7）3obj_ephfileX     目标星历表文件路径（X 从 1 到 obj_total）；
#        1.8）3gaia_catfile     GAIA 星表文件路径；
#        1.9）3gaia_minmag      GAIA 星表最小星等；
#        1.10）3gaia_maxmag     GAIA 星表最大星等；
#        1.11）3match_limit     参考星匹配限（单位：arcsec）；
#        1.12）3delta_T         时间修正量 delta_T（秒），用于修正曝光中点观测时刻；
#        1.13）3obj_total       目标数量；
#   2）主路径文件 fitspath.in：
#        - 每一行给出一个观测日期对应的 FITS 图像目录；
#        - 每个目录下包含 fits.lst（待处理图像列表）及对应的 *.reg 检测文件。
#
# output:
#   1）参考星信息文件：*.ref.reg
#        - DS9 region 格式，记录用于匹配和归算的参考星像面坐标及星表信息；
#   2）目标星观测结果文件：object_X.out（每个目标一个 out 文件）
#        - 包含观测日期与时刻、目标赤经赤纬、历表坐标、O–C 残差、图像 sig0、曝光时间、图像文件名等。
#
# 主要方法与 Fortran 子程序对应关系（本 Python 版本显式实现部分）：
#   Match.read_config()               <->  adias.cfg 解析；
#   Match.read_catalog()              <->  读取 GAIA 星表；
#   Match.read_ephemeris()            <->  读取卫星历表并生成 (T, α, δ) 序列；
#   Match.fits_header()               <->  fits_header，解析 FITS 头并得到曝光中点时间；
#   Match.interpolate()               <->  interT / ENLGR，一维拉格朗日插值目标位置；
#   Match.extract_field_stars()       <->  从 GAIA 星表截取视场内参考星并进行自行改正；
#   Match.cal_rl()                    <->  CAL_RL，计算两星大圆弧距离；
#   Match.rade2ky() / rade2xieta()    <->  赤道坐标 -> 理想坐标；
#   Match.xy2rade()                   <->  量度坐标 -> 赤道坐标；
#   Match.sol_par() + least_squares() <->  sol_par + LEAST + MATINV，解算底片常数 par 及残差 sig0；
#   Match.read_reg_file()             <->  读取 *.reg 检测星列表；
#   Match.select_obj_xy()             <->  在 reg 文件中选取最接近预报位置的目标星像；
#   Match.find_obj_base_angle()       <->  find_obj_baseangle，基于固定底片旋转角度自动寻星与归算；
#   Match.find_obj_base_prepar()      <->  使用上一幅图像得到的 pre_par 直接寻星；
#   Match.write_ref_file()            <->  输出 *.ref.reg 参考星信息；
#   Match.write_object_result()       <->  写入 object_X.out 目标观测结果；
#   Match.sort_output_file()          <->  sort_T，按时间排序输出文件；
#   Match.am2hms()                    <->  am2hms，将赤经赤纬转换为时分秒 / 度分秒字符串。
#
# 使用方法：
#   1）准备 fitspath.in 文件（每行一个 FITS 图像目录）；
#   2）准备 adias.cfg（望远镜参数、GAIA 星表、历表路径、模型类型等）；
#   3）准备 GAIA 星表文件和目标历表文件，并在 adias.cfg 中正确配置；
#   4）确保每个目录下已有 01pre/02detect 生成的 fits.lst 与 *.reg；
#   5）运行：python 03match.py。
#
# 版本与历史：
#   V1.0 by zhy 2019.09.01   Fortran 03match.f90 初始版本；
#   V2.0 add the enhance function by zhy 2019.09.24
#   V3.0 Chinese comment by zhy 2020.01.30
#   2020–2022        逐步加入粗/细匹配策略、delta_T 修正、匹配限调整、目标亮度输出等改进；
#   20210814         适配不同 DATE-OBS/DATE-STA 头关键字格式；
#   20241001         修改过程输出为中文；
#   20241021         修正“目标星为 reg 文件第一行”时被循环逻辑跳过的问题；
#   V4.0 by lhy 2025.12.05 程序改写成python
# ************************************************************************************************

import numpy as np
import os
from astropy.io import fits
from scipy.linalg import inv
import warnings
import time

warnings.filterwarnings('ignore')

class Match:
    def __init__(self):
        self.pi = np.pi
        self.q = self.pi / 180.0
        self.max_size = 900000

    def main(self):
        t0 = time.time()
        """主程序"""
        try:
            with open('fitspath.in', 'r') as f:
                fitspath_list = [line.strip() for line in f if line.strip()]
        except:
            print("无法打开fitspath.in文件")
            return

        n_day = 0

        for fitspath in fitspath_list:
            n_day += 1
            print(f'###########本观测时段，第{n_day:02d}日：fits文件夹：{fitspath}')

            # 读取配置文件
            config = self.read_config()
            if config is None:
                continue

            # 读取星表
            n_gaia, gaia_ra0, gaia_de0, gaia_pr0, gaia_pd0, gaia_mag0 = self.read_catalog(
                config['gaiacatpath'],
                config['min_mag'],
                config['max_mag']
            )
            print('======读取本日配置文件及星表结束')

        # 打开目标输出文件
        obj_file_handles = {}
        os.makedirs(fitspath, exist_ok=True)
        for obj in range(1, config['obj_total'] + 1):
            objoutfile = os.path.join(fitspath, f'object_{obj}.out')
            obj_file_handles[obj] = open(objoutfile, 'w')

            # 统计图像数量
            fits_lst_file = os.path.join(fitspath, 'fits.lst')
            try:
                with open(fits_lst_file, 'r') as f:
                    fits_files = [line.strip().strip('"') for line in f if line.strip()]
                n_fits_total = len(fits_files)
            except:
                print(f"无法打开{fits_lst_file}")
                continue

            print(f'======本日观测图像数量共计：{n_fits_total:4d}幅')

            # 处理每幅图像
            flag_pre_match = 0
            pre_par = np.zeros(30)

            for n_fits, objfitsfile in enumerate(fits_files, 1):
                print()
                print(f'======当前图像：{n_fits:3d}/{n_fits_total:3d} -{objfitsfile}')

                # 读取FITS头文件
                header_info = self.fits_header(objfitsfile, config['tele_label'])
                if header_info is None:
                    continue

                naxis1, naxis2, bscale, bzero, gain, exptime, year, month, day, hh, mm, ss = header_info

                # 计算观测时间
                obj_T = day + (hh * 3600 + mm * 60 + ss + config['delta_t']) / 86400.0
                calpm_epoch = year + ((month - 1) * 30 + day) / 365.0

                # 处理每个目标
                for obj in range(1, config['obj_total'] + 1):
                    print()
                    print(f'*****当前处理目标为：{obj:2d}/{config["obj_total"]:2d}')

                    ephfile = config['ephpath'][obj - 1]

                    # 读取历表
                    n_eph, eph_T, eph_ra, eph_de = self.read_ephemeris(ephfile)
                    print(f'----读取该目标IMCCE历表位置数：{n_eph:4d}')

                    # 内插目标位置
                    obj_ephra = self.interpolate(eph_T, eph_ra, n_eph, obj_T)
                    obj_ephde = self.interpolate(eph_T, eph_de, n_eph, obj_T)

                    # 提取视场内恒星
                    n_gaia_field, gaia_ra_field, gaia_de_field, gaia_mag_field = \
                        self.extract_field_stars(
                            gaia_ra0, gaia_de0, gaia_pr0, gaia_pd0, gaia_mag0, n_gaia,
                            obj_ephra, obj_ephde, config['fsize'],
                            calpm_epoch
                        )
                    print(f'----用于匹配的恒星数量：{n_gaia_field:4d}')

                    # 匹配和归算
                    if flag_pre_match < 1:
                        print('----自动寻星检测确定底片常数')
                        result = self.find_obj_base_angle(
                            objfitsfile, config['tele_label'],
                            config['field_angle'], config['pscale'],
                            config['fl'], config['limit_match'],
                            obj_ephra, obj_ephde,
                            gaia_ra_field, gaia_de_field, gaia_mag_field, n_gaia_field,
                            config['modeltype']
                        )

                        if result['nostar'] == 1:
                            continue

                        if result['nostar'] < 1 and result['nopre'] < 1:
                            print(
                                f'...目标星x/y/obsra/obsde位置：{result["obj_x"]:10.3f}{result["obj_y"]:10.3f}{result["obj_obsra"]:10.3f}{result["obj_obsde"]:10.3f}')
                            print(f'...成功匹配星数：{result["n_match1"]:4d}')
                            self.print_par(result['par1'], config['modeltype'])
                            print(f'...底片模型归算sigma：{result["sig0"]:7.3f}')

                        if 0.0001 < result['sig0'] < 0.06 and result['n_match1'] > 10:
                            flag_pre_match = 1
                            pre_par = result['par1'].copy()
                            pre_x_center = result['x_center']
                            pre_y_center = result['y_center']
                            pre_ra_center = result['ra_center']
                            pre_de_center = result['de_center']


                    else:
                        print('----使用pre_par归算(sig<0.06 & n_match>10)')
                        result = self.find_obj_base_prepar(
                            objfitsfile, pre_par, config['pscale'], config['fl'],
                            config['modeltype'], pre_x_center, pre_y_center,
                            pre_ra_center, pre_de_center, config['limit_match'],
                            obj_ephra, obj_ephde,
                            gaia_ra_field, gaia_de_field, gaia_mag_field, n_gaia_field
                        )

                        if result['nopre'] < 1:
                            print(
                                f'...目标星x/y/obsra/obsde位置：{result["obj_x"]:10.3f}{result["obj_y"]:10.3f}{result["obj_obsra"]:10.3f}{result["obj_obsde"]:10.3f}')
                            print(f'...成功匹配星数：{result["n_match1"]:4d}')
                            print(f'...底片模型归算sigma：{result["sig0"]:7.3f}')
                            print('...其余参数同前')


                    # 输出参考星文件
                    if result.get('n_match1', 0) > 0:
                        ref_file = f"{objfitsfile}{obj}.ref.reg"
                        print(f"准备写入参考星文件: {ref_file}")
                        print(f"参考星数量: {result['n_match1']}")
                        self.write_ref_file(ref_file, result)
                        print(f"参考星文件写入完成")

                    # 输出目标观测结果
                    if abs(result.get('sig0', 999)) < 1.0 and abs(result.get('sig0', 0)) > 0.0001:
                        self.write_object_result(
                            obj_file_handles[obj], year, month, obj_T,
                            result['obj_obsra'], result['obj_obsde'],
                            obj_ephra, obj_ephde,
                            result.get('sig0', 0), hh, mm, ss, exptime,
                            objfitsfile, config['field_angle']
                        )

            # 关闭输出文件
            for fh in obj_file_handles.values():
                fh.close()

            # 输出总结
            print()
            print('================03Match-Program execution summary==================')
            print(f'目前处理目标数：{config["obj_total"]:2d}/{config["obj_total"]:2d}')
            print('参考星信息已输出到*.ref.reg文件（图像文件夹）')
            print('目标星的位置数据输出到object.out（图像文件夹）')
            print('===================================================================')

            # 排序输出文件
            for obj in range(1, config['obj_total'] + 1):
                objoutfile = os.path.join(fitspath, f'object_{obj}.out')
                self.sort_output_file(objoutfile)

            print(f'   本日匹配共归算天然卫星目标个数{config["obj_total"]:3d}')
            print('=================================================================')

        print(f'   本时段观测任务匹配结束，共匹配天数：{n_day:3d}')
        print('=================================================================')
        print(f"代码总耗时: {time.time() - t0:.2f} s")


    def read_config(self):
        """读取配置文件"""
        config = {
            'tele_label': '',
            'fl': 0.0,
            'pscale': 0.0,
            'fsize': 0,
            'modeltype': 0,
            'field_angle': 0.0,
            'ephsource': '',
            'min_mag': 0.0,
            'max_mag': 0.0,
            'limit_match': 0.0,
            'delta_t': 0.0,
            'newoutfile0': '',
            'gaiacatpath': '',
            'obj_total': 0,
            'ephpath': []
        }

        try:
            with open('adias.cfg', 'r') as f:
                lines = f.readlines()

            for line in lines:
                line = line.strip()
                if not line or line.startswith('[') or line.startswith(';'):
                    continue

                if '3tele_label=' in line:
                    config['tele_label'] = line.split('=')[1].strip()
                elif '3tele_focal=' in line:
                    config['fl'] = float(line.split('=')[1])
                elif '3ccd_scale=' in line:
                    config['pscale'] = float(line.split('=')[1])
                elif '3ccd_fieldsize=' in line:
                    config['fsize'] = int(line.split('=')[1])
                elif '3modeltype=' in line:
                    config['modeltype'] = int(line.split('=')[1])
                elif '3plate_angle=' in line:
                    config['field_angle'] = float(line.split('=')[1])
                elif '3obj_ephsource=' in line:
                    config['ephsource'] = line.split('=')[1].strip()
                elif '3gaia_minmag=' in line:
                    config['min_mag'] = float(line.split('=')[1])
                elif '3gaia_maxmag=' in line:
                    config['max_mag'] = float(line.split('=')[1])
                elif '3match_limit=' in line:
                    config['limit_match'] = float(line.split('=')[1])
                elif '3delta_T=' in line:
                    config['delta_t'] = float(line.split('=')[1])
                elif '4specified-output=' in line:
                    config['newoutfile0'] = line.split('=')[1].strip()
                elif '3gaia_catfile=' in line:
                    config['gaiacatpath'] = line.split('=')[1].strip()
                elif '3obj_total=' in line:
                    config['obj_total'] = int(line.split('=')[1])

            # 读取历表路径
            for obj in range(1, config['obj_total'] + 1):
                for line in lines:
                    if f'3obj_ephfile{obj}=' in line:
                        config['ephpath'].append(line.split('=')[1].strip())
                        break
        except:
            print("无法读取配置文件")
            return None

        return config

    def read_catalog(self, catfile, min_mag, max_mag):
        """读取GAIA星表"""
        gaia_ra = []
        gaia_de = []
        gaia_pr = []  # 自行 RA方向
        gaia_pd = []  # 自行 DEC方向
        gaia_mag = []

        try:
            with open(catfile, 'r') as f:
                lines = f.readlines()

            # 跳过前60行
            start_idx = 60

            for line in lines[start_idx:]:
                # 检查结束标记
                if line[:4] == '    ' or line[:4] == '#END':
                    break

                if len(line) < 39:
                    continue

                try:
                    # 从第39个字符后读取数据
                    # 格式: 39x, 2f16.11, 2f10.3, f8.4
                    # 即: RA(16.11) DE(16.11) pmRA(10.3) pmDE(10.3) Gmag(8.4)
                    data_str = line[39:]  # 从第39个字符开始
                    parts = data_str.split()

                    if len(parts) >= 5:
                        cat_ra = float(parts[0])
                        cat_de = float(parts[1])
                        cat_pr = float(parts[2])
                        cat_pd = float(parts[3])
                        cat_mag = float(parts[4])

                        if min_mag <= cat_mag <= max_mag:
                            gaia_ra.append(cat_ra)
                            gaia_de.append(cat_de)
                            gaia_pr.append(cat_pr)
                            gaia_pd.append(cat_pd)
                            gaia_mag.append(cat_mag)
                except (ValueError, IndexError):
                    continue

        except Exception as e:
            print(f"无法读取星表文件：{catfile}, 错误: {e}")
            return 0, None, None, None, None, None

        n_gaia = len(gaia_ra)
        return n_gaia, np.array(gaia_ra), np.array(gaia_de), np.array(gaia_pr), np.array(gaia_pd), np.array(gaia_mag)

    # def read_ephemeris(self, ephfile):
    #     """读取历表文件"""
    #     eph_T = []
    #     eph_ra = []
    #     eph_de = []
    #
    #     try:
    #         with open(ephfile, 'r') as f:
    #             lines = f.readlines()
    #
    #         # 找到数据开始的行（包含 Year M D 的那一行之后）
    #         start_idx = 0
    #         for i, line in enumerate(lines):
    #             if 'Year' in line and 'alpha' in line and 'delta' in line:
    #                 start_idx = i + 1
    #                 break
    #
    #         for line in lines[start_idx:]:
    #             line = line.strip()
    #             if not line or line.startswith('---'):
    #                 continue
    #
    #             try:
    #                 parts = line.split()
    #                 if len(parts) >= 8:
    #                     year = int(parts[0])
    #                     month = int(parts[1])
    #                     day = int(parts[2])
    #                     hh = int(parts[3])
    #                     mm = int(parts[4])
    #                     ss = float(parts[5])
    #                     ra = float(parts[6])
    #                     de = float(parts[7])
    #
    #                     T = day + (hh * 3600.0 + mm * 60.0 + ss) / 86400.0
    #                     eph_T.append(T)
    #                     eph_ra.append(ra * 15.0)  # 时角转度
    #                     eph_de.append(de)
    #             except (ValueError, IndexError):
    #                 continue
    #
    #     except Exception as e:
    #         print(f"无法读取历表文件：{ephfile}, 错误: {e}")
    #         return 0, None, None, None
    #
    #     n_eph = len(eph_T)
    #     return n_eph, np.array(eph_T), np.array(eph_ra), np.array(eph_de)

    def read_ephemeris(self, ephfile):
        """读取历表文件"""
        eph_T = []
        eph_ra = []
        eph_de = []

        try:
            with open(ephfile, 'r', encoding='utf-8') as f:  # 明确指定编码
                lines = f.readlines()

            print(f"历表文件总行数: {len(lines)}")

            # Fortran是跳过前10行
            start_idx = 10

            skipped_lines = 0
            parsed_lines = 0

            for i, line in enumerate(lines[start_idx:], start=start_idx):
                line_strip = line.strip()

                # 跳过以---开头的行
                if line_strip.startswith('---'):
                    skipped_lines += 1
                    continue

                # 跳过空行
                if not line_strip:
                    skipped_lines += 1
                    continue

                try:
                    parts = line_strip.split()
                    if len(parts) >= 8:
                        year = int(parts[0])
                        month = int(parts[1])
                        day = int(parts[2])
                        hh = int(parts[3])
                        mm = int(parts[4])
                        ss = float(parts[5])
                        ra = float(parts[6])
                        de = float(parts[7])

                        T = day + (hh * 3600.0 + mm * 60.0 + ss) / 86400.0
                        eph_T.append(T)
                        eph_ra.append(ra * 15.0)
                        eph_de.append(de)
                        parsed_lines += 1
                    else:
                        print(f"第{i + 1}行数据不足8列: {line_strip}")
                        skipped_lines += 1
                except (ValueError, IndexError) as e:
                    print(f"第{i + 1}行解析失败: {line_strip}, 错误: {e}")
                    skipped_lines += 1

            print(f"跳过行数: {skipped_lines}, 成功解析行数: {parsed_lines}")

        except Exception as e:
            print(f"无法读取历表文件：{ephfile}, 错误: {e}")
            return 0, None, None, None

        n_eph = len(eph_T)
        return n_eph, np.array(eph_T), np.array(eph_ra), np.array(eph_de)

    def fits_header(self, fitsfile, tele_label):
        """读取FITS头文件"""
        try:
            with fits.open(fitsfile) as hdul:
                header = hdul[0].header

                naxis1 = header.get('NAXIS1', 0)
                naxis2 = header.get('NAXIS2', 0)
                bscale = header.get('BSCALE', 1.0)
                bzero = header.get('BZERO', 0.0)
                gain = header.get('GAIN', 1.0)
                exptime = header.get('EXPTIME', 0.0)

                # 根据不同望远镜标签读取时间
                if tele_label == 'ss156':
                    date_obs = header.get('DATE-OBS', '')
                    if date_obs:
                        parts = date_obs.replace('T', ' ').replace('-', ' ').replace(':', ' ').split()
                        year = int(parts[0])
                        month = int(parts[1])
                        day = int(parts[2])
                        hh = int(parts[3])
                        mm = int(parts[4])
                        ss = float(parts[5])
                elif tele_label in ['ss156_2014', 'km100', 'lj240']:
                    date_obs = header.get('DATE-OBS', '') if tele_label != 'ss156_2014' else header.get('DATE-STA', '')
                    if date_obs:
                        parts = date_obs.replace('T', ' ').replace('-', ' ').replace(':', ' ').split()
                        year = int(parts[0])
                        month = int(parts[1])
                        day = int(parts[2])
                        hh = int(parts[3])
                        mm = int(parts[4])
                        ss = float(parts[5])
                elif tele_label == 'km100B':
                    date_obs = header.get('DATE-OBS', '')
                    if date_obs:
                        parts = date_obs.replace('T', ' ').replace('-', ' ').replace(':', ' ').split()
                        year = int(parts[0])
                        month = int(parts[1])
                        day = int(parts[2])
                        hh = int(parts[3])
                        mm = int(parts[4])
                        ss = float(parts[5])
                else:
                    print(f'请检查fits头文件格式！未知的望远镜标签: {tele_label}')
                    return None

                # 修正时间到曝光中间时刻
                ss += 0.5 * exptime
                while ss >= 60:
                    mm += 1
                    ss -= 60
                    if mm >= 60:
                        hh += 1
                        mm -= 60
                        if hh >= 24:
                            day += 1
                            hh -= 24

                # 北京时间转UTC（如果需要）
                if tele_label in ['ss156', 'ss156_2014']:
                    if hh < 8:
                        day -= 1
                        hh += 24
                    hh -= 8

                return naxis1, naxis2, bscale, bzero, gain, exptime, year, month, day, hh, mm, ss
        except Exception as e:
            print(f"读取FITS头文件错误：{e}")
            return None

    def interpolate(self, x, y, n, t):
        """拉格朗日插值"""
        if n <= 0:
            return 0.0
        if n == 1:
            return y[0]
        if n == 2:
            return (y[0] * (t - x[1]) - y[1] * (t - x[0])) / (x[0] - x[1])

        # 找到插值区间
        i = 1
        while i < n and x[i] < t:
            i += 1

        # 选择插值点
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

    def extract_field_stars(self, gaia_ra, gaia_de, gaia_pr, gaia_pd, gaia_mag, n_gaia,
                            obj_ra, obj_de, fsize, epoch):
        """提取视场内恒星并进行自行改正"""
        field_ra = []
        field_de = []
        field_mag = []

        for i in range(n_gaia):
            if (obj_ra - fsize / 60.0 < gaia_ra[i] < obj_ra + fsize / 60.0 and
                    obj_de - fsize / 60.0 < gaia_de[i] < obj_de + fsize / 60.0):
                # 自行改正 (epoch相对于2016年的年数)
                de_corrected = gaia_de[i] + (epoch - 2016) * gaia_pd[i] / 1000.0 / 3600.0
                ra_corrected = gaia_ra[i] + (epoch - 2016) * gaia_pr[i] / 1000.0 / 3600.0 / np.cos(
                    de_corrected * self.q)

                field_ra.append(ra_corrected)
                field_de.append(de_corrected)
                field_mag.append(gaia_mag[i])

        n_field = len(field_ra)
        return n_field, np.array(field_ra), np.array(field_de), np.array(field_mag)

    def cal_rl(self, ra1, dec1, ra2, dec2):
        """计算大圆弧长"""
        cos_rl = np.sin(dec1) * np.sin(dec2) + np.cos(dec1) * np.cos(dec2) * np.cos(ra1 - ra2)
        cos_rl = np.clip(cos_rl, -1.0, 1.0)
        rl = np.arccos(cos_rl)
        return rl

    def xy2rade(self, par, nm, x, y, ra0, de0):
        """量度坐标转赤道坐标"""
        if nm == 6:
            ksi = par[0] * x + par[1] * y + par[2]
            yit = par[3] * x + par[4] * y + par[5]
        elif nm == 12:
            ksi = par[0] * x + par[1] * y + par[2] + par[3] * x ** 2 + par[4] * x * y + par[5] * y ** 2
            yit = par[6] * x + par[7] * y + par[8] + par[9] * x ** 2 + par[10] * x * y + par[11] * y ** 2
        elif nm == 20:
            ksi = (par[0] * x + par[1] * y + par[2] + par[3] * x ** 2 + par[4] * x * y + par[5] * y ** 2 +
                   par[6] * x ** 3 + par[7] * x ** 2 * y + par[8] * x * y ** 2 + par[9] * y ** 3)
            yit = (par[10] * x + par[11] * y + par[12] + par[13] * x ** 2 + par[14] * x * y + par[15] * y ** 2 +
                   par[16] * x ** 3 + par[17] * x ** 2 * y + par[18] * x * y ** 2 + par[19] * y ** 3)
        elif nm == 30:
            ksi = (par[0] * x + par[1] * y + par[2] + par[3] * x ** 2 + par[4] * x * y + par[5] * y ** 2 +
                   par[6] * x ** 3 + par[7] * x ** 2 * y + par[8] * x * y ** 2 + par[9] * y ** 3 +
                   par[10] * y ** 4 + par[11] * x ** 3 * y + par[12] * x ** 2 * y ** 2 + par[13] * x * y ** 3 + par[
                       14] * y ** 4)
            yit = (par[15] * x + par[16] * y + par[17] + par[18] * x ** 2 + par[19] * x * y + par[20] * y ** 2 +
                   par[21] * x ** 3 + par[22] * x ** 2 * y + par[23] * x * y ** 2 + par[24] * y ** 3 +
                   par[25] * y ** 4 + par[26] * x ** 3 * y + par[27] * x ** 2 * y ** 2 + par[28] * x * y ** 3 + par[
                       29] * y ** 4)
        else:
            return 0.0, 0.0

        tand1 = ksi / np.cos(de0) / (1.0 - yit * np.tan(de0))
        ra = ra0 + np.arctan(tand1)

        tand2 = (yit + np.tan(de0)) * np.cos(np.arctan(tand1)) / (1.0 - yit * np.tan(de0))
        de = np.arctan(tand2)

        return ra, de

    def rade2xieta(self, ra, de, ra0, de0):
        """赤道坐标转理想坐标"""
        a = np.cos(de) * np.sin(ra - ra0)
        b = np.cos(de0) * np.sin(de) - np.sin(de0) * np.cos(de) * np.cos(ra - ra0)
        c = np.sin(de0) * np.sin(de) + np.cos(de0) * np.cos(de) * np.cos(ra - ra0)

        xi = a / c
        eta = b / c

        return xi, eta

    def xieta2xy(self, xi, eta, par):
        """理想坐标转量度坐标"""
        a = par[0]
        b = par[1]
        c = par[2]
        d = par[3]
        e = par[4]
        f = par[5]

        denominator = a * e - b * d
        if abs(denominator) < 1e-10:
            return 0.0, 0.0

        sx = (e * xi - b * eta + b * f - c * e) / denominator
        sy = (d * xi - a * eta + a * f - c * d) / (b * d - a * e)

        return sx, sy

    def rade2ky(self, ra, de, ra0, de0):
        """赤道坐标转理想坐标(另一种实现)"""
        ksi01 = np.cos(de) * np.sin(ra - ra0)
        ksi02 = np.sin(de) * np.sin(de0) + np.cos(de) * np.cos(de0) * np.cos(ra - ra0)
        ksi = ksi01 / ksi02

        yit01 = np.sin(de) * np.cos(de0) - np.cos(de) * np.sin(de0) * np.cos(ra - ra0)
        yit02 = np.sin(de) * np.sin(de0) + np.cos(de) * np.cos(de0) * np.cos(ra - ra0)
        yit = yit01 / yit02

        return ksi, yit

    def sol_par(self, x, y, ra, de, n, ra0, de0, nm):
        """解算底片常数"""
        # 转换为理想坐标
        ksi = np.zeros(n)
        yit = np.zeros(n)
        for i in range(n):
            ksi[i], yit[i] = self.rade2ky(ra[i] * self.q, de[i] * self.q,
                                          ra0 * self.q, de0 * self.q)

        # 建立方程
        A = np.zeros((2 * n, nm))
        C = np.zeros((2 * n, 1))

        if nm == 6:
            for i in range(n):
                A[2 * i, 0] = x[i]
                A[2 * i, 1] = y[i]
                A[2 * i, 2] = 1.0

                A[2 * i + 1, 3] = x[i]
                A[2 * i + 1, 4] = y[i]
                A[2 * i + 1, 5] = 1.0

                C[2 * i, 0] = ksi[i]
                C[2 * i + 1, 0] = yit[i]
        elif nm == 12:
            for i in range(n):
                A[2 * i, 0] = x[i]
                A[2 * i, 1] = y[i]
                A[2 * i, 2] = 1.0
                A[2 * i, 3] = x[i] ** 2
                A[2 * i, 4] = x[i] * y[i]
                A[2 * i, 5] = y[i] ** 2

                A[2 * i + 1, 6] = x[i]
                A[2 * i + 1, 7] = y[i]
                A[2 * i + 1, 8] = 1.0
                A[2 * i + 1, 9] = x[i] ** 2
                A[2 * i + 1, 10] = x[i] * y[i]
                A[2 * i + 1, 11] = y[i] ** 2

                C[2 * i, 0] = ksi[i]
                C[2 * i + 1, 0] = yit[i]
        elif nm == 20:
            for i in range(n):
                A[2 * i, 0:10] = [x[i], y[i], 1.0, x[i] ** 2, x[i] * y[i], y[i] ** 2,
                                  x[i] ** 3, x[i] ** 2 * y[i], x[i] * y[i] ** 2, y[i] ** 3]
                A[2 * i + 1, 10:20] = [x[i], y[i], 1.0, x[i] ** 2, x[i] * y[i], y[i] ** 2,
                                       x[i] ** 3, x[i] ** 2 * y[i], x[i] * y[i] ** 2, y[i] ** 3]
                C[2 * i, 0] = ksi[i]
                C[2 * i + 1, 0] = yit[i]
        elif nm == 30:
            for i in range(n):
                A[2 * i, 0:15] = [x[i], y[i], 1.0, x[i] ** 2, x[i] * y[i], y[i] ** 2,
                                  x[i] ** 3, x[i] ** 2 * y[i], x[i] * y[i] ** 2, y[i] ** 3,
                                  x[i] ** 4, x[i] ** 3 * y[i], x[i] ** 2 * y[i] ** 2,
                                  x[i] * y[i] ** 3, y[i] ** 4]
                A[2 * i + 1, 15:30] = [x[i], y[i], 1.0, x[i] ** 2, x[i] * y[i], y[i] ** 2,
                                       x[i] ** 3, x[i] ** 2 * y[i], x[i] * y[i] ** 2, y[i] ** 3,
                                       x[i] ** 4, x[i] ** 3 * y[i], x[i] ** 2 * y[i] ** 2,
                                       x[i] * y[i] ** 3, y[i] ** 4]
                C[2 * i, 0] = ksi[i]
                C[2 * i + 1, 0] = yit[i]

        # 最小二乘法求解
        par, sig0, nused = self.least_squares(A, C, nm, n)

        return par, sig0, nused

    def least_squares(self, A, Y, K, n):
        """最小二乘法"""
        NE = 2 * n
        SFA = 2.6
        SFB = 0.01

        P = np.ones(NE)
        SITA2 = 0.0
        SITA20 = 0.0
        NBIG = 0
        ILOOP = 0

        while True:
            NEP = NE - NBIG * 2
            ILOOP += 1

            # 加权
            AT = A.T.copy()
            for i in range(NE):
                AT[:, i] *= P[i]

            # 求解
            try:
                ATA = AT @ A
                ATA_inv = inv(ATA)
                X = ATA_inv @ AT @ Y
            except:
                return np.zeros(K), 0.0, 0

            # 计算残差
            V = A @ X - Y
            SITA2 = 0.0
            for i in range(NE):
                SITA2 += V[i, 0] ** 2 * P[i]

            if NEP != K:
                SITA2 = np.sqrt(SITA2 / (NEP - K))
            else:
                SITA2 = 0.0

            # 检查收敛
            if abs(SITA2 - SITA20) >= SFB * SITA20 and ILOOP <= 30:
                SITA20 = SITA2
                NBIG = 0
                P = np.ones(NE)

                # 剔除大残差
                for i in range(1, NE, 2):
                    if abs(V[i, 0]) >= SFA * SITA2 or abs(V[i - 1, 0]) >= SFA * SITA2:
                        P[i - 1] = 0.0
                        P[i] = 0.0
                        NBIG += 1
            else:
                break

            if ILOOP > 30:
                break

        nused = NE // 2 - NBIG
        par = X.flatten()

        return par, SITA2, nused

    def read_reg_file(self, regfile):
        """读取reg文件"""
        det_x = []
        det_y = []
        det_flux = []
        snr = []

        try:
            with open(regfile, 'r') as f:
                lines = f.readlines()

            # 跳过前两行头信息
            for line in lines[2:]:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                try:
                    if 'ellipse' in line.lower():
                        # 格式: ellipse   x   y  r1  r2  #  flux  snr  ...
                        parts = line.split()

                        # 提取坐标
                        x = float(parts[1])
                        y = float(parts[2])

                        # 找到 # 后面的数据
                        hash_idx = line.find('#')
                        if hash_idx != -1:
                            after_hash = line[hash_idx + 1:].strip().split()
                            if len(after_hash) >= 2:
                                flux = float(after_hash[0])
                                snr_val = float(after_hash[1])

                                det_x.append(x)
                                det_y.append(y)
                                det_flux.append(flux)
                                snr.append(snr_val)

                except (ValueError, IndexError) as e:
                    continue

        except Exception as e:
            print(f"读取reg文件错误: {regfile}, {e}")

        return np.array(det_x), np.array(det_y), np.array(det_flux), np.array(snr)

    def select_obj_xy(self, x0, y0, xyfile):
        """选择最接近预报位置的星"""
        det_x, det_y, det_flux, snr = self.read_reg_file(xyfile)

        selectflag = 0
        objx = 0.0
        objy = 0.0
        objflux = 0.0
        objsnr = 0.0
        dis0 = 20.0

        for i in range(len(det_x)):
            if abs(det_x[i] - 999.0) >= 1e-6 and abs(det_y[i] - 999.0) >= 1e-6:
                dis = np.sqrt((det_x[i] - x0) ** 2 + (det_y[i] - y0) ** 2)
                if dis <= 3.0 and dis < dis0:
                    dis0 = dis
                    objx = det_x[i]
                    objy = det_y[i]
                    objflux = det_flux[i]
                    objsnr = snr[i]
                    selectflag = 1

        return objx, objy, objflux, objsnr, selectflag

    def find_obj_base_angle(self, fitsfile, tele_label, field_angle, pscale, fl,
                            limit_match, obj_ephra, obj_ephde,
                            gaia_ra0, gaia_de0, gaia_mag0, n_gaia0, modeltype):
        """基于底片角度查找目标"""
        result = {
            'nostar': 0,
            'nopre': 0,
            'obj_x': 0.0,
            'obj_y': 0.0,
            'obj_flux': 0.0,
            'snr': 0.0,
            'obj_obsra': 0.0,
            'obj_obsde': 0.0,
            'n_match1': 0,
            'sig0': 0.0,
            'par1': np.zeros(30),
            'x_center': 0.0,
            'y_center': 0.0,
            'ra_center': 0.0,
            'de_center': 0.0,
            'ref_x': np.zeros(self.max_size),
            'ref_y': np.zeros(self.max_size),
            'ref_ra': np.zeros(self.max_size),
            'ref_de': np.zeros(self.max_size),
            'ref_mag': np.zeros(self.max_size)
        }

        par00 = np.zeros(6)
        par00[0] = 1.0
        par00[1] = 0.0
        par00[2] = 0.0
        par00[3] = 0.0
        par00[4] = 1.0
        par00[5] = 0.0

        par = np.zeros(30)
        par[0] = np.cos(field_angle * self.q) * par00[0] + np.sin(field_angle * self.q) * par00[3]
        par[1] = np.cos(field_angle * self.q) * par00[1] + np.sin(field_angle * self.q) * par00[4]
        par[2] = 0.0
        par[3] = -np.sin(field_angle * self.q) * par00[0] + np.cos(field_angle * self.q) * par00[3]
        par[4] = -np.sin(field_angle * self.q) * par00[1] + np.cos(field_angle * self.q) * par00[4]
        par[5] = 0.0

        # 读取reg文件
        regfile = fitsfile + '.reg'
        det_x, det_y, det_flux, snr = self.read_reg_file(regfile)
        n_det = len(det_x)

        if n_det < 3:
            print(f'{fitsfile}...检测星少于3颗')
            result['nostar'] = 1
            return result

        # 匹配过程 - 主要循环
        n_match1 = 0
        sig1 = 999.0
        obj_x0 = 0.0
        obj_y0 = 0.0
        obj_flux0 = 0.0
        snr0 = 0.0
        ref_x0 = np.zeros(self.max_size)
        ref_y0 = np.zeros(self.max_size)
        ref_flux0 = np.zeros(self.max_size)
        ref_ra0 = np.zeros(self.max_size)
        ref_de0 = np.zeros(self.max_size)
        ref_mag0 = np.zeros(self.max_size)
        par1_best = np.zeros(30)

        # 对每个检测星进行测试
        for j in range(n_det):
            obj_x = det_x[j]
            obj_y = det_y[j]

            # 计算检测星的赤经赤纬
            ref_x = []
            ref_y = []
            ref_flux_temp = []
            ref_ra = []
            ref_de = []
            ref_mag = []

            for k in range(n_det):
                if det_x[k] > 0 and det_y[k] > 0:
                    det_xn = (det_x[k] - obj_x) * pscale / fl
                    det_yn = (det_y[k] - obj_y) * pscale / fl

                    ra, de = self.xy2rade(par[:6], 6, det_xn, det_yn,
                                          obj_ephra * self.q, obj_ephde * self.q)

                    # 与星表匹配
                    for n in range(n_gaia0):
                        rl = self.cal_rl(ra, de,
                                         gaia_ra0[n] * self.q, gaia_de0[n] * self.q)
                        if rl / self.q * 3600 <= limit_match:
                            ref_x.append(det_xn)
                            ref_y.append(det_yn)
                            ref_flux_temp.append(det_flux[k])
                            ref_ra.append(gaia_ra0[n])
                            ref_de.append(gaia_de0[n])
                            ref_mag.append(gaia_mag0[n])
                            break  # 每个检测星只匹配一个星表星

            n_match = len(ref_x)

            # 需要足够的匹配星才能解算
            if n_match >= 3:
                # 解算底片常数
                try:
                    par1, sig0, nused = self.sol_par(
                        np.array(ref_x), np.array(ref_y),
                        np.array(ref_ra), np.array(ref_de),
                        n_match, obj_ephra, obj_ephde, modeltype
                    )
                    sig0 = sig0 / self.q * 3600.0

                    # 选择匹配数最多且sigma较小的
                    if 0.001 < sig0 < 0.5:
                        if n_match > n_match1 or (n_match == n_match1 and sig0 < sig1):
                            n_match1 = n_match
                            sig1 = sig0
                            obj_x0 = det_x[j]
                            obj_y0 = det_y[j]
                            obj_flux0 = det_flux[j]
                            snr0 = snr[j]
                            par1_best = par1.copy()

                            for i in range(n_match):
                                ref_x0[i] = ref_x[i] * fl / pscale + obj_x0
                                ref_y0[i] = ref_y[i] * fl / pscale + obj_y0
                                ref_flux0[i] = ref_flux_temp[i]
                                ref_ra0[i] = ref_ra[i]
                                ref_de0[i] = ref_de[i]
                                ref_mag0[i] = ref_mag[i]
                except Exception as e:
                    continue

        if n_match1 < 3:
            print('...此图像未找到与预报目标位置相近的目标')
            result['nopre'] = 1
            return result

        # 使用最佳匹配结果，重新计算底片常数
        ref_x = (ref_x0[:n_match1] - obj_x0) * pscale / fl
        ref_y = (ref_y0[:n_match1] - obj_y0) * pscale / fl

        par1, sig0, nused = self.sol_par(
            ref_x, ref_y, ref_ra0[:n_match1], ref_de0[:n_match1],
            n_match1, obj_ephra, obj_ephde, modeltype
        )

        # 计算视场中心
        x_center = np.mean(ref_x0[:n_match1])
        y_center = np.mean(ref_y0[:n_match1])

        obj_xn = (x_center - obj_x0) * pscale / fl
        obj_yn = (y_center - obj_y0) * pscale / fl

        ra_center, de_center = self.xy2rade(
            par1[:modeltype], modeltype, obj_xn, obj_yn,
            obj_ephra * self.q, obj_ephde * self.q
        )

        print(
            f'...参考星星座中心xyrade{x_center:11.3f}{y_center:11.3f}{ra_center / self.q:11.3f}{de_center / self.q:11.3f}')

        # 使用中心位置重新计算
        ref_x = (ref_x0[:n_match1] - x_center) * pscale / fl
        ref_y = (ref_y0[:n_match1] - y_center) * pscale / fl

        par1, sig0, nused = self.sol_par(
            ref_x, ref_y, ref_ra0[:n_match1], ref_de0[:n_match1],
            n_match1, ra_center / self.q, de_center / self.q, modeltype
        )
        sig1 = sig0 / self.q * 3600.0

        # 重新匹配参考星（使用更新的中心和底片常数）
        ref_x_new = []
        ref_y_new = []
        ref_flux_new = []
        ref_ra_new = []
        ref_de_new = []
        ref_mag_new = []

        for k in range(n_det):
            if det_x[k] > 0 and det_y[k] > 0:
                det_xn = (det_x[k] - x_center) * pscale / fl
                det_yn = (det_y[k] - y_center) * pscale / fl

                det_ra_k, det_de_k = self.xy2rade(
                    par1[:modeltype], modeltype, det_xn, det_yn,
                    ra_center, de_center
                )

                for n in range(n_gaia0):
                    rl = self.cal_rl(det_ra_k, det_de_k,
                                     gaia_ra0[n] * self.q, gaia_de0[n] * self.q)
                    if rl / self.q * 3600 <= limit_match:
                        ref_x_new.append(det_xn)
                        ref_y_new.append(det_yn)
                        ref_flux_new.append(det_flux[k])
                        ref_ra_new.append(gaia_ra0[n])
                        ref_de_new.append(gaia_de0[n])
                        ref_mag_new.append(gaia_mag0[n])
                        break

        n_match1 = len(ref_x_new)

        # 最终计算底片常数
        par1, sig0, nused = self.sol_par(
            np.array(ref_x_new), np.array(ref_y_new),
            np.array(ref_ra_new), np.array(ref_de_new),
            n_match1, ra_center / self.q, de_center / self.q, modeltype
        )
        sig1 = sig0 / self.q * 3600.0

        # 计算预报位置
        xi, eta = self.rade2xieta(
            obj_ephra * self.q, obj_ephde * self.q,
            ra_center, de_center
        )
        pre_x, pre_y = self.xieta2xy(xi, eta, par1[:6])
        pre_x = pre_x * fl / pscale + x_center
        pre_y = pre_y * fl / pscale + y_center

        print(f'...预报x/y，历表ra/de： {pre_x:11.5f}{pre_y:11.5f}{obj_ephra:11.5f}{obj_ephde:11.5f}')

        # 选择最接近预报位置的星
        obj_x_obs, obj_y_obs, obj_flux_obs, snr_obs, selectflag = \
            self.select_obj_xy(pre_x, pre_y, regfile)

        if selectflag == 0:
            print('...此图像未找到与预报目标位置相近的目标')
            result['nopre'] = 1
            return result

        # 计算观测位置
        obj_xn = (obj_x_obs - x_center) * pscale / fl
        obj_yn = (obj_y_obs - y_center) * pscale / fl

        obj_obsra, obj_obsde = self.xy2rade(
            par1[:modeltype], modeltype, obj_xn, obj_yn,
            ra_center, de_center
        )
        obj_obsra = obj_obsra / self.q
        obj_obsde = obj_obsde / self.q

        print(f'...实测x/y，实测ra/de： {obj_x_obs:11.5f}{obj_y_obs:11.5f}{obj_obsra:11.5f}{obj_obsde:11.5f}')

        if abs(obj_x0 - obj_x_obs) > 0.001 and abs(obj_y0 - obj_y_obs) > 0.001:
            print(f'...自动检测目标与最终确认目标有差异x/y {obj_x0 - obj_x_obs:7.3f}{obj_y0 - obj_y_obs:7.3f}')
        else:
            print('...自动检测确认的目标==最终确认的目标 ')

        # 填充结果
        result['obj_x'] = obj_x_obs
        result['obj_y'] = obj_y_obs
        result['obj_flux'] = obj_flux_obs
        result['snr'] = snr_obs
        result['obj_obsra'] = obj_obsra
        result['obj_obsde'] = obj_obsde
        result['n_match1'] = n_match1
        result['sig0'] = sig1
        result['par1'] = par1
        result['x_center'] = x_center
        result['y_center'] = y_center
        result['ra_center'] = ra_center
        result['de_center'] = de_center

        # 保存参考星信息用于输出
        for i in range(n_match1):
            result['ref_x'][i] = ref_x_new[i] * fl / pscale + x_center
            result['ref_y'][i] = ref_y_new[i] * fl / pscale + y_center
            result['ref_ra'][i] = ref_ra_new[i]
            result['ref_de'][i] = ref_de_new[i]
            result['ref_mag'][i] = ref_mag_new[i]

        return result

    def find_obj_base_prepar(self, fitsfile, par1, pscale, fl, modeltype, pre_x_center, pre_y_center,
                             pre_ra_center, pre_de_center, limit_match, obj_ephra, obj_ephde,
                             gaia_ra0, gaia_de0, gaia_mag0, n_gaia0):
        """使用已有参数查找目标"""
        result = {
            'nopre': 1,
            'obj_x': 0.0,
            'obj_y': 0.0,
            'obj_flux': 0.0,
            'snr': 0.0,
            'obj_obsra': 0.0,
            'obj_obsde': 0.0,
            'sig0': 0.0,
            'n_match1': 0,
            'par1': par1.copy(),
            'x_center': pre_x_center,
            'y_center': pre_y_center,
            'ra_center': pre_ra_center,
            'de_center': pre_de_center,
            'ref_x': np.zeros(self.max_size),
            'ref_y': np.zeros(self.max_size),
            'ref_ra': np.zeros(self.max_size),
            'ref_de': np.zeros(self.max_size),
            'ref_mag': np.zeros(self.max_size)
        }

        regfile = fitsfile + '.reg'
        det_x, det_y, det_flux, snr = self.read_reg_file(regfile)
        n_det = len(det_x)

        # 重新匹配参考星
        ref_x_new = []
        ref_y_new = []
        ref_flux_new = []
        ref_ra_new = []
        ref_de_new = []
        ref_mag_new = []

        for k in range(n_det):
            if det_x[k] > 0 and det_y[k] > 0:
                det_xn = (det_x[k] - pre_x_center) * pscale / fl
                det_yn = (det_y[k] - pre_y_center) * pscale / fl

                det_ra_k, det_de_k = self.xy2rade(
                    par1[:modeltype], modeltype, det_xn, det_yn,
                    pre_ra_center, pre_de_center
                )

                for n in range(n_gaia0):
                    rl = self.cal_rl(det_ra_k, det_de_k,
                                     gaia_ra0[n] * self.q, gaia_de0[n] * self.q)
                    if rl / self.q * 3600 <= limit_match:
                        ref_x_new.append(det_x[k])
                        ref_y_new.append(det_y[k])
                        ref_flux_new.append(det_flux[k])
                        ref_ra_new.append(gaia_ra0[n])
                        ref_de_new.append(gaia_de0[n])
                        ref_mag_new.append(gaia_mag0[n])
                        break

        n_match1 = len(ref_x_new)
        result['n_match1'] = n_match1

        # 保存参考星信息
        for i in range(n_match1):
            result['ref_x'][i] = ref_x_new[i]
            result['ref_y'][i] = ref_y_new[i]
            result['ref_ra'][i] = ref_ra_new[i]
            result['ref_de'][i] = ref_de_new[i]
            result['ref_mag'][i] = ref_mag_new[i]

        # 计算sig0
        if n_match1 >= 3:
            ref_xn = (np.array(ref_x_new) - pre_x_center) * pscale / fl
            ref_yn = (np.array(ref_y_new) - pre_y_center) * pscale / fl

            _, sig0, _ = self.sol_par(
                ref_xn, ref_yn,
                np.array(ref_ra_new), np.array(ref_de_new),
                n_match1, pre_ra_center / self.q, pre_de_center / self.q, modeltype
            )
            result['sig0'] = sig0 / self.q * 3600.0

        # 查找目标星
        rl0 = limit_match
        for k in range(n_det):
            if det_x[k] > 0 and det_y[k] > 0:
                det_xn = (det_x[k] - pre_x_center) * pscale / fl
                det_yn = (det_y[k] - pre_y_center) * pscale / fl

                det_ra, det_de = self.xy2rade(
                    par1[:modeltype], modeltype, det_xn, det_yn,
                    pre_ra_center, pre_de_center
                )

                rl = self.cal_rl(det_ra, det_de, obj_ephra * self.q, obj_ephde * self.q)
                rl = rl / self.q * 3600

                if rl <= limit_match and rl < rl0:
                    rl0 = rl
                    result['obj_x'] = det_x[k]
                    result['obj_y'] = det_y[k]
                    result['obj_flux'] = det_flux[k]
                    result['snr'] = snr[k]
                    result['obj_obsra'] = det_ra / self.q
                    result['obj_obsde'] = det_de / self.q
                    result['nopre'] = 0

        if result['nopre'] > 0:
            print('...据pre_par，未找到与预报目标位置相近的目标')

        return result

    def write_ref_file(self, filename, result):
        """输出参考星文件"""
        try:
            n_match = result.get('n_match1', 0)
            if n_match == 0:
                return

            with open(filename, 'w') as f:
                f.write(
                    'global color=red font="helvetica 10 normal" select=1 highlite=1 edit=1 move=1 delete=1 include=1 fixed=0 source\n')
                f.write('physical\n')

                for n in range(n_match):
                    # 格式: ellipse x y r1 r2 # ra de mag
                    f.write(f'ellipse{result["ref_x"][n]:11.3f}{result["ref_y"][n]:11.3f}')
                    f.write(f'{15.0:6.1f}{15.0:6.1f}  #  ')
                    f.write(f'{result["ref_ra"][n]:15.8f}{result["ref_de"][n]:8.3f}{result["ref_mag"][n]:20.10f}\n')
        except Exception as e:
            print(f"写入参考星文件错误: {e}")

    def write_object_result(self, fh, year, month, obj_T, obj_obsra, obj_obsde,
                            obj_ephra, obj_ephde, sig0, hh, mm, ss, exptime,
                            objfitsfile, field_angle):
        obj_resra = (obj_obsra - obj_ephra) * 3600.0 * np.cos(obj_ephde * self.q)
        obj_resde = (obj_obsde - obj_ephde) * 3600.0

        if abs(obj_resra) < 10 and abs(obj_resde) < 10:
            i1, i2, ff, cc, j1, j2, fff = self.am2hms(obj_obsra * 60.0, obj_obsde * 60.0)

            line = f'{year:6d} {month:02d}{obj_T:10.6f}{i1:3d}{i2:3d}{ff:8.4f} {cc}{j1:02d}{j2:3d}{fff:7.3f}'
            line += f'{obj_obsra:12.7f}{obj_obsde:12.7f}{obj_ephra:12.7f}{obj_ephde:12.7f}'
            line += f'{obj_resra:10.4f}{obj_resde:10.4f}{sig0:10.4f}'
            line += f'{hh:3d}{mm:3d}{ss:6.2f}{exptime:9.2f} {objfitsfile}{field_angle:7.2f}\n'

            fh.write(line)
            print(f'----写入out文件的结果,文件名：object_{os.path.basename(fh.name).split("_")[1].split(".")[0]}')
            print(f'...目标残差{obj_resra:10.4f}{obj_resde:10.4f}')

    def am2hms(self, ra, de):
        hh = int(ra / 60.0 / 15.0)
        mm = int((ra - hh * 60.0 * 15.0) / 15.0)
        ss = (ra - hh * 60.0 * 15.0 - mm * 15) * 60.0 / 15.0

        if de >= 0:
            sign = '+'
        else:
            sign = '-'

        de1 = abs(de)
        ddd = int(de1 / 60.0)
        dmm = int(de1 - ddd * 60.0)
        dss = (de1 - ddd * 60.0 - dmm) * 60.0

        return hh, mm, ss, sign, ddd, dmm, dss

    def sort_output_file(self, filename):
        try:
            lines = []
            times = []

            with open(filename, 'r') as f:
                for line in f:
                    if line.strip():
                        lines.append(line.strip())
                        parts = line.split()
                        if len(parts) > 1:
                            t = float(parts[1])
                            times.append(t)

            if len(lines) > 0 and len(times) == len(lines):
                sorted_indices = np.argsort(times)

                with open(filename, 'w') as f:
                    for idx in sorted_indices:
                        f.write(lines[idx] + '\n')
        except:
            pass

    def print_par(self, par, modeltype):
        if modeltype == 6:
            print(f'...底片常数具体值：{modeltype:2d}-', end='')
            for i in range(6):
                print(f'{par[i]:10.4f}', end='')
            print()
        elif modeltype == 12:
            print(f'...底片常数具体值：{modeltype:2d}-', end='')
            for i in range(12):
                print(f'{par[i]:10.4f}', end='')
            print()
        elif modeltype == 20:
            print(f'...底片常数具体值：{modeltype:2d}-', end='')
            for i in range(20):
                print(f'{par[i]:10.4f}', end='')
            print()
        elif modeltype == 30:
            print(f'...底片常数具体值：{modeltype:2d}-', end='')
            for i in range(30):
                print(f'{par[i]:10.4f}', end='')
            print()

if __name__ == '__main__':
    match = Match()
    match.main()
