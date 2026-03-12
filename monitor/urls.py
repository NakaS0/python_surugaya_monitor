"""`monitor` アプリ専用の URL 定義。

このファイルは、ダッシュボード画面と JSON API を `views.py` に結び付けます。
"""

from django.urls import path

from . import views

app_name = "monitor"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("api/latest-runs/", views.latest_runs_api, name="latest-runs-api"),
]
