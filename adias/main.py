"""ADIAS 统一入口：通过 --step 选择运行阶段。

用法：
  python -m adias.main                    # 跑完整 5 步
  python -m adias.main --step pre         # 仅跑指定步骤
  python -m adias.main --config my.cfg    # 指定配置文件
"""

import argparse
import os
import sys
import time

from adias.application.context import build_context
from adias.application.log import get_logger, setup_logging, teardown_logging
from adias.application.pipeline import PipelineRunner
from adias.application.steps import select_steps, selected_step_names
from adias.config import load_config
from adias.errors import ConfigError

DEFAULT_CONFIG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "inputs",
    "configs",
    "adias2023S0.cfg",
)


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
        help="配置文件路径（默认: inputs/configs/adias2024.cfg）",
    )
    args = parser.parse_args()

    setup_logging()
    log = get_logger()
    t0 = time.time()

    try:
        step_names = selected_step_names(args.step)
        config = load_config(args.config, steps=step_names)
        ctx = build_context(config, step_names)
        log.info(f"共读取到 {len(ctx.fitspath_list)} 个观测目录。\n")

        runner = PipelineRunner(select_steps(args.step))
        runner.run(ctx)

        log.info(f"\n总耗时: {time.time() - t0:.2f} s")
    except ConfigError as e:
        sys.exit(f"错误：{e}")
    finally:
        teardown_logging()


if __name__ == "__main__":
    main()
