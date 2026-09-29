---
name: worldos-presentation-boundary
description: Architectural rules and standards for the WORLDOS frontend (React, TypeScript, state management) and strict presentation boundary enforcement for CesiumJS/Resium 3D visualization.
---

# WORLDOS Presentation Boundary & Frontend Architecture

The frontend is a visualization and user-interaction client for the WORLDOS intelligence platform. It renders projections of the underlying world model but does not compute or dictate world truth.

---

## 1. The Presentation Boundary Invariant

### CesiumJS is a Visualization Canvas, Not an Intelligence Core
- **Never compute spatial topology in the browser**: The browser must not attempt to calculate whether a coordinate lies within a country polygon using client-side JavaScript. PostGIS and the backend spatial engine perform all spatial calculations and provide pre-computed results.
- **Never store authoritative state in Cesium entities**: Cesium `EntityCollection` and `Viewer` instances are ephemeral rendering caches. The canonical state lives in the React state store (or backend API).
- **Graceful Degradation**: The application must remain usable even if 3D WebGL / Cesium fails to initialize (e.g. headless environments, low-power mobile devices, fallback 2D table/card views).

---

## 2. Frontend Technology Stack & Structure

- **Framework**: React 18+ with TypeScript (Strict mode enabled).
- **Build Tool**: Vite (fast HMR, optimized production chunks).
- **Directory Layout**:
  ```
  frontend/src/
  ├── components/          # Reusable presentation components
  │   ├── globe/           # Cesium / Resium 3D world view wrapper
  │   ├── timeline/        # Temporal scrub bar & historical playback
  │   ├── inspector/       # Entity detail card with evidence & provenance
  │   └── common/          # Buttons, modals, data tables
  ├── hooks/               # Custom React hooks (useEntity, useIngestion)
  ├── services/            # Strongly-typed API client contracts
  ├── store/               # State management (Zustand or Context)
  ├── types/               # TypeScript interfaces mirroring backend contracts
  └── App.tsx
  ```

---

## 3. Evidence & Provenance Presentation

Whenever displaying an entity attribute, metric, or event in the UI:
1. Always display the **Epistemic Tier Badge**:
   - `OBSERVED`: Green / Verified
   - `DERIVED`: Blue / Calculated
   - `INFERRED`: Amber / Heuristic
   - `PREDICTED`: Purple / Forecast
   - `SIMULATED`: Gray / Synthetic
2. Provide a clickable **Evidence Drawer**:
   - Show `source_name`, `observed_at`, `fetched_at`, and `confidence` percentage.
   - Show the SHA-256 payload hash and raw JSON record preview.
   - Users must be able to audit the source of every claim directly in the UI.

---

## 4. Cesium Performance & Memory Management

- **Primitive API vs Entity API**: For rendering large collections (>5,000 entities, e.g. global earthquake clusters or flight tracks), use Cesium `PointPrimitiveCollection` or `BillboardCollection` instead of heavy `Entity` objects to prevent garbage collection pauses.
- **Resource Destruction**: When unmounting globe components, explicitly call `viewer.destroy()` and clean up WebGL contexts to prevent memory leaks in single-page navigation.
- **Request Render Mode**: Set `requestRenderMode: true` and `maximumRenderTimeChange: Infinity` so Cesium only re-renders the canvas when camera or entity state changes, reducing GPU utilization by up to 90%.

---

## 5. Anti-Patterns to Avoid

- **Anti-Pattern 1: Globe-First Dependency**: Rendering a blank screen or throwing uncaught errors if WebGL is unavailable.
- **Anti-Pattern 2: Client-Side Entity Merging**: Deduplicating or merging entities inside React components using fuzzy name matches.
- **Anti-Pattern 3: Inverting Coordinate Conventions**: Passing `[lat, lon]` to Cesium's `Cartesian3.fromDegrees(longitude, latitude)` which expects `[lon, lat]`.
