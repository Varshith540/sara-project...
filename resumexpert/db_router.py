"""
db_router.py — ResumeXpert Dual-Database Router
================================================
Rules
-----
  default  → All standard application models (Resume, AnalysisResult, etc.)
  backup   → Models explicitly tagged with app_label == 'backup_store',
             plus any model that sets Meta.using = 'backup' via a mixin.

Usage: tag a model for backup routing by setting its app_label:

    class Meta:
        app_label = 'backup_store'

Or use the BackupModelMixin on any model:

    from resumexpert.db_router import BackupModelMixin

    class AuditLog(BackupModelMixin, models.Model):
        ...
"""


# Labels of Django apps whose models should live on the backup DB.
_BACKUP_APPS = frozenset({'backup_store'})


class BackupDatabaseRouter:
    """
    Routes reads/writes for backup-tagged models to the 'backup' database.
    Everything else goes to 'default'.
    """

    def _is_backup(self, model) -> bool:
        return getattr(model, '_backup_db', False) or model._meta.app_label in _BACKUP_APPS

    # ── Read routing ─────────────────────────────────────────────────────────
    def db_for_read(self, model, **hints):
        if self._is_backup(model):
            return 'backup'
        return 'default'

    # ── Write routing ────────────────────────────────────────────────────────
    def db_for_write(self, model, **hints):
        if self._is_backup(model):
            return 'backup'
        return 'default'

    # ── Relation routing ─────────────────────────────────────────────────────
    def allow_relation(self, obj1, obj2, **hints):
        # Allow relations within the same database only
        db1 = 'backup' if self._is_backup(type(obj1)) else 'default'
        db2 = 'backup' if self._is_backup(type(obj2)) else 'default'
        return db1 == db2

    # ── Migration routing ────────────────────────────────────────────────────
    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label in _BACKUP_APPS:
            return db == 'backup'
        # Standard Django/third-party apps → default only
        return db == 'default'


# ---------------------------------------------------------------------------
# Optional mixin — apply to any model you want routed to backup
# ---------------------------------------------------------------------------

class BackupModelMixin:
    """
    Attach this mixin to any model to route it to the backup database
    without changing its app_label.

    Example
    -------
        class AuditLog(BackupModelMixin, models.Model):
            event = models.TextField()
            created_at = models.DateTimeField(auto_now_add=True)
    """
    _backup_db = True
