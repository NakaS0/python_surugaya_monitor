"""DB に保存するデータ構造を定義するファイル。

このプロジェクトでは、チェック対象、各回の実行結果、新着商品を Django のモデルとして
管理しています。これにより、JSON ファイルではなく SQLite / Django ORM で結果を扱えます。
"""

from django.db import models


class MonitorTarget(models.Model):
    """1つのチェック対象を表すモデル。"""

    target_id = models.SlugField(max_length=100)
    target_set = models.PositiveSmallIntegerField(default=1)
    name = models.CharField(max_length=255)
    url = models.URLField(max_length=2000)
    sort_order = models.PositiveIntegerField(default=0)
    enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["target_set", "sort_order", "target_id"]
        constraints = [
            models.UniqueConstraint(fields=["target_set", "target_id"], name="uniq_target_set_target_id"),
        ]

    def __str__(self) -> str:
        return f"{self.name} (set={self.target_set}, id={self.target_id})"


class CheckRun(models.Model):
    """1回分のチェック結果を表すモデル。"""

    target = models.ForeignKey(MonitorTarget, on_delete=models.CASCADE, related_name="runs")
    checked_at = models.DateTimeField()
    total_items = models.PositiveIntegerField(default=0)
    new_items_count = models.PositiveIntegerField(default=0)
    warning = models.TextField(blank=True)
    raw_report = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-checked_at", "-id"]

    def __str__(self) -> str:
        return f"{self.target.target_id} @ {self.checked_at.isoformat()}"


class NewItem(models.Model):
    """あるチェック結果で見つかった新着商品を表すモデル。"""

    check_run = models.ForeignKey(CheckRun, on_delete=models.CASCADE, related_name="new_items")
    product_id = models.CharField(max_length=200)
    name = models.CharField(max_length=500)
    url = models.URLField(max_length=2000)
    image_url = models.URLField(max_length=2000, blank=True)
    price = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.product_id}: {self.name}"
