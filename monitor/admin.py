"""Django 管理画面でモデルを見やすくする設定。

Admin から対象・実行結果・新着商品を確認しやすくするための表示項目を定義しています。
"""

from django.contrib import admin

from .models import CheckRun, MonitorTarget, NewItem


class NewItemInline(admin.TabularInline):
    """チェック結果の詳細画面で新着商品を一覧表示する。"""

    model = NewItem
    extra = 0
    readonly_fields = ("product_id", "name", "url", "price", "image_url")


@admin.register(MonitorTarget)
class MonitorTargetAdmin(admin.ModelAdmin):
    """チェック対象モデルの管理画面表示設定。"""

    list_display = ("target_id", "name", "sort_order", "enabled", "updated_at")
    list_editable = ("sort_order", "enabled")
    search_fields = ("target_id", "name")


@admin.register(CheckRun)
class CheckRunAdmin(admin.ModelAdmin):
    """チェック結果モデルの管理画面表示設定。"""

    list_display = ("target", "checked_at", "new_items_count", "total_items", "warning")
    list_filter = ("target",)
    search_fields = ("target__target_id", "target__name")
    readonly_fields = ("created_at",)
    inlines = [NewItemInline]
