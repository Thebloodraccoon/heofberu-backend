from app.core.handlers import ALL_HANDLERS


def setup_error_handlers(app):
    """
    Register all custom exception handlers on the FastAPI application.

    Handlers themselves live in ``app.core.handlers`` (one module per
    concern: HTTP exceptions, validation, base/data-layer exceptions,
    database errors, and a final catch-all). Adding a new handler means
    editing that package, not this file — see
    ``app.core.handlers.__init__`` for the registration order rules.
    """

    for exception_cls, handler in ALL_HANDLERS:
        app.add_exception_handler(exception_cls, handler)
