import os
from datetime import timedelta
from django.utils import timezone
from apscheduler.schedulers.background import BackgroundScheduler
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def check_pending_deployments():
    """
    Job that runs periodically to find Pending Deployments older than 24 hours
    that haven't received a reminder in the last 24 hours.
    """
    # Import inside to prevent app registry not ready issues
    from core.models import PendingDeployment
    
    now = timezone.now()
    cutoff_time = now - timedelta(hours=24)
    
    # Find deployments created > 24 hours ago that are STILL pending
    pending_deployments = PendingDeployment.objects.filter(
        status='pending',
        created_at__lte=cutoff_time
    )
    
    for deployment in pending_deployments:
        # Check if we already sent a reminder in the last 24 hours
        if deployment.last_reminder_sent and deployment.last_reminder_sent > cutoff_time:
            continue
            
        send_reminder_email(deployment)
        deployment.last_reminder_sent = now
        deployment.save(update_fields=['last_reminder_sent'])

def send_reminder_email(deployment):
    """Sends the reminder email for a specific deployment."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    SMTP_USER = os.environ.get("SMTP_USER", "your-email@gmail.com")
    SMTP_PASS = os.environ.get("SMTP_PASS", "your-app-password")
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@resumexpert.com")
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"⏰ REMINDER: Pending AI Upgrade Approval (PR #{deployment.pr_number})"
    msg["From"] = SMTP_USER
    msg["To"] = ADMIN_EMAIL
    
    # Links
    base_url = "http://127.0.0.1:8000"
    approve_url = f"{base_url}/api/cicd/approve-deployment/sri-secure-token-123/?pr={deployment.pr_number}"
    reject_url = f"{base_url}/api/cicd/reject-deployment/sri-secure-token-123/?pr={deployment.pr_number}"
    
    html = f"""
    <html>
      <body style="font-family: sans-serif;">
        <h2 style="color: #ff9800;">⏰ Reminder: Autonomous Fix Still Pending</h2>
        <p>Sri AI generated an optimization for <strong>{deployment.file_path}</strong> over 24 hours ago, and it is waiting for your explicit approval or rejection.</p>
        <p>If no action is taken, the code will not be deployed.</p>
        
        <p><strong>Original Analysis:</strong></p>
        <pre style="background: #f4f4f4; padding: 10px;">{deployment.analysis_log}</pre>
        
        <div style="margin: 30px 0; display: flex; gap: 15px;">
            <a href="{approve_url}" style="background-color: #28a745; color: white; padding: 15px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 16px;">Approve and Deploy</a>
            <a href="{reject_url}" style="background-color: #dc3545; color: white; padding: 15px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 16px;">Reject & Discard</a>
        </div>
      </body>
    </html>
    """
    msg.attach(MIMEText(html, "html"))
    
    if SMTP_USER == "your-email@gmail.com":
        print("\n" + "="*50)
        print("📧 [HITL REMINDER Email MOCK] Admin notified.")
        print("="*50 + "\n")
    else:
        try:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASS)
                server.sendmail(SMTP_USER, ADMIN_EMAIL, msg.as_string())
            print(f"📧 Reminder Email Sent for PR {deployment.pr_number}!")
        except Exception as e:
            logger.error(f"Failed to send reminder email: {e}")

def proactive_crawler_job():
    """
    Background SRE: The Proactive Crawler.
    Randomly selects an allowed file and runs proactive_optimize on it.
    """
    import os
    import random
    import sys
    
    root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root_path not in sys.path:
        sys.path.append(root_path)
        
    try:
        from sri_autonomous_healer import proactive_optimize
    except ImportError as e:
        logger.error(f"Failed to import proactive_optimize: {e}")
        return

    # Scope definition
    core_dir = os.path.join(root_path, "core")
    static_js_dir = os.path.join(core_dir, "static", "js") # Actually it's just static/js in core, or static/js at root. Let's use root_path/static/js and core_dir/static/js
    root_static_js = os.path.join(root_path, "static", "js")
    
    allowed_files = []
    
    # Allowed: core/*.py (excluding models.py, apps.py, tests, migrations)
    for root, dirs, files in os.walk(core_dir):
        if "migrations" in root:
            continue
        for file in files:
            if file.endswith(".py"):
                if file in ["models.py", "apps.py", "admin.py", "__init__.py"]:
                    continue
                if file.startswith("test_"):
                    continue
                allowed_files.append(os.path.join(root, file))
                
    # Allowed: Specific JS files
    for js_dir in [static_js_dir, root_static_js]:
        if os.path.exists(js_dir):
            for file in os.listdir(js_dir):
                if file.endswith(".js"):
                    allowed_files.append(os.path.join(js_dir, file))
                    
    if not allowed_files:
        logger.warning("[Proactive Crawler] No allowed files found in scope.")
        return
        
    # Randomly select one file
    target_file = random.choice(allowed_files)
    logger.info(f"🕵️‍♂️ [Proactive Crawler] Sri AI selected {target_file} for optimization.")
    
    try:
        proactive_optimize(target_file)
    except Exception as e:
        logger.error(f"[Proactive Crawler] Failed to optimize {target_file}: {e}")

def start_scheduler():
    scheduler = BackgroundScheduler()
    # Check every 1 hour in production for pending deployments
    scheduler.add_job(check_pending_deployments, 'interval', hours=1, id='check_pending_deployments_job', replace_existing=True)
    
    # Proactive Crawler: Runs every 12 hours
    scheduler.add_job(proactive_crawler_job, 'interval', hours=12, id='proactive_crawler_job', replace_existing=True)
    
    scheduler.start()
    logger.info("⏰ Sri AI Background Reminder Scheduler Started")
