import os
import subprocess
from github import Github

def autonomous_heal_and_deploy(error_traceback, fixed_code, file_path):
    """
    Sre AI calls this to apply the fix and push directly to production.
    """
    try:
        # Step 1: Save current stable state (Commit Hash)
        old_hash = subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip()
        
        # Step 2: Apply the fix
        with open(file_path, 'w') as f:
            f.write(fixed_code)
        
        # Step 3: Direct Push to Main
        subprocess.run(['git', 'add', file_path])
        subprocess.run(['git', 'commit', '-m', f"Sre AI Autonomous Fix: Resolved {error_traceback[:50]}"])
        subprocess.run(['git', 'push', 'origin', 'main'])
        
        print(f"✅ Phoenix Protocol: Fix deployed. Previous stable: {old_hash}")
        return old_hash
    except Exception as e:
        print(f"❌ Autopatcher Failed: {e}")
