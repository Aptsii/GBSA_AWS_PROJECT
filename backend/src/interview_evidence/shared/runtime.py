from __future__ import annotations

from contextvars import ContextVar
from typing import Any, cast

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class _SessionProxy:
    __slots__ = ("_registry",)

    def __init__(self, registry: RequestSessionRegistry) -> None:
        self._registry = registry

    def __getattr__(self, name: str) -> Any:
        return getattr(self._registry.current(), name)


class RequestSessionRegistry:
    __slots__ = ("_current", "_factory", "_proxy")

    def __init__(self, engine: Engine) -> None:
        self._factory = sessionmaker(engine, expire_on_commit=False)
        self._current: ContextVar[Session | None] = ContextVar(
            "interview_evidence_request_session",
            default=None,
        )
        self._proxy = cast(Session, _SessionProxy(self))

    @property
    def proxy(self) -> Session:
        return self._proxy

    def current(self) -> Session:
        session = self._current.get()
        if session is None:
            raise RuntimeError("database access requires an active request transaction")
        return session

    def open(self) -> tuple[Session, object]:
        session = self._factory()
        return session, self._current.set(session)

    def close(self, session: Session, token: object, *, commit: bool) -> None:
        try:
            if commit:
                session.commit()
            else:
                session.rollback()
        finally:
            session.close()
            self._current.reset(token)  # type: ignore[arg-type]


class DatabaseTransactionMiddleware:
    __slots__ = ("app", "registry")

    def __init__(self, app: ASGIApp, registry: RequestSessionRegistry) -> None:
        self.app = app
        self.registry = registry

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        session, token = self.registry.open()
        response_status = 500

        async def observe(message: Message) -> None:
            nonlocal response_status
            if message["type"] == "http.response.start":
                response_status = int(message["status"])
            elif message["type"] == "websocket.accept":
                response_status = 101
            elif message["type"] == "websocket.close" and response_status == 500:
                response_status = 400
            await send(message)

        try:
            await self.app(scope, receive, observe)
        except Exception:
            self.registry.close(session, token, commit=False)
            raise
        else:
            self.registry.close(session, token, commit=response_status < 400)
