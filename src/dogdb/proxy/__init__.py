"""DB-API proxy surface."""

from dogdb.proxy.connection import DBAPIProxy, connect, wrap

__all__ = ["DBAPIProxy", "connect", "wrap"]
