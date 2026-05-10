# 功能：ADIAS 统一入口，通过 --step 选择运行阶段。
# 使用：python -m adias.main --step pre
#       python -m adias.main --step all --config adias.cfg --fitspath fitspath.in

import argparse
import time

from adias.adias_config      import parse_config
from adias.io.adias_text_io  import read_fitspath
from adias.core.adias_preprocessor import run_pre
from adias.core.adias_detector import run_detect
from adias.core.adias_matchor import run_match
from adias.core.adias_analyzer import run_comoc



def main():
    parser = argparse.ArgumentParser(description='ADIAS CCD 图像处理流水线')
    parser.add_argument('--step',
                        choices=['pre', 'detect', 'match', 'comoc', 'all'],
                        default='all',
                        help='运行阶段（默认: all）')
    parser.add_argument('--config',
                        default='/Users/liuhongyu/PythonProject/AstroPyFITS/adias.cfg',
                        help='配置文件路径（默认: adias.cfg）')
    parser.add_argument('--fitspath',
                        default='/Users/liuhongyu/PythonProject/AstroPyFITS/fitspath.in',
                        help='观测路径列表文件（默认: fitspath.in）')
    args = parser.parse_args()

    t0 = time.time()

    config        = parse_config(args.config)
    fitspath_list = read_fitspath(args.fitspath)
    print(f"共读取到 {len(fitspath_list)} 个观测目录。\n")

    if args.step in ('pre', 'all'):
        print("========== 01: 超级背景预处理 ==========")
        run_pre(config, fitspath_list)

    if args.step in ('detect', 'all'):
        print("========== 02: 星象检测 ==========")
        run_detect(config, fitspath_list)

    if args.step in ('match', 'all'):
        print("========== 03: 星象匹配归算 ==========")
        run_match(config, fitspath_list)

    if args.step in ('comoc', 'all'):
        print("========== 04: O-C 统计 ==========")
        run_comoc(config, fitspath_list)

    print(f"\n总耗时: {time.time() - t0:.2f} s")


if __name__ == '__main__':
    main()