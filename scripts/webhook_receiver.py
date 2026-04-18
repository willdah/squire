#!/usr/bin/env python3
"""Minimal HTTP server to receive Squire notification webhooks for integration testing.

Squire posts JSON to each configured webhook URL (see ``WebhookDispatcher``). Run this
script, then point ``squire.toml`` at it:

- Native Squire on the same machine: ``url = "http://127.0.0.1:<port>/webhook"``
- Squire in Docker (receiver on the host): ``url = "http://host.docker.internal:<port>/webhook"``

Enable notifications (``[notifications] enabled = true``) and add a ``[[notifications.webhooks]]``
entry with matching ``url`` and optional ``events`` / ``headers``.

Example: ``uv run python scripts/webhook_receiver.py`` or ``make webhook-receiver``.
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import urlparse


class WebhookHTTPServer(HTTPServer):
    """HTTPServer with webhook path and logging flags."""

    webhook_path: str
    quiet: bool
    verbose_json: bool
    verbose_http: bool

    def __init__(
        self,
        server_address: tuple[str, int],
        RequestHandlerClass: type[BaseHTTPRequestHandler],
        *,
        webhook_path: str,
        quiet: bool,
        verbose_json: bool,
        verbose_http: bool,
    ) -> None:
        self.webhook_path = webhook_path
        self.quiet = quiet
        self.verbose_json = verbose_json
        self.verbose_http = verbose_http
        super().__init__(server_address, RequestHandlerClass)


class WebhookReceiverHandler(BaseHTTPRequestHandler):
    server: WebhookHTTPServer

    def log_message(self, format: str, *args: Any) -> None:
        if self.server.verbose_http:
            super().log_message(format, *args)

    def _send_json(self, code: int, obj: dict[str, Any]) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _path(self) -> str:
        return urlparse(self.path).path

    def do_GET(self) -> None:
        p = self._path()
        if p in ("/", self.server.webhook_path):
            self._send_json(
                200,
                {
                    "status": "ok",
                    "post_json_to": self.server.webhook_path,
                },
            )
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self._path() != self.server.webhook_path:
            self._send_json(404, {"error": "not found"})
            return

        raw_len = self.headers.get("Content-Length")
        try:
            length = int(raw_len) if raw_len is not None else 0
        except ValueError:
            self._send_json(400, {"ok": False, "error": "invalid Content-Length"})
            return

        raw = self.rfile.read(length) if length > 0 else b""
        try:
            data: Any = json.loads(raw.decode() if raw else "{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            self._send_json(400, {"ok": False, "error": str(e)})
            return

        if not isinstance(data, dict):
            self._send_json(400, {"ok": False, "error": "JSON root must be an object"})
            return

        if not self.server.quiet:
            self._print_payload(data)

        self._send_json(200, {"ok": True})

    def _print_payload(self, data: dict[str, Any]) -> None:
        cat = data.get("category", "")
        summary = data.get("summary", "")
        line = f"[webhook] category={cat!r} summary={summary!r}"
        print(line, file=sys.stdout)
        if self.server.verbose_json:
            print(json.dumps(data, indent=2), file=sys.stdout)
            print(file=sys.stdout)


def normalize_path(path: str) -> str:
    p = path.strip()
    if not p.startswith("/"):
        p = "/" + p
    return p


def main() -> None:
    parser = argparse.ArgumentParser(description="Receive Squire notification webhooks (POST JSON).")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: all interfaces)")
    parser.add_argument("--port", type=int, default=9847, help="Listen port (default: 9847)")
    parser.add_argument(
        "--path",
        default="/webhook",
        help="URL path for POST webhooks (default: /webhook)",
    )
    parser.add_argument("--quiet", action="store_true", help="Do not print each payload to stdout")
    parser.add_argument("--verbose", action="store_true", help="After the summary line, print full JSON (indented)")
    parser.add_argument("--verbose-http", action="store_true", help="Log http.server request lines to stderr")
    args = parser.parse_args()

    webhook_path = normalize_path(args.path)
    server = WebhookHTTPServer(
        (args.host, args.port),
        WebhookReceiverHandler,
        webhook_path=webhook_path,
        quiet=args.quiet,
        verbose_json=args.verbose,
        verbose_http=args.verbose_http,
    )
    print(
        f"Listening on http://{args.host}:{args.port}{webhook_path} (GET / or {webhook_path} for health)",
        file=sys.stderr,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.", file=sys.stderr)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
