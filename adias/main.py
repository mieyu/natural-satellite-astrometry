# ADIAS 统一入口：通过 --step 选择运行阶段。
# 用法:
#   python -m adias.main                    # 跑完整 5 步
#   python -m adias.main --step pre         # 仅跑指定步骤
#   python -m adias.main --config my.cfg    # 指定配置文件

import argparse
import os
import sys
import time

from adias import (
    parse_config,
    run_comoc,
    run_detect,
    run_match,
    run_pre,
    run_report,
)
from adias.paths import expand_fitspath

DEFAULT_CONFIG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "adias2024.cfg"
)


class _Tee:
    """同时向 stdout 与文件写出的透明代理。"""

    def __init__(self, file_path):
        self._stdout = sys.stdout
        self._file = open(file_path, "w", encoding="utf-8", buffering=1)
        sys.stdout = self

    def write(self, data):
        self._stdout.write(data)
        self._file.write(data)

    def flush(self):
        self._stdout.flush()
        self._file.flush()

    def close(self):
        sys.stdout = self._stdout
        self._file.close()


def main():
    parser = argparse.ArgumentParser(description="ADIAS CCD 图像处理流水线")
    parser.add_argument(
        "--step",
        choices=["pre", "detect", "match", "comoc", "report", "all"],
        default="all",
        help="运行阶段（默认: all）",
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG,
        help="配置文件路径（默认: 项目根目录下 adias2024.cfg）",
    )
    args = parser.parse_args()

    tee = _Tee("控制台输出.txt")
    t0 = time.time()

    config = parse_config(args.config)
    if not config["fitspath"]:
        sys.exit("错误：cfg 中未配置 1fitspath，无法确定观测目录。")
    fitspath_list = expand_fitspath(config["fitspath"])
    print(f"共读取到 {len(fitspath_list)} 个观测目录。\n")

    if args.step in ("pre", "all"):
        print("========== 01: 超级背景预处理 ==========")
        run_pre(config, fitspath_list)

    if args.step in ("detect", "all"):
        print("========== 02: 星象检测 ==========")
        run_detect(config, fitspath_list)

    if args.step in ("match", "all"):
        print("========== 03: 星象匹配归算 ==========")
        run_match(config, fitspath_list)

    if args.step in ("comoc", "all"):
        print("========== 04: O-C 统计 ==========")
        run_comoc(config, fitspath_list)

    if args.step in ("report", "all"):
        print("========== 05: O-C 散点图报告 ==========")
        run_report(config)

    print(f"\n总耗时: {time.time() - t0:.2f} s")
    tee.close()


if __name__ == "__main__":
    main()
