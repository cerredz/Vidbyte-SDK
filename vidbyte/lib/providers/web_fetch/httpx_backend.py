"""Context Protocol Header

Description:
    Implements a web fetch backend using HttpTransport for simple HTTP GET requests.
Purpose:
    Provides a lightweight HTTP fetching capability with HTML-to-markdown conversion
    for text-based content and PDF detection.
Architecture:
    - HttpxFetchBackend: Uses HttpTransport, regex-based HTML-to-markdown conversion.
    - Handles redirects, errors, and timeouts.
Relations:
    Related to vidbyte.lib.providers.web_fetch.base and vidbyte.lib.http.transport.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from vidbyte.lib.http.transport import HttpTransport
from vidbyte.lib.providers.web_fetch.base import BaseWebFetchBackend, FetchResult

logger = logging.getLogger(__name__)

MAX_BODY_LENGTH = 5 * 1024 * 1024


class HttpxFetchBackend(BaseWebFetchBackend):
    def __init__(self) -> None:
        self._transport = HttpTransport()

    async def fetch(self, url: str, format: str, timeout_ms: int) -> FetchResult:
        timeout_seconds = max(0.5, timeout_ms / 1000.0)

        try:
            response = self._transport.request(
                method="GET",
                url=url,
                headers={},
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            logger.exception("Fetch failed for url: %s", url)
            return FetchResult(
                content=f"Error fetching URL: {exc}",
                content_type="text/plain",
                status_code=0,
                final_url=url,
            )

        content_type = self._extract_content_type(response.headers)
        final_url = url

        if content_type.startswith("application/pdf"):
            return FetchResult(
                content="Content is a PDF. Use pdf_read tool to extract text.",
                content_type="application/pdf",
                status_code=response.status_code,
                final_url=final_url,
            )

        body = response.body[:MAX_BODY_LENGTH]

        if format == "markdown" and content_type.startswith("text/html"):
            body = self._html_to_markdown(body)

        return FetchResult(
            content=body,
            content_type=content_type,
            status_code=response.status_code,
            final_url=final_url,
        )

    @staticmethod
    def _extract_content_type(headers: dict) -> str:
        content_type = ""
        for key, value in headers.items():
            if key.lower() == "content-type":
                content_type = value.split(";")[0].strip()
                break
        return content_type or "text/html"

    @staticmethod
    def _html_to_markdown(html: str) -> str:
        text = html

        text = re.sub(r"<head[^>]*>.*?</head>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<noscript[^>]*>.*?</noscript>", "", text, flags=re.DOTALL | re.IGNORECASE)

        text = re.sub(r"<h1[^>]*>(.*?)</h1>", r"\n\n# \1\n\n", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<h2[^>]*>(.*?)</h2>", r"\n\n## \1\n\n", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<h3[^>]*>(.*?)</h3>", r"\n\n### \1\n\n", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<h4[^>]*>(.*?)</h4>", r"\n\n#### \1\n\n", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<h5[^>]*>(.*?)</h5>", r"\n\n##### \1\n\n", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<h6[^>]*>(.*?)</h6>", r"\n\n###### \1\n\n", text, flags=re.DOTALL | re.IGNORECASE)

        text = re.sub(r"<p[^>]*>(.*?)</p>", r"\n\n\1\n\n", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)

        text = re.sub(r"<strong[^>]*>(.*?)</strong>", r"**\1**", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<b[^>]*>(.*?)</b>", r"**\1**", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<em[^>]*>(.*?)</em>", r"*\1*", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<i[^>]*>(.*?)</i>", r"*\1*", text, flags=re.DOTALL | re.IGNORECASE)

        text = re.sub(r"<a[^>]*href=[\"'](.*?)[\"'][^>]*>(.*?)</a>", r"[\2](\1)", text, flags=re.DOTALL | re.IGNORECASE)

        text = re.sub(r"<li[^>]*>(.*?)</li>", r"- \1\n", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"</?(?:ul|ol)[^>]*>", "\n", text, flags=re.IGNORECASE)

        text = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<pre[^>]*>(.*?)</pre>", r"\n\n```\n\1\n```\n\n", text, flags=re.DOTALL | re.IGNORECASE)

        text = re.sub(r"<img[^>]*alt=[\"'](.*?)[\"'][^>]*>", r"![\1]", text, flags=re.IGNORECASE)

        text = re.sub(r"<[^>]+>", "", text)

        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        text = re.sub(r"&quot;", '"', text)
        text = re.sub(r"&#39;", "'", text)
        text = re.sub(r"&nbsp;", " ", text)

        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()

        return text


__all__ = [
    "HttpxFetchBackend",
]
