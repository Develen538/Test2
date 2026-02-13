import argparse
import csv
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import urllib.parse
import urllib.request
import urllib.error

BASE_URL = "https://www.googleapis.com/youtube/v3"


def load_env_file(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


@dataclass
class ShortsMetric:
    video_id: str
    title: str
    channel_id: str
    channel_title: str
    published_at: str
    default_language: str
    view_count: int
    like_count: int
    comment_count: int
    engagement_score: int
    top_comment_text: str
    top_comment_like_count: int
    collected_at_utc: str


class YouTubeClient:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def _get(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        params = {**params, "key": self.api_key}
        query = urllib.parse.urlencode(params)
        url = f"{BASE_URL}/{endpoint}?{query}"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            raise RuntimeError(
                f"HTTP {exc.code} while requesting {endpoint}. URL={url}. API says: {body or exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Network/API error while requesting {endpoint}: {exc}") from exc


    @staticmethod
    def _is_search_bad_request(exc: RuntimeError) -> bool:
        text = str(exc).lower()
        return "http 400" in text and "search" in text

    def search_shorts(
        self,
        query: str,
        max_results: int,
        channel_id: Optional[str],
        relevance_language: Optional[str],
        region_code: Optional[str],
    ) -> List[str]:
        video_ids: List[str] = []
        next_page_token: Optional[str] = None

        while len(video_ids) < max_results:
            batch_size = min(50, max_results - len(video_ids))
            params: Dict[str, Any] = {
                "part": "id",
                "type": "video",
                "q": query,
                "maxResults": batch_size,
                "order": "date",
                "videoDuration": "short",
            }
            if channel_id:
                params["channelId"] = channel_id
            if relevance_language:
                params["relevanceLanguage"] = relevance_language
            if region_code:
                params["regionCode"] = region_code
            if next_page_token:
                params["pageToken"] = next_page_token

            try:
                data = self._get("search", params)
            except RuntimeError as exc:
                if self._is_search_bad_request(exc) and (relevance_language or region_code):
                    fallback_params = dict(params)
                    fallback_params.pop("relevanceLanguage", None)
                    fallback_params.pop("regionCode", None)
                    data = self._get("search", fallback_params)
                else:
                    raise
            ids = [
                item["id"]["videoId"]
                for item in data.get("items", [])
                if "videoId" in item.get("id", {})
            ]
            if not ids:
                break

            video_ids.extend(ids)
            next_page_token = data.get("nextPageToken")
            if not next_page_token:
                break

        seen = set()
        unique_ids = []
        for vid in video_ids:
            if vid not in seen:
                seen.add(vid)
                unique_ids.append(vid)

        return unique_ids[:max_results]

    def get_videos_details(self, video_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        if not video_ids:
            return {}

        all_items: Dict[str, Dict[str, Any]] = {}
        for start in range(0, len(video_ids), 50):
            chunk = video_ids[start : start + 50]
            data = self._get(
                "videos",
                {
                    "part": "snippet,statistics",
                    "id": ",".join(chunk),
                    "maxResults": len(chunk),
                },
            )
            for item in data.get("items", []):
                all_items[item["id"]] = item

        return all_items

    def get_top_comment(self, video_id: str) -> Dict[str, Any]:
        try:
            data = self._get(
                "commentThreads",
                {
                    "part": "snippet",
                    "videoId": video_id,
                    "maxResults": 1,
                    "order": "relevance",
                    "textFormat": "plainText",
                },
            )
            items = data.get("items", [])
            if not items:
                return {"text": "", "like_count": 0}

            top = items[0]["snippet"]["topLevelComment"]["snippet"]
            return {
                "text": top.get("textDisplay", ""),
                "like_count": int(top.get("likeCount", 0)),
            }
        except urllib.error.HTTPError:
            return {"text": "", "like_count": 0}


def to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def collect_metrics(
    query: str,
    max_results: int,
    channel_id: Optional[str],
    relevance_language: Optional[str],
    region_code: Optional[str],
) -> List[ShortsMetric]:
    load_env_file()
    api_key = os.getenv("YOUTUBE_API_KEY", "")
    if not api_key:
        raise ValueError("YOUTUBE_API_KEY not found. Put it in .env")

    if max_results < 1 or max_results > 100:
        raise ValueError("max_results should be between 1 and 100")

    client = YouTubeClient(api_key)
    video_ids = client.search_shorts(
        query=query,
        max_results=max_results,
        channel_id=channel_id,
        relevance_language=relevance_language,
        region_code=region_code,
    )
    details = client.get_videos_details(video_ids)

    collected_at = datetime.now(timezone.utc).isoformat()
    metrics: List[ShortsMetric] = []

    for video_id in video_ids:
        item = details.get(video_id)
        if not item:
            continue

        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        comment = client.get_top_comment(video_id)
        like_count = to_int(stats.get("likeCount"))
        comment_count = to_int(stats.get("commentCount"))

        metrics.append(
            ShortsMetric(
                video_id=video_id,
                title=snippet.get("title", ""),
                channel_id=snippet.get("channelId", ""),
                channel_title=snippet.get("channelTitle", ""),
                published_at=snippet.get("publishedAt", ""),
                default_language=snippet.get("defaultLanguage", ""),
                view_count=to_int(stats.get("viewCount")),
                like_count=like_count,
                comment_count=comment_count,
                engagement_score=(like_count * 2) + (comment_count * 3),
                top_comment_text=comment["text"],
                top_comment_like_count=to_int(comment["like_count"]),
                collected_at_utc=collected_at,
            )
        )

    metrics.sort(
        key=lambda x: (x.engagement_score, x.like_count, x.comment_count, x.top_comment_like_count),
        reverse=True,
    )
    return metrics


def write_outputs(metrics: List[ShortsMetric], output_prefix: str) -> None:
    Path(output_prefix).parent.mkdir(parents=True, exist_ok=True)
    output_json = Path(f"{output_prefix}.json")
    output_csv = Path(f"{output_prefix}.csv")

    serializable = [asdict(item) for item in metrics]
    output_json.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")

    headers = list(ShortsMetric.__annotations__.keys())
    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(serializable)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect YouTube Shorts metrics")
    parser.add_argument(
        "--query",
        default="смешные видео",
        help="Search query for shorts (default: развлекательная ниша)",
    )
    parser.add_argument("--max-results", type=int, default=30, help="Max shorts to fetch (1..100)")
    parser.add_argument("--channel-id", default=None, help="Optional channel ID filter")
    parser.add_argument(
        "--relevance-language",
        default="ru",
        help="Language hint for search results (e.g. ru, en). Use empty string to disable.",
    )
    parser.add_argument(
        "--region-code",
        default="RU",
        help="Region hint for search results (e.g. RU, US). Use empty string to disable.",
    )
    parser.add_argument(
        "--output",
        default=f"data/shorts_metrics_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
        help="Output file prefix without extension",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        metrics = collect_metrics(
            query=args.query,
            max_results=args.max_results,
            channel_id=args.channel_id,
            relevance_language=args.relevance_language,
            region_code=args.region_code,
        )
    except RuntimeError as exc:
        print("ERROR:", exc)
        print("Подсказка: проверь API key, включен ли YouTube Data API v3, и ограничения ключа (IP/HTTP referrer).")
        print("Быстрый тест без RU-фильтров: --relevance-language '' --region-code ''")
        raise SystemExit(1)

    write_outputs(metrics, args.output)
    print(f"Collected {len(metrics)} shorts. Saved to {args.output}.json and {args.output}.csv")


if __name__ == "__main__":
    main()
