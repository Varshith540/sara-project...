"""
auto_patcher.py — SRE AI Safe Auto-Patcher
==========================================
Strategy: NEVER push AI-generated code directly to main.
Instead, create a timestamped fix-branch via the GitHub API and open a
Draft Pull Request. A human (or a future CI gate) reviews and merges.

Environment variables required:
  SRE_PAT      — Fine-grained GitHub Personal Access Token (repo scope)
  GITHUB_REPO  — "owner/repo-name"  e.g. "Varshith540/resumexpert"
"""

import os
import time
import logging
from github import Github, GithubException

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Primary entry point
# ---------------------------------------------------------------------------

def autonomous_heal_and_deploy(
    error_traceback: str,
    fixed_code: str,
    file_path: str,
    commit_message: str | None = None,
) -> str | None:
    """
    SRE AI calls this to safely apply a fix.

    Parameters
    ----------
    error_traceback : str   — The error string that triggered the patch.
    fixed_code      : str   — The full corrected file content.
    file_path       : str   — Repo-relative path e.g. "core/views.py".
    commit_message  : str   — Optional override for the commit message.

    Returns
    -------
    str   — URL of the opened Draft Pull Request.
    None  — If patching failed (logged, never raises).
    """
    pat  = os.environ.get("SRE_PAT")
    repo_slug = os.environ.get("GITHUB_REPO")

    if not pat or not repo_slug:
        logger.error(
            "[AutoPatcher] SRE_PAT and GITHUB_REPO env vars must be set. "
            "Patch aborted — no changes made."
        )
        return None

    try:
        g    = Github(pat)
        repo = g.get_repo(repo_slug)

        # ── 1. Resolve the current HEAD SHA of main ──────────────────────────
        main_branch = repo.get_branch("main")
        base_sha    = main_branch.commit.sha
        logger.info(f"[AutoPatcher] Base SHA (main HEAD): {base_sha[:8]}")

        # ── 2. Create a timestamped fix branch ───────────────────────────────
        timestamp   = int(time.time())
        branch_name = f"sre-ai/fix-{timestamp}"
        repo.create_git_ref(f"refs/heads/{branch_name}", base_sha)
        logger.info(f"[AutoPatcher] Created branch: {branch_name}")

        # ── 3. Retrieve current file to get its blob SHA (required for update)
        try:
            contents = repo.get_contents(file_path, ref="main")
            file_sha = contents.sha
        except GithubException:
            # File doesn't exist yet on main — this is a new file creation
            file_sha = None

        # ── 4. Push the fix to the branch via GitHub API ──────────────────────
        short_error = error_traceback[:80].replace("\n", " ")
        cm = commit_message or f"fix(sre-ai): auto-patch for '{short_error}'"

        if file_sha:
            repo.update_file(
                path=file_path,
                message=cm,
                content=fixed_code,
                sha=file_sha,
                branch=branch_name,
            )
        else:
            repo.create_file(
                path=file_path,
                message=cm,
                content=fixed_code,
                branch=branch_name,
            )
        logger.info(f"[AutoPatcher] Fix committed to branch '{branch_name}'")

        # ── 5. Open a Draft Pull Request ─────────────────────────────────────
        pr_title = f"🤖 SRE AI Fix: {short_error}"
        pr_body  = _build_pr_body(error_traceback, file_path, base_sha, branch_name)

        pr = repo.create_pull(
            title=pr_title,
            body=pr_body,
            head=branch_name,
            base="main",
            draft=True,           # Draft — requires human to mark ready & merge
        )

        logger.info(f"✅ [AutoPatcher] Draft PR #{pr.number} opened: {pr.html_url}")
        print(f"✅ Phoenix Protocol: Fix staged as Draft PR #{pr.number}")
        print(f"   Review & merge at: {pr.html_url}")
        return pr.html_url

    except GithubException as e:
        logger.error(f"❌ [AutoPatcher] GitHub API error: {e.status} — {e.data}")
    except Exception as e:
        logger.exception(f"❌ [AutoPatcher] Unexpected failure: {e}")

    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_pr_body(
    error_traceback: str,
    file_path: str,
    base_sha: str,
    branch_name: str,
) -> str:
    """Builds a descriptive PR body for human reviewers."""
    return f"""## 🤖 SRE AI — Automated Fix

> **This PR was created automatically by the SRE AI Guardian.**  
> It is a **Draft PR** — do not merge without reviewing the diff.

---

### 📋 Incident Summary

| Field | Value |
|---|---|
| **Affected file** | `{file_path}` |
| **Fix branch** | `{branch_name}` |
| **Base commit (main)** | `{base_sha[:8]}` |
| **Generated at** | {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())} |

### 🔍 Error That Triggered This Patch

```
{error_traceback[:500]}
```

### ✅ Review Checklist

- [ ] Diff looks correct and complete
- [ ] No unintended side effects in other modules
- [ ] Migrations included if models were changed
- [ ] Manual smoke test passed on staging

---
*Auto-generated by `auto_patcher.py`. Contact the SRE team for questions.*
"""
