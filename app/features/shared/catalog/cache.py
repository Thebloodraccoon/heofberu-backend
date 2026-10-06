"""Post-commit cache purge shared by the race and subrace services."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import ServiceMixin
from app.core.base.transaction import after_commit
from app.core.cache import invalidate_many


async def purge_after_commit(db: AsyncSession, *namespaces: str) -> None:
    """Purge ``namespaces`` in one Redis round trip once ``db``'s transaction has committed."""

    names = list(namespaces)
    await after_commit(db, lambda: invalidate_many(names))


class CatalogCacheMixin(ServiceMixin):
    """``BaseService`` mixin: write-path purges go through :func:`purge_after_commit`."""

    cache_namespaces: tuple[str, ...]

    async def _invalidate_cache(self) -> None:
        """Purge ``cache_namespaces`` after commit, in one connection."""

        await purge_after_commit(self.repository.db, *self.cache_namespaces)
