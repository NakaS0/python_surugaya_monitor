import argparse
import json
import os
import webbrowser

from dashboard import serve_dashboard
from fixed_targets import FIXED_TARGETS
from scraper import (
    DEFAULT_BASE_URL,
    bootstrap_login_session,
    check_new_items,
    latest_report_file,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Suruga-ya update monitor with login/adult-content session support."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "init-session",
        help="Open Chrome, login manually, enable adult content visibility, and save cookies.",
    )

    check_parser = subparsers.add_parser("check", help="Run one update check.")
    check_parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Maximum number of result pages to scan. Omit for no limit.",
    )

    watch_parser = subparsers.add_parser("watch", help="Run update check in a loop.")
    watch_parser.description = "Run one full-page monitoring pass, then open dashboard."
    watch_parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Maximum number of result pages to scan. Omit for no limit.",
    )
    watch_parser.add_argument("--ui-host", default="127.0.0.1")
    watch_parser.add_argument("--ui-port", type=int, default=8080)
    watch_parser.add_argument(
        "--no-open-browser",
        action="store_true",
        help="Do not auto-open browser when watch ends.",
    )

    subparsers.add_parser(
        "show-last",
        help="Show the latest check result for the target.",
    )
    show_last_parser = subparsers.choices["show-last"]
    show_last_parser.add_argument("--target", default="default")

    ui_parser = subparsers.add_parser(
        "serve-ui",
        help="Serve a local dashboard for check results.",
    )
    ui_parser.add_argument("--host", default="127.0.0.1")
    ui_parser.add_argument("--port", type=int, default=8080)

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.command == "init-session":
        bootstrap_login_session(open_url=DEFAULT_BASE_URL)
        return

    if args.command == "check":
        for target in FIXED_TARGETS:
            print(f"\n=== Target: {target['name']} ({target['id']}) ===")
            check_new_items(
                max_pages=args.max_pages,
                base_url=target["url"],
                target_id=target["id"],
            )
        return

    if args.command == "watch":
        for target in FIXED_TARGETS:
            print(f"\n=== Target: {target['name']} ({target['id']}) ===")
            check_new_items(
                max_pages=args.max_pages,
                base_url=target["url"],
                target_id=target["id"],
            )
        ui_url = f"http://{args.ui_host}:{args.ui_port}"
        print("\nMonitoring finished (reached last page). Starting dashboard...")
        if not args.no_open_browser:
            webbrowser.open(ui_url)
        serve_dashboard(host=args.ui_host, port=args.ui_port)
        return

    if args.command == "show-last":
        report_file = latest_report_file(args.target)
        if not os.path.exists(report_file):
            print(f"No report file found: {report_file}")
            return

        with open(report_file, "r", encoding="utf-8") as f:
            report = json.load(f)

        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    if args.command == "serve-ui":
        serve_dashboard(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
