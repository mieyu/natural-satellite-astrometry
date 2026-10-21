"""5 步流水线 Step 包装：保持 step 名/标题与历史一致。

Step 协议：拥有 name、title 属性；run(ctx) 返回 StepResult。
所有实际算法在 nspa.core 内，通过 ctx.config（NspaConfig）传参。
"""

from pathlib import Path

from nspa.application.pipeline import StepResult


def _ensure_result(value, name) -> StepResult:
    if isinstance(value, StepResult):
        return value
    return StepResult(name)


class PreStep:
    name = "pre"
    title = "========== 01: 超级背景预处理 =========="

    def run(self, ctx):
        from nspa.core.preprocessor import run_pre

        return _ensure_result(run_pre(ctx.config, ctx.fitspath_list), self.name)


class DetectStep:
    name = "detect"
    title = "========== 02: 星象检测 =========="

    def run(self, ctx):
        from nspa.core.detector import run_detect

        return _ensure_result(run_detect(ctx.config, ctx.fitspath_list), self.name)


class MatchStep:
    name = "match"
    title = "========== 03: 星象匹配归算 =========="

    def run(self, ctx):
        from nspa.core.matcher import run_match

        return _ensure_result(run_match(ctx.config, ctx.fitspath_list), self.name)


class ComocStep:
    name = "comoc"
    title = "========== 04: O-C 统计 =========="

    def run(self, ctx):
        from nspa.core.analyzer import run_comoc

        result = _ensure_result(run_comoc(ctx.config, ctx.fitspath_list, ctx.run_id), self.name)
        ctx.report_dat_files = [
            Path(name) for name in result.output_files if Path(name).suffix.lower() == ".dat"
        ]
        return result


class ReportStep:
    name = "report"
    title = "========== 05: O-C 散点图报告 =========="

    def run(self, ctx):
        from nspa.core.reporter import run_report

        dat_files = ctx.report_dat_files if "comoc" in ctx.selected_steps else None
        return _ensure_result(run_report(ctx.config, dat_files=dat_files), self.name)


STEP_CLASSES = {
    "pre": PreStep,
    "detect": DetectStep,
    "match": MatchStep,
    "comoc": ComocStep,
    "report": ReportStep,
}


def select_steps(step_name):
    if step_name == "all":
        names = ["pre", "detect", "match", "comoc", "report"]
    else:
        names = [step_name]
    return [STEP_CLASSES[name]() for name in names]


def selected_step_names(step_name):
    return [step.name for step in select_steps(step_name)]
