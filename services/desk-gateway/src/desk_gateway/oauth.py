"""OAuth AS for Grok Bot with one passphrase per seat: PKCE + DCR + a consent step.

The passphrase entered on the consent page decides the seat. The minted token carries
`seat:<short>` next to `mcp`, and the gateway refuses that token on any other seat's endpoint.
A seat passphrase is also accepted directly as `x-connector-key` for smoke tests.
"""

from __future__ import annotations

import json
import logging
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.shared.auth import InvalidRedirectUriError, OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl

from desk_gateway.config import SEATS, Settings

logger = logging.getLogger("desk_gateway.oauth")

STATIC_CLIENT_IDS = ("grok", "grok-bot", "desk")
PENDING_TTL_SEC = 600
MAX_CONSENT_ATTEMPTS = 5
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
VALID_SCOPES = ["mcp", *(f"seat:{s}" for s in SEATS)]


class ConsentError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def seat_of(token: AccessToken | None) -> str | None:
    if token is None:
        return None
    for scope in token.scopes:
        if scope.startswith("seat:"):
            seat = scope[5:]
            if seat in SEATS:
                return seat
    return None


def redirect_allowed(uri: str) -> bool:
    parsed = urlparse(uri)
    if parsed.scheme == "https" and parsed.hostname:
        return True
    return parsed.scheme == "http" and (parsed.hostname or "") in LOOPBACK_HOSTS


class StaticClient(OAuthClientInformationFull):
    def validate_redirect_uri(self, redirect_uri: AnyUrl | None) -> AnyUrl:
        if redirect_uri is None:
            raise InvalidRedirectUriError("redirect_uri is required for this client")
        if not redirect_allowed(str(redirect_uri)):
            raise InvalidRedirectUriError("redirect_uri must be https or a loopback address")
        return redirect_uri


@dataclass
class PendingAuthorization:
    request_id: str
    client_id: str
    client_name: str
    params: AuthorizationParams
    created_at: float
    attempts: int = 0

    @property
    def redirect_host(self) -> str:
        return urlparse(str(self.params.redirect_uri)).netloc

    def expired(self) -> bool:
        return time.time() - self.created_at > PENDING_TTL_SEC


class SeatOAuthProvider:
    def __init__(
        self,
        settings: Settings,
        *,
        store_dir: Path,
        token_ttl_sec: int = 86_400,
        refresh_ttl_sec: int = 2_592_000,
    ) -> None:
        self.settings = settings
        self.issuer = settings.issuer_url.rstrip("/")
        self.resource = settings.resource_url.rstrip("/")
        self.token_ttl_sec = token_ttl_sec
        self.refresh_ttl_sec = refresh_ttl_sec
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._codes: dict[str, AuthorizationCode] = {}
        self._access: dict[str, AccessToken] = {}
        self._refresh: dict[str, RefreshToken] = {}
        self._pending: dict[str, PendingAuthorization] = {}
        self._load()

    def _path(self) -> Path:
        return self.store_dir / "oauth-state.json"

    def _load(self) -> None:
        path = self._path()
        if not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        now = time.time()
        for cid, c in (raw.get("clients") or {}).items():
            try:
                self._clients[cid] = OAuthClientInformationFull.model_validate(c)
            except ValueError:
                continue
        for tok, a in (raw.get("access") or {}).items():
            try:
                at = AccessToken.model_validate(a)
                if at.expires_at is None or at.expires_at > now:
                    self._access[tok] = at
            except ValueError:
                continue
        for tok, r in (raw.get("refresh") or {}).items():
            try:
                rt = RefreshToken.model_validate(r)
                if rt.expires_at is None or rt.expires_at > now:
                    self._refresh[tok] = rt
            except ValueError:
                continue

    def _save(self) -> None:
        payload = {
            "clients": {k: v.model_dump(mode="json") for k, v in self._clients.items()},
            "access": {k: v.model_dump(mode="json") for k, v in self._access.items()},
            "refresh": {k: v.model_dump(mode="json") for k, v in self._refresh.items()},
        }
        tmp = self._path().with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(self._path())

    def _static_client(self, client_id: str) -> StaticClient:
        return StaticClient(
            client_id=client_id,
            client_secret=None,
            client_name="Grok Bot (static client)",
            redirect_uris=[AnyUrl("https://localhost/callback")],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            token_endpoint_auth_method="none",
            scope=" ".join(VALID_SCOPES),
        )

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        if client_id in STATIC_CLIENT_IDS:
            return self._static_client(client_id)
        with self._lock:
            return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.client_id or client_info.client_id in STATIC_CLIENT_IDS:
            raise ValueError("invalid client_id")
        with self._lock:
            client_info.scope = " ".join(VALID_SCOPES)
            self._clients[client_info.client_id] = client_info
            self._save()

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        if not params.code_challenge:
            raise AuthorizeError(error="invalid_request", error_description="code_challenge required")
        request_id = secrets.token_urlsafe(24)
        pending = PendingAuthorization(
            request_id=request_id,
            client_id=client.client_id or "unknown",
            client_name=client.client_name or client.client_id or "MCP client",
            params=params,
            created_at=time.time(),
        )
        with self._lock:
            self._pending = {k: v for k, v in self._pending.items() if not v.expired()}
            self._pending[request_id] = pending
        return f"{self.issuer}/oauth/consent?request={request_id}"

    def pending(self, request_id: str) -> PendingAuthorization | None:
        with self._lock:
            item = self._pending.get(request_id)
            if item is None:
                return None
            if item.expired():
                self._pending.pop(request_id, None)
                return None
            return item

    def approve(self, request_id: str, passphrase: str) -> str:
        with self._lock:
            item = self._pending.get(request_id)
            if item is None or item.expired():
                self._pending.pop(request_id, None)
                raise ConsentError("expired")
            seat = self.settings.seat_for_passphrase(passphrase)
            if seat is None:
                item.attempts += 1
                if item.attempts >= MAX_CONSENT_ATTEMPTS:
                    self._pending.pop(request_id, None)
                    raise ConsentError("locked")
                raise ConsentError("bad_passphrase")
            self._pending.pop(request_id, None)
            params = item.params
            code = secrets.token_urlsafe(32)
            self._codes[code] = AuthorizationCode(
                code=code,
                client_id=item.client_id,
                scopes=["mcp", f"seat:{seat}"],
                expires_at=time.time() + 600,
                code_challenge=params.code_challenge,
                redirect_uri=params.redirect_uri,
                redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
                resource=params.resource or self.resource,
                subject=f"seat:{seat}",
            )
        logger.info("oauth consent approved for client=%s seat=%s", item.client_id, seat)
        return construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state)

    def deny(self, request_id: str) -> str | None:
        with self._lock:
            item = self._pending.pop(request_id, None)
        if item is None:
            return None
        return construct_redirect_uri(
            str(item.params.redirect_uri),
            error="access_denied",
            error_description="The operator denied the connection",
            state=item.params.state,
        )

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        with self._lock:
            code = self._codes.get(authorization_code)
            if not code or code.client_id != client.client_id:
                return None
            if code.expires_at < time.time():
                self._codes.pop(authorization_code, None)
                return None
            return code

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        with self._lock:
            stored = self._codes.pop(authorization_code.code, None)
            if not stored:
                raise AuthorizeError(error="invalid_request", error_description="code already used or unknown")
            return self._mint_tokens(client.client_id or stored.client_id, stored.scopes, stored.subject)

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        with self._lock:
            rt = self._refresh.get(refresh_token)
            if not rt or rt.client_id != client.client_id:
                return None
            if rt.expires_at is not None and rt.expires_at < time.time():
                self._refresh.pop(refresh_token, None)
                return None
            return rt

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        with self._lock:
            self._refresh.pop(refresh_token.token, None)
            granted = refresh_token.scopes
            if scopes and not set(scopes) <= set(granted):
                raise AuthorizeError(error="invalid_scope", error_description="scope escalation refused")
            return self._mint_tokens(client.client_id or refresh_token.client_id, granted, refresh_token.subject)

    async def load_access_token(self, token: str) -> AccessToken | None:
        seat = self.settings.seat_for_passphrase(token)
        if seat is not None:
            return AccessToken(
                token=token,
                client_id=f"connector-key:{seat}",
                scopes=["mcp", f"seat:{seat}"],
                expires_at=None,
                resource=self.resource,
                subject=f"seat:{seat}",
            )
        with self._lock:
            at = self._access.get(token)
            if not at:
                return None
            if at.expires_at is not None and at.expires_at < time.time():
                self._access.pop(token, None)
                self._save()
                return None
            return at

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        with self._lock:
            if isinstance(token, AccessToken):
                self._access.pop(token.token, None)
            else:
                self._refresh.pop(token.token, None)
            self._save()

    def _mint_tokens(self, client_id: str, scopes: list[str], subject: str | None) -> OAuthToken:
        now = int(time.time())
        access = secrets.token_urlsafe(32)
        refresh = secrets.token_urlsafe(32)
        self._access[access] = AccessToken(
            token=access,
            client_id=client_id,
            scopes=scopes,
            expires_at=now + self.token_ttl_sec,
            resource=self.resource,
            subject=subject,
        )
        self._refresh[refresh] = RefreshToken(
            token=refresh,
            client_id=client_id,
            scopes=scopes,
            expires_at=now + self.refresh_ttl_sec,
            resource=self.resource,
            subject=subject,
        )
        self._save()
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=self.token_ttl_sec,
            scope=" ".join(scopes),
            refresh_token=refresh,
        )
