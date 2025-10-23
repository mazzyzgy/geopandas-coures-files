import json, os, io, sys
p = r'hangzhou-land.ipynb'
with open(p,'r',encoding='utf-8') as f:
    nb = json.load(f)

md_cell = {
  "cell_type": "markdown",
  "metadata": {},
  "source": [
    "#### 5.2 与百度人口点统计进行对比\n",
    "(a) 排除 '用地类别f' 中道路、绿地、河流等不可能有居住人口和岗位的用地；\n",
    "(b) 用百度人口点与 xzyd 图层空间连接，将所在地块的 dkID 赋值给点图层；\n",
    "(c) 没有相交关系的点，用 building 层去连接并标记；\n",
    "(d) 与 building 也没有相交的点，找到最近地块，赋值最近地块 dkID；\n",
    "(e) 基于 '用地类别f' 与区县分组汇总，统计人口、岗位数量。\n"
  ]
}

code_src = '''# ——— 5.2 与百度人口点统计进行对比 ———
# 说明：此单元依赖已经加载的 xzyd、zone、building 以及 gis_file。
# 如需直接从 GDB 读取百度人口点，请设置 bd_points_layer 候选名。

import numpy as np
import pandas as pd
import geopandas as gpd


def pick_first_existing(col_candidates, df):
    for c in col_candidates:
        if c in df.columns:
            return c
    return None

# 0) 标准化关键列名
land_type_candidates = ['用地类别f', '用地类别f', 'land_type2', 'land_type1', 'LANDUSAGE']
dkid_candidates      = ['dkID', 'xzdkID', 'xzdkid', 'DKID', 'dk_id', 'ID']
zone_name_candidates = ['xzq', 'belong_xzq', '区', '行政区', 'XZQ', 'xzqJD', 'xzqjd']
pop_candidates       = ['人口', '人口', '人口数', 'pop', 'population', 'pop_count']
jobs_candidates      = ['岗位', '岗位', '岗位数', 'jobs', 'job', 'job_count']

land_type_col = pick_first_existing(land_type_candidates, xzyd) or '用地类别f'
dkid_col      = pick_first_existing(dkid_candidates, xzyd) or 'dkID'
zone_name_col = pick_first_existing(zone_name_candidates, zone)

# 1) 读取/准备 百度人口点
bd_points = None
try:
    bd_points  # noqa: F821
except NameError:
    # 常见候选图层名（根据你的GDB自行调整顺序/名称）
    bd_points_layers = [
        '百度人口点', 'baidu_rk_point', 'baidu_points', 'rk_points', '人口点'
    ]
    for lyr in bd_points_layers:
        try:
            bd_points = gpd.read_file(gis_file, layer=lyr)
            print(f"Loaded Baidu points layer: {lyr}")
            break
        except Exception:
            continue
    if bd_points is None:
        raise RuntimeError('未找到百度人口点图层，请设置 bd_points 或调整图层名候选。')

# 统一坐标系
if bd_points.crs != xzyd.crs:
    bd_points = bd_points.to_crs(xzyd.crs)
if zone.crs != xzyd.crs:
    zone = zone.to_crs(xzyd.crs)
if building.crs != xzyd.crs:
    building = building.to_crs(xzyd.crs)

# 2) (a) 过滤不可能有人口/岗位的用地类型
ban_keywords = [
    '道路', '公路', '轨道', '交通', '停车场', '绿地', '公园', '景观', '防护绿',
    '河', '江', '湖', '溪', '水域', '水面', '河道', '湿地', '港口', '广场',
    'road', 'street', 'rail', 'transport', 'green', 'park', 'river', 'water', 'square'
]

def is_banned(val):
    if pd.isna(val):
        return False
    s = str(val)
    return any(k in s for k in ban_keywords)

xzyd['_is_banned_ydf'] = xzyd[land_type_col].apply(is_banned)
xzyd_valid = xzyd[~xzyd['_is_banned_ydf']].copy()

# 3) (b) 点落地到地块（within），赋值 dkID 与 '用地类别f'
join1 = gpd.sjoin(
    bd_points, xzyd_valid[[dkid_col, land_type_col, 'geometry']],
    how='left', predicate='within', lsuffix='pt', rsuffix='dk'
)
join1 = join1.rename(columns={dkid_col: 'dkID_matched', land_type_col: 'ydf_matched'})
join1['match_level'] = np.where(join1['dkID_matched'].notna(), 'xzyd', 'unmatched')

# 4) (c) 未匹配点与 building 连接（within）并标记
unmatched_mask = join1['match_level'].eq('unmatched')
if unmatched_mask.any():
    building_small = building[['geometry']].copy()
    join_bld = gpd.sjoin(
        join1.loc[unmatched_mask, ['geometry']].set_geometry('geometry'),
        building_small, how='left', predicate='within'
    )
    # 标记落在建筑内的点
    has_building = join_bld.index.unique()
    join1.loc[has_building, 'match_level'] = 'building'

# 5) (d) 仍未匹配的点，匹配最近地块（使用有效用地）
still_unmatched = join1['match_level'].eq('unmatched')
if still_unmatched.any():
    near = gpd.sjoin_nearest(
        join1.loc[still_unmatched, ['geometry']].set_geometry('geometry'),
        xzyd_valid[[dkid_col, land_type_col, 'geometry']],
        how='left', distance_col='nearest_dist'
    )
    near = near.rename(columns={dkid_col: 'dkID_matched', land_type_col: 'ydf_matched'})
    join1.loc[still_unmatched, 'dkID_matched'] = near['dkID_matched'].values
    join1.loc[still_unmatched, 'ydf_matched'] = near['ydf_matched'].values
    join1.loc[still_unmatched, 'nearest_dist'] = near['nearest_dist'].values
    join1.loc[still_unmatched, 'match_level'] = 'nearest'

# 6) 对落在 building 的点，如仍没有 dkID，则也用最近地块补上
need_near_for_building = join1['match_level'].eq('building') & join1['dkID_matched'].isna()
if need_near_for_building.any():
    near_b = gpd.sjoin_nearest(
        join1.loc[need_near_for_building, ['geometry']].set_geometry('geometry'),
        xzyd_valid[[dkid_col, land_type_col, 'geometry']],
        how='left', distance_col='nearest_dist'
    )
    near_b = near_b.rename(columns={dkid_col: 'dkID_matched', land_type_col: 'ydf_matched'})
    join1.loc[need_near_for_building, 'dkID_matched'] = near_b['dkID_matched'].values
    join1.loc[need_near_for_building, 'ydf_matched'] = near_b['ydf_matched'].values
    join1.loc[need_near_for_building, 'nearest_dist'] = near_b['nearest_dist'].values
    # 仍保留 match_level='building' 以示来源

# 7) 区县赋值（与 zone 叠加）
join_zone = gpd.sjoin(
    join1[['geometry']].set_geometry('geometry'),
    zone[[zone_name_col, 'geometry']],
    how='left', predicate='within'
) if zone_name_col else None
if join_zone is not None:
    join1['district'] = join_zone[zone_name_col].values
else:
    join1['district'] = None

# 8) 标准化人口/岗位字段名（尽力自动识别）
pop_col  = pick_first_existing(pop_candidates, bd_points)
jobs_col = pick_first_existing(jobs_candidates, bd_points)
if pop_col is None and '人口_推断' in bd_points.columns:
    pop_col = '人口_推断'
if jobs_col is None and '岗位_推断' in bd_points.columns:
    jobs_col = '岗位_推断'

join1['pop']  = bd_points[pop_col].values if pop_col else 1
join1['jobs'] = bd_points[jobs_col].values if jobs_col else 0

# 简单清洗：将无法解析的转为0
for c in ['pop','jobs']:
    join1[c] = pd.to_numeric(join1[c], errors='coerce').fillna(0)

# 9) (e) 基于区与用地类别分组汇总
agg_df = (
    join1
    .dropna(subset=['ydf_matched'])
    .groupby(['district','ydf_matched'], dropna=False)[['pop','jobs']]
    .sum()
    .reset_index()
    .rename(columns={'ydf_matched':'用地类别f'})
)

print('匹配统计：')
print(join1['match_level'].value_counts(dropna=False))
print('分组汇总（按区 x 用地类别f）：')
try:
    display(agg_df.head(10))
except Exception:
    print(agg_df.head(10))

# 可选：导出结果点
# join1.to_file(gis_file, layer='baidu_points_matched', driver='OpenFileGDB')
'''.splitlines(True)

code_cell = {
  "cell_type": "code",
  "execution_count": None,
  "metadata": {},
  "outputs": [],
  "source": code_src
}

nb['cells'].append(md_cell)
nb['cells'].append(code_cell)

with open(p,'w',encoding='utf-8') as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)
print('Appended 5.2 cells to', p)
