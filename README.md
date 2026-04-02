# OnyxCAD - Technical Documentation & Codebase Overview

> **Context for LLMs**: This repository is a lightweight, browser-based STEP file viewer and annotation tool ("PDF for CAD"). It uses a Python Flask backend with CadQuery/OCP for geometry processing and a Three.js frontend for rendering.
> 
> **Core Philosophy**: Treat STEP files as authoritative documents. Metadata (tolerances, threads, colors) is injected directly into the STEP file structures or persisted via sidecar SQLite DB, keyed by geometry hashes.

---

## 📂 File Structure & Logic Map

```text
/
├── app.py                  # Flask routes (entry point)
├── core/                   # Core application logic (modular)
│   ├── state.py            # ModelState singleton & global state
│   ├── loader.py           # STEP loading, tessellation, metadata recovery
│   ├── exporter.py         # STEP export with metadata injection
│   ├── metadata.py         # 3-strategy metadata embed/extract
│   └── utils.py            # Color conversion & utilities
├── face_db.py              # SQLite face fingerprinting & metadata
├── requirements.txt        # Python dependencies (cadquery-ocp, flask, gunicorn)
├── Dockerfile              # GCP deployment container (python:3.11-slim)
├── .dockerignore            # Exclude venv, dev files
├── static/
│   ├── js/
│   │   └── viewer.js       # Three.js viewer + all UI logic
│   └── css/
│       ├── style.css        # Core light theme & layout
│       └── style_expansion.css  # Panel expansion styles
├── templates/
│   └── index.html          # Single-page application
├── tests/
│   ├── run_tests.py        # Main test runner script
│   ├── sample.step         # Default loaded model
│   └── test_*.py           # Unit & integration tests
├── uploads/                # User-uploaded files (persistent)
└── stepviewer.db           # SQLite DB (generated at runtime)
```

---

## 🧠 Core Logic & Systems

### 1. Backend (Modular Architecture)

**Framework**: Flask + Gunicorn  
**Geometry Kernel**: Open Cascade (OCCT) via `cadquery` & `OCP`

| Module | Purpose |
|--------|---------|
| `app.py` | Flask routes, API endpoints |
| `core/loader.py` | `load_step_xcaf()` — STEP reading, face tessellation, metadata recovery |
| `core/exporter.py` | `export_step_xcaf()` — STEP writing with metadata injection |
| `core/metadata.py` | 3-strategy metadata embed/extract (entity, description, comment) |
| `core/state.py` | `ModelState` singleton holding the XDE document and face data |
| `core/utils.py` | Color conversion helpers |
| `face_db.py` | SQLite face fingerprinting, exact + fuzzy matching |

#### Key Functions
*   **`load_step_xcaf(path)`** (`core/loader.py`): 
    *   Reads STEP using `STEPCAFControl_Reader` with XDE document.
    *   Extracts embedded metadata via `extract_meta_from_step()` **before** OCC reads the file.
    *   Iterates topological faces (`TopExp_Explorer`).
    *   **Hashing**: Generates a stable geometry hash for each face.
    *   **Metadata Recovery Priority**: Embedded STEP (hash-based) > Embedded STEP (index-based) > SQLite DB (exact+fuzzy).
    *   **Tessellation**: Converts BRep to Mesh for Three.js.
*   **`export_step_xcaf()`** (`core/exporter.py`):
    *   Writes XDE document with colors via `STEPCAFControl_Writer`.
    *   Injects metadata via 3 strategies (see Metadata System below).
*   **`inject_meta_into_step()` / `extract_meta_from_step()`** (`core/metadata.py`):
    *   **Strategy 1**: `PROPERTY_DEFINITION` → `DESCRIPTIVE_REPRESENTATION_ITEM` (SolidWorks-compatible)
    *   **Strategy 2**: `[SVFM:<base64>]` in PRODUCT description field (universally preserved)
    *   **Strategy 3**: `/* __STEPVIEWER_META_START__ ... */` comment block (fast OnyxCAD-to-OnyxCAD)

### 2. Frontend (`viewer.js` + `index.html`)
**Framework**: Vanilla JS + Three.js (WebGL)

#### Rendering Pipeline
1.  **`loadModel()`**: Fetches JSON from `/upload` (Vertices, Normals, Indices, Metadata).
2.  **`buildScene()`**: Creates `THREE.BufferGeometry` per face with `userData`.
3.  **`fitCameraToGroup()`**: Positions camera at **Isometric (-1, -1, 1)** default.

#### Interaction
*   **Arcball Controls**: `ArcballControls.js` for tumbling rotation.
*   **Raycasting**: Click → highlight face (pink glow), populate right panel.
*   **View Buttons**: Floating bar (F/B/L/R/T/Bo/Iso) for quick camera presets.

### 3. Feature: Tolerance Heat Map
*   **Tight** (≤ 0.005"): **Red** (configurable)
*   **Loose** (> 0.005"): **Gray** (configurable)
*   **None**: Ghosted/transparent
*   Filtering by tolerance type via checkboxes.

### 4. Feature: Hole Wizard
*   Groups faces by thread metadata (e.g. "UNC 1/4-20").
*   Color picker per group, visibility toggle, delete action.
*   Counts unthreaded cylindrical faces.

### 5. Admin Cleanup Tools
*   **3-scope metadata cleanup**: DB only, File only, or All (nuke).
*   Strips all 3 metadata strategies from the STEP file.
*   Clears in-memory `model.face_meta` to prevent re-injection on export.
*   Before/after verification via `extract_meta_from_step()`.

---

## 💾 Database Schema (`stepviewer.db`)

**Table**: `face_meta`
| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | INTEGER | Primary Key |
| `face_hash` | TEXT UNIQUE | 16-char hex geometry fingerprint |
| `meta` | TEXT | JSON: `{color, thread, tolerance, ...}` |
| `surf_type` | TEXT | Surface type (Plane, Cylinder, etc.) |
| `cx, cy, cz` | REAL | Centroid coordinates |
| `area` | REAL | Surface area |
| `dx, dy, dz` | REAL | Bounding box dimensions |
| `n_edges` | INTEGER | Edge count |
| `n_verts` | INTEGER | Vertex count |
| `created_at` | TIMESTAMP | Creation timestamp |
| `updated_at` | TIMESTAMP | Last update timestamp |

---

## 🔄 API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Serve main app (auto-loads `tests/sample.step`) |
| `GET` | `/<uuid>` | Load model by UUID |
| `POST` | `/upload` | Upload STEP file, returns face mesh data + UUID |
| `GET` | `/model/<uuid>` | Get face data for a persisted model |
| `POST` | `/set_color` | Set face color(s) |
| `POST` | `/set_thread` | Set threading metadata |
| `POST` | `/set_tolerance` | Set tolerance metadata (batch) |
| `GET` | `/thread_options` | Get thread dropdown options |
| `GET` | `/tolerance_options` | Get tolerance dropdown options |
| `GET` | `/holes` | Get hole analysis data |
| `POST` | `/export` | Export annotated STEP (UUID filename) |
| `POST` | `/test_cube` | Generate test cube (internal) |
| `GET` | `/test_sample` | Load `tests/sample.step` (internal) |
| `POST` | `/api/admin/clear_metadata` | Admin: Wipe DB + strip file + clear memory |
| `GET` | `/db_stats` | Database statistics |

## 🧪 Running Tests

Tests are located in `tests/` and require the Flask server running on port 5555.

```bash
# Start the server
venv\Scripts\python.exe app.py

# Run the full suite (in another terminal)
venv\Scripts\python.exe tests/run_tests.py

# Or use pytest directly
venv\Scripts\python.exe -m pytest tests/ -v
```
