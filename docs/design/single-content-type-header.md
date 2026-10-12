# Design Doc: Single Content-Type Header

**Status:** Draft
**Author:** Claude
**Created:** 2026-10-12
**Last Updated:** 2026-10-12

---

## 1. Overview

`HttpTransport` adds a default `content-type: application/json` to every JSON request with `dict.setdefault`. `setdefault` is case-sensitive, but HTTP header names are not. A caller that already passes `Content-Type` therefore ends up with two keys. On the async httpx path, httpx sends both lines, and the server reads `content-type: application/json, application/json`. Exa rejects that with HTTP 400. Since the backend moved to SDK v0.2.1, every research search has failed this way. This change adds the default only when no content-type header is present in any spelling, so each request carries exactly one.

---

## 2. Goals & Non-Goals

### Goals
- Every JSON request from `HttpTransport` carries exactly one content-type header.
- A caller's own content-type, in any capitalization, is kept and never overridden.
- One helper owns the rule, and all four JSON send sites use it.

### Non-Goals
- Changing any client's `_headers()`. The transport is the single place where the default is added.
- Adding the provider's response body to `ProviderRequestError` from `_require_ok`. That would have made this failure easier to diagnose, but it's a separate change.
- Changing retry, timeout, or idempotency behavior.

---

## 3. Background & Context

- **Evidence from production (2026-10-12):** a one-off job on the backend service used the production Exa key.
  - `urllib` POSTs of the exact `ExaClient` body returned 200 in all five variants tried: highlights styles, result counts, and with or without contents.
  - The stock SDK `ExaClient` returned 400.
  - An `ExaClient` subclass whose `_headers()` uses the lowercase `content-type` returned 200 with 20 hits.
- **Why only httpx:** `urllib.request.Request` normalizes header names with `str.capitalize()`, so `Content-Type` and `content-type` collapse into one key. httpx keeps each entry, so `client.build_request(..., headers={"Content-Type": ..., "content-type": ...})` sends two lines.
- **Who is affected:** every web operation client that sends `"Content-Type"` through `request_json`: Exa, Firecrawl, Browserbase, Parallel, and Tavily. Exa is confirmed to reject the doubled header. The others depend on how strictly each vendor parses it.
- **Constraint:** the backend pins the SDK by commit, so the fix also has to be cherry-picked onto v0.2.1 for the backend. That is a separate backend change.

---

## 4. Requirements

### Functional Requirements
1. When `json_body` is given and no header name equals `content-type` case-insensitively, the transport adds `content-type: application/json`.
2. When the caller supplies a content-type in any capitalization, the transport adds nothing and keeps the caller's value.
3. When `json_body` is `None`, the transport adds no content-type.
4. The rule applies to the async `HttpTransport._send_once`, `SyncHttpTransport.request_bytes`, the SSE stream, and `SyncHttpTransport._send_once`.

### Non-Functional Requirements
- **Performance:** one pass over a handful of header names per request, which is negligible.
- **Security:** no header values are logged or changed apart from the content-type default.
- **Reliability:** requests that worked before are unchanged. A request that carried a duplicate header now carries a single one.

---

## 5. High-Level Design

A module-level helper `_json_request_headers(headers)` in `vidbyte/lib/http/transport.py` returns a copy of the caller's headers. It adds `content-type: application/json` only when no existing name matches case-insensitively. The four JSON send sites call it in place of `dict(headers)` followed by `setdefault`.

```
ExaClient._headers() {"x-api-key", "Content-Type"}
        -> WebOperationClient.request_json
        -> HttpTransport.request -> _send_once
              request_headers = _json_request_headers(headers)   # keeps "Content-Type", adds nothing
        -> httpx sends ONE content-type line -> Exa 200
```

---

## 6. Detailed Design

### 6.1 Transport header helper

**File(s):** `vidbyte/lib/http/transport.py`
**Type:** Modified

#### What it does
It builds the outgoing header mapping for a JSON request, with at most one content-type.

#### Interface / API
```python
def _json_request_headers(headers: Mapping[str, str]) -> dict[str, str]
```

#### Logic / Algorithm
1. Copy `headers` into a new dict.
2. If any key's `.lower()` equals `content-type`, return the copy unchanged.
3. Otherwise set `content-type` to `application/json` and return the copy.
4. At each of the four send sites, use `request_headers = _json_request_headers(headers)` when `json_body` is not `None`, and `dict(headers)` otherwise.

#### Edge Cases & Error Handling
- **The caller sends `CONTENT-TYPE: application/vnd.api+json`:** kept as is, so a custom type is never replaced.
- **The SSE path:** it sets `accept` after copying. That stays as it is.
- **An empty headers mapping:** the helper only adds the default.

### 6.2 Tests

**File(s):** `tests/test_http_transport_content_type.py`
**Type:** New file

The tests drive the real `HttpTransport` and `ExaClient` against an `httpx.MockTransport`. One mock emulates Exa's strict check by returning 400 unless the request has exactly one content-type line.

### 6.3 Verification script

**File(s):** `scripts/test-single-content-type-header.py`
**Type:** New file

It runs the test module and prints one PASS or FAIL line per case, then an `X/Y` summary. It exits non-zero on any failure.

---

## 7. Data Model Changes

N/A: no data models change.

---

## 8. API Changes

N/A: no public signature changes. The only wire-level change is that duplicate content-type headers are no longer sent.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/single-content-type-header.md` | This design doc |
| MODIFY | `vidbyte/lib/http/transport.py` | Case-insensitive content-type default through one helper |
| CREATE | `tests/test_http_transport_content_type.py` | Pins exactly one content-type header and the Exa round trip |
| CREATE | `scripts/test-single-content-type-header.py` | Labelled verification runner |

---

## 10. Testing Plan

### Unit Tests
- `test_caller_title_case_content_type_is_sent_once`: `Content-Type` from the caller produces one content-type line on the wire. [Hidden Failure]
- `test_caller_lowercase_content_type_is_sent_once`: a lowercase caller header also produces one line. [Edge Case]
- `test_custom_content_type_is_kept_not_replaced`: `CONTENT-TYPE: application/vnd.api+json` stays as the only value. [Silent Failure]
- `test_default_added_when_caller_sends_none`: with no caller content-type, `application/json` is added once. [Hidden Assumption]
- `test_no_content_type_without_json_body`: a GET with no body carries no content-type. [Edge Case]
- `test_helper_does_not_mutate_caller_headers`: the caller's mapping is unchanged after the call. [Hidden Assumption]
- `test_sync_paths_use_the_same_helper`: `SyncHttpTransport._send_once`, `request_bytes`, and `stream_sse` build a single content-type through the helper. Checked on the `urllib.request.Request` each one constructs. [Silent Failure]

### Integration Tests
- `test_exa_search_succeeds_against_a_strict_server`: `ExaClient.search` against a mock that 400s on anything but one content-type line returns hits. Before the fix, this exact call raised `ProviderRequestError` with status 400. [Hidden Failure]

### Manual / QA Test Cases
1. With the fix in the backend's pinned SDK, a production research run's search events report `status: success` rather than `error_status_code: 400`. [Hidden Failure]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| httpx | as pinned | Async HTTP | None; standard header API |
| Exa `/search` | api.exa.ai | Research search | Rejects a doubled content-type with 400 |

---

## 12. Rollout & Deployment

- No feature flag, and nothing breaks.
- The backend picks this up through its commit pin. The backend change cherry-picks this commit onto v0.2.1 and pins that commit, so production gets this fix and nothing else from main.
- Rollback: revert the commit.

---

## 13. Open Questions

- [ ] Should `_require_ok` carry the provider's response body in `ProviderRequestError`? Out of scope here; it would have shortened this diagnosis.

---

## 14. Alternatives Considered

### Alternative 1: Change each client's `_headers()` to lowercase
- What: edit the five clients.
- Why rejected: it fixes the symptom in five places, and the next client would bring the bug back. The transport owns the default, so the transport owns the rule.

### Alternative 2: Use `httpx.Headers` for the merge
- What: build `httpx.Headers(headers)`, then `setdefault`.
- Why rejected: it only covers the httpx path. The urllib paths would still need their own handling, and the helper should serve all four.
