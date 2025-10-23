import json
p = r'hangzhou-land.ipynb'
with open(p,'r',encoding='utf-8') as f:
    nb = json.load(f)

# Build the new 5.2 code cell content
code_src = '''# ——— 5.2 与百度人口点统计进行对比 ———
# 说明：此单元依赖已经加载的 xzyd、zone、building。
# 百度人口点来源：D:/2Gis/Arcgis Packages/OD数据库/od.gdb 图层：百度常住人口数量202411；人口字段：人数

import numpy as np
import pandas as pd
import geopandas as gpd


def pick_first_existing(col_candidates, df):
    for c in col_candidates:
        if c in df.columns:
            return c
    return None

# 0) 标准化关键列名
land_type_candidates = ['用地类别f', 'land_type2', 'land_type1', 'LANDUSAGE']
dkid_candidates      = ['dkID', 'xzdkID', 'xzdkid', 'DKID', 'dk_id', 'ID']
zone_name_candidates = ['xzq', 'belong_xzq', '区', '行政区', 'XZQ', 'xzqJD', 'xzqjd']
pop_candidates       = ['人数', '人口', '人口数', 'pop', 'population', 'pop_count']
jobs_candidates      = ['岗位', '岗位数', 'jobs', 'job', 'job_count']

land_type_col = pick_first_existing(land_type_candidates, xzyd) or '用地类别f'
dkid_col      = pick_first_existing(dkid_candidates, xzyd) or 'dkID'
zone_name_col = pick_first_existing(zone_name_candidates, zone)

# 1) 读取/准备 百度人口点（按用户指定）
bd_points_gdb   = 'D:/2Gis/Arcgis Packages/OD数据库/od.gdb'
bd_points_layer = '百度常住人口数量202411'
try:
    bd_points = gpd.read_file(bd_points_gdb, layer=bd_points_layer)
    print(f"Loaded Baidu points: {bd_points_layer} from {bd_points_gdb}")
except Exception as e:
    print('按用户指定的百度点加载失败，将尝试通用候选。错误：', e)
    bd_points = None
    bd_points_layers = ['百度常住人口点','百度人口点','baidu_rk_point','baidu_points','rk_points','人口点']
    for lyr in bd_points_layers:
        try:
            bd_points = gpd.read_file(bd_points_gdb, layer=lyr)
            print(f"Loaded Baidu points layer: {lyr}")
            break
        except Exception:
            continue
    if bd_points is None:
        raise RuntimeError('未找到百度人口点图层，请检查路径与图层名。')

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

# 8) 人口/岗位字段
pop_col  = '人数' if '人数' in bd_points.columns else pick_first_existing(pop_candidates, bd_points)
jobs_col = pick_first_existing(jobs_candidates, bd_points)

join1['pop']  = bd_points[pop_col].values if pop_col else 1
join1['jobs'] = bd_points[jobs_col].values if jobs_col else 0

for c in ['pop','jobs']:
    join1[c] = pd.to_numeric(join1[c], errors='coerce').fillna(0)

# 9) (e) 分组汇总：区 x 用地类别f
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
# join1.to_file(bd_points_gdb, layer='baidu_points_matched', driver='OpenFileGDB')
'''.splitlines(True)

# Find the existing 5.2 code cell and replace its source
for c in nb['cells'][::-1]:
    if c.get('cell_type') == 'code' and c.get('source') and isinstance(c['source'], list):
        first_line = c['source'][0] if c['source'] else ''
        if isinstance(first_line, str) and '5.2 与百度人口点统计进行对比' in first_line:
            c['source'] = code_src
            break

with open(p,'w',encoding='utf-8') as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)
print('Updated 5.2 code cell in', p)
