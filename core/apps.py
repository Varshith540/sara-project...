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
                        from .auto_patcher import propose_self_healing_patch
                        import threading
                        # Fire and forget auto-patcher so it doesn't block the request
                        t = threading.Thread(target=propose_self_healing_patch, args=(tb_str, file_path, record.getMessage()), daemon=True)
                        t.start()
                    except ImportError:
                        pass

        logger = logging.getLogger('django.request')
        # We also catch core logs
        core_logger = logging.getLogger('core')
        
        heal_handler = AutoHealHandler()
        logger.addHandler(heal_handler)
        core_logger.addHandler(heal_handler)
