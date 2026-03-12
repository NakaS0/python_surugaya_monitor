"""対象同期用の Django 管理コマンド。"""

from django.core.management.base import BaseCommand

from monitor.services import sync_targets


class Command(BaseCommand):
    """`python manage.py sync_monitor_targets` の実装本体。"""

    help = "Sync check targets from .env into the Django database."

    def handle(self, *args, **options):
        """`.env` の対象を DB に同期する。"""

        targets = sync_targets()
        self.stdout.write(self.style.SUCCESS(f"Synced {len(targets)} targets."))
