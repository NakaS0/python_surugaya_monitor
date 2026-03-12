"""WSGI 用の起動設定。

このファイルは、Gunicorn や mod_wsgi のような WSGI サーバーから
Django を起動するときに使われます。開発サーバーだけを使う場合でも、
本番配備ではよく利用されるため Django が自動生成しています。
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
