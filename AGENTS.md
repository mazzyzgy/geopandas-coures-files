# Repository Guidelines

## Project Structure & Module Organization
- Notebooks live at the repo root (`geopandas-*.ipynb`, `hangzhou-land2.ipynb`) and document each analysis step; create new explorations under a clear incremental suffix (e.g., `geopandas-7.ipynb`).
- Automation helpers sit in `scripts/`, all standard Python modules; keep reusable logic here rather than inside notebooks.
- Shared spatial assets and exports belong in `data/` (e.g., `data/nyc/`, `es_cn.parquet`) while intermediate visual outputs stay in `OD_Visualization/`.
- Large shapefiles should remain zipped when archived (see `data/Pedestrian Zone Shapefile (Tabular)_20241220.zip`) and unpacked into a sibling folder with the same stem.

## Environment Setup, Build & Run Commands
- Create an isolated environment before working on notebooks:
  ```bash
  python -m venv .venv && source .venv/bin/activate
  pip install geopandas shapely jupyter
  ```
- Launch the workspace with Jupyter Lab for interactive editing:
  ```bash
  jupyter lab
  ```
- Convert notebooks to a static report when sharing results:
  ```bash
  jupyter nbconvert --to html geopandas-4.ipynb
  ```

## Coding Style & Naming Conventions
- Use Python 3 syntax with 4-space indentation and `snake_case` for functions, variables, and script filenames (`modify_52_jobs.py` is the pattern).
- Keep notebook cells narrow in scope; prefer utility functions in `scripts/` and import them via `%run scripts/<module>.py`.
- When handling GeoPandas objects, guard CRS manipulations (`gdf.to_crs(...)`) and geometry operations with descriptive comments explaining the spatial intent.

## Testing & Validation
- There is no automated test suite yet; execute notebooks end-to-end before pushing:
  ```bash
  jupyter nbconvert --execute --inplace geopandas-3.ipynb
  ```
- For script changes, add a minimal `if __name__ == "__main__":` block or temporary assertions to verify geometry transformations, then remove debug code after validation.
- Sanity-check exported datasets by reopening them in a fresh session and confirming CRS alignment and record counts.

## Commit & Pull Request Guidelines
- The repository currently has no commit history; adopt concise, imperative commit messages (`Add zoning buffer script`) and reference the affected datasets when relevant.
- Provide pull requests with: purpose-driven summaries, key data sources touched, screenshots of critical map outputs, and explicit rerun instructions (`jupyter nbconvert --execute ...`).
- Link any external issue tracker IDs and note required follow-up tasks (e.g., regeneration of `.zip` archives) directly in the PR description.
