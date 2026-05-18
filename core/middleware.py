import traceback
from django.utils.deprecation import MiddlewareMixin
from resumexpert.sri_autonomous_healer import sri_heal

# Global cache to store the latest diagnostics for the frontend Chat UI
_LATEST_DIAGNOSTIC = None

def get_latest_diagnostic():
    return _LATEST_DIAGNOSTIC

def clear_diagnostic():
    global _LATEST_DIAGNOSTIC
    _LATEST_DIAGNOSTIC = None

class SriAIHealerMiddleware(MiddlewareMixin):
    def process_exception(self, request, exception):
        global _LATEST_DIAGNOSTIC
        # Format the traceback
        tb_str = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))
        file_path = "Unknown (Server Error)"
        
        # We attempt to find the file from the traceback
        for line in reversed(traceback.extract_tb(exception.__traceback__)):
            if "resumexpert" in line.filename and "site-packages" not in line.filename:
                file_path = line.filename
                break
                
        # Sri AI healing process
        try:
            # We run this in the background (or block slightly) to get a diagnostic
            # For this MVP, we capture it and format a smart message
            _LATEST_DIAGNOSTIC = {
                "type": "500_error",
                "message": f"I intercepted a server crash in `{file_path}`! \n\n**Error:** {str(exception)}\n\nI am analyzing the stack trace. Please check the server logs."
            }
            # Trigger full healing asynchronously or fire-and-forget
            # In a real async setup we'd use celery, but here we just call it or log it
            import threading
            threading.Thread(target=sri_heal, args=(tb_str, file_path, "")).start()
        except Exception as e:
            print(f"[Sri AI Middleware] Healing failed: {e}")
            
        return None  # Let standard Django 500 processing continue
