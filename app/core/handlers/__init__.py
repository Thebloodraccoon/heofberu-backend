from app.core.handlers import app_error, data_layer, database, http, unhandled, validation

ALL_HANDLERS = [
    *app_error.HANDLERS,
    *http.HANDLERS,
    *validation.HANDLERS,
    *data_layer.HANDLERS,
    *database.HANDLERS,
    *unhandled.HANDLERS,  # must stay last: Exception is the catch-all
]
