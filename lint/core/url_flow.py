"""FILE: lint/core/url_flow.py

PURPOSE: Finds every call in vidbyte/ that receives a `url` argument, traces its URL, HTTP method, and headers, and reports the requests whose origin is a Vidbyte host; also lists every Vidbyte API URL literal in production code and which traced requests each one reaches.
ROLE IN CODEBASE: Shared by rule C017 (platform-route-contract), which checks each traced request against the vendored platform contract, and rule C018 (canonical-api-host), which lists the requests a non-live host literal would carry. It evaluates expressions with lint/core/string_flow.py over the source model in lint/core/python_index.py, and lint/core/platform_contract.py decides which origins are Vidbyte's.
ARCHITECTURE NOTE: A request call whose callee passes its own `url` parameter to another request call is traced at that inner call instead, so a helper's request is judged once, with the method and headers the helper really sends. When a request's URL, method, or headers depend on the enclosing function's parameters (other than a hole that fills one whole path segment), the call is re-evaluated once per traced caller, up to MAX_CALLER_HOPS levels, and the finding is anchored at the outermost caller that supplied the URL.
FUNCTION INVENTORY: TracedRequest, UrlLiteral, UrlFlowTrace (requests_using, unreached) records; UrlFlowTracer.trace; trace_catalog (one cached trace per catalogue and contract, shared by C017 and C018).
COMMON MODIFICATION PATTERNS: A new request-call convention (another argument name for the URL, method, or headers) changes URL_PARAM, METHOD_PARAM, or HEADERS_PARAM handling here, with a C017 scratch fixture.
WHAT NOT TO DO: Do not import vidbyte, contact the network, or drop a request because tracing it is expensive; raise TraceLimitExceeded instead.
KNOWN EDGE CASES: A URL built through an untyped receiver, getattr, a lambda, or a container lookup is a hole, so its literal then reaches no traced request and UrlFlowTrace.unreached reports it. Docstrings and bare string statements are not URL literals.
RELATED DOCS: docs/design/lint-sdk-cross-repo-contracts.md (C017 and C018 sections).
TESTS: python lint/run.py --rule C017 and --rule C018; scratch fixtures and mutants are recorded in the S4 pull request body.
"""

from __future__ import annotations

import ast
import re
import weakref
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from lint.core.discovery import SourceCatalog
from lint.core.platform_contract import UrlOrigin, VidbyteHosts
from lint.core.python_index import FunctionFacts, ModuleFacts, ModuleIndex, direct_calls
from lint.core.string_flow import UNKNOWN_CREDENTIAL, Binding, Frame, StringFlowEvaluator, StringValue, TraceLimitExceeded

MAX_CALLER_HOPS = 3
MAX_CONTEXTS = 256
URL_PARAM = "url"
METHOD_PARAM = "method"
HEADERS_PARAM = "headers"
_TRACES: weakref.WeakKeyDictionary[SourceCatalog, tuple[str, UrlFlowTrace]] = weakref.WeakKeyDictionary()
_URL_IN_TEXT = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s\"'<>`)\]]+")


@dataclass(frozen=True, slots=True)
class TracedRequest:
    """One HTTP request the SDK can send to a Vidbyte origin, anchored at the call that supplied its URL."""

    rel: str
    line: int
    source_line: str
    site: str
    via: tuple[str, ...]
    url: StringValue
    origin: UrlOrigin
    path: tuple[str | None, ...]
    path_display: str
    methods: tuple[str, ...]
    method_unresolved: bool
    credentials: frozenset[str]

    @property
    def location(self) -> str:
        return f"{self.rel}:{self.line}"


@dataclass(frozen=True, slots=True)
class UrlLiteral:
    """A Vidbyte API URL spelled in a string literal (or f-string part) in production code."""

    rel: str
    line: int
    source_line: str
    symbol: str
    url: str
    origin: UrlOrigin
    whole: bool

    @property
    def location(self) -> str:
        return f"{self.rel}:{self.line}"


@dataclass(frozen=True, slots=True)
class UrlFlowTrace:
    """The traced Vidbyte requests and the Vidbyte API URL literals, with which requests each literal reaches."""

    requests: tuple[TracedRequest, ...]
    literals: tuple[UrlLiteral, ...]

    def requests_using(self, literal: UrlLiteral) -> tuple[TracedRequest, ...]:
        return tuple(request for request in self.requests if literal.location in request.url.literal_origins())

    def unreached(self) -> tuple[UrlLiteral, ...]:
        # Whole-value URL literals that no traced request is built from: the trace cannot prove what they call.
        return tuple(literal for literal in self.literals if literal.whole and not self.requests_using(literal))


def trace_catalog(catalog: SourceCatalog, hosts: VidbyteHosts) -> UrlFlowTrace:
    # One trace per catalogue and contract text, so C017 and C018 in the same lint run trace the SDK once.
    cached = _TRACES.get(catalog)
    if cached is not None and cached[0] == hosts.contract.text:
        return cached[1]
    trace = UrlFlowTracer(catalog, hosts).trace()
    _TRACES[catalog] = (hosts.contract.text, trace)
    return trace


class UrlFlowTracer:
    """Finds every request call in vidbyte/, traces its URL, method, and headers, and keeps the Vidbyte requests."""

    def __init__(self, catalog: SourceCatalog, hosts: VidbyteHosts) -> None:
        # Builds the module index once; the caller index is built lazily on the first parameter-dependent request.
        self.catalog = catalog
        self.hosts = hosts
        self.index = ModuleIndex(catalog)
        self.evaluator = StringFlowEvaluator(self.index)
        self._sources = {source.rel: source for source in catalog.python_files()}
        self._url_callees = self._url_callee_names()
        self._calls_by_name: dict[str, list[tuple[ast.Call, Frame]]] | None = None

    def trace(self) -> UrlFlowTrace:
        # Every request site in every module, deduplicated by anchor, method, and URL.
        requests: dict[tuple[str, int, tuple[str, ...], bool, str], TracedRequest] = {}
        for call, frame in self._all_calls():
            for request in self._site_requests(call, frame):
                requests.setdefault((request.rel, request.line, request.methods, request.method_unresolved, request.url.text), request)
        ordered = tuple(sorted(requests.values(), key=lambda item: (item.rel, item.line, item.path_display, item.methods)))
        return UrlFlowTrace(ordered, self._literals())

    def _url_callee_names(self) -> frozenset[str]:
        # Names of vidbyte functions, methods, and classes that accept a positional `url`: the only calls a positional URL can reach.
        names: set[str] = set()
        for module in self.index.modules.values():
            for function in self._functions(module):
                if URL_PARAM in [arg.arg for arg in function.positional()]:
                    names.add(function.node.name)
                    if function.node.name == "__init__" and function.owner is not None:
                        names.add(function.owner.name)
            for cls in module.classes.values():
                if cls.is_dataclass and URL_PARAM in cls.fields:
                    names.add(cls.name)
        return frozenset(names)

    def _all_calls(self) -> Iterator[tuple[ast.Call, Frame]]:
        # Every call with the frame it executes in: module and class bodies, and every function body.
        for module in self.index.modules.values():
            tree = module.source.tree
            if tree is None:
                continue
            for call in direct_calls(tree.body):
                yield call, Frame(module=module)
            for function in self._functions(module):
                for call in self.index.body(function).calls:
                    yield call, Frame(module=module, function=function)
            for cls in module.classes.values():
                for call in direct_calls([statement for statement in cls.node.body if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef))]):
                    yield call, Frame(module=module, class_body=cls)

    def _functions(self, module: ModuleFacts) -> Iterator[FunctionFacts]:
        # Every function definition in the module, nested ones included; methods of module-level classes know their owner.
        tree = module.source.tree
        if tree is None:
            return
        owners = {id(method): cls for cls in module.classes.values() for method in cls.methods.values()}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield self.index.function(module, node, owners.get(id(node)))

    def _url_argument(self, call: ast.Call, frame: Frame) -> ast.expr | None:
        # The URL a call receives: a `url=` keyword, or the positional argument a known callee binds to `url`.
        for keyword in call.keywords:
            if keyword.arg == URL_PARAM:
                return keyword.value
        name = call.func.id if isinstance(call.func, ast.Name) else call.func.attr if isinstance(call.func, ast.Attribute) else ""
        if not call.args or name not in self._url_callees:
            return None
        _, expr, _ = self.evaluator.argument(call, URL_PARAM, frame)
        return expr

    def _site_requests(self, call: ast.Call, frame: Frame) -> list[TracedRequest]:
        # A call that receives a URL; when its callee forwards that URL into its own request call, it is traced there instead.
        url_expr = self._url_argument(call, frame)
        if url_expr is None or self._forwards_url(call, frame):
            return []
        site = frame.module.location(call)
        url_needed, other_needed = self._needed(call, url_expr, frame)
        results: list[TracedRequest] = []
        for context, via in self._contexts(frame, url_needed | other_needed, 0, site):
            # The finding belongs where the URL was built: the site, or the outermost caller that supplied the URL.
            anchor = via[0] if via and url_needed else site
            results.extend(self._requests_in(call, url_expr, context, site, via, anchor))
        return results

    def _forwards_url(self, call: ast.Call, frame: Frame) -> bool:
        # True when a callee builds another request call's URL from its own `url` parameter.
        for target in self.evaluator.targets(call.func, frame):
            function = target.function
            if function is None or URL_PARAM not in function.param_names():
                continue
            inner = Frame(module=function.module, function=function)
            marker = id(function.node)
            for inner_call in self.index.body(function).calls:
                expr = self._url_argument(inner_call, inner)
                if expr is not None and any(piece.param == URL_PARAM and piece.function == marker for value in self.evaluator.values(expr, inner) for piece in value.pieces):
                    return True
        return False

    def _needed(self, call: ast.Call, url_expr: ast.expr, frame: Frame) -> tuple[set[str], set[str]]:
        # The enclosing function's parameters a caller must bind to settle this request: (for the URL, for method and headers).
        # A hole that fills one whole path segment (like /runs/{run_id}/close) is a route parameter and needs no caller.
        function = frame.function
        if function is None:
            return set(), set()
        marker = id(function.node)
        url_needed: set[str] = set()
        for value in self.evaluator.values(url_expr, frame):
            url_needed |= self._unsettled_params(value, marker)
        other: set[str] = set()
        has_method, method_expr, _ = self.evaluator.argument(call, METHOD_PARAM, frame)
        if has_method and method_expr is not None:
            other |= {piece.param for value in self.evaluator.values(method_expr, frame) for piece in value.pieces if piece.text is None and piece.function == marker and piece.param}
        _, headers_expr, _ = self.evaluator.argument(call, HEADERS_PARAM, frame)
        params = function.param_names() - {function.receiver_name()}
        if isinstance(headers_expr, ast.Name) and headers_expr.id in params:
            other.add(headers_expr.id)
        elif isinstance(headers_expr, ast.Dict):
            other |= {value.id for key, value in zip(headers_expr.keys, headers_expr.values, strict=True) if key is None and isinstance(value, ast.Name) and value.id in params}
        return url_needed, other

    def _unsettled_params(self, value: StringValue, marker: int) -> set[str]:
        # Parameter holes that leave the origin unknown, or that sit inside or across path segments of a Vidbyte URL.
        params = {piece.param for piece in value.pieces if piece.text is None and piece.function == marker and piece.param}
        if not params:
            return set()
        origin = UrlOrigin.parse(value.literal_prefix())
        if origin is None:
            # Callers can settle an unknown origin only when the first hole is one of this function's parameters.
            first_hole = next(piece for piece in value.pieces if piece.text is None)
            return params if first_hole.function == marker and first_hole.param else set()
        if not self.hosts.is_vidbyte(origin):
            return set()
        texts = [piece.text for piece in value.pieces]
        unsettled: set[str] = set()
        for index, piece in enumerate(value.pieces):
            if piece.text is not None or piece.function != marker or not piece.param:
                continue
            before = "".join(text for text in texts[:index] if text is not None)
            after = next((text for text in texts[index + 1:] if text), "")
            bounded = before.endswith("/") and (after == "" or after[0] in "/?#") and all(text is not None for text in texts[:index])
            if not bounded or (index + 1 < len(texts) and texts[index + 1] is None):
                unsettled.add(piece.param)
        return unsettled

    def _contexts(self, frame: Frame, needed: set[str], hops: int, site: str) -> list[tuple[Frame, tuple[str, ...]]]:
        # The frame itself, or, when the request is built from the function's parameters, one bound frame per traced caller.
        function = frame.function
        if function is None or not needed or hops >= MAX_CALLER_HOPS:
            return [(frame, ())]
        contexts: list[tuple[Frame, tuple[str, ...]]] = []
        for caller_call, caller_frame in self._callers(function):
            for target in self.evaluator.targets(caller_call.func, caller_frame):
                if target.function is None or target.function.node is not function.node:
                    continue
                caller_needed = self._needed_in_caller(self.evaluator.bind(target, caller_call, caller_frame), needed, caller_frame)
                for caller_context, caller_via in self._contexts(caller_frame, caller_needed, hops + 1, site):
                    bound = Frame(module=function.module, function=function, args=self.evaluator.bind(target, caller_call, caller_context), receiver=target.receiver)
                    contexts.append((bound, (*caller_via, caller_frame.module.location(caller_call))))
                    if len(contexts) > MAX_CONTEXTS:
                        raise TraceLimitExceeded(f"{site} is reached through more than {MAX_CONTEXTS} caller contexts; raise MAX_CONTEXTS in lint/core/url_flow.py with a fixture.")
        return contexts or [(frame, ())]

    def _needed_in_caller(self, bindings: Mapping[str, Binding], needed: set[str], caller_frame: Frame) -> set[str]:
        # The caller's own parameters that flow into the arguments the callee's request depends on.
        function = caller_frame.function
        if function is None:
            return set()
        marker = id(function.node)
        found: set[str] = set()
        for name in needed:
            binding = bindings.get(name)
            if binding is None or binding.expr is None:
                continue
            found |= {piece.param for value in self.evaluator.values(binding.expr, caller_frame) for piece in value.pieces if piece.text is None and piece.function == marker and piece.param}
            found |= {node.id for node in ast.walk(binding.expr) if isinstance(node, ast.Name) and node.id in function.param_names() and node.id != function.receiver_name()}
        return found

    def _callers(self, function: FunctionFacts) -> list[tuple[ast.Call, Frame]]:
        # Calls anywhere in vidbyte/ that resolve to this function (matched by name first, then by full resolution).
        if self._calls_by_name is None:
            index: dict[str, list[tuple[ast.Call, Frame]]] = {}
            for call, frame in self._all_calls():
                name = call.func.id if isinstance(call.func, ast.Name) else call.func.attr if isinstance(call.func, ast.Attribute) else ""
                if name:
                    index.setdefault(name, []).append((call, frame))
            self._calls_by_name = index
        candidates = self._calls_by_name.get(function.node.name, [])
        return [(call, frame) for call, frame in candidates if any(target.function is not None and target.function.node is function.node for target in self.evaluator.targets(call.func, frame))]

    def _requests_in(self, call: ast.Call, url_expr: ast.expr, frame: Frame, site: str, via: tuple[str, ...], anchor: str) -> list[TracedRequest]:
        # Evaluates the URL, method, and headers in one context and keeps the values whose origin is a Vidbyte host.
        results: list[TracedRequest] = []
        anchor_rel, _, anchor_text = anchor.rpartition(":")
        anchor_line = int(anchor_text)
        source = self._sources.get(anchor_rel)
        methods: tuple[tuple[str, ...], bool] | None = None
        credentials: frozenset[str] = frozenset({UNKNOWN_CREDENTIAL})
        for value in self.evaluator.values(url_expr, frame):
            parsed = self._split(value)
            if parsed is None:
                continue
            if methods is None:
                methods = self._methods(call, frame)
                _, headers_expr, _ = self.evaluator.argument(call, HEADERS_PARAM, frame)
                credentials = self.evaluator.credentials(headers_expr, frame)
            origin, path, display = parsed
            results.append(TracedRequest(rel=anchor_rel, line=anchor_line, source_line=source.line_at(anchor_line).strip() if source is not None else "", site=site, via=via, url=value, origin=origin, path=path, path_display=display, methods=methods[0], method_unresolved=methods[1], credentials=credentials))
        return results

    def _methods(self, call: ast.Call, frame: Frame) -> tuple[tuple[str, ...], bool]:
        # The upper-cased literal methods this call sends, and whether any possible method is unknown.
        has_method, method_expr, _ = self.evaluator.argument(call, METHOD_PARAM, frame)
        method_frame: Frame | None = frame
        if not has_method:
            method_expr, method_frame = self._default_method(call, frame)
        if method_expr is None or method_frame is None:
            return (), True
        values = self.evaluator.values(method_expr, method_frame)
        methods = tuple(sorted({value.text.upper() for value in values if value.is_literal}))
        return methods, any(not value.is_literal for value in values) or not methods

    def _default_method(self, call: ast.Call, frame: Frame) -> tuple[ast.expr | None, Frame | None]:
        # The callee's declared default for `method` (a parameter default or a dataclass field default), when the call omits it.
        for target in self.evaluator.targets(call.func, frame):
            _, names, declaring = self.evaluator.parameters(target)
            if METHOD_PARAM not in names:
                continue
            if declaring is not None:
                default = declaring.default(METHOD_PARAM)
                if default is not None:
                    return default, Frame(module=declaring.module, class_body=declaring.owner)
            elif target.cls is not None:
                for cls in self.index.bases(target.cls):
                    values = cls.constants.get(METHOD_PARAM, [])
                    if values and values[-1] is not None:
                        return values[-1], Frame(module=cls.module, class_body=cls)
        return None, None

    def _split(self, value: StringValue) -> tuple[UrlOrigin, tuple[str | None, ...], str] | None:
        # The Vidbyte origin at the start of a value, its path pieces with query and fragment removed, and a display form.
        origin = UrlOrigin.parse(value.literal_prefix())
        if origin is None or not self.hosts.is_vidbyte(origin):
            return None
        pieces: list[str | None] = []
        display: list[str] = []
        skip = origin.end
        for piece in value.pieces:
            if piece.text is None:
                pieces.append(None)
                display.append("{" + (piece.label or "?") + "}")
                continue
            text = piece.text[skip:]
            skip = max(0, skip - len(piece.text))
            cut = re.search(r"[?#]", text)
            kept = text[: cut.start()] if cut is not None else text
            if kept:
                pieces.append(kept)
                display.append(kept)
            if cut is not None:
                break
        return origin, tuple(pieces), "".join(display)

    def _literals(self) -> tuple[UrlLiteral, ...]:
        # Vidbyte API URLs spelled in non-docstring string literals and f-string parts under vidbyte/.
        found: list[UrlLiteral] = []
        for source in self.catalog.python_files():
            if source.tree is None:
                continue
            docstrings = _docstring_ids(source.tree)
            symbols = _assigned_symbols(source.tree)
            for node in ast.walk(source.tree):
                if not isinstance(node, ast.Constant) or not isinstance(node.value, str) or id(node) in docstrings:
                    continue
                for match in _URL_IN_TEXT.finditer(node.value):
                    origin = UrlOrigin.parse(match.group(0))
                    if origin is None or not self.hosts.is_api_surface(origin, match.group(0)[origin.end:]):
                        continue
                    found.append(UrlLiteral(rel=source.rel, line=node.lineno, source_line=source.line_at(node.lineno).strip(), symbol=symbols.get(id(node), ""), url=match.group(0), origin=origin, whole=match.start() == 0))
        return tuple(found)


def _docstring_ids(tree: ast.Module) -> set[int]:
    # Every bare string expression statement: docstrings and string-as-comment blocks are not code values.
    return {id(node.value) for node in ast.walk(tree) if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)}


def _assigned_symbols(tree: ast.Module) -> dict[int, str]:
    # Maps a string constant (directly or inside an f-string) to the name its assignment binds.
    symbols: dict[int, str] = {}
    for node in ast.walk(tree):
        targets: list[ast.expr] = list(node.targets) if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) and node.value is not None else []
        value = node.value if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
        names = [target.id if isinstance(target, ast.Name) else target.attr if isinstance(target, ast.Attribute) else "" for target in targets]
        name = next((item for item in names if item), "")
        if value is None or not name:
            continue
        for inner in ast.walk(value):
            if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                symbols.setdefault(id(inner), name)
    return symbols
