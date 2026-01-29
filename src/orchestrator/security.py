"""Security utilities: URL validation and API key middleware."""

import ipaddress
import logging
import re
from typing import Callable
from urllib.parse import urlparse

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


# --- T-037: URL Validation ---


class UrlValidationError(Exception):
    """Raised when URL validation fails."""

    pass


class UrlValidator:
    """
    Validates and sanitizes URLs before HTTP requests.

    Provides SSRF protection by blocking private/internal IPs,
    localhost, and invalid schemes.
    """

    # Private IP ranges (RFC 1918 + RFC 5737 + link-local)
    PRIVATE_RANGES = [
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("127.0.0.0/8"),  # Loopback
        ipaddress.ip_network("169.254.0.0/16"),  # Link-local
        ipaddress.ip_network("0.0.0.0/8"),  # "This" network
        ipaddress.ip_network("224.0.0.0/4"),  # Multicast
        ipaddress.ip_network("255.255.255.255/32"),  # Broadcast
        # IPv6 private ranges
        ipaddress.ip_network("::1/128"),  # Loopback
        ipaddress.ip_network("fc00::/7"),  # Unique local
        ipaddress.ip_network("fe80::/10"),  # Link-local
    ]

    # Blocked hostnames
    BLOCKED_HOSTNAMES = {
        "localhost",
        "localhost.localdomain",
        "ip6-localhost",
        "ip6-loopback",
    }

    # Allowed schemes
    ALLOWED_SCHEMES = {"http", "https"}

    def __init__(
        self,
        allowed_domains: list[str] | None = None,
        block_private_ips: bool = True,
    ) -> None:
        """
        Initialize URL validator.

        Args:
            allowed_domains: Optional allowlist of trusted domains
            block_private_ips: Whether to block private IP addresses
        """
        self._allowed_domains = set(allowed_domains or [])
        self._block_private_ips = block_private_ips

    def _is_private_ip(self, ip_str: str) -> bool:
        """Check if IP address is in a private range."""
        try:
            ip = ipaddress.ip_address(ip_str)
            for network in self.PRIVATE_RANGES:
                if ip in network:
                    return True
            return False
        except ValueError:
            # Not a valid IP, could be a hostname
            return False

    def _is_blocked_hostname(self, hostname: str) -> bool:
        """Check if hostname is blocked."""
        hostname_lower = hostname.lower()

        # Direct match
        if hostname_lower in self.BLOCKED_HOSTNAMES:
            return True

        # Check for localhost variants
        if hostname_lower.startswith("localhost") or hostname_lower.endswith(".local"):
            return True

        return False

    def validate(self, url: str) -> str:
        """
        Validate a URL for safety.

        Args:
            url: URL to validate

        Returns:
            Validated URL string

        Raises:
            UrlValidationError: If URL is invalid or blocked
        """
        if not url:
            raise UrlValidationError("Empty URL")

        try:
            parsed = urlparse(url)
        except Exception as e:
            raise UrlValidationError(f"Invalid URL format: {e}")

        # Check scheme
        if parsed.scheme.lower() not in self.ALLOWED_SCHEMES:
            raise UrlValidationError(
                f"Invalid scheme '{parsed.scheme}'. Allowed: {self.ALLOWED_SCHEMES}"
            )

        # Check hostname exists
        hostname = parsed.hostname
        if not hostname:
            raise UrlValidationError("URL missing hostname")

        # Check for blocked hostnames
        if self._is_blocked_hostname(hostname):
            raise UrlValidationError(f"Blocked hostname: {hostname}")

        # Check for private IPs
        if self._block_private_ips and self._is_private_ip(hostname):
            raise UrlValidationError(f"Private IP addresses are blocked: {hostname}")

        # If allowlist is configured, enforce it
        if self._allowed_domains:
            if not self._matches_allowed_domain(hostname):
                raise UrlValidationError(
                    f"Domain not in allowlist: {hostname}"
                )

        logger.debug(f"URL validated: {url}")
        return url

    def _matches_allowed_domain(self, hostname: str) -> bool:
        """Check if hostname matches any allowed domain."""
        hostname_lower = hostname.lower()
        for domain in self._allowed_domains:
            domain_lower = domain.lower()
            # Exact match or subdomain match
            if hostname_lower == domain_lower or hostname_lower.endswith(
                f".{domain_lower}"
            ):
                return True
        return False

    def is_valid(self, url: str) -> bool:
        """Check if URL is valid without raising exception."""
        try:
            self.validate(url)
            return True
        except UrlValidationError:
            return False


# Default validator instance
default_url_validator = UrlValidator()


# --- T-038: API Key Handler ---


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for API key authentication.

    Validates Bearer token in Authorization header against
    configured API key.
    """

    # Paths that bypass authentication
    BYPASS_PATHS = {
        "/health",
        "/",
        "/docs",
        "/redoc",
        "/openapi.json",
    }

    def __init__(
        self,
        app,
        api_key: str,
        bypass_paths: set[str] | None = None,
    ) -> None:
        """
        Initialize API key middleware.

        Args:
            app: FastAPI application
            api_key: Expected API key value
            bypass_paths: Paths that don't require authentication
        """
        super().__init__(app)
        self._api_key = api_key
        self._bypass_paths = bypass_paths or self.BYPASS_PATHS

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> JSONResponse:
        """Process request and validate API key."""
        path = request.url.path

        # Skip auth for bypass paths
        if path in self._bypass_paths:
            return await call_next(request)

        # Extract Authorization header
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Missing Authorization header"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Parse Bearer token
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Invalid Authorization header format. Use: Bearer <token>"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = auth_header[7:]  # Strip "Bearer "

        # Validate token
        if token != self._api_key:
            client_host = request.client.host if request.client else "unknown"
            logger.warning(f"Invalid API key attempt from {client_host}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Invalid API key"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        return await call_next(request)


def get_api_key_header(request: Request, api_key: str) -> str:
    """
    Dependency for API key validation.

    Usage in route:
        @app.get("/protected")
        async def protected(key: str = Depends(lambda r: get_api_key_header(r, settings.api_key))):
            ...
    """
    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header[7:]

    if token != api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token
