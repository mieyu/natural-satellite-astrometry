# 功能：统一解析 adias.cfg 配置文件，供所有 core 模块调用。
# 使用：from adias.config import parse_config
#       config = parse_config()           # 默认读取当前目录 adias.cfg
#       config = parse_config('my.cfg')   # 指定路径

import os


def parse_config(config_path='adias.cfg'):
    """
    解析 adias.cfg，返回完整参数字典。所有参数均有默认值，配置文件缺失时不崩溃。

    解析规则
    --------
    - 跳过空行和以 !, ;, #, [ 开头的注释行
    - 去除行内 % 之后的注释
    - 键名前缀数字（如 1med_width）在映射表中统一处理
    """
    defaults = {
        # 01pre
        'biasflag': 0, 'darkflag': 0, 'flatflag': 0, 'superflag': 0,
        'med_length': 1, 'med_width': 25, 'bkgdmode': 2, 'enhance_flag': 1,
        # 02detect
        'bkgd_threshold': 5.0, 'snr_threshold': 5.0, 'pos_method': 2,
        # 03match
        'tele_label': '', 'fl': 0.0, 'pscale': 0.0, 'fsize': 0,
        'modeltype': 0, 'field_angle': 0.0, 'ephsource': '',
        'min_mag': 0.0, 'max_mag': 0.0, 'limit_match': 0.0,
        'delta_t': 0.0, 'gaiacatpath': '', 'obj_total': 0, 'ephpath': [],
        # 04comoc
        'newoutfile0': '', 'eps': 0.0, 'oc_limit': 0.0,
        'mean_limit': 0.0, 'del_flag': 0,
    }

    # cfg 键名 -> (内部变量名, 类型)
    key_map = {
        '1biasflag':         ('biasflag',        'int'),
        '1darkflag':         ('darkflag',         'int'),
        '1flatflag':         ('flatflag',         'int'),
        '1superflag':        ('superflag',        'int'),
        '1med_length':       ('med_length',       'int'),
        '1med_width':        ('med_width',        'int'),
        '1bkgdmode':         ('bkgdmode',         'int'),
        '1enhance_flag':     ('enhance_flag',     'int'),
        '2bkgd_threshold':   ('bkgd_threshold',   'float'),
        '2snr_threshold':    ('snr_threshold',    'float'),
        '2pos_method':       ('pos_method',       'int'),
        '3tele_label':       ('tele_label',       'str'),
        '3tele_focal':       ('fl',               'float'),
        '3ccd_scale':        ('pscale',           'float'),
        '3ccd_fieldsize':    ('fsize',            'int'),
        '3modeltype':        ('modeltype',        'int'),
        '3plate_angle':      ('field_angle',      'float'),
        '3obj_ephsource':    ('ephsource',        'str'),
        '3gaia_minmag':      ('min_mag',          'float'),
        '3gaia_maxmag':      ('max_mag',          'float'),
        '3match_limit':      ('limit_match',      'float'),
        '3delta_T':          ('delta_t',          'float'),
        '3gaia_catfile':     ('gaiacatpath',      'str'),
        '3obj_total':        ('obj_total',        'int'),
        '4specified-output': ('newoutfile0',      'str'),
        '4eps':              ('eps',              'float'),
        '4std_limit':        ('oc_limit',         'float'),
        '4mean_limit':       ('mean_limit',       'float'),
        '4del_flag':         ('del_flag',         'int'),
    }

    if not os.path.exists(config_path):
        print(f"警告：配置文件 '{config_path}' 未找到，使用默认参数。")
        return defaults

    with open(config_path, 'r', encoding='utf-8-sig') as f:
        lines = f.readlines()

    params = defaults.copy()

    for line in lines:
        line = line.strip()
        if not line or line.startswith(('!', ';', '#', '[')):
            continue
        if '=' not in line:
            continue
        raw_key, raw_val = line.split('=', 1)
        key   = raw_key.strip()
        value = raw_val.split('%')[0].strip()
        if not value or key not in key_map:
            continue
        var_name, var_type = key_map[key]
        try:
            if var_type == 'int':
                params[var_name] = int(value)
            elif var_type == 'float':
                params[var_name] = float(value)
            else:
                params[var_name] = value
        except ValueError:
            print(f"警告：无法解析 {key}={value}，保留默认值。")

    # ephpath 列表：数量由 obj_total 决定，需在主循环后单独处理
    params['ephpath'] = []
    for obj in range(1, params['obj_total'] + 1):
        for line in lines:
            if f'3obj_ephfile{obj}=' in line:
                val = line.split('=', 1)[1].split('%')[0].strip()
                params['ephpath'].append(val)
                break

    return params