"""
WSGI config for resumexpert project.
"""

import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'resumexpert.settings')
application = get_wsgi_application()

# ---------------------------------------------------------------------------
# System Reliability Guardian (Keep-Alive Thread)
# ---------------------------------------------------------------------------
import threading
import time
import requests
import logging

logger = logging.getLogger(__name__)

def _keep_alive_ping():
    """
    Pings the public /ping/ endpoint every 10 minutes (600s) to prevent 
    Render Free Tier from spinning down due to inactivity.
    """
    app_url = os.environ.get('APP_URL', 'http://127.0.0.1:10000').rstrip('/')
    ping_url = f"{app_url}/ping/"
    
    while True:
        try:
            time.sleep(600)
            requests.get(ping_url, timeout=10)
            logger.info(f"[SRG] Keep-Alive Ping successful to {ping_url}")
        except Exception as e:
            logger.warning(f"[SRG] Keep-Alive Ping failed: {e}")

try:
    # Start the thread as a daemon so it doesn't block worker shutdown
    t = threading.Thread(target=_keep_alive_ping, daemon=True)
    t.start()
    logger.info("[SRG] Keep-Alive Guardian thread started.")
except Exception as e:
    logger.error(f"[SRG] Failed to start Guardian thread: {e}")
