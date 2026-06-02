"""
Kaspi.kz scraper — async Playwright-based parser for category listings
and individual product cards. Uses Redis caching.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import redis.asyncio as aioredis
from playwright.async_api import BrowserContext, Page

from retailpool.config import settings
from retailpool.scraper.antifraud import RateLimiter, is_blocked
from retailpool.schemas.product import ProductCard

logger = logging.getLogger(__name__)


class KaspiScraper:
    """
    Scrapes Kaspi category pages and product cards.

    Usage::
        redis = aioredis.from_url(settings.REDIS_URL)
        scraper = KaspiScraper(context=ctx, redis=redis)
        products = await scraper.scrape_category("https://kaspi.kz/shop/c/air-humidifiers/")
    """

    def __init__(
        self,
        context: BrowserContext,
        redis: aioredis.Redis | None = None,
        rate_limiter: RateLimiter | None = None,
        cache_ttl: int | None = None,
    ) -> None:
        self._ctx = context
        self._redis = redis
        self._limiter = rate_limiter or RateLimiter()
        self._cache_ttl = cache_ttl or settings.REDIS_CACHE_TTL

    # ── Cache helpers ─────────────────────────────────────────────────
    def _cache_key(self, url: str) -> str:
        h = hashlib.md5(url.encode()).hexdigest()
        return f"kaspi:cache:{h}"

    async def _get_cached(self, url: str) -> list[dict] | None:
        if not self._redis:
            return None
        data = await self._redis.get(self._cache_key(url))
        if data:
            logger.debug("Cache HIT for %s", url)
            return json.loads(data)
        return None

    async def _set_cache(self, url: str, data: list[dict]) -> None:
        if not self._redis:
            return
        await self._redis.setex(
            self._cache_key(url), self._cache_ttl, json.dumps(data, ensure_ascii=False)
        )

    # ── Category scraping ─────────────────────────────────────────────
    async def scrape_category(
        self, category_url: str, max_products: int = 30
    ) -> list[ProductCard]:
        """
        Scrape product listing from a Kaspi category page.
        Returns validated ProductCard list.
        """
        cached = await self._get_cached(category_url)
        if cached:
            return [ProductCard(**item) for item in cached]

        page: Page = await self._ctx.new_page()
        products: list[ProductCard] = []

        try:
            await self._limiter.wait()
            resp = await page.goto(category_url, wait_until="domcontentloaded", timeout=30000)

            if resp and is_blocked(await page.content(), resp.status):
                logger.warning("BLOCKED on category page: %s", category_url)
                return []

            # Wait for product cards to render
            await page.wait_for_selector(
                "[data-product-id], .item-card, .product-card", timeout=10000
            )

            # Extract product data from the listing
            raw_items = await page.evaluate("""() => {
                const cards = document.querySelectorAll(
                    '[data-product-id], .item-card, .product-card'
                );
                return Array.from(cards).map(card => {
                    const link = card.querySelector('a[href*="/shop/p/"]');
                    const titleEl = card.querySelector(
                        '.item-card__name, .product-card__title, [data-product-name]'
                    );
                    const priceEl = card.querySelector(
                        '.item-card__prices-price, .product-card__price'
                    );
                    const ratingEl = card.querySelector(
                        '.rating, [data-rating]'
                    );
                    const reviewEl = card.querySelector(
                        '.item-card__reviews, .product-card__reviews-count'
                    );

                    const href = link ? link.getAttribute('href') : '';
                    const productId = card.getAttribute('data-product-id')
                        || (href.match(/\\/p\\/([^/?]+)/) || [])[1]
                        || '';

                    const priceText = priceEl ? priceEl.textContent.replace(/[^\\d]/g, '') : '0';

                    return {
                        kaspi_id: productId,
                        title: titleEl ? titleEl.textContent.trim() : '',
                        url: href ? 'https://kaspi.kz' + href : '',
                        price: parseInt(priceText) || 0,
                        rating: ratingEl
                            ? parseFloat(ratingEl.getAttribute('data-rating')
                              || ratingEl.textContent) || null
                            : null,
                        review_count: reviewEl
                            ? parseInt(reviewEl.textContent.replace(/[^\\d]/g, '')) || 0
                            : 0,
                    };
                });
            }""")

            # Extract category slug from URL
            slug = category_url.rstrip("/").split("/")[-1]

            for item in raw_items[:max_products]:
                if not item.get("kaspi_id") or not item.get("title"):
                    continue
                products.append(ProductCard(
                    kaspi_id=item["kaspi_id"],
                    title=item["title"],
                    category_slug=slug,
                    url=item.get("url", ""),
                    price_min=item.get("price"),
                    price_max=item.get("price"),
                    rating=item.get("rating"),
                    review_count=item.get("review_count", 0),
                ))

            # Cache results
            await self._set_cache(
                category_url, [p.model_dump(mode="json") for p in products]
            )
            logger.info("Scraped %d products from %s", len(products), slug)

        except Exception as exc:
            logger.error("Error scraping category %s: %s", category_url, exc)
        finally:
            await page.close()

        return products

    # ── Product card detail scraping ──────────────────────────────────
    async def scrape_product_card(self, product_url: str) -> dict[str, Any] | None:
        """
        Scrape detailed product card page for visual audit data:
        photo count, description length, infographics, seller info.
        """
        page: Page = await self._ctx.new_page()

        try:
            await self._limiter.wait()
            resp = await page.goto(product_url, wait_until="domcontentloaded", timeout=30000)

            if resp and is_blocked(await page.content(), resp.status):
                logger.warning("BLOCKED on product page: %s", product_url)
                return None

            await page.wait_for_selector(
                ".product, .item, [data-product-id]", timeout=10000
            )

            detail = await page.evaluate("""() => {
                // Count product images
                const gallery = document.querySelectorAll(
                    '.gallery__thumb, .product-gallery img, [data-gallery] img'
                );
                const photoCount = gallery.length;

                // Check for infographics (images with overlay text / badges)
                const hasInfographics = document.querySelectorAll(
                    '.infographic, [data-infographic], .badge-overlay'
                ).length > 0;

                // Description
                const descEl = document.querySelector(
                    '.product__description, [data-product-description], .item__description'
                );
                const descLength = descEl ? descEl.textContent.trim().length : 0;

                // Seller count
                const sellers = document.querySelectorAll(
                    '.sellers-table__row, .offer-list__item, [data-merchant]'
                );

                // Rating
                const ratingEl = document.querySelector('[data-rating], .rating__value');
                const rating = ratingEl
                    ? parseFloat(ratingEl.getAttribute('data-rating')
                      || ratingEl.textContent) || null
                    : null;

                // Review count
                const reviewEl = document.querySelector(
                    '.reviews-count, .product-rating__count'
                );
                const reviewCount = reviewEl
                    ? parseInt(reviewEl.textContent.replace(/[^\\d]/g, '')) || 0
                    : 0;

                return {
                    photo_count: photoCount,
                    has_infographics: hasInfographics,
                    description_length: descLength,
                    seller_count: sellers.length,
                    rating: rating,
                    review_count: reviewCount,
                };
            }""")

            return detail

        except Exception as exc:
            logger.error("Error scraping product %s: %s", product_url, exc)
            return None
        finally:
            await page.close()

    # ── Seller count for category ─────────────────────────────────────
    async def get_seller_count(self, category_url: str) -> int:
        """Count unique sellers on a category listing page."""
        page: Page = await self._ctx.new_page()
        try:
            await self._limiter.wait()
            await page.goto(category_url, wait_until="domcontentloaded", timeout=30000)

            count = await page.evaluate("""() => {
                const sellers = document.querySelectorAll(
                    '[data-merchant-id], .item-card__merchant, .seller-name'
                );
                const unique = new Set(
                    Array.from(sellers).map(el =>
                        el.getAttribute('data-merchant-id')
                        || el.textContent.trim()
                    )
                );
                return unique.size;
            }""")
            return count or 0
        except Exception:
            return 0
        finally:
            await page.close()
