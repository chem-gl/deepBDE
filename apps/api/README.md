# DeepBDE API

API for Bond Dissociation Energy (BDE) prediction using the DeepBDE machine learning model.
Based on research from [DeepBDE](https://github.com/MSRG/DeepBDE/).

## Disk Cache System

DeepBDE API uses a disk-based cache system to speed up repeated queries for molecules, BDE predictions, and fragmentations.

- **Location:** Cache files are stored in `api/controllers/_cache/v4/`.
- **Clear cache:** Delete the `_cache` folder or change the cache version in the code (`CACHE_VERSION` in `cache_controller.py`).
- **Auto-regeneration:** The cache rebuilds as new queries are made.
- **Purpose:** This system improves performance for repeated or similar requests and is safe to delete at any time.

## Main Features

- BDE prediction for single or multiple bonds in molecules from SMILES.
- 2D molecule image generation and bond visualization.
- Molecular fragmentation in SMILES and XYZ formats, with BDE values for each fragment.
- Validation of cleavage products and BDE calculation for proposed products.
- Downloadable TXT reports with prediction and fragmentation results.
- System health check and status endpoints.
- Interactive documentation with examples for simple and complex molecules (ethanol, benzene, caffeine, taxol, cholesterol, morphine, etc.).
- Always up-to-date OpenAPI YAML schema available at `/api/schema/`.

## API Endpoints

- `POST /api/v1/predict/info/` — Get enriched molecule information: canonical SMILES, SVG image, atom and bond positions, and unique ID.
- `POST /api/v1/predict/info-smile-canonical/` — Get canonical SMILES and unique ID for a molecule.
- `POST /api/v1/predict/single/` — Predict BDE for a specific bond in a molecule.
- `POST /api/v1/predict/multiple/` — Predict BDEs for multiple bonds in a molecule.
- `POST /api/v1/infer/all/` — Predict BDEs for all single bonds in a molecule.
- `POST /api/v1/BDEEvaluate/` — Generate molecular fragments in SMILES and/or XYZ format with BDE values for each fragment.
- `POST /api/v1/ObtainBDEFragments/` — Find the bond that generates specific fragments and calculate its BDE.
- `POST /api/v1/predict/check/` — Validate cleavage products and compare with predicted fragments, including BDE calculation.
- `POST /api/v1/download_report/` — Download a TXT report with prediction and fragmentation results.
- `GET /api/v1/health/` — System health check.

## Usage Workflow

1. Send a SMILES to `/api/v1/predict/info/` to get the 2D image and bond indices.
2. Use `/api/v1/predict/info-smile-canonical/` to get canonical SMILES and molecule ID.
3. Use `/api/v1/predict/single/` to predict BDE for a specific bond.
4. Use `/api/v1/predict/multiple/` to predict BDEs for multiple bonds.
5. Predict all single bond BDEs with `/api/v1/infer/all/`.
6. Generate molecular fragments (SMILES and/or XYZ) with `/api/v1/BDEEvaluate/` (set `export_smiles` and/or `export_xyz`).
7. Find the bond that generates specific fragments with `/api/v1/ObtainBDEFragments/`.
8. Validate cleavage products and compare with predicted fragments using `/api/v1/predict/check/`.
9. Download a complete TXT report with `/api/v1/download_report/` (set `format` to `txt`).

## Installation & Deployment

1. Clone the repository:

   ```bash
   git clone https://github.com/chem-gl/DeepBDE-Api.git
   cd DeepBDE-Api
   ```

2. Build the Docker image:

   ```bash
   docker build -t deepbde-api .
   ```

3. Start the container:

   ```bash
   docker run -p 8000:8000 deepbde-api
   ```

4. The API will be available at `http://localhost:8000/`.

## Interactive Documentation

- Swagger UI: `/api/docs/`
- ReDoc: `/api/redoc/`
- OpenAPI YAML Schema: `/api/schema/`

## Project Structure

- `api/` — Business logic, views, serializers, DTOs, and controllers.
- `api/model/dto.py` — Data class definitions for requests and responses.
- `api/controllers/` — Controllers for each endpoint group.
- `api/controllers/_cache/` — Disk cache for molecule queries and predictions.
- `api/public/openapi.yaml` — Auto-generated OpenAPI schema.
- `predictor/` — Main Django configuration and routes.
- `deepbde/` — DeepBDE model code and utilities.

## Usage Examples

The Swagger documentation includes examples for simple and complex molecules (ethanol, benzene, caffeine, taxol, cholesterol, morphine, etc.) in all endpoints.

## Technical Notes

- Only single, non-cyclic bonds can be predicted.
- BDE values are returned in kcal/mol.
- Molecule IDs are SHA256 hashes (16 characters).
- Supports SMILES input with automatic canonicalization.
- Caching system for improved performance.
- Bilingual API documentation (English and Spanish).

## License

This project is for academic and research use. See the LICENSE file for more details.

---

Developed by the DeepBDE team. For questions or support, contact the repository authors.
