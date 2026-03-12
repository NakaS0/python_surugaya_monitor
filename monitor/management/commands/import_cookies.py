"""Cookie 取り込み用の Django 管理コマンド。"""

from django.core.management.base import BaseCommand, CommandError

from scraper import import_cookies_from_file, save_cookie_header


class Command(BaseCommand):
    """`python manage.py import_cookies` の実装本体。"""

    help = "Create surugaya_cookies.json from a file or Cookie header string."

    def add_arguments(self, parser):
        """Cookie の入力方法を引数で受け取る。"""

        parser.add_argument("--file", help="Path to a cookie JSON file or plain Cookie header text.")
        parser.add_argument("--header", help="Cookie header text like 'a=b; c=d'.")

    def handle(self, *args, **options):
        """ヘッダー文字列またはファイルから Cookie を保存する。"""

        cookie_file = options.get("file")
        cookie_header = options.get("header")

        if cookie_file:
            count = import_cookies_from_file(cookie_file)
        elif cookie_header:
            count = save_cookie_header(cookie_header)
        else:
            raise CommandError("import_cookies requires --file or --header.")

        self.stdout.write(self.style.SUCCESS(f"Saved {count} cookies to surugaya_cookies.json"))
