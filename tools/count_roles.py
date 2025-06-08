import os
import json
from collections import Counter

RESULTS_DIR = os.path.abspath("results")
role_counter = Counter()

def count_roles():
    for calendar_dir in os.listdir(RESULTS_DIR):
        dir_path = os.path.join(RESULTS_DIR, calendar_dir)
        traj_path = os.path.join(dir_path, "trajectory.json")
        if os.path.isdir(dir_path) and os.path.exists(traj_path):
            try:
                with open(traj_path, "r", encoding="utf-8") as f:
                    traj = json.load(f)
                for step in traj.values():
                    try:
                        role = (
                            step["action"]["action_output"]["action"]["node_properties"].get("role")
                        )
                        if role is not None:
                            role_counter[role] += 1
                    except Exception:
                        continue
            except Exception as e:
                print(f"Error reading {traj_path}: {e}")

    print("Role counts across all trajectories:")
    for role, count in role_counter.most_common():
        print(f"{role!r}: {count}")

if __name__ == "__main__":
    count_roles() 