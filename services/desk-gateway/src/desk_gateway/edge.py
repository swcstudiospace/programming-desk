"""Edge ingress gateway proxying, latency-based geo-steering, failover rerouting, and distributed token-bucket rate limiting (REQ-EDGE-001, REQ-EDGE-002).

Coordinates multi-region VPS desk instances (e.g. us-east, eu-central, ap-southeast)
with dynamic latency probing, health-aware geo-steering, and atomic token-bucket traffic policing
synchronized via DragonflyDB/Redis with per-seat burst ceilings.
"""

from __future__ import annotations

import asyncio
import logging
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from desk_gateway.config import SEATS, Settings

logger = logging.getLogger("desk_gateway.edge")


class EdgeError(Exception):
    """Base exception for edge routing and rate limiting errors."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class RateLimitExceeded(EdgeError):
    """Raised when request rate or burst limit is exceeded."""

    def __init__(
        self,
        key: str,
        retry_after: float,
        limit: int,
        remaining: int,
        reset_epoch: float,
        reason: str = "Rate limit exceeded",
    ) -> None:
        super().__init__("rate_limit_exceeded", reason, 429)
        self.key = key
        self.retry_after = max(0.0, retry_after)
        self.limit = limit
        self.remaining = remaining
        self.reset_epoch = reset_epoch

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Retry-After": str(int(math.ceil(self.retry_after))),
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(int(math.ceil(self.reset_epoch))),
        }


@dataclass
class RegionEndpoint:
    region_id: str
    endpoint_url: str
    latitude: float
    longitude: float
    is_active: bool = True
    healthy: bool = True
    latency_ms: float = 0.0
    last_health_check: float = 0.0
    consecutive_failures: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "region_id": self.region_id,
            "endpoint_url": self.endpoint_url,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "is_active": self.is_active,
            "healthy": self.healthy,
            "latency_ms": round(self.latency_ms, 2),
            "last_health_check": self.last_health_check,
            "consecutive_failures": self.consecutive_failures,
            "metadata": self.metadata,
        }


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points on the Earth in kilometers."""
    r = 6371.0  # Earth's radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


class GeoSteeringRouter:
    """Evaluates multi-region VPS endpoints using measured latencies or geodesic proximity.

    Directs client requests to the lowest-latency healthy regional desk instance
    and automatically shifts traffic upon regional failures (REQ-EDGE-001).
    """

    def __init__(
        self,
        default_region: str = "us-east",
        latency_threshold_ms: float = 400.0,
        failure_threshold: int = 3,
    ) -> None:
        self.default_region = default_region
        self.latency_threshold_ms = latency_threshold_ms
        self.failure_threshold = failure_threshold
        self._regions: dict[str, RegionEndpoint] = {}
        self._lock = threading.Lock()

    def register_region(
        self,
        region_id: str,
        endpoint_url: str,
        latitude: float,
        longitude: float,
        latency_ms: float = 10.0,
        healthy: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> RegionEndpoint:
        with self._lock:
            ep = RegionEndpoint(
                region_id=region_id,
                endpoint_url=endpoint_url.rstrip("/"),
                latitude=latitude,
                longitude=longitude,
                healthy=healthy,
                latency_ms=latency_ms,
                last_health_check=time.time(),
                metadata=metadata or {},
            )
            self._regions[region_id] = ep
            return ep

    def get_region(self, region_id: str) -> RegionEndpoint | None:
        with self._lock:
            return self._regions.get(region_id)

    def list_regions(self) -> list[dict[str, Any]]:
        with self._lock:
            return [ep.to_dict() for ep in self._regions.values()]

    def update_health(
        self,
        region_id: str,
        healthy: bool,
        latency_ms: float | None = None,
        force: bool = False,
    ) -> RegionEndpoint:
        with self._lock:
            if region_id not in self._regions:
                raise EdgeError("region_not_found", f"Region '{region_id}' not registered", 404)
            ep = self._regions[region_id]
            ep.last_health_check = time.time()
            if latency_ms is not None:
                ep.latency_ms = max(0.0, latency_ms)

            if healthy:
                ep.consecutive_failures = 0
                # If latency breaches threshold, flag as degraded / unhealthy for routing
                if ep.latency_ms > self.latency_threshold_ms:
                    ep.healthy = False
                    logger.warning(
                        "Region %s marked unhealthy due to latency %0.2fms > %0.2fms",
                        region_id,
                        ep.latency_ms,
                        self.latency_threshold_ms,
                    )
                else:
                    ep.healthy = True
            else:
                ep.consecutive_failures += 1
                if force or ep.consecutive_failures >= self.failure_threshold:
                    ep.healthy = False
            return ep

    def select_best_region(
        self,
        client_lat: float | None = None,
        client_lon: float | None = None,
        preferred_region: str | None = None,
        observed_latencies: dict[str, float] | None = None,
    ) -> tuple[RegionEndpoint, str]:
        """Selects the best healthy region endpoint.

        Returns (RegionEndpoint, selection_reason).
        Priority:
        1. Explicit preferred_region (if healthy).
        2. Client-provided observed_latencies (lowest latency among healthy regions).
        3. Server-measured latency_ms (lowest latency among healthy regions).
        4. Geodesic closest region (if client_lat/lon provided).
        5. Default region or any available active region.
        """
        with self._lock:
            healthy_regions = [r for r in self._regions.values() if r.is_active and r.healthy]

            # If no regions healthy, fall back to any active region or raise
            if not healthy_regions:
                active_regions = [r for r in self._regions.values() if r.is_active]
                if not active_regions:
                    raise EdgeError("no_active_regions", "No active region endpoints available", 503)
                logger.warning("All healthy regions exhausted; falling back to degraded active region")
                return active_regions[0], "emergency_fallback_all_degraded"

            # 1. Preferred region check
            if preferred_region:
                for r in healthy_regions:
                    if r.region_id == preferred_region:
                        return r, "preferred_match"

            # 2. Client observed latencies
            if observed_latencies:
                candidate = None
                best_obs = float("inf")
                for r in healthy_regions:
                    obs = observed_latencies.get(r.region_id)
                    if obs is not None and obs < best_obs:
                        best_obs = obs
                        candidate = r
                if candidate:
                    return candidate, f"client_observed_latency ({best_obs:.1f}ms)"

            # 3. Geodesic distance steering if coordinates given
            if client_lat is not None and client_lon is not None:
                candidate = min(
                    healthy_regions,
                    key=lambda r: haversine_distance_km(client_lat, client_lon, r.latitude, r.longitude),
                )
                dist = haversine_distance_km(client_lat, client_lon, candidate.latitude, candidate.longitude)
                return candidate, f"geo_proximity ({dist:.1f}km)"

            # 4. Server-measured lowest latency
            lowest_latency = min(healthy_regions, key=lambda r: r.latency_ms)
            return lowest_latency, f"server_latency ({lowest_latency.latency_ms:.1f}ms)"


class TokenBucketPolicer:
    """In-memory atomic token-bucket rate limiter with burst capability.

    Employs leaky/token bucket algorithm:
    - capacity: maximum burst allowed (e.g. 120 tokens)
    - fill_rate: tokens replenished per second (e.g. 60/60 = 1.0 token/sec)
    """

    def __init__(self, capacity: int, fill_rate_per_sec: float) -> None:
        self.capacity = max(1, capacity)
        self.fill_rate = max(0.001, fill_rate_per_sec)
        self.tokens = float(self.capacity)
        self.last_update = time.time()
        self._lock = threading.Lock()

    def consume(self, amount: int = 1) -> tuple[bool, float, int, float]:
        """Attempts to consume `amount` tokens.

        Returns (allowed, retry_after_sec, remaining_tokens, reset_epoch).
        """
        with self._lock:
            now = time.time()
            delta = max(0.0, now - self.last_update)
            self.last_update = now
            # Replenish tokens up to capacity
            self.tokens = min(float(self.capacity), self.tokens + delta * self.fill_rate)

            reset_epoch = now + max(0.0, (self.capacity - self.tokens) / self.fill_rate)

            if self.tokens >= amount:
                self.tokens -= amount
                remaining = int(math.floor(self.tokens))
                return True, 0.0, remaining, reset_epoch

            # Insufficient tokens
            needed = amount - self.tokens
            retry_after = needed / self.fill_rate
            remaining = int(math.floor(self.tokens))
            return False, retry_after, remaining, reset_epoch


@dataclass
class RateLimitConfig:
    rate_per_min: int = 60
    burst_capacity: int = 120


class DistributedRateLimiter:
    """Distributed rate limiter synchronized via DragonflyDB/Redis with per-seat burst ceilings (REQ-EDGE-002).

    Falls back smoothly to local in-memory token buckets if DragonflyDB is offline or unconfigured.
    """

    def __init__(
        self,
        dragonfly_service: Any = None,
        default_rate_per_min: int = 60,
        default_burst: int = 120,
    ) -> None:
        self.dragonfly = dragonfly_service
        self.default_rate_per_min = default_rate_per_min
        self.default_burst = default_burst
        self._seat_configs: dict[str, RateLimitConfig] = {}
        self._local_buckets: dict[str, TokenBucketPolicer] = {}
        self._lock = threading.Lock()

        # Default per-seat rate ceilings
        self.configure_seat("lead", rate_per_min=120, burst_capacity=240)
        self.configure_seat("systems", rate_per_min=120, burst_capacity=240)
        self.configure_seat("infra", rate_per_min=120, burst_capacity=240)
        self.configure_seat("web", rate_per_min=60, burst_capacity=120)
        self.configure_seat("android", rate_per_min=60, burst_capacity=120)
        self.configure_seat("ios", rate_per_min=60, burst_capacity=120)
        self.configure_seat("quality", rate_per_min=60, burst_capacity=120)

    def configure_seat(self, seat: str, rate_per_min: int, burst_capacity: int) -> None:
        with self._lock:
            self._seat_configs[seat] = RateLimitConfig(
                rate_per_min=rate_per_min,
                burst_capacity=burst_capacity,
            )
            # Recreate local policer if present
            self._local_buckets[seat] = TokenBucketPolicer(
                capacity=burst_capacity,
                fill_rate_per_sec=rate_per_min / 60.0,
            )

    def get_config(self, key: str) -> RateLimitConfig:
        with self._lock:
            if key in self._seat_configs:
                return self._seat_configs[key]
            return RateLimitConfig(rate_per_min=self.default_rate_per_min, burst_capacity=self.default_burst)

    def _get_local_bucket(self, key: str) -> TokenBucketPolicer:
        with self._lock:
            if key not in self._local_buckets:
                cfg = self.get_config(key)
                self._local_buckets[key] = TokenBucketPolicer(
                    capacity=cfg.burst_capacity,
                    fill_rate_per_sec=cfg.rate_per_min / 60.0,
                )
            return self._local_buckets[key]

    async def check_rate_limit(self, key: str, amount: int = 1) -> tuple[bool, float, int, float]:
        """Checks rate limit for `key` (seat or origin identifier).

        Attempts DragonflyDB atomic token update if available; falls back to in-memory policer.
        Returns: (allowed: bool, retry_after_sec: float, remaining: int, reset_epoch: float).
        """
        cfg = self.get_config(key)
        capacity = cfg.burst_capacity
        fill_rate = cfg.rate_per_min / 60.0

        if self.dragonfly and getattr(self.dragonfly, "configured", False):
            try:
                allowed, retry_after, remaining, reset_epoch = await self._check_dragonfly(
                    key=key,
                    capacity=capacity,
                    fill_rate=fill_rate,
                    amount=amount,
                )
                return allowed, retry_after, remaining, reset_epoch
            except Exception as exc:
                logger.warning("Dragonfly rate limiting failed (%s); falling back to local bucket", exc)

        # In-memory policer fallback
        policer = self._get_local_bucket(key)
        return policer.consume(amount=amount)

    async def _check_dragonfly(
        self,
        key: str,
        capacity: int,
        fill_rate: float,
        amount: int,
    ) -> tuple[bool, float, int, float]:
        """DragonflyDB token bucket lua/eval implementation or simulated atomic step."""
        now = time.time()
        redis_key = f"desk:ratelimit:tokenbucket:{key}"

        import redis.asyncio as redis

        client = redis.from_url(
            self.dragonfly.url,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
            decode_responses=True,
        )
        try:
            # Lua script to atomically refill and deduct token bucket
            lua_script = """
            local key = KEYS[1]
            local capacity = tonumber(ARGV[1])
            local fill_rate = tonumber(ARGV[2])
            local amount = tonumber(ARGV[3])
            local now = tonumber(ARGV[4])

            local data = redis.call('HMGET', key, 'tokens', 'last_update')
            local tokens = tonumber(data[1])
            local last_update = tonumber(data[2])

            if not tokens or not last_update then
                tokens = capacity
                last_update = now
            else
                local delta = math.max(0, now - last_update)
                tokens = math.min(capacity, tokens + delta * fill_rate)
                last_update = now
            end

            local allowed = 0
            local retry_after = 0
            if tokens >= amount then
                tokens = tokens - amount
                allowed = 1
            else
                retry_after = (amount - tokens) / fill_rate
            end

            redis.call('HMSET', key, 'tokens', tokens, 'last_update', last_update)
            redis.call('EXPIRE', key, math.ceil(capacity / fill_rate) + 60)

            return {allowed, tostring(retry_after), tostring(tokens)}
            """
            result = await client.eval(
                lua_script,
                1,
                redis_key,
                str(capacity),
                str(fill_rate),
                str(amount),
                str(now),
            )
            allowed = bool(result[0])
            retry_after = float(result[1])
            remaining = int(math.floor(float(result[2])))
            reset_epoch = now + (retry_after if not allowed else max(0.0, (capacity - remaining) / fill_rate))
            return allowed, retry_after, remaining, reset_epoch
        finally:
            await client.aclose()


class EdgeIngressGateway:
    """Coordinates edge ingress proxying, geo-steering routing, and distributed rate limiting (REQ-EDGE-001, REQ-EDGE-002)."""

    def __init__(
        self,
        settings: Settings,
        dragonfly_service: Any = None,
    ) -> None:
        self.settings = settings
        self.router = GeoSteeringRouter(
            default_region=settings.edge_default_region if hasattr(settings, "edge_default_region") else "us-east",
            latency_threshold_ms=settings.edge_latency_threshold_ms if hasattr(settings, "edge_latency_threshold_ms") else 400.0,
        )
        self.limiter = DistributedRateLimiter(
            dragonfly_service=dragonfly_service,
            default_rate_per_min=settings.edge_rate_limit_per_minute if hasattr(settings, "edge_rate_limit_per_minute") else 60,
            default_burst=settings.edge_burst_capacity if hasattr(settings, "edge_burst_capacity") else 120,
        )
        self._init_default_regions()

    def _init_default_regions(self) -> None:
        """Seed known multi-region VPS gateway regions."""
        self.router.register_region(
            region_id="us-east",
            endpoint_url=f"https://us-east.{self.settings.public_host}",
            latitude=38.9072,
            longitude=-77.0369,
            latency_ms=15.0,
            healthy=True,
            metadata={"datacenter": "vps-ashburn", "tier": "primary"},
        )
        self.router.register_region(
            region_id="eu-central",
            endpoint_url=f"https://eu-central.{self.settings.public_host}",
            latitude=50.1109,
            longitude=8.6821,
            latency_ms=90.0,
            healthy=True,
            metadata={"datacenter": "vps-frankfurt", "tier": "secondary"},
        )
        self.router.register_region(
            region_id="ap-southeast",
            endpoint_url=f"https://ap-southeast.{self.settings.public_host}",
            latitude=1.3521,
            longitude=103.8198,
            latency_ms=180.0,
            healthy=True,
            metadata={"datacenter": "vps-singapore", "tier": "secondary"},
        )

    async def enforce_rate_limit(self, key: str, amount: int = 1) -> dict[str, str]:
        """Enforces rate limiting on key.

        Returns HTTP response headers if allowed; raises RateLimitExceeded if throttled.
        """
        allowed, retry_after, remaining, reset_epoch = await self.limiter.check_rate_limit(key, amount=amount)
        cfg = self.limiter.get_config(key)
        headers = {
            "Retry-After": str(int(math.ceil(retry_after))) if not allowed else "0",
            "X-RateLimit-Limit": str(cfg.burst_capacity),
            "X-RateLimit-Remaining": str(max(0, remaining)),
            "X-RateLimit-Reset": str(int(math.ceil(reset_epoch))),
        }
        if not allowed:
            raise RateLimitExceeded(
                key=key,
                retry_after=retry_after,
                limit=cfg.burst_capacity,
                remaining=remaining,
                reset_epoch=reset_epoch,
                reason=f"Rate limit exceeded for key '{key}'. Burst capacity: {cfg.burst_capacity}",
            )
        return headers

    def route_request(
        self,
        client_lat: float | None = None,
        client_lon: float | None = None,
        preferred_region: str | None = None,
        observed_latencies: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Resolves target regional desk instance based on geo-steering and health status."""
        region, reason = self.router.select_best_region(
            client_lat=client_lat,
            client_lon=client_lon,
            preferred_region=preferred_region,
            observed_latencies=observed_latencies,
        )
        return {
            "selected_region": region.region_id,
            "endpoint_url": region.endpoint_url,
            "latency_ms": region.latency_ms,
            "reason": reason,
            "region": region.to_dict(),
        }
