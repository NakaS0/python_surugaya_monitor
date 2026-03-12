"""チェック実行と DB 保存を扱うサービス層。"""

from __future__ import annotations

from datetime import datetime

from django.utils import timezone

from fixed_targets import get_targets
from scraper import check_new_items

from .models import CheckRun, MonitorTarget, NewItem


def sync_targets(active_set: int | None = None) -> list[MonitorTarget]:
    """指定セットのターゲットを DB と同期する。"""

    targets: list[MonitorTarget] = []
    active_ids: list[str] = []

    active_set = active_set or 1
    for index, item in enumerate(get_targets(active_set=active_set), start=1):
        active_ids.append(item["id"])
        target, _ = MonitorTarget.objects.update_or_create(
            target_id=item["id"],
            target_set=active_set,
            defaults={
                "name": item["name"],
                "url": item["url"],
                "sort_order": index,
                "enabled": True,
            },
        )
        targets.append(target)

    MonitorTarget.objects.filter(target_set=active_set).exclude(target_id__in=active_ids).update(enabled=False)
    return targets


def _create_check_run(target: MonitorTarget, report: dict) -> CheckRun:
    checked_at_raw = report.get("checked_at")
    checked_at = datetime.fromisoformat(checked_at_raw) if checked_at_raw else timezone.now()
    if timezone.is_naive(checked_at):
        checked_at = timezone.make_aware(checked_at, timezone.get_current_timezone())

    run = CheckRun.objects.create(
        target=target,
        checked_at=checked_at,
        total_items=int(report.get("total_items") or 0),
        new_items_count=int(report.get("new_items_count") or 0),
        warning=str(report.get("warning") or ""),
        raw_report=report,
    )

    for item in report.get("new_items") or []:
        if not isinstance(item, dict):
            continue
        NewItem.objects.create(
            check_run=run,
            product_id=str(item.get("id") or ""),
            name=str(item.get("name") or ""),
            url=str(item.get("url") or ""),
            image_url=str(item.get("image_url") or ""),
            price=str(item.get("price") or ""),
        )

    return run


def run_checks(max_pages: int | None = None, active_set: int | None = None) -> list[CheckRun]:
    """現在の対象セット全件をチェックして保存する。"""

    results: list[CheckRun] = []
    for target in sync_targets(active_set=active_set):
        if not target.enabled:
            continue
        report = check_new_items(
            max_pages=max_pages,
            base_url=target.url,
            target_id=target.target_id,
        )
        results.append(_create_check_run(target, report))
    return results


def run_check_for_target(target: MonitorTarget, max_pages: int | None = None) -> CheckRun:
    """指定ターゲット 1 件だけチェックして保存する。"""

    report = check_new_items(
        max_pages=max_pages,
        base_url=target.url,
        target_id=target.target_id,
    )
    return _create_check_run(target, report)
