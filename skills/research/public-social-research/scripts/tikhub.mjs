import { execFile } from "node:child_process"
import { realpathSync } from "node:fs"
import { readFile } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { promisify } from "node:util"

import { researchProfile, supportedResearchCapabilities } from "./research-profiles.mjs"

const TIKHUB_DOCS_BASE_URL = "https://docs.tikhub.io"
const TIKHUB_PROVIDER = "tikhub"
const REQUEST_TIMEOUT_MS = 60_000
const DOC_TIMEOUT_MS = 15_000
const MAX_INDEX_BYTES = 512 * 1024
const MAX_DOCUMENT_BYTES = 768 * 1024
const MAX_PAYLOAD_BYTES = 256 * 1024
const MAX_RESPONSE_BYTES = 4 * 1024 * 1024
const MAX_RETURNED_ENTRIES = 100
const OO_COMMAND_TIMEOUT_MS = 15_000
const MAX_RESEARCH_CALLS = 5
const MAX_RESEARCH_ITEMS = 50
const execFileAsync = promisify(execFile)

export const TIKHUB_ALLOWED_PATH_PREFIXES = [
  "/api/v1/health/",
  "/api/v1/tiktok/",
  "/api/v1/douyin/",
  "/api/v1/wechat_channels/",
  "/api/v1/wechat_mp/",
  "/api/v1/wechat_search/",
  "/api/v1/weibo/",
  "/api/v1/youtube/",
  "/api/v1/reddit/",
  "/api/v1/twitter/",
  "/api/v1/zhihu/",
  "/api/v1/kuaishou/",
  "/api/v1/xiaohongshu/",
]

const PLATFORM_BY_GROUP_PREFIX = [
  ["Health-Check", "health"],
  ["TikTok-", "tiktok"],
  ["Douyin-", "douyin"],
  ["WeChat-Channels-", "wechat_channels"],
  ["WeChat-Media-Platform-", "wechat_mp"],
  ["WeChat-Search-", "wechat_search"],
  ["Weibo-", "weibo"],
  ["YouTube-", "youtube"],
  ["Reddit-", "reddit"],
  ["Twitter-", "twitter"],
  ["Zhihu-", "zhihu"],
  ["Kuaishou-", "kuaishou"],
  ["Xiaohongshu-", "xiaohongshu"],
]

const PLATFORM_IDS = new Set(PLATFORM_BY_GROUP_PREFIX.map(([, platform]) => platform))

function errorResult(errorCode, message, details = {}) {
  return { status: "error", errorCode, message: String(message).slice(0, 500), ...details }
}

function parseArguments(argv) {
  const [operation, ...rest] = argv
  const values = {}
  for (let index = 0; index < rest.length; index += 1) {
    const item = rest[index]
    if (!item.startsWith("--")) throw new Error(`Unexpected argument: ${item}`)
    const name = item.slice(2)
    if (name === "help") {
      values.help = true
      continue
    }
    const value = rest[index + 1]
    if (value === undefined || value.startsWith("--")) throw new Error(`Missing value for --${name}`)
    if (Object.hasOwn(values, name)) throw new Error(`Duplicate argument: --${name}`)
    values[name] = value
    index += 1
  }
  return { operation, values }
}

function helpResult(operation) {
  const commands = {
    research:
      'research (--platform <id> | --platforms <id,id>) --intent content-search [--query <text>] [--queries-json <platform-to-query object>] --time-range <yesterday|today|last-24-hours|last-7-days|YYYY-MM-DD> [--timezone <IANA>] [--rank <popularity|recent|relevance>] [--limit <1-50>] [--max-calls <1-5>]',
    list: "list [--platform <id>] [--query <title words>]",
    inspect: "inspect --documentation-url <current TikHub documentation URL>",
    call:
      "call --method <GET|POST|PUT|PATCH|DELETE> --path </api/v1/...> [--query-json <object>] [--body-json <object>] [--payload-file <workspace path>]",
  }
  if (operation && commands[operation]) return { status: "success", operation: "help", usage: commands[operation] }
  return { status: "success", operation: "help", commands }
}

async function fetchText(url, { fetchImpl, maxBytes, timeoutMs }) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetchImpl(url, { signal: controller.signal })
    if (!response.ok) throw new Error(`TikHub documentation returned HTTP ${response.status}`)
    const text = await response.text()
    if (new TextEncoder().encode(text).byteLength > maxBytes) {
      throw new Error("TikHub documentation exceeded the allowed response size")
    }
    return text
  } finally {
    clearTimeout(timer)
  }
}

function parseIndex(text) {
  const entries = []
  const pattern = /^- ([^[]+?) \[([^\]]+)\]\((https:\/\/[^\s)]+\/[0-9]+e0\.md)\):/gm
  let match
  while ((match = pattern.exec(text)) !== null) {
    const group = match[1].trim()
    const mapping = PLATFORM_BY_GROUP_PREFIX.find(([prefix]) => group === prefix || group.startsWith(prefix))
    if (mapping && match[3].startsWith(`${TIKHUB_DOCS_BASE_URL}/`)) {
      entries.push({ platform: mapping[1], group, title: match[2].trim(), documentationUrl: match[3] })
    }
  }
  return entries
}

function isOfficialDocumentUrl(value) {
  try {
    const official = new URL(TIKHUB_DOCS_BASE_URL)
    const candidate = new URL(value)
    return (
      candidate.origin === official.origin &&
      !candidate.username &&
      !candidate.password &&
      !candidate.search &&
      !candidate.hash &&
      /^\/[0-9]+e0\.md$/.test(candidate.pathname)
    )
  } catch {
    return false
  }
}

function allowedPathPrefix(value) {
  return TIKHUB_ALLOWED_PATH_PREFIXES.find((prefix) => String(value || "").startsWith(prefix))
}

function sanitizedOpenapi(value) {
  const lines = value.split("\n")
  const kept = []
  let skippedBlockIndent
  for (const line of lines) {
    const indentation = line.match(/^\s*/)[0].length
    if (skippedBlockIndent !== undefined) {
      if (!line.trim() || indentation > skippedBlockIndent) continue
      skippedBlockIndent = undefined
    }
    const sensitiveKey = line.match(/^(\s*)(securitySchemes|security|servers):\s*(.*)$/)
    if (sensitiveKey) {
      if (!sensitiveKey[3]) skippedBlockIndent = sensitiveKey[1].length
      continue
    }
    kept.push(line)
  }
  return kept.join("\n").trim()
}

function extractContract(markdown) {
  const titleMatch = markdown.match(/^#\s+(.+)$/m)
  const openapiMatch = markdown.match(/## OpenAPI Specification\s*\n+```ya?ml\s*\n([\s\S]*?)\n```/i)
  if (!openapiMatch) throw new Error("The TikHub endpoint document has no OpenAPI YAML block")
  const openapi = sanitizedOpenapi(openapiMatch[1])
  const routeMatch = openapi.match(/^\s{2}(\/api\/v1\/[^\s:]+):\s*\n\s{4}(get|post|put|patch|delete):/m)
  const allowedPrefix = routeMatch && allowedPathPrefix(routeMatch[1])
  if (!routeMatch || !allowedPrefix) throw new Error("The documented endpoint is outside the enabled TikHub scope")
  return {
    title: titleMatch ? titleMatch[1].trim() : "TikHub API",
    platform: allowedPrefix.split("/")[3],
    path: routeMatch[1],
    method: routeMatch[2].toUpperCase(),
    openapi,
  }
}

function validatedPath(value) {
  const pathname = String(value || "").trim()
  const hasControlCharacter = [...pathname].some((character) => {
    const code = character.codePointAt(0) ?? 0
    return code <= 31 || code === 127
  })
  if (
    !allowedPathPrefix(pathname) ||
    pathname.includes("%") ||
    pathname.includes("\\") ||
    pathname.includes("?") ||
    pathname.includes("#") ||
    hasControlCharacter ||
    pathname.split("/").some((segment) => segment === "." || segment === "..")
  ) {
    throw new Error("path must be a plain relative path under an enabled TikHub prefix")
  }
  return pathname
}

function fusionBaseUrl(endpointValue) {
  const endpoint = String(endpointValue || "").trim().toLowerCase()
  if (!endpoint || !/^[a-z0-9.-]+$/.test(endpoint) || endpoint.startsWith(".") || endpoint.endsWith(".")) {
    throw new Error("OO endpoint is unavailable or invalid")
  }
  return `https://fusion-api.${endpoint}`
}

async function readOoJson(args) {
  const { stdout } = await execFileAsync("oo", args, {
    encoding: "utf8",
    timeout: OO_COMMAND_TIMEOUT_MS,
    maxBuffer: 1024 * 1024,
  })
  const parsed = JSON.parse(stdout)
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("OO CLI returned an unsupported JSON result")
  }
  return parsed
}

export async function loadOoAuth() {
  const llmConfig = await readOoJson(["llm", "config", "--json"])
  const authStatus = await readOoJson(["auth", "status", "--json"])
  const apiKey = String(llmConfig.apiKey || "").trim()
  const accounts = Array.isArray(authStatus.accounts) ? authStatus.accounts : []
  const activeAccount =
    accounts.find((account) => account && account.active === true) ||
    accounts.find((account) => account && account.id === authStatus.activeAccountId)
  const endpoint = String(activeAccount?.endpoint || authStatus.envOverride?.endpoint || "").trim()
  if (authStatus.status !== "logged-in" || !apiKey || !endpoint) {
    throw new Error("The authenticated OO account is unavailable")
  }
  return { apiKey, endpoint }
}

function parseOptionalJson(value, label) {
  if (value === undefined) return undefined
  try {
    return JSON.parse(value)
  } catch {
    throw new Error(`${label} must be valid JSON`)
  }
}

async function readPayloadFile(filename, runtime) {
  const payloadRoot = path.resolve(runtime.cwd)
  const payloadFile = path.resolve(filename)
  const relativePayload = path.relative(payloadRoot, payloadFile)
  if (relativePayload.startsWith("..") || path.isAbsolute(relativePayload)) {
    throw new Error("payload-file must be inside the current private workspace")
  }
  return JSON.parse(await runtime.readFileImpl(payloadFile, "utf8"))
}

async function responseText(response) {
  const length = Number(response.headers.get("content-length") || 0)
  if (length > MAX_RESPONSE_BYTES) throw new Error("Fusion response exceeded the allowed response size")
  const text = await response.text()
  if (new TextEncoder().encode(text).byteLength > MAX_RESPONSE_BYTES) {
    throw new Error("Fusion response exceeded the allowed response size")
  }
  return text
}

function proxyErrorCode(status) {
  if (status === 401 || status === 403) return "not_authenticated"
  if (status === 402) return "quota_exhausted"
  if (status === 429) return "rate_limited"
  return "proxy_http_error"
}

async function listApis(values, runtime) {
  const platform = String(values.platform || "").trim()
  if (platform && !PLATFORM_IDS.has(platform)) return errorResult("invalid_arguments", "platform is not enabled")
  try {
    const text = await fetchText(`${TIKHUB_DOCS_BASE_URL}/llms.txt`, {
      fetchImpl: runtime.fetchImpl,
      maxBytes: MAX_INDEX_BYTES,
      timeoutMs: DOC_TIMEOUT_MS,
    })
    const entries = parseIndex(text)
    if (entries.length === 0) throw new Error("No enabled API entries were found in the current TikHub index")
    const queryWords = String(values.query || "")
      .trim()
      .toLowerCase()
      .split(/\s+/)
      .filter(Boolean)
    const platformEntries = platform ? entries.filter((entry) => entry.platform === platform) : entries
    const filtered = queryWords.length
      ? platformEntries.filter((entry) => {
          const haystack = `${entry.group} ${entry.title}`.toLowerCase()
          return queryWords.every((word) => haystack.includes(word))
        })
      : platformEntries
    const selected = queryWords.length && filtered.length === 0 ? [] : filtered
    const platformCounts = {}
    for (const entry of entries) platformCounts[entry.platform] = (platformCounts[entry.platform] || 0) + 1
    return {
      status: "success",
      operation: "list",
      source: `${TIKHUB_DOCS_BASE_URL}/llms.txt`,
      currentCount: entries.length,
      platformCounts,
      availableCount: platformEntries.length,
      matchedCount: selected.length,
      entries: selected.slice(0, MAX_RETURNED_ENTRIES),
      truncated: selected.length > MAX_RETURNED_ENTRIES,
      filterMatched: queryWords.length === 0 || filtered.length > 0,
      ...(queryWords.length && filtered.length === 0
        ? { message: "No title matched every query word. Retry once with fewer title-like words." }
        : {}),
    }
  } catch (error) {
    return errorResult("documentation_unavailable", error.message || error)
  }
}

async function inspectApi(values, runtime) {
  const documentationUrl = String(values["documentation-url"] || "").trim()
  if (!isOfficialDocumentUrl(documentationUrl)) {
    return errorResult("invalid_documentation_url", "documentation URL must come from the current TikHub index")
  }
  try {
    const markdown = await fetchText(documentationUrl, {
      fetchImpl: runtime.fetchImpl,
      maxBytes: MAX_DOCUMENT_BYTES,
      timeoutMs: DOC_TIMEOUT_MS,
    })
    return { status: "success", operation: "inspect", documentationUrl, ...extractContract(markdown) }
  } catch (error) {
    return errorResult("invalid_documentation", error.message || error)
  }
}

function valueAtPath(value, pathParts) {
  if (!Array.isArray(pathParts)) return undefined
  let current = value
  for (const part of pathParts) {
    if (!current || typeof current !== "object") return undefined
    current = current[part]
  }
  return current
}

function valuesAtPath(value, pathParts) {
  let current = [value]
  for (const part of pathParts) {
    if (part === "*") {
      current = current.flatMap((entry) => (Array.isArray(entry) ? entry : []))
    } else {
      current = current
        .map((entry) => (entry && typeof entry === "object" ? entry[part] : undefined))
        .filter((entry) => entry !== undefined)
    }
  }
  return current
}

function optionalIntegerValue(value) {
  if (value === undefined || value === null || value === "") return null
  const parsed = Number.parseInt(String(value), 10)
  return Number.isFinite(parsed) ? parsed : null
}

function optionalBooleanValue(value) {
  if (value === undefined || value === null || value === "") return null
  if ([true, 1, "1", "true"].includes(value)) return true
  if ([false, 0, "0", "false"].includes(value)) return false
  return Boolean(value)
}

function boundedInteger(value, { label, defaultValue, minimum, maximum }) {
  if (value === undefined) return defaultValue
  const parsed = Number(value)
  if (!Number.isInteger(parsed) || parsed < minimum || parsed > maximum) {
    throw new Error(`${label} must be an integer from ${minimum} to ${maximum}`)
  }
  return parsed
}

function zonedParts(date, timezone, includeTime = false) {
  const options = {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    ...(includeTime
      ? { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }
      : {}),
  }
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", options)
      .formatToParts(date)
      .filter((part) => part.type !== "literal")
      .map((part) => [part.type, part.value]),
  )
  return {
    year: Number(parts.year),
    month: Number(parts.month),
    day: Number(parts.day),
    ...(includeTime
      ? { hour: Number(parts.hour), minute: Number(parts.minute), second: Number(parts.second) }
      : {}),
  }
}

function shiftCalendarDate(parts, days) {
  const shifted = new Date(Date.UTC(parts.year, parts.month - 1, parts.day + days))
  return { year: shifted.getUTCFullYear(), month: shifted.getUTCMonth() + 1, day: shifted.getUTCDate() }
}

function timezoneOffsetMs(date, timezone) {
  const parts = zonedParts(date, timezone, true)
  const representedAsUtc = Date.UTC(
    parts.year,
    parts.month - 1,
    parts.day,
    parts.hour,
    parts.minute,
    parts.second,
  )
  return representedAsUtc - Math.floor(date.getTime() / 1000) * 1000
}

function localMidnightEpochMs(parts, timezone) {
  const targetAsUtc = Date.UTC(parts.year, parts.month - 1, parts.day)
  let candidate = targetAsUtc
  for (let attempt = 0; attempt < 3; attempt += 1) {
    candidate = targetAsUtc - timezoneOffsetMs(new Date(candidate), timezone)
  }
  return candidate
}

function calendarDateString(parts) {
  return `${String(parts.year).padStart(4, "0")}-${String(parts.month).padStart(2, "0")}-${String(parts.day).padStart(2, "0")}`
}

function localTimestamp(epochMs, timezone) {
  const parts = zonedParts(new Date(epochMs), timezone, true)
  return `${calendarDateString(parts)} ${String(parts.hour).padStart(2, "0")}:${String(parts.minute).padStart(2, "0")}:${String(parts.second).padStart(2, "0")}`
}

function resolveTimeRange(value, timezone, now) {
  zonedParts(now, timezone)
  const range = String(value || "").trim().toLowerCase()
  if (!range) throw new Error("time-range is required")
  if (range === "last-24-hours") {
    return {
      kind: range,
      startMs: now.getTime() - 24 * 60 * 60 * 1000,
      endMs: now.getTime(),
      upstreamWindow: "rolling24Hours",
    }
  }
  if (range === "last-7-days") {
    return {
      kind: range,
      startMs: now.getTime() - 7 * 24 * 60 * 60 * 1000,
      endMs: now.getTime(),
      upstreamWindow: "recent7Days",
    }
  }

  const today = zonedParts(now, timezone)
  let target
  if (range === "today") target = today
  else if (range === "yesterday") target = shiftCalendarDate(today, -1)
  else {
    const match = range.match(/^(\d{4})-(\d{2})-(\d{2})$/)
    if (!match) throw new Error("time-range must be yesterday, today, last-24-hours, last-7-days, or YYYY-MM-DD")
    target = { year: Number(match[1]), month: Number(match[2]), day: Number(match[3]) }
    if (calendarDateString(zonedParts(new Date(Date.UTC(target.year, target.month - 1, target.day)), "UTC")) !== range) {
      throw new Error("time-range contains an invalid calendar date")
    }
  }
  const startMs = localMidnightEpochMs(target, timezone)
  const endMs = localMidnightEpochMs(shiftCalendarDate(target, 1), timezone)
  if (startMs > now.getTime() || now.getTime() - startMs > 8 * 24 * 60 * 60 * 1000) {
    throw new Error("the selected profile supports only dates within the recent seven-day window")
  }
  return {
    kind: range,
    calendarDate: calendarDateString(target),
    startMs,
    endMs: Math.min(endMs, now.getTime()),
    upstreamWindow: "recent7Days",
  }
}

function relativePublishedMs(value, now) {
  const normalized = String(value || "")
    .trim()
    .toLowerCase()
    .replace(/^(streamed|premiered)\s+/, "")
  const match = normalized.match(/^(\d+)\s+(second|minute|hour|day|week)s?\s+ago$/)
  if (!match) return Number.NaN
  const unitMs = {
    second: 1000,
    minute: 60 * 1000,
    hour: 60 * 60 * 1000,
    day: 24 * 60 * 60 * 1000,
    week: 7 * 24 * 60 * 60 * 1000,
  }
  return now.getTime() - Number(match[1]) * unitMs[match[2]]
}

function publishedMs(item, fields, now) {
  const epochSeconds = optionalIntegerValue(valueAtPath(item, fields.publishedEpoch))
  if (epochSeconds !== null) return epochSeconds * 1000
  const epochMs = optionalIntegerValue(valueAtPath(item, fields.publishedEpochMs))
  if (epochMs !== null) return epochMs
  const publishedAt = valueAtPath(item, fields.publishedAt)
  const parsed = Date.parse(String(publishedAt || ""))
  if (Number.isFinite(parsed)) return parsed
  return relativePublishedMs(valueAtPath(item, fields.publishedRelative), now)
}

function parsedDurationSeconds(item, fields) {
  const durationMs = optionalIntegerValue(valueAtPath(item, fields.durationMs))
  if (durationMs !== null) return Math.round(durationMs / 1000)
  const value = String(valueAtPath(item, fields.durationText) || "").trim()
  if (!/^\d{1,3}:\d{2}(?::\d{2})?$/.test(value)) return null
  return value
    .split(":")
    .map(Number)
    .reduce((total, part) => total * 60 + part, 0)
}

function normalizeResearchItem(item, fields, timezone, now) {
  const itemPublishedMs = publishedMs(item, fields, now)
  if (!Number.isFinite(itemPublishedMs)) return undefined
  const id = String(valueAtPath(item, fields.id) || "")
  const hashtagsValue = valueAtPath(item, fields.hashtags)
  const hashtags = Array.isArray(hashtagsValue)
    ? hashtagsValue
        .map((entry) =>
          entry && typeof entry === "object"
            ? valueAtPath(entry, fields.hashtagName || ["cha_name"])
            : entry,
        )
        .filter((entry) => typeof entry === "string" && entry.trim())
    : []
  return {
    id,
    publishedAt: new Date(itemPublishedMs).toISOString(),
    publishedLocal: localTimestamp(itemPublishedMs, timezone),
    description: String(valueAtPath(item, fields.description) || "").replace(/\s+/g, " ").trim().slice(0, 500),
    url: fields.canonicalUrlTemplate
      ? fields.canonicalUrlTemplate.replace("{id}", encodeURIComponent(id))
      : String(valueAtPath(item, fields.url) || ""),
    durationSeconds: parsedDurationSeconds(item, fields),
    author: {
      name: valueAtPath(item, fields.authorName) == null ? null : String(valueAtPath(item, fields.authorName)),
      followers: optionalIntegerValue(valueAtPath(item, fields.authorFollowers)),
      verified: optionalBooleanValue(valueAtPath(item, fields.authorVerified)),
    },
    metrics: {
      likes: optionalIntegerValue(valueAtPath(item, fields.likes)),
      comments: optionalIntegerValue(valueAtPath(item, fields.comments)),
      shares: optionalIntegerValue(valueAtPath(item, fields.shares)),
      collects: optionalIntegerValue(valueAtPath(item, fields.collects)),
      plays: optionalIntegerValue(valueAtPath(item, fields.plays)),
    },
    hashtags,
  }
}

function initialPaginationState(profile) {
  return { ...(profile.pagination?.initialState || {}) }
}

function addPaginationFields(payload, profile, state) {
  for (const [stateName, requestField] of Object.entries(profile.pagination?.requestFields || {})) {
    if (state[stateName] !== undefined) payload[requestField] = state[stateName]
  }
}

function nextPaginationState(data, profile, currentState) {
  const rules = profile.pagination?.nextState
  if (!rules || Object.keys(rules).length === 0) return undefined
  const nextState = { ...currentState }
  let changed = false
  for (const [stateName, rule] of Object.entries(rules)) {
    let nextValue
    if (Array.isArray(rule.path)) nextValue = valueAtPath(data, rule.path)
    else if (Number.isFinite(rule.increment)) nextValue = Number(currentState[stateName] || 0) + rule.increment
    if (nextValue === undefined || nextValue === null) continue
    if (nextValue !== currentState[stateName]) changed = true
    nextState[stateName] = nextValue
  }
  return changed ? nextState : undefined
}

function responseHasMore(data, response) {
  if (response.hasMore === "unknown") return true
  const value = valueAtPath(data, response.hasMorePath)
  if (response.hasMoreMode === "present") return value !== undefined && value !== null && value !== ""
  return [true, 1, "1"].includes(value)
}

function researchSort(items, rank, fields) {
  if (rank === "popularity") {
    const metric = fields.popularityMetric || "likes"
    return items.sort(
      (left, right) => Number(right.metrics[metric] ?? 0) - Number(left.metrics[metric] ?? 0),
    )
  }
  if (rank === "recent") {
    return items.sort((left, right) => right.publishedAt.localeCompare(left.publishedAt))
  }
  return items
}

async function researchOne(values, runtime) {
  const platform = String(values.platform || "").trim()
  const intent = String(values.intent || "content-search").trim()
  const profile = researchProfile(platform, intent)
  if (!profile) {
    return errorResult("unsupported_intent", "No fast research profile is available for this platform and intent.", {
      platform,
      intent,
      supported: supportedResearchCapabilities(),
      fallback: "Use list, inspect, and call for the generic workflow.",
    })
  }
  try {
    const query = String(values.query || "").trim()
    if (!query) throw new Error("query is required")
    const timezone = String(values.timezone || "Asia/Shanghai").trim()
    const rank = String(values.rank || "popularity").trim()
    const rankValue = profile.request.rankValues[rank]
    if (rankValue === undefined) {
      throw new Error(`rank must be one of: ${Object.keys(profile.request.rankValues).join(", ")}`)
    }
    const limit = boundedInteger(values.limit, {
      label: "limit",
      defaultValue: 10,
      minimum: 1,
      maximum: MAX_RESEARCH_ITEMS,
    })
    const maxCalls = boundedInteger(values["max-calls"], {
      label: "max-calls",
      defaultValue: MAX_RESEARCH_CALLS,
      minimum: 1,
      maximum: MAX_RESEARCH_CALLS,
    })
    const now = runtime.nowImpl()
    const timeRange = resolveTimeRange(values["time-range"], timezone, now)

    const found = new Map()
    const requestIds = []
    let requestCount = 0
    let paginationState = initialPaginationState(profile)
    let hasMore = true
    let stopReason = "max_calls"
    while (requestCount < maxCalls && hasMore && found.size < limit) {
      const requestPayload = {
        ...profile.request.staticFields,
        [profile.request.keywordField]: query,
      }
      if (profile.request.rankField) requestPayload[profile.request.rankField] = rankValue
      const upstreamTimeValue = profile.request.timeValues?.[timeRange.upstreamWindow]
      if (profile.request.timeField && upstreamTimeValue !== undefined) {
        requestPayload[profile.request.timeField] = upstreamTimeValue
      }
      addPaginationFields(requestPayload, profile, paginationState)
      const callValues = {
        method: profile.method,
        path: profile.path,
        [`${profile.request.location}-json`]: JSON.stringify(requestPayload),
      }
      requestCount += 1
      const result = await callApi(callValues, runtime)
      if (result.status !== "success") {
        return { ...result, operation: "research", platform, intent, requestCount, requestIds }
      }
      if (result.requestId) requestIds.push(result.requestId)
      let data = valueAtPath(result, profile.response.dataPath)
      if (typeof data === "string") data = JSON.parse(data)
      if (!data || typeof data !== "object") {
        return errorResult("malformed_proxy_response", "The research profile could not read the provider payload.", {
          operation: "research",
          platform,
          intent,
          requestCount,
          requestIds,
        })
      }
      const rawItems = profile.response.itemsPath.includes("*")
        ? valuesAtPath(data, profile.response.itemsPath)
        : valueAtPath(data, profile.response.itemsPath)
      let oldestPublishedMs
      for (const rawItem of Array.isArray(rawItems) ? rawItems : []) {
        const providerItem = valueAtPath(rawItem, profile.response.itemPath)
        if (!providerItem) continue
        const normalized = normalizeResearchItem(providerItem, profile.fields, timezone, now)
        if (!normalized) continue
        const publishedMs = Date.parse(normalized.publishedAt)
        oldestPublishedMs = oldestPublishedMs === undefined ? publishedMs : Math.min(oldestPublishedMs, publishedMs)
        if (publishedMs >= timeRange.startMs && publishedMs < timeRange.endMs && normalized.id) {
          found.set(normalized.id, normalized)
        }
      }

      hasMore = responseHasMore(data, profile.response)
      if (!hasMore) {
        stopReason = found.size > limit ? "limit_reached" : "no_more"
        break
      }
      if (found.size >= limit) {
        stopReason = "limit_reached"
        break
      }
      if (rank === "recent" && oldestPublishedMs !== undefined && oldestPublishedMs < timeRange.startMs) {
        stopReason = "date_boundary"
        break
      }
      const nextState = nextPaginationState(data, profile, paginationState)
      if (!nextState) {
        stopReason = "unpageable"
        break
      }
      paginationState = nextState
    }

    const items = researchSort([...found.values()], rank, profile.fields).slice(0, limit)
    return {
      status: "success",
      operation: "research",
      platform,
      intent,
      query,
      rank,
      timezone,
      timeRange: {
        kind: timeRange.kind,
        ...(timeRange.calendarDate ? { calendarDate: timeRange.calendarDate } : {}),
        start: new Date(timeRange.startMs).toISOString(),
        end: new Date(timeRange.endMs).toISOString(),
      },
      coverage: "search_sample",
      truncated: hasMore || found.size > items.length,
      stopReason,
      requestCount,
      requestIds,
      matchedCount: found.size,
      returnedCount: items.length,
      items,
    }
  } catch (error) {
    return errorResult("invalid_arguments", error.message || error, { operation: "research", platform, intent })
  }
}

async function research(values, runtime) {
  if (!values.platforms) return await researchOne(values, runtime)
  try {
    if (values.platform) throw new Error("platform and platforms cannot be combined")
    const platforms = [...new Set(String(values.platforms).split(",").map((value) => value.trim()).filter(Boolean))]
    if (platforms.length < 2) throw new Error("platforms must contain at least two comma-separated platform IDs")
    const intent = String(values.intent || "content-search").trim()
    const unsupported = platforms.filter((platform) => !researchProfile(platform, intent))
    if (unsupported.length) {
      return errorResult("unsupported_intent", "Every batch platform must have a fast research profile.", {
        operation: "research",
        platforms,
        unsupported,
        supported: supportedResearchCapabilities(),
      })
    }
    const maxCalls = boundedInteger(values["max-calls"], {
      label: "max-calls",
      defaultValue: MAX_RESEARCH_CALLS,
      minimum: 1,
      maximum: MAX_RESEARCH_CALLS,
    })
    if (maxCalls < platforms.length) {
      throw new Error("max-calls must allow at least one proxy request per platform")
    }
    const queryByPlatform = parseOptionalJson(values["queries-json"], "queries-json") || {}
    if (!queryByPlatform || typeof queryByPlatform !== "object" || Array.isArray(queryByPlatform)) {
      throw new Error("queries-json must be a JSON object keyed by platform")
    }
    const defaultQuery = String(values.query || "").trim()
    const queries = Object.fromEntries(
      platforms.map((platform) => {
        const query = String(queryByPlatform[platform] || defaultQuery).trim()
        if (!query) throw new Error(`query is required for platform: ${platform}`)
        return [platform, query]
      }),
    )
    const budgets = platforms.map(() => 1)
    for (let index = platforms.length; index < maxCalls; index += 1) {
      budgets[index % platforms.length] += 1
    }
    const entries = await Promise.all(
      platforms.map(async (platform, index) => [
        platform,
        await researchOne(
          {
            ...values,
            platform,
            query: queries[platform],
            "max-calls": String(budgets[index]),
          },
          runtime,
        ),
      ]),
    )
    const results = Object.fromEntries(entries)
    const successful = entries.filter(([, result]) => result.status === "success")
    const requestCount = entries.reduce((total, [, result]) => total + Number(result.requestCount || 0), 0)
    const requestIds = entries.flatMap(([, result]) => result.requestIds || [])
    if (successful.length === 0) {
      return errorResult("all_platforms_failed", "Every platform research request failed.", {
        operation: "research",
        platforms,
        requestCount,
        requestIds,
        results,
      })
    }
    return {
      status: "success",
      operation: "research",
      mode: "multi-platform",
      platforms,
      intent,
      queries,
      coverage: "platform_search_samples",
      partial: successful.length !== entries.length,
      truncated: successful.some(([, result]) => result.truncated),
      requestCount,
      requestIds,
      results,
    }
  } catch (error) {
    return errorResult("invalid_arguments", error.message || error, { operation: "research" })
  }
}

async function callApi(values, runtime) {
  let requestStarted = false
  try {
    let credentials
    try {
      credentials = await runtime.loadOoAuthImpl()
    } catch {
      return errorResult("not_authenticated", "The authenticated OO session is unavailable.")
    }
    const fusionUrl = fusionBaseUrl(credentials.endpoint)
    const method = String(values.method || "").toUpperCase()
    if (!["GET", "POST", "PUT", "PATCH", "DELETE"].includes(method)) throw new Error("method is not supported")
    const pathname = validatedPath(values.path)
    let query = parseOptionalJson(values["query-json"], "query-json")
    let body = parseOptionalJson(values["body-json"], "body-json")
    if (values["payload-file"]) {
      if (query !== undefined || body !== undefined) throw new Error("payload-file cannot be combined with inline JSON")
      const filePayload = await readPayloadFile(values["payload-file"], runtime)
      query = filePayload.query
      body = filePayload.body
    }
    if (query !== undefined && (!query || typeof query !== "object" || Array.isArray(query))) {
      throw new Error("query must be a JSON object")
    }
    const payload = { provider: TIKHUB_PROVIDER, method, path: pathname }
    if (query !== undefined) payload.query = query
    if (body !== undefined) payload.body = body
    if (new TextEncoder().encode(JSON.stringify(payload)).byteLength > MAX_PAYLOAD_BYTES) {
      throw new Error("request payload exceeded the allowed size")
    }

    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
    try {
      requestStarted = true
      const response = await runtime.fetchImpl(`${fusionUrl}/v1/proxy/action/request`, {
        method: "POST",
        headers: { authorization: `Bearer ${credentials.apiKey}`, "content-type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      })
      const text = await responseText(response)
      let parsed
      try {
        parsed = text ? JSON.parse(text) : null
      } catch {
        parsed = text
      }
      if (!response.ok) {
        return errorResult(
          proxyErrorCode(response.status),
          parsed && typeof parsed === "object" && parsed.error
            ? parsed.error
            : `Fusion API returned HTTP ${response.status}`,
          { proxyStatus: response.status },
        )
      }
      if (parsed && typeof parsed === "object" && parsed.success === false) {
        return errorResult(String(parsed.code || "proxy_error"), parsed.error || parsed.message || "Fusion proxy failed")
      }
      const upstream =
        parsed &&
        typeof parsed === "object" &&
        parsed.success === true &&
        parsed.data &&
        typeof parsed.data === "object"
          ? parsed.data
          : parsed
      if (!upstream || typeof upstream !== "object" || typeof upstream.status !== "number") {
        return errorResult("malformed_proxy_response", "Fusion API returned an unsupported response envelope.")
      }
      const upstreamBody = upstream.body
      const businessCode = upstreamBody && typeof upstreamBody === "object" ? upstreamBody.code : undefined
      if (upstream.status !== 200 || (businessCode !== undefined && businessCode !== 200)) {
        return errorResult("upstream_error", "TikHub returned an unsuccessful result.", {
          upstreamStatus: upstream.status,
          upstreamCode: businessCode,
          requestId: upstreamBody && typeof upstreamBody === "object" ? upstreamBody.request_id : undefined,
          body: upstreamBody,
        })
      }
      return {
        status: "success",
        operation: "call",
        upstreamStatus: upstream.status,
        requestId: upstreamBody && typeof upstreamBody === "object" ? upstreamBody.request_id : undefined,
        body: upstreamBody,
      }
    } finally {
      clearTimeout(timer)
    }
  } catch (error) {
    const errorCode = error.name === "AbortError" ? "timeout" : requestStarted ? "network_error" : "invalid_arguments"
    return errorResult(errorCode, error.message || error)
  }
}

export async function executeTikHubCommand(argv, overrides = {}) {
  const loadOoAuthImpl = overrides.loadOoAuthImpl || loadOoAuth
  let credentialsPromise
  const runtime = {
    env: overrides.env || process.env,
    cwd: overrides.cwd || process.cwd(),
    fetchImpl: overrides.fetchImpl || fetch,
    readFileImpl: overrides.readFileImpl || readFile,
    loadOoAuthImpl: async () => {
      credentialsPromise ||= Promise.resolve().then(() => loadOoAuthImpl())
      return await credentialsPromise
    },
    nowImpl: overrides.nowImpl || (() => new Date()),
  }
  let parsed
  try {
    parsed = parseArguments(argv)
  } catch (error) {
    return errorResult("invalid_arguments", error.message || error)
  }
  if (parsed.operation === "--help" || parsed.values.help) return helpResult(parsed.operation === "--help" ? undefined : parsed.operation)
  if (parsed.operation === "research") return await research(parsed.values, runtime)
  if (parsed.operation === "list") return await listApis(parsed.values, runtime)
  if (parsed.operation === "inspect") return await inspectApi(parsed.values, runtime)
  if (parsed.operation === "call") return await callApi(parsed.values, runtime)
  return errorResult("invalid_arguments", "operation must be research, list, inspect, or call")
}

const invokedPath = process.argv[1] ? path.resolve(process.argv[1]) : ""
const modulePath = fileURLToPath(import.meta.url)
let invokedDirectly = invokedPath === modulePath
if (invokedPath && !invokedDirectly) {
  try {
    invokedDirectly = realpathSync(invokedPath) === realpathSync(modulePath)
  } catch {
    // Keep the lexical comparison result when either path cannot be resolved.
  }
}
if (invokedDirectly) {
  const result = await executeTikHubCommand(process.argv.slice(2))
  process.stdout.write(`${JSON.stringify(result)}\n`)
}
