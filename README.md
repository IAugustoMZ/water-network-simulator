# Water Network Simulator

High-fidelity steady-state hydraulic simulation platform for a realistic small-city water distribution network.

## Features

- **Full hydraulic physics** — Darcy-Weisbach with Colebrook-White friction factor (Halley's method), no approximations
- **Newton-Raphson solver** — sparse analytical Jacobian, Armijo line search, 3-tier recovery heuristics
- **Realistic pump models** — PCHIP manufacturer curves, affinity laws for variable speed, cavitation detection (NPSHa vs NPSHr)
- **ISA valve model** — Cv-based equal-percentage characteristic, supports isolation / PRV / FCV
- **60-node city network** — meshed topology, 40–80 m topography, 3 parallel main pumps + 1 booster, 25 valves
- **6 pre-defined scenarios** — baseline, valve restriction, pump speed reduction, pump failure, demand increase, high-elevation stress
- **Interactive React UI** — D3 network graph, pump/valve sliders, results dashboard with charts

---

## Architecture

```
water-network-simulator/
├── backend/                  # FastAPI + Python simulation engine
│   ├── app/
│   │   ├── graph/            # Network topology (models.py, network.py)
│   │   ├── physics/          # Friction, pump, valve, headloss dispatcher
│   │   ├── solver/           # Newton-Raphson, Jacobian, postprocessor
│   │   ├── network/          # Realistic city network definition
│   │   ├── storage/          # In-memory stores (TTL-based)
│   │   └── api/              # FastAPI routers + Pydantic schemas
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                 # React + TypeScript + Vite
│   ├── src/
│   │   ├── components/       # NetworkGraph, ControlPanel, ResultsDashboard
│   │   ├── store/            # Zustand simulation state
│   │   ├── services/         # Axios API client
│   │   └── types/            # TypeScript interfaces
│   ├── nginx.conf
│   └── Dockerfile
├── docker-compose.yml
└── .env.example
```

---

## Quick Start (Docker — recommended)

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd water-network-simulator

# 2. Copy environment config
cp .env.example .env

# 3. Build and start
docker compose up --build

# 4. Open your browser
open http://localhost:3000
```

The backend API is available at `http://localhost:8000`.
API docs (Swagger UI) at `http://localhost:8000/docs`.

---

## Local Development

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev        # starts Vite dev server at http://localhost:5173
```

> In dev mode, Vite proxies `/api/*` to `http://localhost:8000` — no CORS issues.

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/network/default-id` | ID of the pre-loaded city network |
| `POST` | `/network` | Upload a custom network definition |
| `POST` | `/simulate` | Run steady-state simulation |
| `GET` | `/results/{id}` | Retrieve full simulation results |
| `GET` | `/scenarios` | List available pre-defined scenarios |

Full interactive docs: `http://localhost:8000/docs`

### Simulate a scenario

```bash
curl -X POST http://localhost:8000/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "network_id": "default-city-network",
    "scenario_name": "pump_failure",
    "overrides": {
      "pumps": { "PUMP2": { "speed_ratio": 0.9 } },
      "valves": {},
      "demand_multipliers": {},
      "global_demand_multiplier": 1.0,
      "tank_levels": {}
    }
  }'
```

---

## Physical Models

### Pipes — Darcy-Weisbach

$$h_f = f \cdot \frac{L}{D} \cdot \frac{Q|Q|}{2gA^2} \quad \text{[m]}$$

Friction factor $f$ via **Colebrook-White** (solved with Halley's method, converges in 3–4 iterations):

$$\frac{1}{\sqrt{f}} = -2\log_{10}\!\left(\frac{\varepsilon/D}{3.7} + \frac{2.51}{Re\sqrt{f}}\right)$$

- Regimes: laminar (Re < 2000), transitional (2000–4000), turbulent (Re ≥ 4000)
- Minor losses included: $\sum K \cdot Q|Q| / (2gA^2)$

### Pumps — PCHIP + Affinity Laws
**PCHIP** (Piecewise Cubic Hermite) interpolation for $H(Q)$, $\eta(Q)$, $\text{NPSHr}(Q)$.

**Affinity laws** (variable-speed operation):

$$Q' = Q \cdot \frac{n}{n_0}, \qquad H' = H \cdot \left(\frac{n}{n_0}\right)^2$$

**Cavitation** check — flagged when $\text{NPSHa} < \text{NPSHr}$:

$$\text{NPSHa} = H_{\text{suction}} - H_{\text{vapor}}$$

### Valves — ISA $C_v$ model

$$h = \frac{Q|Q|}{C_{v,\text{eff}}^2 \cdot g}, \qquad C_{v,\text{eff}} = C_{v,\text{max}} \cdot R^{x-1}$$

- $R = 50$ (rangeability), $x$ = opening fraction

### Solver — Newton-Raphson
- **H-equation formulation**: nodal heads as unknowns (n_free × n_free system)
- **Sparse Jacobian**: assembled analytically via chain rule inversion
- **Armijo backtracking line search**: guarantees residual decrease
- **Convergence**: $\|F\|_\infty < 10^{-6}\,\text{m}^3/\text{s}$ (typical: 8–20 iterations)

---

## Network Summary

| Element | Count | Details |
|---------|-------|---------|
| Junction nodes | 60 | Elevation 3–80 m, demand 2–30 L/s |
| Reservoir | 1 | Head = 75 m (source) |
| Elevated tank | 1 | Elevation 68 m, 14 m diameter |
| Pipes | 97 | D = 100–500 mm, various roughness |
| Main pumps | 3 parallel | Shutoff 65 m, BEP Q=45 L/s H=52 m η=82% |
| Booster pump | 1 | Hill zone, shutoff 35 m, BEP Q=15 L/s |
| Isolation valves | 15 | Default fully open |
| PRV | 6 | Zone pressure regulators |
| FCV | 4 | Flow-controlled branches |
| Aged pipe | 1 | ε = 2.0 mm (fouled cement lining) |

---

## Scenarios

| Scenario | Description |
|----------|-------------|
| `baseline` | Normal operation — all pumps ON, all valves fully open |
| `valve_restriction` | Close ISO04, ISO07, ISO12 — test flow redistribution |
| `pump_speed_reduction` | Main pumps at 80% speed (affinity laws applied) |
| `pump_failure` | PUMP1 off — 2-of-3 pump redundancy test |
| `demand_increase` | All demands × 1.2 — peak hour simulation |
| `high_elevation_stress` | Booster off + hill zone demand × 1.5 — pressure deficiency test |

---

## Computed Outputs

| Category | Outputs |
|----------|---------|
| **Nodes** | Pressure (m, kPa), hydraulic head, demand |
| **Pipes** | Flow (L/s), velocity (m/s), head loss (m), Re, friction factor, flow direction |
| **Pumps** | Q, H, η, power (kW), NPSHa, NPSHr, cavitation margin, status |
| **Valves** | Flow, pressure drop, opening (%), status |
| **Tanks** | Water level, head, outflow, residence time |
| **System** | Mass balance error, min/max pressure, low-pressure nodes, flow reversals, bottlenecks, system efficiency |
