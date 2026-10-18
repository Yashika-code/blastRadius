"""
Stand-alone seeding script for FalkorDB topology graph.
Usage:
    python scripts/seed_graph.py [--reset]
"""
import argparse
import sys
import os

# Add root directory to python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.graph.seed import seed_database
from app.graph.schema import apply_schema
from app.graph.client import falkor_client

def main():
    parser = argparse.ArgumentParser(description="Seed BlastRadius topology into FalkorDB")
    parser.add_argument("--reset", action="store_true", default=True, help="Reset existing graph before seeding")
    args = parser.parse_args()

    print(f"Connecting to FalkorDB on {falkor_client.client}...")
    schema_res = apply_schema()
    print(f"Schema application: {schema_res.get('status')}")

    res = seed_database(reset=args.reset)
    print(f"Seeding completed: {res}")

if __name__ == "__main__":
    main()
