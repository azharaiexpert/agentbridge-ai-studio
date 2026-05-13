import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import Database
from app.seed import seed_workspace_data


if __name__ == "__main__":
    db = Database()
    seed_workspace_data(db)
    print(f"Seeded {len(db.list_agents())} agents and {len(db.list_workflows())} workflows")
