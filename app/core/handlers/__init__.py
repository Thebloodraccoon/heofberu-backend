from app.core.handlers import data_layer, database, http, unhandled, validation

ALL_HANDLERS = [
    *http.HANDLERS,
    *validation.HANDLERS,
    *data_layer.HANDLERS,
    *database.HANDLERS,
    *unhandled.HANDLERS,  # must stay last: Exception is the catch-all
]
