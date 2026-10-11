"""FILE: lint/rules/c018_canonical_api_host.py

PURPOSE: Detect Vidbyte API URLs hardcoded in SDK production code whose origin the vendored platform contract does not list with status `live`: a `planned` host that does not serve traffic yet, or a host (or scheme or port) the contract does not list at all.
ROLE IN CODEBASE: Enforces C018, the SDK consumer side of cross-repo contract X06. cerredz/Vidbyte publishes its public API origins in lint/contracts/vidbyte-platform-contract.json; every Vidbyte API host the SDK spells must be one of the live ones, or requests to it never reach the platform.
ARCHITECTURE NOTE: The literal scan and the request trace come from lint/core/url_flow.py (shared with C017 through trace_catalog, so one lint run traces once); host classification and the contract come from lint/core/platform_contract.py, which fails closed. This module only judges each literal's origin and explains which requests it would carry.
FUNCTION INVENTORY: HostEvidence gathers the requests, managed-route consequence, pinning tests, and credential intent for one literal; CanonicalApiHostRule reports and explains, rendering the flagged line repaired as a correct example.
COMMON MODIFICATION PATTERNS: A new host status in the contract needs a decision here about whether it may be spelled in SDK code, plus a scratch fixture.
WHAT NOT TO DO: Do not import vidbyte, resolve DNS or contact the host, edit the vendored contract, or treat a website link (vidbyte.ai pages) as an API host.
KNOWN EDGE CASES: A URL inside a longer message string counts. Docstrings and bare string statements do not. Hosts compare case-insensitively, but the scheme and port must match the listed origin exactly, so http:// to a listed https host is unlisted.
RELATED DOCS: docs/design/lint-sdk-cross-repo-contracts.md (C018); lint/contracts/README.md; lint catalog X06.
TESTS: python lint/run.py --rule C018; scratch fixtures, fail-closed contract cases, and mutants are recorded in the S4 pull request body.
"""

from __future__ import annotations

from dataclasses import dataclass

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog
from lint.core.platform_contract import LIVE_STATUS, PLATFORM_CONTRACT_REL, REFRESH_DOC_REL, PlatformContract, PlatformContractLoader, RouteMatcher, VidbyteHosts
from lint.core.registry import Rule
from lint.core.url_flow import UrlFlowTrace, UrlLiteral, trace_catalog

_PLANNED = "planned-host"
_UNLISTED = "unlisted-host"
_KINDS = frozenset({_PLANNED, _UNLISTED})
_MANAGED_ROUTE_PREFIX = "models."
_KEY_INTENT = "@intent managed-key-stays-on-vidbyte-host"
_TEST_PREFIXES = ("tests/", "scripts/")
_LISTED = 6


@dataclass(frozen=True, slots=True)
class HostEvidence:
    """What one non-live host literal affects: the requests built from it, whether they are managed model calls, and what pins it."""

    requests: str
    managed: bool
    tests: str
    intent: str

    @classmethod
    def gather(cls, catalog: SourceCatalog, contract: PlatformContract, trace: UrlFlowTrace, literal: UrlLiteral) -> HostEvidence:
        # The traced requests built from the literal, the contract routes they reach, and the tests and intent that pin the host.
        matcher = RouteMatcher(contract.routes)
        requests = trace.requests_using(literal)
        routes = {route.name for request in requests for route in matcher.match(request.path)}
        listed = "; ".join(f"{'/'.join(request.methods) or 'an unknown method'} {request.path_display or '/'} ({request.location})" for request in requests[:_LISTED])
        more = f"; and {len(requests) - _LISTED} more" if len(requests) > _LISTED else ""
        tests = [f"{source.rel}:{number}" for source in catalog.all_python_files() if source.rel.startswith(_TEST_PREFIXES) for number, line in enumerate(source.text.splitlines(), start=1) if literal.origin.host in line.lower()]
        intent = next((f"{source.rel}:{number}" for source in catalog.python_files() for number, line in enumerate(source.text.splitlines(), start=1) if _KEY_INTENT in line), "")
        return cls(requests=listed + more, managed=any(name.startswith(_MANAGED_ROUTE_PREFIX) for name in routes), tests=", ".join(tests[:_LISTED]) + (f", and {len(tests) - _LISTED} more" if len(tests) > _LISTED else ""), intent=intent)


class CanonicalApiHostRule(Rule):
    """Requires every Vidbyte API host spelled in SDK production code to be listed as live in the platform contract."""

    id = "C018"
    name = "canonical-api-host"
    severity = "blocking"
    summary = "Every Vidbyte API URL in a vidbyte/ string literal must use an origin that lint/contracts/vidbyte-platform-contract.json lists in public_api_hosts with status live; a planned host does not serve traffic and an unlisted host is not part of the platform's public API."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Load the contract (raising when it is unusable), list the Vidbyte API literals, and report each non-live origin.
        contract = PlatformContractLoader.load(catalog)
        hosts = VidbyteHosts(contract)
        trace = trace_catalog(catalog, hosts)
        findings: list[Finding] = []
        for literal in trace.literals:
            entry = hosts.entry(literal.origin)
            if entry is not None and entry.status == LIVE_STATUS:
                continue
            evidence = HostEvidence.gather(catalog, contract, trace, literal)
            kind = _UNLISTED if entry is None else _PLANNED
            extra = {
                "kind": kind,
                "origin": literal.origin.origin,
                "url": literal.url,
                "path": literal.url[literal.origin.end:] or "/",
                "spelled": literal.url[:literal.origin.end],
                "symbol": literal.symbol,
                "status": entry.status if entry is not None else "",
                "contract_line": contract.cite(contract.line_of(f'"url": "{entry.url}"') if entry is not None else contract.line_of('"public_api_hosts"')),
                "listed": "; ".join(f"{host.url} ({host.status})" for host in contract.hosts),
                "live": ", ".join(hosts.live_urls()),
                "requests": evidence.requests,
                "managed": "yes" if evidence.managed else "no",
                "tests": evidence.tests,
                "intent": evidence.intent,
            }
            findings.append(Finding(rule_id=self.id, rel_path=literal.rel, line=literal.line, source_line=literal.source_line, symbol=literal.symbol or literal.url, extra=extra))
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # One consequence and repair path for both kinds; the what names the status, the requests, and the managed impact.
        extra = finding.extra
        kind = extra.get("kind", "")
        if kind not in _KINDS:
            raise ValueError(f"C018 finding has unknown kind {kind!r}.")
        live = extra["live"] or "the live host the contract lists"
        first_live = live.split(", ")[0]
        return Diagnostic(
            what_happened=self._what(finding, kind),
            why_blocked=f"cerredz/Vidbyte publishes its public API origins in {PLATFORM_CONTRACT_REL} (public_api_hosts), marking each `live` (serving traffic) or `planned` (intended, not serving). A planned origin does not serve traffic, so an SDK request to it fails with a DNS or connection error before it reaches the platform and the feature built on it is broken for every user. An unlisted origin (another Vidbyte host, `http://`, or another port) is not part of the platform's public API: nothing promises it serves the contract's routes, and the platform does not vouch for it to receive a Vidbyte API key. The cross-repo contract plan states it directly: consumer host rules flag literals that are not listed, and literals whose status is not `live` (lint catalog X06, canonical-api-host; docs/design/lint-sdk-cross-repo-contracts.md).",
            how_to_fix=self._repair(finding, first_live),
            correct_examples=(
                f"{PLATFORM_CONTRACT_REL} public_api_hosts - {extra['listed']}; only the live origin may appear in SDK code.",
                f"`{self._repaired_line(finding, first_live)}` at {finding.location()} - the same path on the live origin.",
            ),
            will_not_work=(
                f"Editing {PLATFORM_CONTRACT_REL} to mark the host live: the copy must stay byte-identical to cerredz/Vidbyte. When the platform makes the host live, its regenerated contract says so and a re-vendor ({REFRESH_DOC_REL}) clears this finding with no SDK change.",
                "Moving the host into an environment-variable default, a class attribute, or split string pieces: C018 scans every non-docstring literal under vidbyte/, and a host the scan cannot see is also invisible to C017's route checks.",
                "Letting callers pass any base URL to work around the host: a request that carries the caller's Vidbyte API key must stay on a Vidbyte origin, so an override has to be validated against the contract's live hosts.",
                "Raising C018's baseline in lint/baseline.json: the baseline only freezes the known managed-gateway finding, and a second non-live host is a second outage.",
            ),
            verify=f"{self.verify_command()} && python lint/run.py --rule C017",
        )

    @staticmethod
    def _what(finding: Finding, kind: str) -> str:
        # The literal, the contract's verdict on its origin, the requests it carries, and the managed-call consequence.
        extra = finding.extra
        holder = f"`{extra['symbol']}` hardcodes" if extra["symbol"] else "a string literal hardcodes"
        if kind == _PLANNED:
            verdict = f"listed in {PLATFORM_CONTRACT_REL} with status `{extra['status']}`, not `live` ({extra['contract_line']}), so it does not serve traffic"
        else:
            verdict = f"not listed in the public_api_hosts of {PLATFORM_CONTRACT_REL} ({extra['contract_line']}), which lists only {extra['listed']}"
        requests = f" Requests built from it: {extra['requests']}." if extra["requests"] else " No traced request is built from it, so it is either unused or reached through code C017 cannot follow."
        managed = " They include the contract's managed model routes (models.*), so managed JEV calls cannot reach the platform: each request above fails with a DNS or connection error before the Vidbyte gateway sees it." if extra["managed"] == "yes" else ""
        return f"{finding.location()} {holder} the Vidbyte API URL {extra['url']}, whose origin {extra['origin']} is {verdict}.{requests}{managed}"

    @staticmethod
    def _repaired_line(finding: Finding, first_live: str) -> str:
        # The flagged source line with its origin replaced by the live one, or the bare repaired URL when the line does not hold it.
        spelled = finding.extra["spelled"]
        if spelled and spelled in finding.source_line:
            return finding.source_line.replace(spelled, first_live)
        return f'"{first_live}{finding.extra["path"]}"'

    @staticmethod
    def _repair(finding: Finding, first_live: str) -> str:
        # Numbered steps: switch to the live origin (or a validated configurable base URL), update pinning tests, verify.
        extra = finding.extra
        name = f"`{extra['symbol']}`" if extra["symbol"] else f"the literal at {finding.location()}"
        intent = f" That keeps `{_KEY_INTENT}` ({extra['intent']}) true: the caller's vb_live_ bearer key never follows a caller-chosen URL." if extra["intent"] else ""
        tests = f"3. Update the tests that pin the old origin in the same change: {extra['tests']}." if extra["tests"] else "3. Search tests/ for the old origin and update any assertion that pins it."
        return "\n".join((
            f"1. Change the origin of {name} to the live host the contract lists, {first_live}, and keep the path {extra['path']}.",
            f"2. If the host must be configurable, add a base-URL setting whose default is {first_live} and reject any override that is not one of the contract's live hosts.{intent}",
            tests,
            "4. Run `python lint/run.py --rule C018` and `python lint/run.py --rule C017`, so the moved requests are still checked against contract routes.",
        ))


RULE = CanonicalApiHostRule()
