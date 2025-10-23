import json
from pathlib import Path

NB_PATH = Path('hangzhou-land.ipynb')

def main():
    nb = json.loads(NB_PATH.read_text(encoding='utf-8'))
    cells = nb.get('cells', [])

    new_src = [
        "# Export full xzyd and building to Esri FileGDB\n",
        "import os\n",
        "from shapely import wkb\n",
        "\n",
        "def _drop_z(geom):\n",
        "    if geom is None:\n",
        "        return None\n",
        "    try:\n",
        "        return wkb.loads(wkb.dumps(geom, output_dimension=2))\n",
        "    except Exception:\n",
        "        return geom\n",
        "\n",
        "# Make safe copies and fix geometry\n",
        "xzyd_export = xzyd.copy()\n",
        "xzyd_export['geometry'] = xzyd_export['geometry'].apply(_drop_z).buffer(0)\n",
        "building_export = building.copy()\n",
        "building_export['geometry'] = building_export['geometry'].apply(_drop_z).buffer(0)\n",
        "\n",
        "# Align CRS\n",
        "if xzyd_export.crs != building_export.crs:\n",
        "    building_export = building_export.to_crs(xzyd_export.crs)\n",
        "\n",
        "# Use writable FileGDB driver, not OpenFileGDB\n",
        "xzyd_export.to_file(gis_file, layer='xzyd_all', driver='FileGDB')\n",
        "building_export.to_file(gis_file, layer='building_all', driver='FileGDB')\n",
        "print('Written layers to FileGDB:', gis_file)\n",
    ]

    new_cell = {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": new_src,
    }

    # Find cells that write using OpenFileGDB
    idxs = []
    for i, c in enumerate(cells):
        if c.get('cell_type') == 'code':
            src = ''.join(c.get('source', []))
            if 'OpenFileGDB' in src and 'to_file' in src:
                idxs.append(i)

    if not idxs:
        print('No OpenFileGDB write cells found; nothing changed.')
        return

    idxs = sorted(set(idxs))
    first = idxs[0]
    cells[first] = new_cell
    for j in reversed(idxs[1:]):
        del cells[j]
    nb['cells'] = cells
    NB_PATH.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding='utf-8')
    print('Replaced cells at indices:', idxs)

if __name__ == '__main__':
    main()

