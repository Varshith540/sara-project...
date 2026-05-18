"""
Sri AI Healer — Cognitive Recursive Generative Design (CRGD)
============================================================
Includes Meta-Learning (ChromaDB), Recursive Debate Protocol,
and Proactive Autonomous Benchmarking (PAB).
"""

import os
import json
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import difflib

# Third-party imports
import google.generativeai as genai
try:
    import chromadb
except ImportError:
    chromadb = None

# Import the existing Draft PR logic from auto_patcher
from auto_patcher import autonomous_heal_and_deploy

logger = logging.getLogger(__name__)

# Configure Gemini
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER", "your-email@gmail.com")
SMTP_PASS = os.environ.get("SMTP_PASS", "your-app-password")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@resumexpert.com")

# ---------------------------------------------------------------------------
# Vector DB Memory Module
# ---------------------------------------------------------------------------
class VectorDBMemory:
    def __init__(self, db_path="./.chromadb"):
        self.enabled = chromadb is not None
        if not self.enabled:
            logger.warning("ChromaDB not installed. Sri AI Memory disabled.")
            return
            
        self.client = chromadb.PersistentClient(path=db_path)
        self.collection = self.client.get_or_create_collection(name="sri_memory")
        
    def add_heuristic(self, text: str, metadata: dict):
        if not self.enabled: return
        doc_id = f"heuristic_{self.collection.count() + 1}"
        self.collection.add(
            documents=[text],
            metadatas=[metadata],
            ids=[doc_id]
        )
        print(f"🧠 [Memory] Saved new heuristic to Vector DB: {text[:50]}...")
        
    def get_relevant_heuristics(self, query: str, n_results=3) -> list[str]:
        if not self.enabled or self.collection.count() == 0:
            return []
        # Ensure we don't request more results than we have in the DB
        n = min(n_results, self.collection.count())
        results = self.collection.query(
            query_texts=[query],
            n_results=n
        )
        heuristics = results.get("documents", [[]])[0]
        return heuristics

sri_memory = VectorDBMemory()

# ---------------------------------------------------------------------------
# Core LLM Call Helper
# ---------------------------------------------------------------------------
def _call_gemini_json(prompt: str) -> dict:
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY is not set.")
        return {}
        
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```json"): text = text[7:]
        if text.startswith("```"): text = text[3:]
        if text.endswith("```"): text = text[:-3]
        return json.loads(text.strip())
    except Exception as e:
        logger.error(f"Gemini API failure: {e}")
        return {}

def _call_gemini_text(prompt: str) -> str:
    if not GEMINI_API_KEY: return ""
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini API failure: {e}")
        return ""

# ---------------------------------------------------------------------------
# Phase 1: The Generator
# ---------------------------------------------------------------------------
def generate_first_draft(traceback: str, current_code: str, file_path: str, heuristics: list[str]) -> dict:
    """Agent 1: Writes the initial working fix."""
    memory_context = "\n".join([f"- {h}" for h in heuristics]) if heuristics else "None"
    
    prompt = f"""
    You are Agent 1 (The Generator) of Sri AI. A backend error occurred in {file_path}.
    
    Past Learnings (DO NOT REPEAT MISTAKES):
    {memory_context}
    
    Traceback:
    ```
    {traceback}
    ```
    
    Current Code:
    ```
    {current_code}
    ```
    
    Generate the FIRST DRAFT patch. Output your response STRICTLY as a valid JSON object:
    {{
        "fixed_code": "the full new code as a string",
        "explanation": "why you made these changes"
    }}
    """
    return _call_gemini_json(prompt)

# ---------------------------------------------------------------------------
# Phase 2: The Adversarial Critic
# ---------------------------------------------------------------------------
def critique_and_optimize(first_draft_code: str, file_path: str, heuristics: list[str]) -> dict:
    """Agent 2: Tears down the first draft and forces an optimal rewrite."""
    memory_context = "\n".join([f"- {h}" for h in heuristics]) if heuristics else "None"
    
    prompt = f"""
    You are Agent 2 (The Adversarial Critic) of Sri AI. Act as a Senior Principal Engineer.
    
    Past Learnings to enforce:
    {memory_context}
    
    Review this First Draft Code for {file_path}:
    ```
    {first_draft_code}
    ```
    
    It might work, but is it the MOST optimal, high-performance way?
    Find security flaws, time-complexity issues, or better modern generative design patterns.
    
    Return the highly optimized version STRICTLY as a valid JSON object:
    {{
        "optimized_code": "the full, highly optimized new code as a string",
        "critique_reasoning": "your ruthless critique of the first draft and why this is better"
    }}
    """
    return _call_gemini_json(prompt)

# ---------------------------------------------------------------------------
# Phase 3: The Meta-Reflector
# ---------------------------------------------------------------------------
def meta_reflect_and_learn(traceback: str, first_draft: str, optimized_code: str):
    """Agent 3: Extracts a Golden Rule from the debate."""
    prompt = f"""
    You are Agent 3 (The Meta-Reflector) of Sri AI.
    We just had an error, wrote a First Draft, and then an Adversarial Critic optimized it.
    
    Error Traceback:
    {traceback}
    
    What cognitive blind spot existed in the first draft that the optimized code fixed?
    Extract a single, concise "Golden Rule" heuristic (max 2 sentences) that we must learn from this.
    """
    heuristic = _call_gemini_text(prompt)
    if heuristic:
        sri_memory.add_heuristic(heuristic, {"source": "CRGD-Reflection"})

# ---------------------------------------------------------------------------
# Proactive Autonomous Benchmarking (PAB)
# ---------------------------------------------------------------------------
def shadow_benchmark(original_code: str, new_code: str) -> str:
    """Statically benchmarks Old vs New using Gemini as an arbiter."""
    prompt = f"""
    You are the Proactive Benchmark Arbiter. 
    Compare the Old Code and New Optimized Code for structural complexity, performance, and memory usage.
    
    Old Code:
    ```
    {original_code}
    ```
    
    New Code:
    ```
    {new_code}
    ```
    
    Is the new code significantly better?
    Respond STRICTLY with either 'WINNER=OPTIMIZED' or 'WINNER=ORIGINAL', followed by a newline and the reason.
    """
    return _call_gemini_text(prompt)

def proactive_optimize(file_path: str):
    """Proactively hunts for optimization opportunities in working code."""
    print(f"🔎 [PAB] Proactively profiling {file_path}...")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            original_code = f.read()
    except Exception as e:
        logger.error(f"Failed to read file: {e}")
        return
        
    prompt = f"""
    You are the Proactive Optimization Agent. Review this working code for {file_path}.
    Is there a drastically more highly-performant, edge-case-proof, or elegant generative design?
    If yes, output the optimized code. If no, output the original code.
    
    ```
    {original_code}
    ```
    
    Output STRICTLY as JSON:
    {{
        "optimized_code": "the full new code",
        "explanation": "what you optimized and why"
    }}
    """
    
    result = _call_gemini_json(prompt)
    if not result or "optimized_code" not in result:
        return
        
    optimized_code = result["optimized_code"]
    explanation = result["explanation"]
    
    if optimized_code.strip() == original_code.strip():
        print("✅ [PAB] Code is already optimal.")
        return
        
    print("⚖️ [PAB] Shadow Benchmarking new algorithm...")
    benchmark_result = shadow_benchmark(original_code, optimized_code)
    print(f"[PAB Benchmark]: {benchmark_result}")
    
    if "WINNER=OPTIMIZED" in benchmark_result:
        print("🏆 [PAB] New optimization won the benchmark! Triggering HITL Gateway.")
        # Trigger HITL Gateway
        pr_url = autonomous_heal_and_deploy(
            error_traceback="Proactive Benchmark Upgrade",
            fixed_code=optimized_code,
            file_path=file_path,
            commit_message=f"perf(sri-ai): Proactive optimization of {file_path}"
        )
        if pr_url:
            diff_list = list(difflib.unified_diff(
                original_code.splitlines(), optimized_code.splitlines(), fromfile="original", tofile="optimized", lineterm=""
            ))
            send_hitl_email("N/A - Proactive Scan", explanation, "Proactive Upgrade Approval", pr_url, "\n".join(diff_list))

# ---------------------------------------------------------------------------
# HITL Gateway & Execution
# ---------------------------------------------------------------------------
def classify_risk(file_path: str, fixed_code: str, current_code: str) -> tuple[str, str]:
    if "models.py" in file_path or "migrations" in file_path or file_path.endswith(".env"):
        return "HIGH RISK", "Modifies models, migrations, or environment configs."
    if fixed_code.strip() == "" and current_code.strip() != "":
        return "HIGH RISK", "Proposes complete file deletion."
    if file_path.endswith((".js", ".css", ".html")) or "views.py" in file_path:
        return "LOW RISK", "Safe frontend/view change."
    return "HIGH RISK", "Complex backend logic."

def send_hitl_email(traceback: str, explanation: str, risk_reason: str, pr_url: str, diff: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "🚨 [Sri AI Healer] Action Required: PR Approval"
    msg["From"] = SMTP_USER
    msg["To"] = ADMIN_EMAIL
    
    # Extract PR number from URL or fallback to "unknown"
    pr_number = pr_url.split('/')[-1] if '/' in pr_url else '1'
    
    # Create the Pending Deployment record in the DB
    try:
        from core.models import PendingDeployment
        import django
        django.setup()
        
        # We try to extract file path from the diff
        file_path_guess = "unknown_file"
        if "--- original" in diff:
            lines = diff.splitlines()
            for line in lines:
                if line.startswith("+++ optimized") or line.startswith("+++ "):
                    file_path_guess = line.replace("+++ ", "").strip()
                    break
        
        PendingDeployment.objects.create(
            pr_number=pr_number,
            file_path=file_path_guess,
            analysis_log=explanation
        )
    except Exception as e:
        logger.error(f"Failed to create PendingDeployment record: {e}")
        
    one_click_url = f"http://127.0.0.1:8000/api/cicd/approve-deployment/sri-secure-token-123/?pr={pr_number}"
    reject_url = f"http://127.0.0.1:8000/api/cicd/reject-deployment/sri-secure-token-123/?pr={pr_number}"
    
    text = f"""
    Risk Reason: {risk_reason}
    
    Plan Details: {explanation}
    
    GitHub Review: {pr_url}
    
    ONE-CLICK APPROVE & DEPLOY:
    {one_click_url}
    
    ONE-CLICK REJECT & DISCARD:
    {reject_url}
    
    Diff: {diff[:1000]}
    """
    msg.attach(MIMEText(text, "plain"))
    
    html = f"""
    <html>
      <body style="font-family: sans-serif;">
        <h2 style="color: #d9534f;">🚨 Action Required: Autonomous Fix Staged</h2>
        <p><strong>Reason:</strong> {risk_reason}</p>
        <p><strong>Plan Details:</strong></p>
        <pre style="background: #f4f4f4; padding: 10px;">{explanation}</pre>
        <p><a href="{pr_url}">Review on GitHub</a></p>
        <div style="margin: 30px 0; display: flex; gap: 15px;">
            <a href="{one_click_url}" style="background-color: #28a745; color: white; padding: 15px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 16px;">Approve and Deploy</a>
            <a href="{reject_url}" style="background-color: #dc3545; color: white; padding: 15px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 16px;">Reject & Discard</a>
        </div>
        <h4>Diff Preview:</h4>
        <pre style="background: #272822; color: #f8f8f2; padding: 10px;">{diff[:1000]}</pre>
      </body>
    </html>
    """
    msg.attach(MIMEText(html, "html"))
    
    if SMTP_USER == "your-email@gmail.com":
        print("\n" + "="*50)
        print("📧 [HITL Email MOCK] Admin notified.")
        print(text)
        print("="*50 + "\n")
    else:
        try:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASS)
                server.sendmail(SMTP_USER, ADMIN_EMAIL, msg.as_string())
            print("📧 HITL Email Sent with One-Click Deploy Link!")
        except Exception as e:
            logger.error(f"Failed to send email: {e}")

# ---------------------------------------------------------------------------
# The CRGD Orchestrator
# ---------------------------------------------------------------------------
def sri_heal(traceback: str, file_path: str, current_code: str):
    """Main Entry Point for Error Resolution."""
    print(f"🤖 [CRGD Phase 0] Loading Meta-Memory for {file_path}...")
    heuristics = sri_memory.get_relevant_heuristics(traceback)
    
    print("🤖 [CRGD Phase 1] Generator Agent writing first draft...")
    draft = generate_first_draft(traceback, current_code, file_path, heuristics)
    if not draft: return
    
    print("🧠 [CRGD Phase 2] Adversarial Critic optimizing the code...")
    optimized = critique_and_optimize(draft["fixed_code"], file_path, heuristics)
    if not optimized: return
    
    print("📖 [CRGD Phase 3] Meta-Reflector extracting Golden Rule...")
    meta_reflect_and_learn(traceback, draft["fixed_code"], optimized["optimized_code"])
    
    final_code = optimized["optimized_code"]
    debate_summary = f"First Draft Logic:\n{draft['explanation']}\n\nCritic Optimization:\n{optimized['critique_reasoning']}"
    
    risk_level, risk_reason = classify_risk(file_path, final_code, current_code)
    print(f"📊 [CRGD Phase 4] Risk Classification: {risk_level} ({risk_reason})")
    
    if risk_level == "LOW RISK":
        print("✅ LOW RISK. Applying patch locally...")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(final_code)
    else:
        print("⚠️ HIGH RISK. Opening Draft PR...")
        pr_url = autonomous_heal_and_deploy(
            error_traceback=traceback,
            fixed_code=final_code,
            file_path=file_path,
            commit_message=f"fix(sri-ai): Auto-patch for {file_path}"
        )
        if pr_url:
            diff_list = list(difflib.unified_diff(current_code.splitlines(), final_code.splitlines(), lineterm=""))
            send_hitl_email(traceback, debate_summary, risk_reason, pr_url, "\n".join(diff_list))

