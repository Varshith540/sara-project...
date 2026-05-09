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
                                from .gemini_service import _get_client, _generate, SreAIRouter
                                import sys
                                import os
                                # Add root to sys.path to import auto_patcher
                                root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                                if root_path not in sys.path:
                                    sys.path.append(root_path)
                                from auto_patcher import autonomous_heal_and_deploy
                                
                                client = _get_client()
                                if not client:
                                    return
                                    
                                prompt = f"""You are the Level 6 Autonomous SRE Server Guardian (Phoenix Protocol).
The system encountered a critical crash.
Error: {error_msg}

Traceback:
{traceback_str}

If you know the python file and line number causing this, provide the EXACT full content of the corrected file.
Do NOT use markdown code blocks like ```python, JUST output the raw python code perfectly indented.
If you cannot confidently fix it, output exactly: ABORT_HEAL
"""
                                raw_fix, _ = _generate(client, prompt, task_type=SreAIRouter.FORMATTING)
                                
                                if "ABORT_HEAL" in raw_fix or not raw_fix.strip():
                                    return
                                    
                                raw_fix = raw_fix.replace("```python", "").replace("```", "").strip()
                                
                                # Use the file path from traceback if possible, else the one from log record
                                target_file = file_path
                                if not target_file or 'resumexpert' not in target_file:
                                    # Very basic fallback (in production you'd parse traceback better)
                                    import re
                                    match = re.search(r'File "([^"]+\.py)"', traceback_str)
                                    if match:
                                        target_file = match.group(1)
                                
                                if target_file and os.path.exists(target_file):
                                    autonomous_heal_and_deploy(error_msg, raw_fix, target_file)
                                
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
