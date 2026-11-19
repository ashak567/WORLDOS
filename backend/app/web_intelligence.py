"""Live Web, Social, and Neural Intelligence Engine for WORLDOS.

Integrates Exa Neural Search and Tavily AI Search to synthesize real-time intelligence
from Reddit discussions, live travel reports, news, and authoritative web sources.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

logger = logging.getLogger("worldos.web_intelligence")

_root = Path(__file__).resolve().parents[2]
if (_root / ".env.local").exists():
    load_dotenv(_root / ".env.local")
if (_root / ".env").exists():
    load_dotenv(_root / ".env")
_backend = Path(__file__).resolve().parents[1]
if (_backend / ".env.local").exists():
    load_dotenv(_backend / ".env.local")
if (_backend / ".env").exists():
    load_dotenv(_backend / ".env")


def _get_exa_api_key() -> str:
    return os.getenv("EXA_API_KEY", "").strip()


def _get_tavily_api_key() -> str:
    return os.getenv("TAVILY_API_KEY", "").strip()


def search_reddit_intelligence(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search Reddit discussions via Exa domain filtering or Tavily fallback."""
    exa_key = _get_exa_api_key()
    if exa_key:
        try:
            req = urllib.request.Request(
                "https://api.exa.ai/search",
                headers={
                    "x-api-key": exa_key,
                    "Content-Type": "application/json",
                    "User-Agent": "WORLDOS-Intelligence/1.0",
                },
                data=json.dumps({
                    "query": query,
                    "type": "auto",
                    "numResults": limit,
                    "includeDomains": ["reddit.com"],
                    "contents": {"highlights": True},
                }).encode("utf-8"),
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                results = []
                for item in data.get("results", []):
                    highlights = item.get("highlights", [])
                    snippet = highlights[0] if highlights else item.get("text", "")[:200]
                    results.append({
                        "platform": "reddit",
                        "title": item.get("title") or "Reddit Discussion",
                        "url": item.get("url"),
                        "snippet": snippet,
                        "published_date": item.get("publishedDate"),
                    })
                if results:
                    return results
        except Exception as exc:
            logger.warning("Exa Reddit search failed: %s; falling back to Tavily", exc)

    tavily_key = _get_tavily_api_key()
    if tavily_key:
        try:
            req = urllib.request.Request(
                "https://api.tavily.com/search",
                headers={"Content-Type": "application/json"},
                data=json.dumps({
                    "api_key": tavily_key,
                    "query": f"{query} site:reddit.com",
                    "max_results": limit,
                    "search_depth": "basic",
                }).encode("utf-8"),
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [
                    {
                        "platform": "reddit",
                        "title": item.get("title") or "Reddit Thread",
                        "url": item.get("url"),
                        "snippet": item.get("content", "")[:250],
                    }
                    for item in data.get("results", [])
                ]
        except Exception as exc:
            logger.error("Tavily Reddit search failed: %s", exc)

    return []


def search_web_intelligence(query: str, limit: int = 5, platform: str = "auto") -> list[dict[str, Any]]:
    """Synthesize live web intelligence using Exa Neural Search and Tavily AI Search."""
    if platform == "reddit":
        return search_reddit_intelligence(query, limit=limit)

    results: list[dict[str, Any]] = []
    exa_key = _get_exa_api_key()
    if exa_key and platform in ("auto", "exa"):
        try:
            req = urllib.request.Request(
                "https://api.exa.ai/search",
                headers={
                    "x-api-key": exa_key,
                    "Content-Type": "application/json",
                    "User-Agent": "WORLDOS-Intelligence/1.0",
                },
                data=json.dumps({
                    "query": query,
                    "type": "auto",
                    "numResults": limit,
                    "contents": {"highlights": True},
                }).encode("utf-8"),
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data.get("results", []):
                    highlights = item.get("highlights", [])
                    snippet = highlights[0] if highlights else item.get("text", "")[:200]
                    domain = urllib.parse.urlparse(item.get("url", "")).netloc
                    results.append({
                        "platform": "reddit" if "reddit.com" in domain else "exa",
                        "title": item.get("title") or "Web Intelligence",
                        "url": item.get("url"),
                        "snippet": snippet,
                        "source": domain,
                    })
                if results:
                    return results
        except Exception as exc:
            logger.warning("Exa search error: %s; trying Tavily", exc)

    tavily_key = _get_tavily_api_key()
    if tavily_key and (not results or platform == "tavily"):
        try:
            req = urllib.request.Request(
                "https://api.tavily.com/search",
                headers={"Content-Type": "application/json"},
                data=json.dumps({
                    "api_key": tavily_key,
                    "query": query,
                    "max_results": limit,
                    "search_depth": "basic",
                }).encode("utf-8"),
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data.get("results", []):
                    domain = urllib.parse.urlparse(item.get("url", "")).netloc
                    results.append({
                        "platform": "reddit" if "reddit.com" in domain else "tavily",
                        "title": item.get("title") or "Web Intelligence",
                        "url": item.get("url"),
                        "snippet": item.get("content", "")[:250],
                        "source": domain,
                    })
        except Exception as exc:
            logger.error("Tavily search error: %s", exc)

    return results
