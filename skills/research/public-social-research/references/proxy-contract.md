# Fusion proxy contract

## Stable boundary

- Adapter: the repository-owned `scripts/tikhub.mjs` bundled under `$HERMES_BUNDLED_SKILLS/research/public-social-research`; it is not installed or downloaded at runtime.
- Documentation: the adapter accepts endpoint documents only from the fixed official `https://docs.tikhub.io` origin.
- Provider: the adapter internally fixes `tikhub`; callers cannot choose it.
- Transport: the adapter derives the Fusion origin from the active OO account endpoint reported by `oo auth status --json` and sends the restricted proxy request itself.
- Authentication: the adapter reads the authenticated API key from `oo llm config --json` and injects Authorization in process memory. Never request, print, persist, or forward a TikHub key or OOMOL token.
- Methods: `GET`, `POST`, `PUT`, `PATCH`, or `DELETE`, exactly as proven by the inspected endpoint.
- Caller-controlled upstream headers are intentionally unavailable.

Allowed normalized upstream path prefixes:

```text
/api/v1/health/
/api/v1/tiktok/
/api/v1/douyin/
/api/v1/wechat_channels/
/api/v1/wechat_mp/
/api/v1/wechat_search/
/api/v1/weibo/
/api/v1/youtube/
/api/v1/reddit/
/api/v1/twitter/
/api/v1/zhihu/
/api/v1/kuaishou/
/api/v1/xiaohongshu/
```

The `call` subcommand accepts:

```json
{
  "method": "GET",
  "path": "/api/v1/<enabled-platform>/...",
  "queryJson": "{\"documented_query_field\":\"value\"}",
  "bodyJson": "{\"documented_body_field\":\"value\"}"
}
```

Pass inline values with `--query-json` and `--body-json`. For nested or quote-heavy values, use `--payload-file` with an object containing `query` and/or `body`. Payload files must stay under the current private working directory. OO authentication comes only from the active OO CLI account and may not be supplied as command arguments.

## Unified research operation

`research` exposes one cross-platform command contract. Platform and intent differences live in checked-in declarative profiles rather than separate commands. A profile fixes the verified documentation source, method, path, request-field mapping, pagination state, and normalized output fields. A matching profile does not fetch the endpoint index or documentation at runtime. If no matching profile exists, the operation returns `unsupported_intent` without making a network or proxy request; callers may then use `list`, `inspect`, and `call`.

Common inputs are `platform`, `intent`, `query`, `time-range`, `timezone`, `rank`, `limit`, and `max-calls`. The operation resolves calendar dates in the requested IANA timezone, uses only profile-declared response state for pagination, reuses one OO authentication lookup, deduplicates provider IDs, and stops on sufficient results, a meaningful date boundary, the end of pagination, unproven pagination, or the five-call safety ceiling. `unpageable` is a safe partial result, not an invitation to guess the next offset, cursor, token, or page.

For multi-platform research, replace `platform` with comma-separated `platforms`. Use one shared `query` or a `queries-json` object keyed by platform. Every requested platform must have a fast profile, and `max-calls` is a global budget that must allow at least one request per platform. The adapter executes platform requests concurrently and returns per-platform results without resetting the budget.

Successful output includes:

```json
{
  "status": "success",
  "operation": "research",
  "coverage": "search_sample",
  "truncated": false,
  "stopReason": "no_more",
  "requestCount": 2,
  "requestIds": ["..."],
  "items": []
}
```

`coverage` describes what the selected upstream search can support; it is not a claim of exhaustive platform coverage. `truncated` reports whether more upstream pages remained when the operation stopped or matching local results were omitted by `limit`.

Batch output uses `mode: "multi-platform"`, aggregates `requestCount` and `requestIds`, and stores each ordinary research result under `results.<platform>`. `partial: true` means at least one platform failed while another succeeded. Missing normalized metrics, author fields, and durations are `null`, not fabricated zero values.

## Result

Successful normalized output has:

```json
{
  "status": "success",
  "upstreamStatus": 200,
  "requestId": "...",
  "body": {
    "code": 200,
    "data": {}
  }
}
```

Use `body.data` as the provider payload. Other `body` fields are provider metadata and diagnostics. Keep `requestId` with any reported partial failure.

An error result has `status: "error"` plus an `errorCode`. It may also include `proxyStatus`, `upstreamStatus`, `upstreamCode`, `requestId`, or `body`. These structured fields are authoritative; do not infer authentication, quota, or provider state from prose alone.

## Multi-step workflows

For generic workflows, inspect all distinct endpoints before the first paid call when practical. Execute the least expensive narrowing step first, filter locally, and pass only documented IDs or cursors into the next step. Keep a total shortlist of at most five objects unless the user approves a larger paid plan. For cross-platform work, budget calls across the complete task rather than resetting the limit for each platform. Do not run paid calls merely to learn an output shape.
