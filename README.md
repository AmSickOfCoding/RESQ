# RESQ - Emergency Response Digital Twin Platform

## Project Overview
RESQ is a Digital Twin simulation and decision-support engine designed to optimize real-time emergency response dispatch, unit pathfinding, and hospital capacity allocation during critical municipal events.

## Architecture
The platform follows a modular architecture separating core spatial topology models, decision/routing algorithms, data persistence, and API controllers:
- `src/core/`: World graph, incident lifecycle, and unit domain entities.
- `src/engine/`: Routing algorithms, dispatch scoring functions, and explainable audit trails.
- `src/data/`: Data loading, persistence adapters, and scenario parsers.
- `src/api/`: Facade controller exposing simulation execution and failure injection hooks.
- `src/ui/`: Presentation and visualization interface logic.

## Setup Instructions
1. Clone the repository and navigate into the root directory.
2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy default environment settings:
   ```bash
   cp .env.example .env
   ```

## Team Roles
- **Core Simulation & Graph Engineering**: `src/core/`
- **Routing & Dispatch Algorithms**: `src/engine/`
- **Data & Scenario Pipeline**: `src/data/`, `scenarios/`
- **API Facade & Control Hooks**: `src/api/`
- **UI & Visualization**: `src/ui/`

## Running Scenarios
To run pre-configured simulation scenarios:
```bash
make run
```
Or execute scenario scripts directly via Python.
