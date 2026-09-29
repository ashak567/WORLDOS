# WORLDOS Antigravity IDE Extension Manifest

This manifest documents the IDE extensions evaluated, installed, and configured in the Antigravity IDE environment for WORLDOS.

---

## 1. Extension Catalog & Status

| Extension Name | Publisher | Version | Marketplace Source | Purpose | WORLDOS Subsystem | Tier | Existing Equivalent | Security / Permissions |
|---|---|---|---|---|---|---|---|---|
| `ms-python.python` | Microsoft | 2026.4.0 | VS Code / Antigravity Marketplace | Core Python language support, environment resolution, and syntax highlighting. | Backend (`backend/`) | **Required** | Native Antigravity language client | Official Microsoft extension; runs in standard sandbox. |
| `ms-python.debugpy` | Microsoft | 2026.6.0 | VS Code / Antigravity Marketplace | Interactive debugging for Python processes and FastAPI endpoints. | Backend (`backend/`) | **Required** | CLI pdb | Official Microsoft debugger; local execution only. |
| `ms-python.vscode-python-envs` | Microsoft | 1.20.1 | VS Code / Antigravity Marketplace | Discovery and switching between virtual environments (`.venv`, Conda). | Backend (`backend/`) | Recommended | Manual terminal activation | Official Microsoft extension; reads local filesystem envs. |
| `charliermarsh.ruff` | Astral / Charlie Marsh | 2026.84.0 | VS Code / Antigravity Marketplace | Ultra-fast Python linting and formatting; enforces import sorting and PEP standards. | Backend (`backend/`) | **Required** | Black / Flake8 / Isort | Official Astral extension; executed locally; zero telemetry/cloud dependency. |
| `ckolkman.vscode-postgres` | Chris Kolkman | 1.4.3 | VS Code / Antigravity Marketplace | PostgreSQL and PostGIS connection management, SQL execution, and table schema inspection. | Database Layer (`db/`) | Recommended | `psql` CLI | Connects exclusively to local or configured database credentials (port 5432). |
| `ms-azuretools.vscode-docker` | Microsoft | 2.0.0 | VS Code / Antigravity Marketplace | Container management, Dockerfile syntax, and compose stack inspection (`worldos-postgres`, `worldos-api`). | Infrastructure / Containers | **Required** | `docker` CLI | Official Microsoft extension; communicates via local Docker socket. |
| `ms-azuretools.vscode-containers` | Microsoft | 2.4.5 | VS Code / Antigravity Marketplace | Development inside containers and devcontainer orchestration. | Infrastructure / Containers | Recommended | Manual container exec | Official Microsoft extension. |
| `redhat.vscode-yaml` | Red Hat | 1.24.0 | VS Code / Antigravity Marketplace | YAML language support, JSON Schema validation for Docker Compose and CI workflows. | Configuration (`compose.yaml`) | **Required** | Basic text editor | Official Red Hat extension; standard language server protocol. |
| `tamasfe.even-better-toml` | Tamas Feher | 0.21.2 | VS Code / Antigravity Marketplace | TOML syntax, formatting, and validation for `pyproject.toml`. | Configuration (`pyproject.toml`) | Recommended | Generic syntax highlighting | Highly rated open-source extension; local LSP only. |
| `dbaeumer.vscode-eslint` | Microsoft / Dirk Baeumer | 3.0.34 | VS Code / Antigravity Marketplace | Real-time ESLint error and warning reporting for TypeScript and React. | Frontend (`frontend/`) | Recommended | CLI `npm run lint` | Official ESLint extension; runs project-local npm packages. |
| `esbenp.prettier-vscode` | Prettier | 12.4.0 | VS Code / Antigravity Marketplace | Code formatter for JavaScript, TypeScript, CSS, HTML, and JSON. | Frontend (`frontend/`) | Recommended | Manual format script | Official Prettier team extension; local AST formatting only. |

---

## 2. Extensions Evaluated and Rejected

| Candidate Extension | Proposed Area | Reason for Rejection |
|---|---|---|
| `randomfrac.geojson-preview` / `henoc.geojson-preview` | Geospatial | **Rejected**: Unmaintained, not present in verified marketplace, security risk from unverified webview rendering. GeoJSON is validated deterministically in backend engines and rendered via the React/Cesium frontend. |
| `Cesium Snippets` / Unofficial Cesium Packs | 3D World / Presentation | **Rejected**: Unofficial third-party snippet packs last updated >5 years ago. Outdated API calls that encourage anti-patterns (treating Cesium as a data store). Cesium in WORLDOS is strictly a presentation layer. |
| Random "AI Assistant" / Autocomplete Extensions | AI Tools | **Rejected**: Antigravity already provides native, high-context AI agent orchestration. Third-party AI extensions introduce duplicate latency, ungrounded code suggestions, and telemetry leakage. |
| `ms-python.black-formatter` / `ms-python.flake8` | Python Tooling | **Rejected**: Redundant. `charliermarsh.ruff` completely supersedes Black, Flake8, and Isort at 10-100x the speed without toolchain collisions. |
| Database Admin Webviews (Unverified) | Database | **Rejected**: Heavyweight electron webviews with broad file/network access. `ckolkman.vscode-postgres` and standard Docker CLI provide clean, native inspection. |

---

## 3. Tooling Boundaries

```
┌────────────────────────────────────────────────────────┐
│                   Antigravity IDE                       │
│  [Developer Tooling]                                   │
│  • Ruff (Python linting/formatting)                    │
│  • VSCode Postgres (SQL/schema inspection)             │
│  • VSCode Docker (container orchestration)             │
│  • ESLint + Prettier (frontend code quality)           │
│  • YAML & TOML (manifest schema validation)            │
└───────────────────────────┬────────────────────────────┘
                            │ Guides developer interactions
                            ▼
┌────────────────────────────────────────────────────────┐
│             Project-Local Agent Skills                  │
│  [.agents/skills/]                                     │
│  • worldos-engineering (20 architectural rules)        │
│  • worldos-provenance-fusion (evidence & identity)     │
│  • worldos-spatial-engineering (PostGIS & topology)    │
│  • worldos-database-architecture (Postgres vs DuckDB)  │
│  • worldos-source-adapters (ingestion contracts)       │
│  • modern-python-fastapi (contracts & routing)         │
│  • worldos-testing (deterministic pytest & hypothesis) │
│  • worldos-security-threat-model (SSRF & defaults)     │
│  • worldos-presentation-boundary (Cesium presentation) │
│  • worldos-observability-metrics (structured telemetry)│
│  • worldos-git-adr-discipline (conventional commits)   │
└────────────────────────────────────────────────────────┘
```
