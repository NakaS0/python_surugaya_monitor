"""Django 全体の URL ルーティング設定。

このファイルは「どの URL にアクセスしたとき、どの処理へ渡すか」を決めます。
現在は以下の2系統を公開しています。

- `/admin/`: Django 標準の管理画面
- `/`: `monitor` アプリのダッシュボード
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("monitor.urls")),
]
