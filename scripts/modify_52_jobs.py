import json
p = r'hangzhou-land.ipynb'
with open(p,'r',encoding='utf-8') as f:
    nb = json.load(f)

code_src = '''# ——— 5.2 与百度人口点统计进行对比 ———
# 说明：此单元依赖已经加载的 xzyd、zone、building。
# 百度“常住人口”点：D:/2Gis/Arcgis Packages/OD数据库/od.gdb / 图层：百度常住人口数量202411 / 人口字段：人数
# 百度“就业人口”点：D:/2Gis/Arcgis Packages/OD数据库/od.gdb / 图层：百度就业人口数量202411 / 值字段：人数

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

land_type_col = pick_first_existing(land_type_candidates, xzyd) or '用地类别f'
dkid_col      = pick_first_existing(dkid_candidates, xzyd) or 'dkID'
zone_name_col = pick_first_existing(zone_name_candidates, zone)

# 1) 读取百度“常住人口/就业人口”点
bd_gdb = 'D:/2Gis/Arcgis Packages/OD数据库/od.gdb'
lyr_pop = '百度常住人口数量202411'
lyr_job = '百度就业人口数量202411'

try:
    bd_points_pop = gpd.read_file(bd_gdb, layer=lyr_pop)
    print(f"Loaded POP points: {lyr_pop}")
except Exception as e:
    raise RuntimeError(f'读取常住人口点失败: {e}')

try:
    bd_points_jobs = gpd.read_file(bd_gdb, layer=lyr_job)
    print(f"Loaded JOB points: {lyr_job}")
except Exception as e:
    raise RuntimeError(f'读取就业人口点失败: {e}')

# 统一坐标系
for _df_name in ['bd_points_pop','bd_points_jobs','zone','building']:
    _df = locals()[_df_name]
    if _df.crs != xzyd.crs:
        locals()[_df_name] = _df.to_crs(xzyd.crs)

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

# 通用匹配函数：将点匹配到有效地块，补 building/nearest，赋 district，并返回指定值列

def match_points_to_land(points_gdf: gpd.GeoDataFrame, value_field: str, out_col: str) -> gpd.GeoDataFrame:
    pts = points_gdf.copy()
    # 点落地到地块（within）
    j = gpd.sjoin(
        pts, xzyd_valid[[dkid_col, land_type_col, 'geometry']],
        how='left', predicate='within', lsuffix='pt', rsuffix='dk'
    )
    j = j.rename(columns={dkid_col: 'dkID_matched', land_type_col: 'ydf_matched'})
    j['match_level'] = np.where(j['dkID_matched'].notna(), 'xzyd', 'unmatched')

    # building 标记
    unmatched_mask = j['match_level'].eq('unmatched')
    if unmatched_mask.any():
        building_small = building[['geometry']].copy()
        j_bld = gpd.sjoin(
            j.loc[unmatched_mask, ['geometry']].set_geometry('geometry'),
            building_small, how='left', predicate='within'
        )
        has_building = j_bld.index.unique()
        j.loc[has_building, 'match_level'] = 'building'

    # 最近地块补缺
    still_unmatched = j['match_level'].eq('unmatched')
    if still_unmatched.any():
        near = gpd.sjoin_nearest(
            j.loc[still_unmatched, ['geometry']].set_geometry('geometry'),
            xzyd_valid[[dkid_col, land_type_col, 'geometry']],
            how='left', distance_col='nearest_dist'
        )
        near = near.rename(columns={dkid_col: 'dkID_matched', land_type_col: 'ydf_matched'})
        j.loc[still_unmatched, 'dkID_matched'] = near['dkID_matched'].values
        j.loc[still_unmatched, 'ydf_matched'] = near['ydf_matched'].values
        j.loc[still_unmatched, 'nearest_dist'] = near['nearest_dist'].values
        j.loc[still_unmatched, 'match_level'] = 'nearest'

    need_near_for_building = j['match_level'].eq('building') & j['dkID_matched'].isna()
    if need_near_for_building.any():
        near_b = gpd.sjoin_nearest(
            j.loc[need_near_for_building, ['geometry']].set_geometry('geometry'),
            xzyd_valid[[dkid_col, land_type_col, 'geometry']],
            how='left', distance_col='nearest_dist'
        )
        near_b = near_b.rename(columns={dkid_col: 'dkID_matched', land_type_col: 'ydf_matched'})
        j.loc[need_near_for_building, 'dkID_matched'] = near_b['dkID_matched'].values
        j.loc[need_near_for_building, 'ydf_matched'] = near_b['ydf_matched'].values
        j.loc[need_near_for_building, 'nearest_dist'] = near_b['nearest_dist'].values

    # 赋区县
    if zone_name_col:
        jz = gpd.sjoin(
            j[['geometry']].set_geometry('geometry'),
            zone[[zone_name_col, 'geometry']],
            how='left', predicate='within'
        )
        j['district'] = jz[zone_name_col].values
    else:
        j['district'] = None

    # 值列
    j[out_col] = pd.to_numeric(pts[value_field].reindex(j.index), errors='coerce').fillna(0).values
    return j

# 分别匹配人口与岗位
pop_join  = match_points_to_land(bd_points_pop,  '人数', 'pop')
jobs_join = match_points_to_land(bd_points_jobs, '人数', 'jobs')

print('常住人口匹配统计:')
print(pop_join['match_level'].value_counts(dropna=False))
print('就业人口匹配统计:')
print(jobs_join['match_level'].value_counts(dropna=False))

# 汇总：区 × 用地类别
pop_agg = (
    pop_join.dropna(subset=['ydf_matched'])
            .groupby(['district','ydf_matched'], dropna=False)['pop']
            .sum().reset_index()
)
jobs_agg = (
    jobs_join.dropna(subset=['ydf_matched'])
             .groupby(['district','ydf_matched'], dropna=False)['jobs']
             .sum().reset_index()
)

agg_df = (
    pop_agg.merge(jobs_agg, how='outer', on=['district','ydf_matched'])
           .fillna({'pop':0,'jobs':0})
           .rename(columns={'ydf_matched':'用地类别f'})
)

print('分组汇总（按区 x 用地类别f）：')
try:
    display(agg_df.head(10))
except Exception:
    print(agg_df.head(10))

# 可选：导出结果点
# pop_join.to_file(bd_gdb, layer='baidu_pop_matched_202411', driver='OpenFileGDB')
# jobs_join.to_file(bd_gdb, layer='baidu_jobs_matched_202411', driver='OpenFileGDB')
'''.splitlines(True)

# Replace the last 5.2 code cell by searching for its header line
for c in nb['cells'][::-1]:
    if c.get('cell_type') == 'code' and c.get('source') and isinstance(c['source'], list):
        first_line = c['source'][0] if c['source'] else ''
        if isinstance(first_line, str) and '5.2 与百度人口点统计进行对比' in first_line:
            c['source'] = code_src
            break

with open(p,'w',encoding='utf-8') as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)
print('Updated 5.2 code cell (added jobs layer support) in', p)
