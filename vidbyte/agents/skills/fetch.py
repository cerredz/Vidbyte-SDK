"""FILE: vidbyte/agents/skills/fetch.py

PURPOSE: Defines SkillFetch, the one HTTP step every networked skill source uses: a GET through the SDK's HttpTransport with the fixed skill-source timeout, one retry on retryable statuses, the backoff, no redirects, a size cap, and a whole-step deadline, with every failure that left no HTTP answer turned into an explained SkillResolution.
ROLE IN CODEBASE: Used by GitHubSkillResolver (github.py) for the commit lookup, tree listing, and raw SKILL.md, and by VendorSkillResolver (vendor.py) for the vendor content download and skill record. Each resolver maps HTTP statuses itself; this step maps only transport exceptions and the deadline.
ARCHITECTURE NOTE: AGENTS.md principle 5: the timeout, retry, backoff, and size cap live in HttpTransport.request, and this class only fixes their values for skill sources. The deadline wraps the whole call, retry included, because the transport's timeout bounds each network operation, not a server that drips bytes. SKILL_FETCH_DEADLINE_SECONDS is read as this module's global when the call runs, so tests can patch it here.
FUNCTION INVENTORY: SkillFetch.get(*, url, headers, max_bytes, step) -> HttpResponse | SkillResolution; SkillFetch._refused(error, host, step, max_bytes, hint) -> SkillResolution; SkillFetch._expired(host, step, hint) -> SkillResolution.
COMMON MODIFICATION PATTERNS: Change a bound in vidbyte/lib/constants/skills.py, never here. A new networked source passes its own SkillFetchStep member and maps statuses in its own resolver.
WHAT NOT TO DO IN THIS FILE: 1. Do not follow redirects; httpx keeps x-api-key across origins. 2. Do not add a retry loop (S064); retries come only from retry_count. 3. Do not copy the transport's response excerpt or any body into a detail. 4. Do not catch TimeoutError unless the step's own deadline expired, or a programming error would read as a network failure.
KNOWN EDGE CASES: A timeout or connection error is not retried within a run (the transport retries only on status codes); it is retried on the next run because FETCH_FAILED is transient. A body over the cap on a 2xx answer is TOO_LARGE and remembered; on any other status it is FETCH_FAILED. Every HTTP answer, whatever its status, is handed back for the resolver to map.
RELATED DOCS: vidbyte/agents/skills/README.md; vidbyte/lib/http/transport.py; docs/spec/jev-skill-sources/spec.md (section 9.2)
TESTS: tests/features/jev_skills_preload/test_skill_sources_fetch.py
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from http import HTTPStatus
from urllib.parse import urlsplit

from vidbyte.lib.constants.skills import (
    SKILL_FETCH_BACKOFF_SECONDS,
    SKILL_FETCH_DEADLINE_SECONDS,
    SKILL_FETCH_RETRY_COUNT,
    SKILL_FETCH_TIMEOUT_SECONDS,
)
from vidbyte.lib.dataclasses.skills import SkillResolution
from vidbyte.lib.enums.skills import SkillFetchStep, SkillUnavailableReason
from vidbyte.lib.errors import ProviderRequestError
from vidbyte.lib.http.transport import HttpResponse, HttpTransport


class SkillFetch:
    """One bounded GET for a skill source; failures without an HTTP answer become explained resolutions."""

    def __init__(self) -> None:
        self.transport = HttpTransport()

    async def get(self, *, url: str, headers: Mapping[str, str], max_bytes: int, step: SkillFetchStep) -> HttpResponse | SkillResolution:
        # @intent skill-fetch-bounded-step
        # Every skill request goes through the shared transport
        # with fixed bounds and no redirects, inside one
        # deadline for the whole step. Only failures that left
        # no HTTP answer become resolutions here; each resolver
        # maps statuses, so every answer is handed back.
        host = urlsplit(url).hostname or url
        # The tree listing is the one step an entry can skip, so its
        # failures say how.
        hint = " Set path= on the entry to skip the tree listing." if step is SkillFetchStep.GITHUB_TREE else ""
        # Send the request with the fixed timeout,
        # one retry on retryable statuses, and the
        # size cap of what this step downloads.
        deadline = asyncio.timeout(SKILL_FETCH_DEADLINE_SECONDS)
        try:
            async with deadline:
                return await self.transport.request(
                    method="GET",
                    url=url,
                    headers=headers,
                    timeout_seconds=SKILL_FETCH_TIMEOUT_SECONDS,
                    retry_count=SKILL_FETCH_RETRY_COUNT,
                    backoff_seconds=SKILL_FETCH_BACKOFF_SECONDS,
                    max_response_bytes=max_bytes,
                    follow_redirects=False,
                )
        except ProviderRequestError as error:
            # No usable answer arrived:
            # unreachable, or a body over the cap.
            return self._refused(error, host, step, max_bytes, hint)
        except TimeoutError:
            # Only this step's own deadline is an expected failure; any
            # other timeout is a programming error and propagates.
            if deadline.expired():
                return self._expired(host, step, hint)
            raise

    @staticmethod
    def _refused(error: ProviderRequestError, host: str, step: SkillFetchStep, max_bytes: int, hint: str) -> SkillResolution:
        # @intent skill-fetch-transport-failure
        # A missing status is a connection failure or timeout;
        # a 2xx status means the body was over the cap
        # (permanent); any other status means an oversized
        # error body (transient). Never echo the excerpt.
        status = error.status_code
        if status is None:
            return SkillResolution(reason=SkillUnavailableReason.FETCH_FAILED, detail=f"Could not reach {host} during {step.value} (the connection failed or timed out); retried on the next run.{hint}")
        if HTTPStatus.OK <= status < HTTPStatus.MULTIPLE_CHOICES:
            return SkillResolution(reason=SkillUnavailableReason.TOO_LARGE, detail=f"The {step.value} answer from {host} is larger than its {max_bytes}-byte cap, so it was not read.")
        return SkillResolution(reason=SkillUnavailableReason.FETCH_FAILED, detail=f"{host} answered {step.value} with HTTP {status} and an error body over the {max_bytes}-byte cap; retried on the next run.")

    @staticmethod
    def _expired(host: str, step: SkillFetchStep, hint: str) -> SkillResolution:
        # @intent skill-fetch-deadline
        # A server that keeps the step open past the
        # deadline is treated like an unreachable
        # one: FETCH_FAILED, retried on the next run.
        return SkillResolution(reason=SkillUnavailableReason.FETCH_FAILED, detail=f"{host} did not finish {step.value} within SKILL_FETCH_DEADLINE_SECONDS ({SKILL_FETCH_DEADLINE_SECONDS} s); retried on the next run.{hint}")


__all__ = ["SkillFetch"]
