from __future__ import annotations

from core.logger import get_logger

_logger = get_logger(__name__)


class XAPIError(Exception):
    pass


class XClient:
    """
    Twikit-based X (Twitter) client.
    Twikit uses web scraping — no official API key required.
    Session is cached after first login to avoid re-authenticating on every call.
    """

    def __init__(self, username: str, password: str, email: str) -> None:
        self._username = username
        self._password = password
        self._email = email
        self._client = None
        self._authenticated = False

    async def _ensure_authenticated(self) -> None:
        if self._authenticated:
            return
        try:
            from twikit import Client
        except ImportError as exc:
            raise XAPIError(
                "twikit is not installed. Run: pip install twikit"
            ) from exc

        self._client = Client("en-US")
        _logger.info("Authenticating with X via Twikit.")
        await self._client.login(
            auth_info_1=self._username,
            auth_info_2=self._email,
            password=self._password,
        )
        self._authenticated = True
        _logger.info("Twikit authentication successful.")

    async def post_tweet(self, text: str) -> str:
        """Post a tweet and return its ID."""
        await self._ensure_authenticated()
        _logger.info("Posting tweet (%d chars).", len(text))
        tweet = await self._client.create_tweet(text=text)
        tweet_id = str(tweet.id)
        _logger.info("Tweet posted: %s", tweet_id)
        return tweet_id
