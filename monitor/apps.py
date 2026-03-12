"""Django に `monitor` アプリを登録する設定。"""

from django.apps import AppConfig


class MonitorConfig(AppConfig):
    """`monitor` アプリの基本情報。"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "monitor"
