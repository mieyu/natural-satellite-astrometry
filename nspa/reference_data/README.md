# 星表与历表准备

统一入口 `prepare_references(request, progress, cancel)` 支持分别从 inputs 文件和网络获取历表、Gaia 星表。
本模块不导入 Tk、不启动科学处理阶段、不改写输入或配置文件。UI 在准备成功后把返回路径交给原配置生成器。

```python
from pathlib import Path
from nspa.reference_data import ReferenceRequest, prepare_references

request = ReferenceRequest(
    fitspaths=(Path("inputs/images/U/2020/20201113/fits"),),
    cache_root=Path("inputs/catalogs/_downloaded"),
    eph_source="download",
    gaia_source="download",
    targets=("U1", "U2", "U5"),
    tele_label="km100",
    observatory="286",
    field_half_arcmin=15,
)
prepared = prepare_references(request, progress=print)
# prepared.eph_files, prepared.gaia_catfile, prepared.obj_total, prepared.manifest_path
```

本地模式使用 `eph_source="inputs"` / `gaia_source="inputs"`，对应设置 `local_eph_files` 和 `local_gaia_file`。
两种来源可混合。`cancel` 是可选 `threading.Event`；取消会抛 `PreparationCancelled`。所有 UI 参数必须在主线程读成请求，再交给后台工作线程。

## 模块

- `models.py`：请求、结果、统一错误类型。
- `planning.py`：按现有 FITS 读取规则取得曝光中点 UTC、应用时间改正，推导单月时间范围和覆盖所有轨迹的 Gaia 天区。
- `providers/local.py`：只读检查已有文件；用于自动 Gaia 查询时同时核对本地历表的目标、月份、UTC/ICRF 和时间覆盖。
- `providers/imcce.py`：直接提交官方 CGI，十进制小时/度数输出，分块请求，无可见性裁剪，校验实际模型及完整时刻网格。
- `providers/gaia.py`：ESA TAP 的 `gaiadr3.gaia_source`、`votable_plain`、六列查询；检查 QUERY_STATUS、单位和天区。
- `providers/transport.py`：有限超时/重试、响应大小限制、取消检查；直连或使用系统代理，始终验证 HTTPS 证书。
- `formats.py`：生成十行表头历表及六十行表头、39 字符来源编号前缀的 Gaia 兼容 DAT，保留原始数值精度。
- `validation.py`：时间覆盖、插值点数、现有读取器回读验证。
- `cache.py`：请求哈希、文件 SHA256、临时目录和原子发布；损坏缓存会报错而不覆盖。
- `service.py`：协调两种来源并返回最终文件路径和批次来源记录。

## 科学约定与边界

- 时间来自 FITS 的设备读取规则及曝光中点，不能只从目录或文件名推测。因现有算法按月内日数插值，第一版要求单个 UTC 月份；时间改正后越过不支持的月边界会明确报错。
- 历表默认一分钟一步、前后五分钟余量，边界限制在本月，至少准备四个插值点。下载不启用可见性筛选，以覆盖已选曝光。
- Gaia 保留 DR3 的 ICRS/2016.0 数据和自行，下载时不提前做观测历元改正；这一步由现有归算算法执行。查询范围包含整段目标轨迹、参考星搜索半宽及余量；默认半径至少 30′，最大 5°。
- `source_id, ra, dec, pmra, pmdec, phot_g_mean_mag` 原始响应完整保存。必需数值缺失的记录在兼容文件中排除，数量记入 manifest，不补零。五字段保留上游精度，不按旧文件显示位数提前截断。
- 优先以对应本地历表的卫星理论为版本提示；否则核对推荐理论。上游给不出所需理论时失败，绝不自动改用 JPL/GUST86 等替代。
- 静态官方表单标签与 CGI 的实际编号曾不一致：2026-10-29 天王星实测 `plnvar=0` 返回 Lainey 2015、`plnvar=2` 返回 GUST86，`nde=6` 返回 DE441。因此编号由 provider 处理，每个实际响应仍需核对返回头。模型探测仅在有限候选编号间核验同一所需理论，不接收不匹配的模型。
- 下载按当前 FITS 时段制定请求，起点可能与历史下载不同。2026-10-30 实测 U2 的 146 点中有 3 个赤经值与旧文件末位相差 1e-10 小时（最大 Δα cosδ 约 5.25e-6 角秒）；保留上游原值和完整请求，不使用旧文件强行修正。相同模型/字段不表示任意批次都与旧文本每个十进制末位或整条算法输出完全相同。
- `targets.json` 是依据七组 MULTI-SAT 表单整理的 185 项编号元数据，包含行星中心和系统质心；编号不能由卫星序号简单拼接（如 J14=5006、U24=7022、N3=8008）。模型是否可用仍以上游实际响应为准。

## 文件保护和缓存

默认下载目录为所选 inputs 的 `catalogs/_downloaded/`，项目默认目录已加入 Git 忽略规则。每种来源按内容参数单独缓存：

```text
_downloaded/
  ephemeris/<request-sha256>/
    raw-000.html
    EPH_U1_202011.DAT
    manifest.json
  gaia/<query-sha256>/
    raw.vot
    GAIA3_FIELD_202011.DAT
    manifest.json
  jobs/<unique-id>.json
```

缓存只有在单位、模型、时间覆盖和现有读取器回读全部通过后才原子发布。失败/取消清理本次临时目录；此前已完整发布的其他目标可继续复用。对已存在缓存仅校验和读取，不静默替换损坏内容；需要重取时可指定新的缓存目录。

UI 运行配置另存到所选 outputs 的 `runs/ui_<唯一编号>/config.cfg`，不改 inputs/configs；配置注释记录 reference manifest。

官方服务：

- [IMCCE-SAI MULTI-SAT](https://www.sai.msu.ru/neb/nss/nssreq7e.htm)
- [ESA Gaia Archive TAP](https://gea.esac.esa.int/tap-server/tap/sync)
- [Gaia TAP 输出格式说明](https://docs.astropy.org/projects/astroquery/en/latest/gaia/gaia.html)
