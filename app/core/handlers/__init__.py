from app.core.handlers import app_error, database, http, unhandled, validation

ALL_HANDLERS = [
    *app_error.HANDLERS,
    *http.HANDLERS,
    *validation.HANDLERS,
    *database.HANDLERS,
    *unhandled.HANDLERS,  # must stay last: Exception is the catch-all
]
