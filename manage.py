#!/usr/bin/env python
"""Django 管理コマンドの入口。

このファイルは、`python manage.py ...` で始まるすべての操作の起点です。
主に次のような用途で使います。

- `runserver`: 開発用サーバーを起動する
- `migrate`: DB テーブルを作成・更新する
- `run_monitor`: チェックを実行して DB に保存する
- `sync_monitor_targets`: `.env` の対象を DB に同期する
- `import_cookies`: Cookie を保存する
"""
import os
import sys


def main():
    """Django の管理コマンド実行処理を起動する。"""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
