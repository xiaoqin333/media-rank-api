import asyncio
import json
import os
import re
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import quote, urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response


SERVICE_NAME = "media-rank-api"
SERVICE_VERSION = "1.0.0"
ROOT_PATH = os.getenv("ROOT_PATH", "").rstrip("/")
STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_CACHE_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "600"))
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))
API_KEY = os.getenv("RANK_API_KEY", "").strip()
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "").strip()
TMDB_API_DOMAIN = os.getenv("TMDB_API_DOMAIN", "api.themoviedb.org").strip().rstrip("/")
TMDB_PROXY_URL = os.getenv("TMDB_PROXY_URL", "").strip()
TMDB_LANGUAGE = os.getenv("TMDB_LANGUAGE", "zh-CN").strip()

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

SOURCE_ALIASES = {
    "tmdb": "tmdb",
    "themoviedb": "tmdb",
    "the movie db": "tmdb",
    "TMDB": "tmdb",
    "douban": "douban",
    "豆瓣": "douban",
    "iqiyi": "iqiyi",
    "爱奇艺": "iqiyi",
    "tencent": "tencent",
    "tencentvideo": "tencent",
    "腾讯": "tencent",
    "腾讯视频": "tencent",
    "youku": "youku",
    "优酷": "youku",
    "mango": "mango",
    "mgtv": "mango",
    "芒果": "mango",
    "芒果tv": "mango",
}

TYPE_ALIASES = {
    "movie": "movie",
    "film": "movie",
    "电影": "movie",
    "tv": "tv",
    "series": "tv",
    "drama": "tv",
    "电视剧": "tv",
    "剧集": "tv",
    "variety": "variety",
    "show": "variety",
    "综艺": "variety",
    "anime": "anime",
    "animation": "anime",
    "动漫": "anime",
    "动画": "anime",
}

SOURCE_LABELS = {
    "tmdb": "TMDB",
    "douban": "豆瓣",
    "iqiyi": "爱奇艺",
    "tencent": "腾讯视频",
    "youku": "优酷",
    "mango": "芒果TV",
}

ALLOWED_IMAGE_HOSTS = (
    "tmdb.org",
    "doubanio.com",
    "iqiyipic.com",
    "qpic.cn",
    "alicdn.com",
    "ykimg.com",
    "hitv.com",
)


class UpstreamError(RuntimeError):
    pass


class TTLCache:
    def __init__(self) -> None:
        self._values: dict[str, tuple[float, Any]] = {}
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def get_or_load(
        self,
        key: str,
        ttl: int,
        loader: Callable[[], Awaitable[Any]],
    ) -> tuple[Any, bool]:
        now = time.monotonic()
        entry = self._values.get(key)
        if entry and entry[0] > now:
            return entry[1], True
        async with self._locks[key]:
            now = time.monotonic()
            entry = self._values.get(key)
            if entry and entry[0] > now:
                return entry[1], True
            value = await loader()
            self._values[key] = (time.monotonic() + ttl, value)
            return value, False


class RateLimiter:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def allow(self, client_id: str) -> tuple[bool, int]:
        now = time.monotonic()
        window_start = now - 60
        async with self._lock:
            hits = self._hits[client_id]
            while hits and hits[0] <= window_start:
                hits.popleft()
            if len(hits) >= self.limit:
                retry_after = max(1, int(60 - (now - hits[0])))
                return False, retry_after
            hits.append(now)
        return True, 0


cache = TTLCache()
rate_limiter = RateLimiter(RATE_LIMIT_PER_MINUTE)


@asynccontextmanager
async def lifespan(app: FastAPI):
    timeout = httpx.Timeout(connect=10.0, read=25.0, write=15.0, pool=10.0)
    app.state.http = httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )
    app.state.tmdb_http = httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
        proxy=TMDB_PROXY_URL or None,
    )
    try:
        yield
    finally:
        await app.state.http.aclose()
        await app.state.tmdb_http.aclose()


app = FastAPI(
    title="影视榜单统一 API",
    description="聚合豆瓣、爱奇艺、腾讯视频、优酷、芒果TV榜单数据。",
    version=SERVICE_VERSION,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def access_guard(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/"):
        client_id = (
            request.headers.get("x-real-ip")
            or request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
            or (request.client.host if request.client else "unknown")
        )
        allowed, retry_after = await rate_limiter.allow(client_id)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "error": {
                        "code": "rate_limited",
                        "message": "请求过于频繁，请稍后重试。",
                        "retry_after_seconds": retry_after,
                    },
                },
                headers={"Retry-After": str(retry_after)},
            )
        if API_KEY:
            provided = request.headers.get("x-api-key") or request.query_params.get("api_key", "")
            if provided != API_KEY:
                return JSONResponse(
                    status_code=401,
                    content={
                        "success": False,
                        "error": {
                            "code": "unauthorized",
                            "message": "缺少或无效的 X-API-Key。",
                        },
                    },
                )
    return await call_next(request)


def normalize_source(source: str) -> str:
    key = source.strip().lower()
    normalized = SOURCE_ALIASES.get(key)
    if not normalized:
        raise ValueError(f"不支持的来源：{source}")
    return normalized


def normalize_media_type(media_type: str) -> str:
    key = media_type.strip().lower()
    normalized = TYPE_ALIASES.get(key)
    if not normalized:
        raise ValueError(f"不支持的媒体类型：{media_type}")
    return normalized


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def extract_year(text: Any) -> Optional[int]:
    match = re.search(r"(?<!\d)(19|20)\d{2}(?!\d)", str(text or ""))
    return int(match.group(0)) if match else None


def make_item(
    *,
    rank: int,
    title: Any,
    source: str,
    media_type: str,
    source_id: Any = None,
    year: Any = None,
    url: Any = None,
    poster: Any = None,
    description: Any = None,
    score: Any = None,
    popularity: Any = None,
) -> Optional[dict[str, Any]]:
    clean_title = str(title or "").strip()
    if not clean_title:
        return None
    parsed_year = safe_int(year, 0) or extract_year(description)
    return {
        "rank": rank,
        "title": clean_title,
        "year": parsed_year,
        "media_type": media_type,
        "source": source,
        "source_name": SOURCE_LABELS[source],
        "source_id": str(source_id) if source_id not in (None, "") else None,
        "url": str(url) if url else None,
        "poster": str(poster) if poster else None,
        "description": str(description).strip() if description else None,
        "score": score if score not in (None, "") else None,
        "popularity": popularity if popularity not in (None, "") else None,
    }


async def fetch_douban(
    client: httpx.AsyncClient,
    media_type: str,
    page: int,
    limit: int,
) -> list[dict[str, Any]]:
    start = (page - 1) * limit
    if media_type == "movie":
        path = "movie"
        extra: dict[str, str] = {}
    else:
        path = "tv"
        extra = {"category": "tv", "type": "tv"}
        if media_type == "variety":
            extra = {"category": "show", "type": "show"}
        elif media_type == "anime":
            extra = {"category": "tv", "type": "tv_animation"}
    params = {"start": str(start), "limit": str(limit), **extra}
    response = await client.get(
        f"https://m.douban.com/rexxar/api/v2/subject/recent_hot/{path}",
        params=params,
        headers={
            "Referer": "https://m.douban.com/",
            "Accept": "application/json, text/plain, */*",
        },
    )
    response.raise_for_status()
    payload = response.json()
    items = payload.get("items") or payload.get("subjects") or []
    results: list[dict[str, Any]] = []
    for index, item in enumerate(items[:limit], start=start + 1):
        picture = item.get("pic") or {}
        rating = item.get("rating") or {}
        normalized = make_item(
            rank=index,
            title=item.get("title"),
            source="douban",
            media_type=media_type,
            source_id=item.get("id"),
            year=item.get("year") or item.get("card_subtitle"),
            url=f"https://movie.douban.com/subject/{item.get('id')}/" if item.get("id") else None,
            poster=picture.get("large") or picture.get("normal"),
            description=item.get("card_subtitle"),
            score=rating.get("value"),
            popularity=rating.get("count"),
        )
        if normalized:
            results.append(normalized)
    return results


async def fetch_tmdb(
    client: httpx.AsyncClient,
    media_type: str,
    page: int,
    limit: int,
) -> list[dict[str, Any]]:
    if not TMDB_API_KEY:
        raise UpstreamError("TMDB_API_KEY 未配置。")
    if media_type == "movie":
        path = "/3/trending/movie/week"
        params: dict[str, Any] = {"language": TMDB_LANGUAGE, "page": str(page)}
    elif media_type == "tv":
        path = "/3/trending/tv/week"
        params = {"language": TMDB_LANGUAGE, "page": str(page)}
    elif media_type == "variety":
        path = "/3/discover/tv"
        params = {
            "language": TMDB_LANGUAGE,
            "page": str(page),
            "sort_by": "popularity.desc",
            "with_genres": "10764",
            "include_adult": "false",
        }
    else:
        path = "/3/discover/tv"
        params = {
            "language": TMDB_LANGUAGE,
            "page": str(page),
            "sort_by": "popularity.desc",
            "with_genres": "16",
            "with_original_language": "ja",
            "include_adult": "false",
        }

    headers = {"Accept": "application/json"}
    if TMDB_API_KEY.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {TMDB_API_KEY}"
    else:
        params["api_key"] = TMDB_API_KEY

    response = await client.get(f"https://{TMDB_API_DOMAIN}{path}", params=params, headers=headers)
    response.raise_for_status()
    payload = response.json()
    upstream_items = payload.get("results") or []
    offset = (page - 1) * limit
    results: list[dict[str, Any]] = []
    for index, item in enumerate(upstream_items[:limit], start=offset + 1):
        item_type = "movie" if item.get("media_type") == "movie" or media_type == "movie" else "tv"
        poster_path = item.get("poster_path")
        normalized = make_item(
            rank=index,
            title=item.get("title") or item.get("name"),
            source="tmdb",
            media_type=media_type,
            source_id=item.get("id"),
            year=item.get("release_date") or item.get("first_air_date"),
            url=(
                f"https://www.themoviedb.org/{item_type}/{item.get('id')}"
                if item.get("id")
                else None
            ),
            poster=f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None,
            description=item.get("overview"),
            score=round(float(item.get("vote_average") or 0), 1) or None,
            popularity=item.get("popularity"),
        )
        if normalized:
            results.append(normalized)
    return results


IQIYI_CHANNELS = {
    "movie": "1",
    "tv": "2",
    "anime": "4",
    "variety": "6",
}


async def fetch_iqiyi(
    client: httpx.AsyncClient,
    media_type: str,
    page: int,
    limit: int,
) -> list[dict[str, Any]]:
    response = await client.get(
        "https://mesh.if.iqiyi.com/portal/pcw/rankList/comSecRankList",
        params={
            "v": "1",
            "page_st": "0",
            "tag": "0",
            "category_id": IQIYI_CHANNELS[media_type],
            "date": "",
            "pg_num": "1",
        },
        headers={"Referer": "https://www.iqiyi.com/"},
    )
    response.raise_for_status()
    payload = response.json()
    item_groups = (payload.get("data") or {}).get("items") or []
    upstream_items = (item_groups[0].get("contents") if item_groups else []) or []
    offset = (page - 1) * limit
    upstream_items = upstream_items[offset:offset + limit]
    results: list[dict[str, Any]] = []
    for index, item in enumerate(upstream_items, start=offset + 1):
        page_url = str(item.get("pageUrl") or "")
        if page_url.startswith("http://"):
            page_url = "https://" + page_url[7:]
        normalized = make_item(
            rank=safe_int(item.get("order"), index),
            title=item.get("title"),
            source="iqiyi",
            media_type=media_type,
            source_id=item.get("tvid") or item.get("aid") or item.get("id"),
            year=item.get("tags"),
            url=page_url or None,
            poster=item.get("img") or item.get("imageCover"),
            description=item.get("desc") or item.get("promptDesc"),
            popularity=item.get("mainIndex") or item.get("recIndex"),
        )
        if normalized:
            results.append(normalized)
    return results


TENCENT_CHANNELS = {
    "tv": "100113",
    "movie": "100173",
    "variety": "100109",
    "anime": "100119",
}


async def fetch_tencent(
    client: httpx.AsyncClient,
    media_type: str,
    page: int,
    limit: int,
) -> list[dict[str, Any]]:
    url = (
        "https://pbaccess.video.qq.com/"
        "trpc.universal_backend_service.page_server_rpc.PageServer/GetPageData"
    )
    params = {
        "video_appid": "1000005",
        "vplatform": "2",
        "vversion_name": "8.9.10",
        "new_mark_label_enabled": "1",
    }
    body: dict[str, Any] = {
        "page_params": {
            "channel_id": TENCENT_CHANNELS[media_type],
            "page_type": "channel_operation",
            "page_id": "channel_list_second_page",
            "filter_params": "sort=75",
        }
    }
    headers = {
        "Referer": "https://v.qq.com/",
        "Content-Type": "application/json",
    }

    async def request_page() -> dict[str, Any]:
        response = await client.post(url, params=params, json=body, headers=headers)
        response.raise_for_status()
        return response.json().get("data") or {}

    data = await request_page()
    if page > 1:
        next_context = data.get("next_page_context") or {}
        context_key = next(
            (
                key
                for key in next_context
                if key.startswith("_ds_cli_") and key.endswith("_page")
            ),
            None,
        )
        if not context_key:
            return []
        body["page_context"] = {context_key: str(page - 1)}
        data = await request_page()

    media_items: list[dict[str, Any]] = []
    for module_list in data.get("module_list_datas", []):
        for module in module_list.get("module_datas", []):
            entries = module.get("item_data_lists", {}).get("item_datas", [])
            media_items = [
                entry
                for entry in entries
                if str(entry.get("item_type")) == "2" and entry.get("item_params")
            ]
            if media_items:
                break
        if media_items:
            break

    offset = (page - 1) * limit
    results: list[dict[str, Any]] = []
    for index, entry in enumerate(media_items[:limit], start=offset + 1):
        item = entry.get("item_params") or {}
        cid = item.get("cid")
        normalized = make_item(
            rank=index,
            title=item.get("title") or item.get("series_name"),
            source="tencent",
            media_type=media_type,
            source_id=cid,
            year=item.get("year") or item.get("publish_date"),
            url=f"https://v.qq.com/x/cover/{cid}.html" if cid else None,
            poster=item.get("new_pic_vt") or item.get("new_pic_hz"),
            description=item.get("sub_title") or item.get("second_title"),
            popularity=item.get("third_title"),
        )
        if normalized:
            results.append(normalized)
    return results


MANGO_CHANNELS = {
    "tv": "2",
    "movie": "3",
    "variety": "1",
    "anime": "50",
}


async def fetch_mango(
    client: httpx.AsyncClient,
    media_type: str,
    page: int,
    limit: int,
) -> list[dict[str, Any]]:
    response = await client.get(
        "https://pianku.api.mgtv.com/rider/list/pcweb/v3",
        params={
            "allowedRC": "1",
            "platform": "pcweb",
            "channelId": MANGO_CHANNELS[media_type],
            "pn": str(page),
            "pc": str(limit),
            "hudong": "1",
            "_support": "10000000",
            "sort": "c2",
        },
        headers={"Referer": "https://www.mgtv.com/"},
    )
    response.raise_for_status()
    payload = response.json()
    upstream_items = (payload.get("data") or {}).get("hitDocs") or []
    offset = (page - 1) * limit
    results: list[dict[str, Any]] = []
    for index, item in enumerate(upstream_items[:limit], start=offset + 1):
        clip_id = item.get("clipId")
        normalized = make_item(
            rank=index,
            title=item.get("title"),
            source="mango",
            media_type=media_type,
            source_id=clip_id,
            year=item.get("year"),
            url=f"https://www.mgtv.com/b/{clip_id}/" if clip_id else None,
            poster=item.get("img"),
            description=item.get("desc") or item.get("subtitle"),
            score=item.get("score"),
            popularity=item.get("playCount") or item.get("hot"),
        )
        if normalized:
            results.append(normalized)
    return results


def youku_type_matches(label: str, media_type: str) -> bool:
    if media_type == "tv":
        return "电视剧" in label
    if media_type == "movie":
        return "电影" in label
    if media_type == "anime":
        return "动漫" in label
    return "综艺" in label or "相声" in label


async def fetch_youku(
    client: httpx.AsyncClient,
    media_type: str,
    page: int,
    limit: int,
) -> list[dict[str, Any]]:
    if page > 1:
        return []
    response = await client.get(
        "https://www.youku.com/ku/webhome",
        headers={
            "Referer": "https://www.youku.com/",
            "Accept-Encoding": "identity",
        },
    )
    response.raise_for_status()
    html = response.text
    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    def decode_json_string(value: str) -> str:
        try:
            return json.loads(f'"{value}"')
        except (json.JSONDecodeError, TypeError):
            return value.replace("\\u002F", "/")

    # 优酷把部分榜单（尤其是综艺）只放在页面内嵌 JSON 中，不渲染为普通 DOM。
    for match in re.finditer(r'"title":"([^"]*热度榜·TOP(\d+))"', html):
        label = match.group(1)
        if not youku_type_matches(label, media_type):
            continue
        prefix = html[max(0, match.start() - 9000):match.start()]
        title_matches = list(re.finditer(r'"title":"([^"]+)"', prefix))
        if not title_matches:
            continue
        title = decode_json_string(title_matches[-1].group(1)).strip()
        if not title or title in seen:
            continue
        seen.add(title)
        poster_matches = list(re.finditer(r'"img":"([^"]+)"', prefix))
        description_matches = list(re.finditer(r'"desc":"([^"]+)"', prefix))
        action_matches = list(
            re.finditer(
                r'"action":\{"type":"JUMP_TO_SHOW","value":"([^"]+)"',
                prefix,
            )
        )
        source_id = (
            decode_json_string(action_matches[-1].group(1))
            if action_matches
            else title
        )
        poster = (
            decode_json_string(poster_matches[-1].group(1))
            if poster_matches
            else None
        )
        if poster and poster.startswith("http://"):
            poster = "https://" + poster[7:]
        description = (
            decode_json_string(description_matches[-1].group(1))
            if description_matches
            else label
        )
        href = (
            f"https://v.youku.com/video?s={source_id}"
            if source_id != title
            else f"https://so.youku.com/search_video/q_{quote(title)}"
        )
        rank = int(match.group(2))
        normalized = make_item(
            rank=rank,
            title=title,
            source="youku",
            media_type=media_type,
            source_id=source_id,
            url=href or None,
            poster=poster,
            description=description,
            popularity=label,
        )
        if normalized:
            results.append(normalized)

    # 兼容优酷页面结构调整：内嵌 JSON 解析不到时，回退读取可见榜单卡片。
    if not results:
        soup = BeautifulSoup(html, "html.parser")
        for subtitle_node in soup.select('div[class*="pack_subtitle"]'):
            label = subtitle_node.get_text(" ", strip=True)
            if "热度榜" not in label or not youku_type_matches(label, media_type):
                continue
            anchor = subtitle_node.find_parent("a")
            if not anchor:
                continue
            title_node = anchor.select_one('div[class*="pack_title"]')
            title = title_node.get_text(" ", strip=True) if title_node else ""
            if not title or title in seen:
                continue
            seen.add(title)
            poster_node = anchor.select_one("img[src]")
            href = str(anchor.get("href") or "")
            if href.startswith("//"):
                href = "https:" + href
            elif href.startswith("/"):
                href = "https://www.youku.com" + href
            rank_match = re.search(r"TOP(\d+)", label, re.IGNORECASE)
            rank = int(rank_match.group(1)) if rank_match else len(results) + 1
            source_match = re.search(r"(?:[?&])s=([^&]+)", href)
            normalized = make_item(
                rank=rank,
                title=title,
                source="youku",
                media_type=media_type,
                source_id=source_match.group(1) if source_match else title,
                url=href or None,
                poster=poster_node.get("src") if poster_node else None,
                description=label,
                popularity=label,
            )
            if normalized:
                results.append(normalized)
    results.sort(key=lambda item: item["rank"])
    return results[:limit]


FETCHERS = {
    "tmdb": fetch_tmdb,
    "douban": fetch_douban,
    "iqiyi": fetch_iqiyi,
    "tencent": fetch_tencent,
    "youku": fetch_youku,
    "mango": fetch_mango,
}


async def load_ranking(
    client: httpx.AsyncClient,
    tmdb_client: httpx.AsyncClient,
    source: str,
    media_type: str,
    page: int,
    limit: int,
) -> tuple[list[dict[str, Any]], bool]:
    async def loader() -> list[dict[str, Any]]:
        try:
            active_client = tmdb_client if source == "tmdb" else client
            return await FETCHERS[source](active_client, media_type, page, limit)
        except httpx.HTTPError as exc:
            raise UpstreamError(f"{SOURCE_LABELS[source]}上游请求失败：{exc}") from exc
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise UpstreamError(f"{SOURCE_LABELS[source]}返回数据解析失败：{exc}") from exc

    return await cache.get_or_load(
        f"{source}:{media_type}:{page}:{limit}",
        DEFAULT_CACHE_SECONDS,
        loader,
    )


def error_response(exc: Exception, source: Optional[str] = None) -> JSONResponse:
    message = str(exc)
    code = "invalid_request"
    status_code = 422
    if isinstance(exc, UpstreamError):
        code = "upstream_error"
        status_code = 502
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "source": source,
            "error": {"code": code, "message": message},
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def success_payload(
    source: str,
    media_type: str,
    page: int,
    limit: int,
    items: list[dict[str, Any]],
    cached: bool,
) -> dict[str, Any]:
    return {
        "success": True,
        "source": source,
        "source_name": SOURCE_LABELS[source],
        "media_type": media_type,
        "page": page,
        "limit": limit,
        "count": len(items),
        "items": items,
        "cache": {
            "hit": cached,
            "ttl_seconds": DEFAULT_CACHE_SECONDS,
        },
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def is_allowed_image_url(raw_url: str) -> bool:
    parsed = urlparse(raw_url)
    host = (parsed.hostname or "").lower()
    return (
        parsed.scheme in {"http", "https"}
        and any(host == allowed or host.endswith("." + allowed) for allowed in ALLOWED_IMAGE_HOSTS)
    )


@app.get("/", include_in_schema=False)
async def root() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/portal-widget.js", include_in_schema=False)
async def portal_widget() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "portal-widget.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "success": True,
        "status": "ok",
        "version": SERVICE_VERSION,
        "time": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/sources")
async def sources() -> dict[str, Any]:
    return {
        "success": True,
        "sources": [
            {
                "id": source,
                "name": SOURCE_LABELS[source],
                "media_types": ["movie", "tv", "variety", "anime"],
                "aliases": [
                    alias
                    for alias, target in SOURCE_ALIASES.items()
                    if target == source and alias != source
                ],
            }
            for source in FETCHERS
        ],
        "media_types": ["movie", "tv", "variety", "anime"],
        "cache_ttl_seconds": DEFAULT_CACHE_SECONDS,
    }


@app.get("/api/v1/image")
async def image_proxy(request: Request, url: str) -> Response:
    if not is_allowed_image_url(url):
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": {
                    "code": "image_host_not_allowed",
                    "message": "该图片域名不在允许列表中。",
                },
            },
        )
    host = (urlparse(url).hostname or "").lower()
    if host.endswith("tmdb.org"):
        referer = "https://www.themoviedb.org/"
    elif host.endswith("doubanio.com"):
        referer = "https://movie.douban.com/"
    elif host.endswith("qpic.cn"):
        referer = "https://v.qq.com/"
    elif host.endswith("ykimg.com") or host.endswith("alicdn.com"):
        referer = "https://www.youku.com/"
    elif host.endswith("hitv.com"):
        referer = "https://www.mgtv.com/"
    else:
        referer = "https://www.iqiyi.com/"
    try:
        upstream = await request.app.state.http.get(
            url,
            headers={"Referer": referer, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"},
        )
        upstream.raise_for_status()
        final_host = (upstream.url.host or "").lower()
        if not any(
            final_host == allowed or final_host.endswith("." + allowed)
            for allowed in ALLOWED_IMAGE_HOSTS
        ):
            raise UpstreamError("图片跳转到了未授权域名。")
        content_type = upstream.headers.get("content-type", "").split(";", 1)[0].strip()
        if not content_type.startswith("image/"):
            raise UpstreamError("上游返回的内容不是图片。")
        content = upstream.content
        if len(content) > 8 * 1024 * 1024:
            raise UpstreamError("图片体积超过 8MB。")
        return Response(
            content=content,
            media_type=content_type,
            headers={
                "Cache-Control": "public, max-age=86400, immutable",
                "Content-Length": str(len(content)),
            },
        )
    except (httpx.HTTPError, UpstreamError) as exc:
        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "error": {"code": "image_proxy_error", "message": str(exc)},
            },
        )


@app.get("/api/v1/rankings/all")
async def all_rankings(
    request: Request,
    media_type: str = Query("tv", alias="type"),
    limit: int = Query(20, ge=1, le=50),
) -> JSONResponse:
    try:
        normalized_type = normalize_media_type(media_type)
    except ValueError as exc:
        return error_response(exc)

    async def one(source: str) -> tuple[str, Any, Optional[Exception]]:
        try:
            items, cached = await load_ranking(
                request.app.state.http,
                request.app.state.tmdb_http,
                source,
                normalized_type,
                1,
                limit,
            )
            return source, success_payload(source, normalized_type, 1, limit, items, cached), None
        except Exception as exc:
            return source, None, exc

    tasks = await asyncio.gather(*(one(source) for source in FETCHERS))
    source_results: dict[str, Any] = {}
    failures = 0
    for source, payload, exc in tasks:
        if exc:
            failures += 1
            source_results[source] = {
                "success": False,
                "source": source,
                "source_name": SOURCE_LABELS[source],
                "error": {"code": "upstream_error", "message": str(exc)},
            }
        else:
            source_results[source] = payload
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "partial": failures > 0,
            "media_type": normalized_type,
            "sources": source_results,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        },
    )


@app.get("/api/v1/rankings/{source}")
async def ranking(
    request: Request,
    source: str,
    media_type: str = Query("tv", alias="type"),
    page: int = Query(1, ge=1, le=50),
    limit: int = Query(20, ge=1, le=50),
) -> JSONResponse:
    try:
        normalized_source = normalize_source(source)
        normalized_type = normalize_media_type(media_type)
        items, cached = await load_ranking(
            request.app.state.http,
            request.app.state.tmdb_http,
            normalized_source,
            normalized_type,
            page,
            limit,
        )
        return JSONResponse(
            content=success_payload(
                normalized_source,
                normalized_type,
                page,
                limit,
                items,
                cached,
            )
        )
    except (ValueError, UpstreamError) as exc:
        return error_response(exc, source)


@app.get("/api/v1/rankings")
async def ranking_query(
    request: Request,
    source: str,
    media_type: str = Query("tv", alias="type"),
    page: int = Query(1, ge=1, le=50),
    limit: int = Query(20, ge=1, le=50),
) -> JSONResponse:
    return await ranking(request, source, media_type, page, limit)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8891")),
        root_path=ROOT_PATH,
    )
