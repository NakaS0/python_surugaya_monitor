"""ASGI 用の起動設定。

このファイルは、非同期サーバーから Django を起動するときの入口です。
通常の開発では直接触ることは少ないですが、WebSocket や ASGI サーバー
（uvicorn など）で動かすときに使われます。
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_asgi_application()
