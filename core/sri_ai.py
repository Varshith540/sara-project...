import logging
import os
import time
from typing import Optional

from github import Github, GithubException
from github.Repository import Repository

logger = logging.getLogger("sri_ai.git_controller")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO  = os.getenv("GITHUB_REPO", "")
MAIN_BRANCH  = "main"
PATCH_BRANCH_PREFIX = "auto-heal-patch"

PROTECTED_PATHS = {
    "settings.py", "settings/", "manage.py", ".env",
    "requirements.txt", "migrations/", ".github/workflows/",
}

def _is_path_protected(file_path: str) -> bool:
    return any(file_path.endswith(p) or f"/{p}" in file_path for p in PROTECTED_PATHS)

def _get_repo() -> Repository:
    if not GITHUB_TOKEN or not GITHUB_REPO:
        raise EnvironmentError("GITHUB_TOKEN and GITHUB_REPO must be set.")
    g = Github(GITHUB_TOKEN)
    return g.get_repo(GITHUB_REPO)

def auto_heal_and_deploy(job_id: str, file_path: str, new_content: str, error_summary: str, severity: str = "MEDIUM") -> dict:
    if _is_path_protected(file_path):
        logger.warning("[GitController] Blocked attempt to patch protected path: %s", file_path)
        return {"status": "blocked", "reason": f"{file_path} is protected."}

    patch_branch = f"{PATCH_BRANCH_PREFIX}-{job_id}"
    commit_msg   = (
        f"fix(sri-ai): Auto-heal patch [{job_id}]\n\n"
        f"Severity : {severity}\nFile     : {file_path}\nSummary  : {error_summary}\n\n"
        f"[Automated patch — awaiting CI verification before merge]"
    )

    try:
        repo = _get_repo()
        main_ref = repo.get_branch(MAIN_BRANCH)
        main_sha = main_ref.commit.sha

        try:
            repo.create_git_ref(ref=f"refs/heads/{patch_branch}", sha=main_sha)
        except GithubException as e:
            if e.status != 422: raise

        try:
            existing_file = repo.get_contents(file_path, ref=patch_branch)
            file_sha = existing_file.sha
        except GithubException:
            file_sha = None

        content_bytes = new_content.encode("utf-8")
        if file_sha:
            repo.update_file(path=file_path, message=commit_msg, content=content_bytes, sha=file_sha, branch=patch_branch)
        else:
            repo.create_file(path=file_path, message=commit_msg, content=content_bytes, branch=patch_branch)

        pr_body = (
            f"## 🤖 Sri AI Auto-Heal Patch\n\n"
            f"**Job ID** : `{job_id}`\n**File** : `{file_path}`\n**Severity**: `{severity}`\n\n"
            f"### What was fixed\n{error_summary}\n\n---\n"
            f"⚙️  *This PR was created autonomously by Sri AI.*\n"
            f"🧪 *The Synthetic QA Bot is running CI tests right now.*\n"
            f"✅ *If all tests pass, this PR will auto-merge.*\n"
            f"❌ *If tests fail, this PR will be auto-closed and the patch discarded.*\n"
        )

        pr = repo.create_pull(
            title=f"fix(sri-ai): [{severity}] Auto-heal — {file_path} [{job_id}]",
            body=pr_body, head=patch_branch, base=MAIN_BRANCH, draft=False
        )

        return {"status": "pr_opened", "branch": patch_branch, "pr_url": pr.html_url, "pr_number": pr.number, "job_id": job_id}

    except Exception as exc:
        logger.exception("[GitController] Error for job %s: %s", job_id, exc)
        return {"status": "error", "error": str(exc), "job_id": job_id}

def draft_heal_pr(error_source: str, error_trace: str, context: str = "", job_id: str = "legacy") -> dict:
    logger.info("[GitController] Legacy wrapper called for %s", error_source)
    return {"status": "logged_for_analysis", "source": error_source}
