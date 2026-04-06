# **********************************CCD 图像预处理：O-C 统计与野值剔除**********************************
# program name: 04comoc.py（Python 版 comoc.f90）
# function：
#   1）对前面匹配程序（03match）计算得到的观测目标 O-C 残差进行统计，迭代剔除野值，给出最终 O-C 的均值和标准偏差；
#   2）剔除模式 1：使用 (data-mean) 的绝对值 > std_limit×σ 的删除原则（配置项 4std_limit，一般取 2.6，推荐）；
#   3）剔除模式 2：使用 |data-mean| > mean_limit 的删除原则（配置项 4mean_limit，一般控制最终标准偏差不大于 0.03）；
#   4）可选择是否删除前面所有过程文件（*_n.fit, *.reg 等）：当 del_flag=1 时删除，调试阶段建议设 0；
#   5）可选使用 eps（4eps）限制：约束 |O-C| 不超过给定角秒上限。
#
# input：
#   0）注意修改 4specified-output，避免不同日期数据混在同一个输出文件中；
#   1）配置文件 adias.cfg（关键参数示例）：
#        1.1）fits 图像路径列表文件：1fitspath=.../fitspath.in
#        1.2）指定观测结果输出目录：4specified-output=/path/to/output_dir
#        1.3）标准差剔除模式参数：4std_limit=2.6
#        1.4）固定残差剔除模式参数：4mean_limit=0.03
#        1.5）残差绝对值上限（可选）：4eps=0.3
#        1.6）是否删除过程文件：4del_flag=0/1（0 保留，1 删除 *_n.fit 与 *.reg）
#   2）fitspath.in：每行一个观测日的 fits 图像文件夹路径，例如：
#        /Users/xxx/AstroPyFITS/observation_image_20231214
#   3）由前面程序得到的观测结果文件：每个 fits 文件夹内的 object_i.out（i = 1..obj_total）
#
# output：
#   1）每个观测日、每个目标的野值剔除结果（存于对应 fits 目录中）：
#        final_object_i.out      —— 剔除野值后的观测记录
#        final_oc_i.out          —— 该日期 O-C 统计结果（均值、标准偏差、迭代次数等）
#   2）汇总到指定输出目录（4specified-output）的按日期整理文件：
#        YYYYMMDDi.out           —— 当日该目标的剔除后观测记录汇总
#        YYYYMMDDi_obsdata_i.out —— 当日该目标的用于后续处理的观测子集
#        YYYYMMDDi_all_i.out     —— 当日该目标的完整行格式（便于检查）
#   3）全时段 O-C 汇总文件（按目标输出）：
#        00oc_i.out              —— 记录每一日期的样本数、均值、标准偏差以及剔除后结果
#
# by zhy 2019.08.25
# V3.0  Chinese comment by zhy 2020.01.31
# V4.0 by lhy 2025.12.05 程序改写成python
# ************************************************************************************************


import os
import math
import numpy as np


def main():
    m = 10000

    # 初始化变量
    tempcha = [''] * m
    new_tempcha = [''] * m
    res_ra = np.zeros(m)
    res_de = np.zeros(m)
    new_ra = np.zeros(m)
    new_de = np.zeros(m)
    ocra = np.zeros(m)
    ocde = np.zeros(m)

    # 01--读配置文件
    try:
        with open('adias.cfg', 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except:
        print("错误: 无法打开配置文件 adias.cfg")
        return

    obj_total = 0
    newoutfile0 = ''
    eps = 0.0
    oc_limit = 0.0
    mean_limit = 0.0
    del_flag = 0

    for line in lines:
        if '3obj_total=' in line:
            obj_total = int(line.split('=')[1].strip())
        elif '4specified-output=' in line:
            newoutfile0 = line.split('=')[1].strip()
        elif '4eps=' in line:
            eps = float(line.split('=')[1].strip())
        elif '4std_limit=' in line:
            oc_limit = float(line.split('=')[1].strip())
        elif '4mean_limit=' in line:
            mean_limit = float(line.split('=')[1].strip())
        elif '4del_flag=' in line:
            del_flag = int(line.split('=')[1].strip())

    # 确保输出目录存在
    if not os.path.exists(newoutfile0):
        os.makedirs(newoutfile0)
        print(f"创建输出目录: {newoutfile0}")

    obj = 0

    # 开始处理每个目标
    while obj < obj_total:
        obj += 1
        obj_label = str(obj)

        o_cfile = os.path.join(newoutfile0, f'00oc_{obj_label}.out')
        f3 = open(o_cfile, 'a', encoding='utf-8')

        try:
            with open('fitspath.in', 'r', encoding='utf-8') as f1:
                fitspath_lines = f1.readlines()
        except:
            print("错误: 无法打开文件 fitspath.in")
            f3.close()
            return

        if len(fitspath_lines) == 0:
            f3.close()
            continue

        # 读取第一行获取基本路径信息用于月度文件
        first_path = fitspath_lines[0].strip()

        # 提取目录名作为月度文件名的一部分
        try:
            dir_name = os.path.basename(first_path)
            month_outfile = os.path.join(newoutfile0, dir_name + obj_label + '.dat')
        except:
            month_outfile = os.path.join(newoutfile0, 'month_output_' + obj_label + '.dat')

        f18 = open(month_outfile, 'a', encoding='utf-8')

        n_day = 0

        # 逐日处理
        for fitspath in fitspath_lines:
            fitspath = fitspath.strip()
            n_day += 1

            print()
            print(f'{n_day:3d}-本日fits文件：{fitspath}')

            newoutfile = newoutfile0

            # 02--如果配置文件删除标识设置1，则删除过程文件
            if del_flag == 1:
                try:
                    # 删除_n.fit文件
                    for fname in os.listdir(fitspath):
                        if fname.endswith('_n.fit'):
                            os.remove(os.path.join(fitspath, fname))
                        elif fname.endswith('.reg'):
                            os.remove(os.path.join(fitspath, fname))
                    print('   过程文件已删除!!（*_n.fit,*.reg）')
                except Exception as e:
                    print(f'   删除过程文件时出错: {e}')

            # 03--编辑输出文件名
            objoutfile = os.path.join(fitspath, f'object_{obj_label}.out')
            newoutfile1 = os.path.join(fitspath, f'final_object_{obj_label}.out')
            o_cfile1 = os.path.join(fitspath, f'final_oc_{obj_label}.out')

            # 从observation_image目录中的文件提取日期
            # 文件名格式: 20231214J7-001I.fit
            try:
                fits_files = [f for f in os.listdir(fitspath) if f.endswith('.fit') and not f.endswith('_n.fit')]
                if fits_files:
                    # 提取前8位日期 20231214
                    date_str = fits_files[0][:8]
                else:
                    date_str = 'output'
            except:
                date_str = 'output'

            newoutfile = os.path.join(newoutfile0, date_str + obj_label + '.out')
            ic = newoutfile.rfind('.')
            obsdatafile = newoutfile[:ic] + f'_obsdata_{obj_label}.out'
            alloutfile = newoutfile[:ic] + f'_all_{obj_label}.out'

            # 04--读数据文件计算平均值与标准偏差
            if not os.path.exists(objoutfile):
                print(f'警告: 文件不存在 {objoutfile}')
                continue

            with open(objoutfile, 'r', encoding='utf-8') as f2:
                lines2 = f2.readlines()

            f4 = open(newoutfile, 'w', encoding='utf-8')
            f14 = open(alloutfile, 'w', encoding='utf-8')
            f5 = open(o_cfile1, 'w', encoding='utf-8')
            f6 = open(newoutfile1, 'w', encoding='utf-8')
            f7 = open(obsdatafile, 'w', encoding='utf-8')

            n_obj = 0
            res_ra = np.zeros(m)
            res_de = np.zeros(m)
            ocra = np.zeros(m)
            ocde = np.zeros(m)
            tempcha = [''] * m

            for i, line in enumerate(lines2):
                if len(line.strip()) == 0:
                    continue
                tempcha[i] = line.rstrip('\n')
                # 确保行长度足够
                if len(line) >= 147:
                    f14.write(line[:147] + '\n')
                else:
                    f14.write(line)
                # 读取第95-105列和第105-115列的数据
                try:
                    if len(line) >= 115:
                        res_ra[i] = float(line[95:105])
                        res_de[i] = float(line[105:115])
                        n_obj += 1
                except ValueError as e:
                    print(f'警告: 第{i + 1}行数据格式错误: {e}')
                    continue
                except Exception as e:
                    print(f'警告: 第{i + 1}行处理出错: {e}')
                    continue

            f14.close()

            # 041--统计原始数据均值与标准偏差
            if n_obj > 0:
                mean_ra0 = np.sum(res_ra[:n_obj]) / n_obj
                mean_de0 = np.sum(res_de[:n_obj]) / n_obj

                for i in range(n_obj):
                    ocra[i] = (res_ra[i] - mean_ra0) ** 2
                    ocde[i] = (res_de[i] - mean_de0) ** 2

                if n_obj > 1:
                    std_ra0 = math.sqrt(np.sum(ocra[:n_obj]) / (n_obj - 1))
                    std_de0 = math.sqrt(np.sum(ocde[:n_obj]) / (n_obj - 1))
                else:
                    std_ra0 = 0.0
                    std_de0 = 0.0
            else:
                mean_ra0 = 0.0
                mean_de0 = 0.0
                std_ra0 = 0.0
                std_de0 = 0.0

            if n_obj < 2:
                mean_ra0 = 999.999
                mean_de0 = 999.999
                std_ra0 = 999.999
                std_de0 = 999.999

            f5.write('=================res数据统计结果=================\n')
            f5.write(f'  原始数据数量n_obj：{n_obj:4d}\n')
            f5.write(f'  原始数据均值ra,de：{mean_ra0:12.4f}{mean_de0:12.4f}\n')
            f5.write(f'  原始数据方差ra,de：{std_ra0:12.4f}{std_de0:12.4f}\n')
            if oc_limit > 0.0:
                f5.write(f'*********剔除野值标准(oc_limit)：{oc_limit:5.2f}  *********\n')
            else:
                f5.write(f'*********剔除野值标准(mean_limit)：{mean_limit:5.2f}  *********\n')

            print('================04Comoc-Program execution summary==================')
            print('=================res数据统计结果=================')
            print(f'  原始数据数量n_obj：{n_obj:4d}')
            print(f'  原始数据均值ra,de：{mean_ra0:12.4f}{mean_de0:12.4f}')
            print(f'  原始数据方差ra,de：{std_ra0:12.4f}{std_de0:12.4f}')
            if oc_limit > 0.0:
                print(f'*********剔除野值标准(oc_limit)：{oc_limit:5.2f}  *********')
            else:
                print(f'*********剔除野值标准(mean_limit)：{mean_limit:5.2f}  *********')

            n_obj0 = n_obj
            mean_ra = mean_ra0
            mean_de = mean_de0
            std_ra = std_ra0
            std_de = std_de0

            # 迭代剔除野值
            iloop = 1
            while True:
                n_new = 0
                new_tempcha = [''] * m
                new_ra = np.zeros(m)
                new_de = np.zeros(m)
                ocra = np.zeros(m)
                ocde = np.zeros(m)

                for i in range(n_obj):
                    if oc_limit > 0.0:
                        if (abs(res_ra[i] - mean_ra) < oc_limit * std_ra and
                                abs(res_de[i] - mean_de) < oc_limit * std_de and
                                abs(res_ra[i]) < eps and abs(res_de[i]) < eps):
                            new_tempcha[n_new] = tempcha[i]
                            new_ra[n_new] = res_ra[i]
                            new_de[n_new] = res_de[i]
                            n_new += 1
                    else:
                        if (abs(res_ra[i] - mean_ra) < mean_limit and
                                abs(res_de[i] - mean_de) < mean_limit):
                            new_tempcha[n_new] = tempcha[i]
                            new_ra[n_new] = res_ra[i]
                            new_de[n_new] = res_de[i]
                            n_new += 1

                if n_new > 0:
                    mean_ra = np.sum(new_ra[:n_new]) / n_new
                    mean_de = np.sum(new_de[:n_new]) / n_new

                    for i in range(n_new):
                        ocra[i] = (new_ra[i] - mean_ra) ** 2
                        ocde[i] = (new_de[i] - mean_de) ** 2

                    if n_new > 1:
                        std_ra = math.sqrt(np.sum(ocra[:n_new]) / (n_new - 1))
                        std_de = math.sqrt(np.sum(ocde[:n_new]) / (n_new - 1))
                    else:
                        std_ra = 0.0
                        std_de = 0.0
                else:
                    mean_ra = 0.0
                    mean_de = 0.0
                    std_ra = 0.0
                    std_de = 0.0

                if n_obj > n_new:
                    tempcha = new_tempcha.copy()
                    res_ra = new_ra.copy()
                    res_de = new_de.copy()
                    n_obj = n_new
                    iloop += 1
                else:
                    break

            if n_obj0 < 1:
                mean_ra0 = 0
                mean_de0 = 0
                std_ra0 = 0
                std_de0 = 0
                n_new = 0
                mean_ra = 0
                mean_de = 0
                std_ra = 0
                std_de = 0
            elif n_new < 1:
                n_new = 0
                mean_ra = 0
                mean_de = 0
                std_ra = 0
                std_de = 0

            if n_obj < 2:
                mean_ra = 999.999
                mean_de = 999.999
                std_ra = 999.999
                std_de = 999.999

            f5.write(f'  剔除野值后数据数量n_new：{n_new:4d}\n')
            f5.write(f'  剔除野值后数据均值ra,de：{mean_ra:12.4f}{mean_de:12.4f}\n')
            f5.write(f'  剔除野值后数据方差ra,de：{std_ra:12.4f}{std_de:12.4f}\n')
            f5.write(f'  剔除野值迭代次数：{iloop:2d}\n')

            print(f'  剔除野值后数据数量n_new：{n_new:4d}')
            print(f'  剔除野值后数据均值ra,de：{mean_ra:12.4f}{mean_de:12.4f}')
            print(f'  剔除野值后数据方差ra,de：{std_ra:12.4f}{std_de:12.4f}')
            print(f'  剔除野值迭代次数：{iloop:2d}')
            print(f'  残差文件输出:{o_cfile}')

            # 输出结果
            if std_ra < 0.3 and std_de < 0.3 and n_new > 1:
                f3.write(
                    f'{date_str} & {n_obj0:4d} & {mean_ra0:9.3f} & {mean_de0:9.3f} & {std_ra0:9.3f} & {std_de0:9.3f} & {n_new:4d} & {mean_ra:9.3f} & {mean_de:9.3f} & {std_ra:9.3f} & {std_de:9.3f}\n')
                print(
                    f'{date_str}{n_obj0:4d}{mean_ra0:9.4f}{mean_de0:9.4f}{std_ra0:9.4f}{std_de0:9.4f}{n_new:4d}{mean_ra:9.4f}{mean_de:9.4f}{std_ra:9.4f}{std_de:9.4f}')

                for i in range(n_new):
                    if len(new_tempcha[i]) >= 147:
                        f4.write(new_tempcha[i][:147] + '\n')
                    else:
                        f4.write(new_tempcha[i] + '\n')
                    f6.write(new_tempcha[i] + '\n')
                    if len(new_tempcha[i]) >= 48:
                        f7.write(new_tempcha[i][:48] + '\n')
                    else:
                        f7.write(new_tempcha[i] + '\n')
                    if len(new_tempcha[i]) >= 147:
                        f18.write(new_tempcha[i][:147] + '\n')
                    else:
                        f18.write(new_tempcha[i] + '\n')
            else:
                print('删除该日期数据：============')
                print(
                    f'{date_str}{n_obj0:4d}{mean_ra0:9.4f}{mean_de0:9.4f}{std_ra0:9.4f}{std_de0:9.4f}{n_new:4d}{mean_ra:9.4f}{mean_de:9.4f}{std_ra:9.4f}{std_de:9.4f}')
                print('================')

            f4.close()
            f5.close()
            f6.close()
            f7.close()

        # 处理下一个目标
        f18.close()
        f3.close()

    print(f'   本日匹配共归算天然卫星目标个数{obj:3d}')
    print('=================================================================')
    print(f'数据统计归算结束，共处理数据天数：{n_day:3d}')
    print('=================================================================')
    print('=====================ADIAS END======================')

if __name__ == '__main__':
    main()