import json
import logging
import time
from uuid import uuid4


logger = logging.getLogger("app.http")


class RequestLog:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = uuid4().hex
        started = time.monotonic()
        status = 500

        async def log_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message.setdefault("headers", []).append((b"x-request-id", request_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, log_send)
        finally:
            path = scope.get("path", "")
            if path not in ("/api/v1/health", "/api/v1/ready"):
                logger.info(json.dumps({
                    "event": "http_request", "request_id": request_id,
                    "method": scope.get("method"), "route": path.split("/")[3:5],
                    "status": status, "duration_ms": round((time.monotonic() - started) * 1000, 1),
                }))


def configure_error_tracking(settings):
    dsn = settings.sentry_dsn.get_secret_value()
    if not dsn:
        return
    import sentry_sdk

    def sanitize(event, hint):
        request = event.get("request")
        if request:
            for key in ("headers", "cookies", "data", "query_string", "url"):
                request.pop(key, None)
        return event

    sentry_sdk.init(
        dsn=dsn, environment=settings.app_env, send_default_pii=False,
        max_request_body_size="never", include_local_variables=False,
        traces_sample_rate=0.0,
        before_send=sanitize,
    )
