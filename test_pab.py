import os
import sys
# Ensure the current directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sri_autonomous_healer import proactive_optimize

file_to_test = os.path.join(os.path.dirname(__file__), "core", "resume_parser.py")

print(f"Starting Proactive Autonomous Benchmarking on {file_to_test}...\n")
proactive_optimize(file_to_test)
print("\nDone.")
