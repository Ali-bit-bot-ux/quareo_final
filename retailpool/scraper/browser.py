"""
Playwright Browser Manager for Kaspi scraping.

Async context manager for stealth browser contexts with
rotated UA, viewport, locale, and proxy.
"""

from __future__ import annotations

import logging
from types import TracebackType

from playwright.async_api import (
    async_playwright, Browser, BrowserContext, Playwright,
)

from retailpool.config import settings
from retailpool.scraper.antifraud import BaseProxyProvider, UserAgentRotator

logger = logging.getLogger(__name__)


class BrowserManager:
    """Manages Playwright Chromium browser + stealth contexts."""

    def __init__(
        self,
        proxy_provider: BaseProxyProvider | None = None,
        ua_rotator: UserAgentRotator | None = None,
        headless: bool | None = None,
    ) -> None:
        self._proxy_provider = proxy_provider
        self._ua_rotator = ua_rotator or UserAgentRotator()
        self._headless = headless if headless is not None else settings.SCRAPER_HEADLESS
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    async def __aenter__(self) -> BrowserManager:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self._headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        logger.info("Browser launched (headless=%s)", self._headless)
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None,
                        exc_val: BaseException | None,
                        exc_tb: TracebackType | None) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser closed.")

    async def new_context(self) -> BrowserContext:
        """Create stealth context with KZ locale, proxy, rotated UA."""
        assert self._browser is not None, "Use `async with BrowserManager()`"

        ua = self._ua_rotator.get_random()
        kwargs: dict = {
            "user_agent": ua,
            "locale": "ru-KZ",
            "timezone_id": "Asia/Almaty",
            "viewport": {"width": 1920, "height": 1080},
            "java_script_enabled": True,
            "ignore_https_errors": True,
            "extra_http_headers": {
                "Accept-Language": "ru-KZ,ru;q=0.9,en-US;q=0.8",
                "DNT": "1",
            },
        }

        if self._proxy_provider:
            proxy_url = await self._proxy_provider.get_proxy()
            if proxy_url:
                kwargs["proxy"] = {"server": proxy_url}

        ctx = await self._browser.new_context(**kwargs)

        # Mask navigator.webdriver
        await ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {} };
        """)
        return ctx
