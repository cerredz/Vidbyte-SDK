"""FILE: lint/rules/c017_platform_route_contract.py

PURPOSE: Detect SDK HTTP requests to a Vidbyte host whose path, method, or credential does not match a route in the vendored platform contract, requests whose route or method cannot be determined statically, and Vidbyte API URL literals that no traced request uses.
ROLE IN CODEBASE: Enforces C017, the SDK consumer side of cross-repo contract X05. cerredz/Vidbyte generates lint/contracts/vidbyte-platform-contract.json from its backend RouteRule declarations; this rule proves every request the SDK sends to the platform names one of those routes with an accepted method and access class.
ARCHITECTURE NOTE: lint/core/url_flow.py finds request calls and traces their URL, method, and headers; lint/core/platform_contract.py loads the contract (failing closed) and matches paths. This module only judges each traced request and explains the result.
FUNCTION INVENTORY: RouteJudge.judge classifies one traced request; UntracedUrls lists literals no request uses; PlatformRouteContractRule reports and explains.
COMMON MODIFICATION PATTERNS: A new access class in the contract needs an ACCESS_ACCEPTS entry stating which SDK credentials it admits. A new kind needs a branch in RouteJudge, what/repair text, and a scratch fixture.
WHAT NOT TO DO: Do not import vidbyte, contact the network, edit the vendored contract, or treat an untraceable request as passing.
KNOWN EDGE CASES: A hole filling one path segment matches a contract `{param}`; a hole spanning segments leaves the route unresolved when it fits several contract paths. The SDK holds no browser session, so any SESSION route is an access mismatch whatever the headers say. Headers the tracer cannot read leave API_KEY and PUBLIC access unchecked.
RELATED DOCS: docs/design/lint-sdk-cross-repo-contracts.md (C017); lint/contracts/README.md; lint catalog X05.
TESTS: python lint/run.py --rule C017; scratch fixtures, fail-closed contract cases, and mutants are recorded in the S4 pull request body.
"""

from __future__ import annotations

from dataclasses import dataclass

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog
from lint.core.platform_contract import PLATFORM_CONTRACT_REL, REFRESH_DOC_REL, PlatformContract, PlatformContractLoader, PlatformRoute, RouteMatcher, VidbyteHosts
from lint.core.registry import Rule
from lint.core.string_flow import API_KEY, NO_CREDENTIAL, UNKNOWN_CREDENTIAL
from lint.core.url_flow import TracedRequest, UrlFlowTrace, UrlLiteral, trace_catalog

_UNKNOWN_ROUTE = "unknown-route"
_PATH_UNRESOLVED = "path-unresolved"
_METHOD_UNRESOLVED = "method-unresolved"
_METHOD_MISMATCH = "method-mismatch"
_ACCESS_MISMATCH = "access-mismatch"
_UNTRACED = "untraced-url"
_KINDS = frozenset({_UNKNOWN_ROUTE, _PATH_UNRESOLVED, _METHOD_UNRESOLVED, _METHOD_MISMATCH, _ACCESS_MISMATCH, _UNTRACED})
_SESSION = "SESSION"
# Which SDK credentials each contract access class admits. The SDK holds a Vidbyte API key or nothing; never a browser session.
ACCESS_ACCEPTS: dict[str, frozenset[str]] = {"API_KEY": frozenset({API_KEY}), "PUBLIC": frozenset({API_KEY, NO_CREDENTIAL}), _SESSION: frozenset()}
_CREDENTIAL_TEXT = {API_KEY: "the caller's Vidbyte API key in an Authorization header", NO_CREDENTIAL: "no Authorization header"}
_LISTED = 5


class UnknownAccessClass(RuntimeError):
    """The contract gives a route an access class C017 has no credential rule for; guessing would hide or invent findings."""


@dataclass(frozen=True, slots=True)
class Verdict:
    """The first contract disagreement found for one traced request, with the routes it was judged against."""

    kind: str
    routes: tuple[PlatformRoute, ...]
    detail: str


class RouteJudge:
    """Judges one traced request against the contract: route, then method, then access."""

    def __init__(self, contract: PlatformContract) -> None:
        self.contract = contract
        self.matcher = RouteMatcher(contract.routes)

    def judge(self, request: TracedRequest) -> Verdict | None:
        # The route must be unique, the method known and accepted, and the credential admitted by the route's access class.
        matches = self.matcher.match(request.path)
        if not matches:
            return Verdict(_UNKNOWN_ROUTE, self.matcher.closest(request.path_display), "")
        literal_path = "".join(piece for piece in request.path if piece is not None) if None not in request.path else ""
        exact = tuple(route for route in matches if not route.has_params and route.path == literal_path)
        routes = exact or matches
        if len({route.normalized_path for route in routes}) > 1:
            return Verdict(_PATH_UNRESOLVED, routes, "")
        allowed = sorted({method for route in routes for method in route.methods})
        if request.method_unresolved:
            return Verdict(_METHOD_UNRESOLVED, routes, ", ".join(allowed))
        wrong = [method for method in request.methods if method not in allowed]
        if wrong:
            return Verdict(_METHOD_MISMATCH, routes, ", ".join(wrong))
        for route in routes:
            if not set(route.methods) & set(request.methods):
                continue
            if route.access not in ACCESS_ACCEPTS:
                raise UnknownAccessClass(f"{self.contract.cite(self.contract.route_line(route))} gives route {route.name} access class {route.access!r}, which C017 has no rule for. Add it to ACCESS_ACCEPTS in lint/rules/c017_platform_route_contract.py, stating which SDK credentials it admits, before relying on C017.")
            if self._rejects(route.access, request.credentials):
                return Verdict(_ACCESS_MISMATCH, (route,), route.access)
        return None

    @staticmethod
    def _rejects(access: str, credentials: frozenset[str]) -> bool:
        # A SESSION route rejects every SDK request; otherwise only fully known credentials can be judged.
        if access == _SESSION:
            return True
        if UNKNOWN_CREDENTIAL in credentials:
            return False
        return not credentials & ACCESS_ACCEPTS[access]


class PlatformRouteContractRule(Rule):
    """Requires every SDK request to a Vidbyte host to match a contract route's path, method, and access class."""

    id = "C017"
    name = "platform-route-contract"
    severity = "blocking"
    summary = "Every HTTP request the SDK sends to a Vidbyte host must go to a route in lint/contracts/vidbyte-platform-contract.json, with a method that route accepts and a credential its access class admits; the route and method must be statically determinable, and every Vidbyte API URL literal must reach a traced request."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Load the contract (raising when it is unusable), trace the requests, and judge each one.
        contract = PlatformContractLoader.load(catalog)
        trace = trace_catalog(catalog, VidbyteHosts(contract))
        judge = RouteJudge(contract)
        findings = [finding for request in trace.requests if (finding := self._request_finding(contract, judge, request)) is not None]
        findings.extend(self._untraced_finding(literal, trace) for literal in trace.unreached())
        return findings

    def _request_finding(self, contract: PlatformContract, judge: RouteJudge, request: TracedRequest) -> Finding | None:
        verdict = judge.judge(request)
        if verdict is None:
            return None
        routes = "; ".join(f"{route.name} {'/'.join(route.methods)} {route.path} ({route.access}, {contract.cite(contract.route_line(route))})" for route in verdict.routes[:_LISTED])
        more = f"; and {len(verdict.routes) - _LISTED} more" if len(verdict.routes) > _LISTED else ""
        methods = "/".join(request.methods) if request.methods else "an unknown method"
        extra = {
            "kind": verdict.kind,
            "request": f"{methods} {request.origin.origin}{request.path_display}",
            "methods": methods,
            "path": request.path_display or "/",
            "origin": request.origin.origin,
            "site": request.site,
            "via": " -> ".join((*request.via, request.site)) if request.via else request.site,
            "trail": "; ".join(request.url.trail) if request.url.trail else f"a literal at {request.site}",
            "credential": self._credential_text(request.credentials),
            "routes": routes + more,
            "route_count": str(len(verdict.routes)),
            "detail": verdict.detail,
            "contract_commit": contract.source_commit,
        }
        return Finding(rule_id=self.id, rel_path=request.rel, line=request.line, source_line=request.source_line, symbol=f"{methods} {request.path_display or '/'}", extra=extra)

    def _untraced_finding(self, literal: UrlLiteral, trace: UrlFlowTrace) -> Finding:
        extra = {"kind": _UNTRACED, "url": literal.url, "symbol": literal.symbol, "traced": str(len(trace.requests))}
        return Finding(rule_id=self.id, rel_path=literal.rel, line=literal.line, source_line=literal.source_line, symbol=literal.symbol or literal.url, extra=extra)

    @staticmethod
    def _credential_text(credentials: frozenset[str]) -> str:
        known = [_CREDENTIAL_TEXT[item] for item in sorted(credentials) if item in _CREDENTIAL_TEXT]
        if UNKNOWN_CREDENTIAL in credentials:
            known.append("headers C017 cannot read statically")
        return " or ".join(known)

    def explain(self, finding: Finding) -> Diagnostic:
        # One what/repair pair per kind, sharing the consequence, examples, and rejected shortcuts.
        kind = finding.extra.get("kind", "")
        if kind not in _KINDS:
            raise ValueError(f"C017 finding has unknown kind {kind!r}.")
        return Diagnostic(
            what_happened=self._what(finding, kind),
            why_blocked=f"The Vidbyte backend serves only the routes its RouteRule declarations register, and {PLATFORM_CONTRACT_REL} is generated from those declarations (cerredz/Vidbyte scripts/generate-platform-contract.py, B065). A request to a path the contract does not list returns 404, a method it does not accept returns 405, and a credential its access class does not admit returns 401 or 403, so the SDK feature behind the request fails for every user (lint catalog X05; docs/design/lint-sdk-cross-repo-contracts.md). A request C017 cannot resolve statically, or a Vidbyte URL it cannot follow to a request, could break the same way without any check noticing.",
            how_to_fix=self._repair(finding, kind),
            correct_examples=(
                "vidbyte/providers/typesafe.py:177 - `_TypeSafeHttpCall` gets `method=\"POST\"`, a URL built from `DecisionModelConfig.resolved_endpoint` plus `JEV_SYSTEMONE_PATH`, and `HttpResponseParser.bearer_headers`, which trace to contract route models.typesafe.systemone (POST, API_KEY).",
                "vidbyte/lib/dataclasses/model_configs.py:419 `resolved_run_close_url` - `JEV_MANAGED_RUN_CLOSE_PATH.format(run_id=run_id)` keeps {run_id} as one path segment, which matches contract route models.runs.close (POST /api/v1/models/runs/{run_id}/close).",
            ),
            will_not_work=(
                "Changing the path, method, or headers until C017 passes without checking the backend: the contract mirrors what the backend serves, so the request must change to what the backend actually accepts, or the backend must add the route first.",
                f"Editing {PLATFORM_CONTRACT_REL} to add or change a route: the copy must stay byte-identical to cerredz/Vidbyte. Land the backend route there first, then re-vendor as {REFRESH_DOC_REL} describes.",
                "Building the URL through getattr, a dict lookup, an untyped helper, or a computed method so C017 cannot see it: an unresolved request or an untraced Vidbyte URL is itself a C017 finding.",
                "Raising C017's baseline in lint/baseline.json: the baseline is 0, and every finding is a platform request that fails or cannot be checked.",
            ),
            verify=self.verify_command(),
        )

    @staticmethod
    def _what(finding: Finding, kind: str) -> str:
        # States the request, how its URL was built, and exactly what the contract says instead.
        extra = finding.extra
        where = finding.location()
        if kind == _UNTRACED:
            holder = f"`{extra['symbol']}` holds" if extra["symbol"] else "a string literal holds"
            return f"{where} {holder} the Vidbyte API URL {extra['url']}, but no traced Vidbyte request is built from it ({extra['traced']} were traced), so C017 cannot tell which routes the SDK calls with it."
        request = f"{where} sends {extra['request']} (request call {extra['via']}; URL built from {extra['trail']})"
        contract = f"{PLATFORM_CONTRACT_REL} (cerredz/Vidbyte at {extra['contract_commit'][:8]})"
        if kind == _UNKNOWN_ROUTE:
            return f"{request}, but no route in {contract} has the path {extra['path']}. The closest contract routes are: {extra['routes']}."
        if kind == _PATH_UNRESOLVED:
            return f"{request}, but the parts of its path known only at run time let it match {extra['route_count']} different contract paths, so C017 cannot tell which route it calls: {extra['routes']}."
        if kind == _METHOD_UNRESOLVED:
            return f"{request}, but its HTTP method is not a literal C017 can resolve at the call or from the callee's default. The contract route accepts {extra['detail']}: {extra['routes']}."
        if kind == _METHOD_MISMATCH:
            return f"{request} with method {extra['detail']}, which the contract route does not accept: {extra['routes']}."
        return f"{request} carrying {extra['credential']}, but the contract route has access class {extra['detail']}, which does not admit it: {extra['routes']}."

    @staticmethod
    def _repair(finding: Finding, kind: str) -> str:
        # Numbered steps for this kind, ending with the focused check.
        extra = finding.extra
        verify = "Run `python lint/run.py --rule C017`."
        if kind == _UNTRACED:
            return "\n".join((
                f"1. Find the request that uses {extra['url']} and pass the URL to it as `url=` through constructs C017 traces: constants, f-strings, `+`, `str.format`, `removeprefix`/`removesuffix`/`strip`, and methods called on a receiver whose class is annotated or constructed in the same function.",
                "2. If the request already does that but goes through an idiom C017 cannot follow, extend lint/core/url_flow.py with a scratch fixture instead of reshaping product code around the linter.",
                f"3. If the value is never requested (for example a link shown to users), point it at the website rather than an API host, or delete it if nothing reads it. {verify}",
            ))
        if kind in {_UNKNOWN_ROUTE, _PATH_UNRESOLVED}:
            first = "Compare the path with the closest contract routes above; a typo, a missing /api/v1 prefix, or a stale path segment is the usual cause." if kind == _UNKNOWN_ROUTE else "Make the route visible at the request: build the path from constants and literals, and keep any runtime value to one whole path segment (for example `/runs/{run_id}/close` via `str.format`)."
            return "\n".join((
                f"1. {first}",
                f"2. If the backend really serves this path, add the route in cerredz/Vidbyte first, regenerate its contract, and re-vendor it as {REFRESH_DOC_REL} describes.",
                f"3. Keep the constant that holds the path in vidbyte/lib/constants/ beside the endpoint it extends. {verify}",
            ))
        if kind in {_METHOD_UNRESOLVED, _METHOD_MISMATCH}:
            return "\n".join((
                f"1. Pass the method as a literal at the request call, `method=\"{extra['detail'].split(', ')[0]}\"`, using a method the contract route lists." if kind == _METHOD_UNRESOLVED else f"1. Change the method at {extra['site']} to one the contract route lists, or confirm in cerredz/Vidbyte that the backend accepts {extra['detail']} and update the route there first.",
                "2. If the method comes from a helper parameter, pass the literal at every caller; C017 follows callers up to three levels.",
                f"3. {verify}",
            ))
        return "\n".join((
            "1. Send the credential the route's access class admits: API_KEY routes need the caller's Vidbyte API key as `Authorization: Bearer vb_live_...` (HttpResponseParser.bearer_headers), PUBLIC routes need nothing, and SESSION routes are browser-only and must not be called from the SDK.",
            "2. If the SDK needs a SESSION-only capability, ask for an API_KEY route in cerredz/Vidbyte and re-vendor the contract once it exists.",
            f"3. {verify}",
        ))


RULE = PlatformRouteContractRule()
