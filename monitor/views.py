"""ダッシュボード表示と API を提供するビュー。"""

from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from fixed_targets import available_target_sets, default_active_target_set

from .models import CheckRun, MonitorTarget
from .services import run_check_for_target, run_checks, sync_targets

SESSION_KEY_ACTIVE_SET = "active_target_set"


def _current_active_set(request) -> int:
    value = request.session.get(SESSION_KEY_ACTIVE_SET, default_active_target_set())
    if isinstance(value, int) and 1 <= value <= 4:
        return value
    return default_active_target_set()


def _set_options():
    return [item for item in available_target_sets() if item["value"] in {1, 2}]


def dashboard(request):
    """メインのダッシュボード画面を表示する。"""

    active_set = _current_active_set(request)

    if request.method == "POST":
        action = request.POST.get("action", "").strip()

        if action == "switch_set":
            raw = request.POST.get("active_set", "").strip()
            if raw.isdigit():
                new_set = int(raw)
                request.session[SESSION_KEY_ACTIVE_SET] = new_set
                sync_targets(active_set=new_set)
            return redirect("/")

        if action == "check_all":
            selected_target_id = request.POST.get("selected_target", "").strip()
            sync_targets(active_set=active_set)
            run_checks(active_set=active_set)
            return redirect(f"/?target={selected_target_id}" if selected_target_id else "/")

        target_id = request.POST.get("target", "").strip()
        sync_targets(active_set=active_set)
        target = get_object_or_404(
            MonitorTarget,
            target_id=target_id,
            target_set=active_set,
            enabled=True,
        )
        run_check_for_target(target)
        return redirect(f"/?target={target.target_id}")

    selected_target_id = request.GET.get("target", "").strip()
    targets = list(MonitorTarget.objects.filter(target_set=active_set, enabled=True))
    if not targets:
        sync_targets(active_set=active_set)
        targets = list(MonitorTarget.objects.filter(target_set=active_set, enabled=True))

    if selected_target_id:
        selected_target = get_object_or_404(
            MonitorTarget,
            target_id=selected_target_id,
            target_set=active_set,
            enabled=True,
        )
    else:
        selected_target = targets[0] if targets else None

    summaries = []
    for target in targets:
        latest_run = target.runs.order_by("-checked_at", "-id").first()
        summaries.append({"target": target, "latest_run": latest_run})

    recent_runs = []
    selected_run = None
    display_items_run = None
    graph_runs = []
    new_items = []
    if selected_target is not None:
        recent_runs = list(selected_target.runs.order_by("-checked_at", "-id")[:3])
        graph_runs = list(selected_target.runs.order_by("-checked_at", "-id")[:100])
        selected_run = recent_runs[0] if recent_runs else None
        display_items_run = (
            selected_target.runs.filter(new_items_count__gt=0).order_by("-checked_at", "-id").first()
        )
        if display_items_run is None:
            display_items_run = selected_run
        new_items = list(display_items_run.new_items.all()) if display_items_run else []

    graph_points = [
        {
            "checked_at": run.checked_at.strftime("%Y-%m-%d %H:%M:%S"),
            "total_items": run.total_items,
        }
        for run in reversed(graph_runs)
    ]

    context = {
        "summaries": summaries,
        "selected_target": selected_target,
        "selected_run": selected_run,
        "display_items_run": display_items_run,
        "recent_runs": recent_runs,
        "graph_runs": graph_points,
        "new_items": new_items,
        "latest_overall_run": CheckRun.objects.filter(target__target_set=active_set).order_by("-checked_at", "-id").first(),
        "active_target_set": active_set,
        "target_sets": _set_options(),
    }
    return render(request, "monitor/dashboard.html", context)


def latest_runs_api(request):
    """各ターゲットの最新結果だけを JSON で返す。"""

    active_set = _current_active_set(request)
    sync_targets(active_set=active_set)

    payload = []
    for target in MonitorTarget.objects.filter(target_set=active_set, enabled=True):
        latest_run = target.runs.order_by("-checked_at", "-id").first()
        payload.append(
            {
                "target_id": target.target_id,
                "name": target.name,
                "latest_run": None
                if latest_run is None
                else {
                    "checked_at": latest_run.checked_at.isoformat(),
                    "total_items": latest_run.total_items,
                    "new_items_count": latest_run.new_items_count,
                    "warning": latest_run.warning,
                },
            }
        )
    return JsonResponse({"targets": payload, "active_set": active_set})
