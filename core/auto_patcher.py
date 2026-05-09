import os
import time
import logging
from github import Github
from github import Auth

logger = logging.getLogger(__name__)

def propose_self_healing_patch(traceback_str: str, file_path: str = None, error_msg: str = ""):
    """
    Sre AI GitOps Auto-Patcher.
    Takes a traceback, asks Sre AI for a code fix, and creates a GitHub Pull Request.
    """
    token = os.environ.get("GITHUB_TOKEN")
    repo_name = os.environ.get("GITHUB_REPO")  # e.g., 'Varshith540/resumexpert'
    
    if not token or not repo_name:
        logger.warning("[GitOps] GITHUB_TOKEN or GITHUB_REPO not set. Auto-patcher disabled.")
        return

    try:
        from .gemini_service import _get_client, _generate, SreAIRouter
        client = _get_client()
        if not client:
            return

        # 1. Ask Sre AI for the fix
        prompt = f"""You are the Level 5 Autonomous SRE Server Guardian of Anti-Gravity.
The system just encountered a critical crash.
Error: {error_msg}

Traceback:
{traceback_str}

If you know the python file and line number causing this, provide the EXACT full content of the corrected file.
Do NOT use markdown code blocks like ```python, JUST output the raw python code perfectly indented.
If you cannot confidently fix it, output exactly: ABORT_HEAL
"""
        raw_fix, _ = _generate(client, prompt, task_type=SreAIRouter.FORMATTING)
        
        if "ABORT_HEAL" in raw_fix or not raw_fix.strip():
            logger.info("[GitOps] Sre AI decided it could not confidently auto-heal this error.")
            return

        # Clean up any accidental markdown blocks Sre AI might include despite instructions
        raw_fix = raw_fix.replace("```python", "").replace("```", "").strip()

        # 2. Authenticate with GitHub
        auth = Auth.Token(token)
        g = Github(auth=auth)
        repo = g.get_repo(repo_name)

        # 3. Identify the target file
        target_repo_path = None
        if file_path and 'resumexpert' in file_path:
            # Convert absolute server path to relative repo path
            # e.g., c:\resumexpert_complete\resumexpert\core\views.py -> core/views.py
            parts = file_path.replace('\\', '/').split('resumexpert/')
            if len(parts) > 1:
                target_repo_path = parts[-1]
        
        if not target_repo_path:
            logger.warning(f"[GitOps] Could not determine repository path for {file_path}")
            return

        # 4. Create a new branch
        source_branch = repo.get_branch("main")
        new_branch_name = f"sre-auto-heal-{int(time.time())}"
        repo.create_git_ref(ref=f"refs/heads/{new_branch_name}", sha=source_branch.commit.sha)

        # 5. Push the patch
        try:
            file_contents = repo.get_contents(target_repo_path, ref="main")
            repo.update_file(
                path=file_contents.path,
                message=f"Sre AI Auto-Heal: Fixed {error_msg[:50]}",
                content=raw_fix,
                sha=file_contents.sha,
                branch=new_branch_name
            )
        except Exception as e:
            logger.error(f"[GitOps] Failed to update file in repo: {e}")
            return

        # 6. Create Pull Request
        pr = repo.create_pull(
            title=f"[Sre AI] Auto-Heal Patch: {error_msg[:60]}",
            body=f"**Level 5 Autonomous Guardian Protocol**\n\nThe Log Watcher Daemon detected an exception:\n```python\n{traceback_str[-500:]}\n```\n\nSre AI has analyzed the stack trace and generated this patch. Please review carefully before merging.",
            head=new_branch_name,
            base="main"
        )
        logger.info(f"[GitOps] Successfully proposed Auto-Heal PR: {pr.html_url}")

    except Exception as exc:
        logger.error(f"[GitOps] Auto-Patcher encountered an internal error: {exc}")
