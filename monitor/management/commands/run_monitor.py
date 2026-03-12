"""チェック実行用の Django 管理コマンド。"""

from django.core.management.base import BaseCommand

from monitor.services import run_checks


class Command(BaseCommand):
    """`python manage.py run_monitor` の実装本体。"""

    help = "Run the Suruga-ya check and persist results into the Django database."

    def add_arguments(self, parser):
        """コマンドライン引数を追加する。"""

        parser.add_argument(
            "--max-pages",
            type=int,
            default=None,
            help="Maximum number of pages to scan for each target.",
        )

    def handle(self, *args, **options):
        """サービス層を呼び出してチェック結果を保存する。"""

        runs = run_checks(max_pages=options["max_pages"])
        self.stdout.write(self.style.SUCCESS(f"Stored {len(runs)} check runs."))
