# app/middleware/

The request middleware chain and global exception-handler registration,
assembled by `app/main.py.setup_middleware` / `setup_error_handlers`.

## Layout

- `config.py` — `MiddlewareConfig`: per-stage config dicts (CORS, gzip,
  rate limit, timing/logging thresholds, trusted hosts) and
  `should_enable_middleware()` gating which pieces run per stage.
- `request_id.py` — tags every request/response with `X-Request-ID`
  (honors an incoming header).
- `timing.py` — sets `X-Process-Time` and logs slow requests.
- `logging.py` — request/response logging with skip paths (off in prod).
- `rate_limit.py` — Redis-backed fixed-window per-IP limiting; degrades
  to a bounded in-memory counter when Redis is unavailable.
- `error_handler.py` — thin registrar looping over `app.core.handlers.ALL_HANDLERS`;
  handler implementations live in `app/core/handlers/`.
- `utils.py` — shared helpers (`get_client_ip` honoring proxy headers).

## Conventions

- **Middleware ordering and enablement logic are load-bearing** — do not
  reorder registrations in `main.py` or change dispatch logic here.
- New middlewares are added as their own module, exported from
  `__init__.py`, and gated through `MiddlewareConfig`.
