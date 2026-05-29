import logging
import traceback
import time
from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        # ── Level 5: Log Watcher Daemon (Sre AI GitOps Hook) ──
        class AutoHealHandler(logging.Handler):
            def __init__(self):
                super().__init__()
                self.last_heal_time = 0
                self.cooldown_seconds = 600  # 10 minutes max 1 heal

            def emit(self, record):
                if record.levelno >= logging.ERROR:
                    # Prevent infinite loops if auto-patcher itself fails
                    if "GitOps" in record.getMessage() or "Sre AI" in record.getMessage():
                        return
                    
                    now = time.time()
                    if now - self.last_heal_time < self.cooldown_seconds:
                        return
                    
                    self.last_heal_time = now
                    
                    # Extract traceback if present
                    tb_str = ""
                    if record.exc_info:
                        tb_str = "".join(traceback.format_exception(*record.exc_info))
                    else:
                        tb_str = record.getMessage()

                    # Extract file path if we can guess it from the record
                    file_path = getattr(record, 'pathname', '')

                    try:
                        import threading
                        
                        def sre_ai_heal_pipeline(traceback_str, file_path, error_msg):
                            try:
                                import sys
                                import os
                                import re
                                
                                # Add root to sys.path to import sri_autonomous_healer
                                root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                                if root_path not in sys.path:
                                    sys.path.append(root_path)
                                
                                from sri_autonomous_healer import sri_heal
                                
                                # Use the file path from traceback if possible, else the one from log record
                                target_file = file_path
                                if not target_file or 'resumexpert' not in target_file:
                                    # Very basic fallback (in production you'd parse traceback better)
                                    match = re.search(r'File "([^"]+\.py)"', traceback_str)
                                    if match:
                                        target_file = match.group(1)
                                
                                if target_file and os.path.exists(target_file):
                                    with open(target_file, "r", encoding="utf-8") as f:
                                        current_code = f.read()
                                    
                                    # Trigger the Full CRGD Loop (Reactive Watcher)
                                    sri_heal(traceback_str, target_file, current_code)

                                
                            except Exception as e:
                                pass # Silent fail in daemon

                        # Fire and forget auto-patcher so it doesn't block the request
                        t = threading.Thread(target=sre_ai_heal_pipeline, args=(tb_str, file_path, record.getMessage()), daemon=True)
                        t.start()
                    except ImportError:
                        pass

        logger = logging.getLogger('django.request')
        # We also catch core logs
        core_logger = logging.getLogger('core')
        
        heal_handler = AutoHealHandler()
        logger.addHandler(heal_handler)
        core_logger.addHandler(heal_handler)

        # Import and start background scheduler securely
        # Check to prevent running the scheduler twice in dev mode with auto-reload
        import os
        if os.environ.get('RUN_MAIN', None) != 'true':
            try:
                from . import scheduler
                scheduler.start_scheduler()
            except ImportError as e:
                logging.error(f"Failed to start APScheduler: {e}")

        # ── Omni-Heal: Start Soft-Heal background daemon ──
        try:
            from core.sri_autonomous_healer import start_soft_heal_engine
            start_soft_heal_engine()
        except Exception as e:
            logging.error(f"[OmniHeal] Failed to start Soft-Heal engine: {e}")
