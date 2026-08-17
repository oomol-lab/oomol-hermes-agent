export const RESEARCH_PROFILES = {
  douyin: {
    "content-search": {
      documentationUrl: "https://docs.tikhub.io/370212780e0.md",
      method: "POST",
      path: "/api/v1/douyin/search/fetch_video_search_v2",
      request: {
        location: "body",
        keywordField: "keyword",
        rankField: "sort_type",
        rankValues: {
          relevance: "0",
          popularity: "1",
          recent: "2",
        },
        timeField: "publish_time",
        timeValues: {
          rolling24Hours: "1",
          recent7Days: "7",
        },
        staticFields: {
          filter_duration: "0",
          content_type: "1",
        },
      },
      pagination: {
        initialState: {
          cursor: 0,
          searchId: "",
          backtrace: "",
        },
        requestFields: {
          cursor: "cursor",
          searchId: "search_id",
          backtrace: "backtrace",
        },
        nextState: {
          cursor: { path: ["business_config", "next_page", "cursor"] },
          searchId: { path: ["business_config", "next_page", "search_id"] },
          backtrace: { path: ["business_config", "next_page", "backtrace"] },
        },
      },
      response: {
        dataPath: ["body", "data"],
        itemsPath: ["business_data"],
        itemPath: ["data", "aweme_info"],
        hasMorePath: ["business_config", "has_more"],
      },
      fields: {
        canonicalUrlTemplate: "https://www.douyin.com/video/{id}",
        id: ["aweme_id"],
        description: ["desc"],
        publishedEpoch: ["create_time"],
        url: ["share_url"],
        durationMs: ["video", "duration"],
        authorName: ["author", "nickname"],
        authorFollowers: ["author", "follower_count"],
        authorVerified: ["author", "is_verified"],
        likes: ["statistics", "digg_count"],
        comments: ["statistics", "comment_count"],
        shares: ["statistics", "share_count"],
        collects: ["statistics", "collect_count"],
        plays: ["statistics", "play_count"],
        hashtags: ["cha_list"],
      },
    },
  },
  tiktok: {
    "content-search": {
      documentationUrl: "https://docs.tikhub.io/186826113e0.md",
      method: "GET",
      path: "/api/v1/tiktok/app/v3/fetch_video_search_result",
      request: {
        location: "query",
        keywordField: "keyword",
        rankField: "sort_type",
        rankValues: {
          relevance: 0,
          popularity: 1,
        },
        timeField: "publish_time",
        timeValues: {
          rolling24Hours: 1,
          recent7Days: 7,
        },
        staticFields: {
          offset: 0,
          count: 20,
          region: "US",
        },
      },
      response: {
        dataPath: ["body", "data"],
        itemsPath: ["search_item_list"],
        itemPath: ["aweme_info"],
        hasMorePath: ["has_more"],
      },
      fields: {
        id: ["aweme_id"],
        description: ["desc"],
        publishedEpoch: ["create_time"],
        url: ["share_info", "share_url"],
        authorName: ["author", "nickname"],
        authorFollowers: ["author", "follower_count"],
        authorVerified: ["author", "verification_type"],
        likes: ["statistics", "digg_count"],
        comments: ["statistics", "comment_count"],
        shares: ["statistics", "share_count"],
        collects: ["statistics", "collect_count"],
        plays: ["statistics", "play_count"],
      },
    },
  },
  youtube: {
    "content-search": {
      documentationUrl: "https://docs.tikhub.io/413417977e0.md",
      method: "GET",
      path: "/api/v1/youtube/web/search_video",
      request: {
        location: "query",
        keywordField: "search_query",
        rankValues: {
          relevance: null,
          popularity: null,
          recent: null,
        },
        timeField: "order_by",
        timeValues: {
          rolling24Hours: "today",
          recent7Days: "this_week",
        },
        staticFields: {
          language_code: "en",
          country_code: "us",
        },
      },
      pagination: {
        initialState: {},
        requestFields: {
          continuationToken: "continuation_token",
        },
        nextState: {
          continuationToken: { path: ["continuation_token"] },
        },
      },
      response: {
        dataPath: ["body", "data"],
        itemsPath: ["videos"],
        itemPath: [],
        hasMorePath: ["continuation_token"],
        hasMoreMode: "present",
      },
      fields: {
        canonicalUrlTemplate: "https://www.youtube.com/watch?v={id}",
        id: ["video_id"],
        description: ["title"],
        publishedRelative: ["published_time"],
        durationText: ["video_length"],
        authorName: ["author"],
        plays: ["number_of_views"],
        popularityMetric: "plays",
      },
    },
  },
  reddit: {
    "content-search": {
      documentationUrl: "https://docs.tikhub.io/369454687e0.md",
      method: "GET",
      path: "/api/v1/reddit/app/fetch_dynamic_search",
      request: {
        location: "query",
        keywordField: "query",
        rankField: "sort",
        rankValues: {
          relevance: "RELEVANCE",
          popularity: "HOT",
          recent: "NEW",
        },
        timeField: "time_range",
        timeValues: {
          rolling24Hours: "day",
          recent7Days: "week",
        },
        staticFields: {
          search_type: "post",
          safe_search: "unset",
          allow_nsfw: "0",
          need_format: false,
        },
      },
      response: {
        dataPath: ["body", "data"],
        itemsPath: [
          "search",
          "dynamic",
          "components",
          "main",
          "edges",
          "*",
          "node",
          "children",
          "*",
          "post",
        ],
        itemPath: [],
        hasMore: "unknown",
      },
      fields: {
        id: ["id"],
        description: ["postTitle"],
        publishedAt: ["createdAt"],
        url: ["url"],
      },
    },
  },
  twitter: {
    "content-search": {
      documentationUrl: "https://docs.tikhub.io/215701673e0.md",
      method: "GET",
      path: "/api/v1/twitter/web/fetch_search_timeline",
      request: {
        location: "query",
        keywordField: "keyword",
        rankField: "search_type",
        rankValues: {
          relevance: "Top",
          popularity: "Top",
          recent: "Latest",
        },
        staticFields: {},
      },
      pagination: {
        initialState: {},
        requestFields: {
          cursor: "cursor",
        },
        nextState: {
          cursor: { path: ["next_cursor"] },
        },
      },
      response: {
        dataPath: ["body", "data"],
        itemsPath: ["timeline"],
        itemPath: [],
        hasMorePath: ["next_cursor"],
        hasMoreMode: "present",
      },
      fields: {
        canonicalUrlTemplate: "https://twitter.com/i/web/status/{id}",
        id: ["tweet_id"],
        description: ["text"],
        publishedAt: ["created_at"],
        authorName: ["user_info", "name"],
        authorFollowers: ["user_info", "followers_count"],
        authorVerified: ["user_info", "verified"],
        likes: ["favorites"],
        comments: ["replies"],
        shares: ["retweets"],
        collects: ["bookmarks"],
        plays: ["views"],
        hashtags: ["entities", "hashtags"],
        hashtagName: ["text"],
      },
    },
  },
}

export function researchProfile(platform, intent) {
  return RESEARCH_PROFILES[platform]?.[intent]
}

export function supportedResearchCapabilities() {
  return Object.fromEntries(
    Object.entries(RESEARCH_PROFILES).map(([platform, intents]) => [platform, Object.keys(intents)]),
  )
}
