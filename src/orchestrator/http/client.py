"""HTTP client with retry logic, timeouts, and rate limit handling."""

import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    """Raised when API rate limit is hit."""

    def __init__(self, retry_after: float | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(f"Rate limited. Retry after: {retry_after}s")


class HttpClient:
    """
    HTTP client with retry logic, timeouts, and rate limit handling.

    Uses httpx for async HTTP requests with exponential backoff
    retry logic and automatic rate limit handling.
    """

    DEFAULT_TIMEOUT = httpx.Timeout(
        connect=10.0,
        read=30.0,
        write=10.0,
        pool=10.0,
    )

    def __init__(
        self,
        base_url: str | None = None,
        timeout: httpx.Timeout | None = None,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
        headers: dict[str, str] | None = None,
    ) -> None:
        """
        Initialize the HTTP client.

        Args:
            base_url: Optional base URL for all requests
            timeout: Request timeout configuration
            max_retries: Maximum retry attempts
            backoff_factor: Exponential backoff multiplier
            headers: Default headers for all requests
        """
        self._base_url = base_url
        self._timeout = timeout or self.DEFAULT_TIMEOUT
        self._max_retries = max_retries
        self._backoff_factor = backoff_factor
        self._default_headers = headers or {}
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url or "",
                timeout=self._timeout,
                headers=self._default_headers,
                follow_redirects=True,
            )
        return self._client

    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff delay."""
        return self._backoff_factor * (2**attempt)

    async def _handle_rate_limit(self, response: httpx.Response) -> float:
        """
        Handle 429 rate limit response.

        Args:
            response: The 429 response

        Returns:
            Seconds to wait before retry
        """
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
        # Default to 60 seconds if no Retry-After header
        return 60.0

    async def request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """
        Make an HTTP request with retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            **kwargs: Additional arguments for httpx

        Returns:
            httpx.Response

        Raises:
            httpx.HTTPStatusError: For non-retryable errors
            RateLimitError: When rate limit exhausted
        """
        client = await self._get_client()
        last_exception: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                response = await client.request(method, url, **kwargs)

                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = await self._handle_rate_limit(response)
                    if attempt < self._max_retries:
                        logger.warning(
                            f"Rate limited on {method} {url}. "
                            f"Waiting {retry_after}s (attempt {attempt + 1})"
                        )
                        await asyncio.sleep(retry_after)
                        continue
                    else:
                        raise RateLimitError(retry_after)

                # Retry on server errors
                if response.status_code >= 500:
                    if attempt < self._max_retries:
                        backoff = self._calculate_backoff(attempt)
                        logger.warning(
                            f"Server error {response.status_code} on {method} {url}. "
                            f"Retrying in {backoff}s (attempt {attempt + 1})"
                        )
                        await asyncio.sleep(backoff)
                        continue
                    else:
                        response.raise_for_status()

                return response

            except httpx.TimeoutException as e:
                last_exception = e
                if attempt < self._max_retries:
                    backoff = self._calculate_backoff(attempt)
                    logger.warning(
                        f"Timeout on {method} {url}. "
                        f"Retrying in {backoff}s (attempt {attempt + 1})"
                    )
                    await asyncio.sleep(backoff)
                    continue
                raise

            except httpx.ConnectError as e:
                last_exception = e
                if attempt < self._max_retries:
                    backoff = self._calculate_backoff(attempt)
                    logger.warning(
                        f"Connection error on {method} {url}. "
                        f"Retrying in {backoff}s (attempt {attempt + 1})"
                    )
                    await asyncio.sleep(backoff)
                    continue
                raise

        # Should not reach here, but just in case
        if last_exception:
            raise last_exception
        raise RuntimeError("Unexpected retry loop exit")

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """Make a GET request."""
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        """Make a POST request."""
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> httpx.Response:
        """Make a PUT request."""
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        """Make a DELETE request."""
        return await self.request("DELETE", url, **kwargs)

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        """Make a GET request and return JSON response."""
        response = await self.get(url, **kwargs)
        response.raise_for_status()
        return response.json()

    async def post_json(self, url: str, data: Any, **kwargs: Any) -> Any:
        """Make a POST request with JSON body and return JSON response."""
        response = await self.post(url, json=data, **kwargs)
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
            logger.info("HTTP client closed")

    async def __aenter__(self) -> "HttpClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()


class SyncHttpClient:
    """
    Synchronous wrapper for HttpClient.

    Useful for non-async contexts like scheduler jobs.
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: httpx.Timeout | None = None,
        max_retries: int = 3,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Initialize the sync HTTP client."""
        self._base_url = base_url
        self._timeout = timeout or HttpClient.DEFAULT_TIMEOUT
        self._max_retries = max_retries
        self._default_headers = headers or {}
        self._client: httpx.Client | None = None

    def _get_client(self) -> httpx.Client:
        """Get or create the sync HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(
                base_url=self._base_url or "",
                timeout=self._timeout,
                headers=self._default_headers,
                follow_redirects=True,
            )
        return self._client

    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff delay."""
        return 1.0 * (2**attempt)

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """Make a GET request with retry logic."""
        client = self._get_client()
        last_exception: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                response = client.get(url, **kwargs)

                if response.status_code == 429:
                    retry_after = float(response.headers.get("Retry-After", 60))
                    if attempt < self._max_retries:
                        logger.warning(f"Rate limited. Waiting {retry_after}s")
                        time.sleep(retry_after)
                        continue
                    raise RateLimitError(retry_after)

                if response.status_code >= 500 and attempt < self._max_retries:
                    backoff = self._calculate_backoff(attempt)
                    logger.warning(f"Server error. Retrying in {backoff}s")
                    time.sleep(backoff)
                    continue

                return response

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_exception = e
                if attempt < self._max_retries:
                    backoff = self._calculate_backoff(attempt)
                    logger.warning(f"Error: {e}. Retrying in {backoff}s")
                    time.sleep(backoff)
                    continue
                raise

        if last_exception:
            raise last_exception
        raise RuntimeError("Unexpected retry loop exit")

    def get_json(self, url: str, **kwargs: Any) -> Any:
        """Make a GET request and return JSON."""
        response = self.get(url, **kwargs)
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None and not self._client.is_closed:
            self._client.close()
            self._client = None

    def __enter__(self) -> "SyncHttpClient":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
