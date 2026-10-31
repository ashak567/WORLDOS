from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from app.ingestion.live_context import (
    LiveContextFeedError,
    fetch_global_climate,
    fetch_global_news,
)


class LiveContextFeedTests(unittest.TestCase):
    now = datetime(2026, 10, 31, tzinfo=UTC)

    @patch("app.ingestion.live_context._download")
    def test_parses_nasa_monthly_csv_after_title_line(self, download) -> None:
        csv_body = (
            "Land-Ocean: Global Means\n"
            "Year,Jan,Feb,Mar,Apr,May,Jun,Jul,Aug,Sep,Oct,Nov,Dec,J-D,D-N,DJF,MAM,JJA,SON\n"
            "2024,0.85,0.87,0.88,0.89,0.90,0.91,0.92,0.93,0.94,0.95,0.96,***,0.91,0.91,0.87,0.89,0.92,0.95\n"
            "2025,***,***,***,***,***,***,***,***,***,***,***,***,***,***,***,***,***,***\n"
        ).encode()
        download.return_value = (csv_body, self.now, "fresh")

        climate, retrieved_at, status = fetch_global_climate(self.now)

        self.assertEqual(climate["period"], "2024-11")
        self.assertEqual(climate["global_temperature_anomaly_c"], 0.96)
        self.assertEqual(retrieved_at, self.now)
        self.assertEqual(status, "fresh")

    @patch("app.ingestion.live_context._download")
    def test_rejects_climate_csv_without_monthly_header(self, download) -> None:
        download.return_value = (b"title\nnot,a,climate,file\n", self.now, "fresh")

        with self.assertRaises(LiveContextFeedError):
            fetch_global_climate(self.now)

    @patch("app.ingestion.live_context._download")
    def test_parses_gdelt_article_list_response(self, download) -> None:
        payload = {
            "articles": [
                {
                    "title": "Example earthquake report",
                    "url": "https://example.org/story",
                    "domain": "example.org",
                    "seendate": "20261031T120000Z",
                    "language": "English",
                    "sourcecountry": "United States",
                }
            ]
        }
        download.return_value = (json.dumps(payload).encode(), self.now, "fresh")

        articles, retrieved_at, status = fetch_global_news(self.now)

        self.assertEqual(articles[0]["title"], "Example earthquake report")
        self.assertEqual(articles[0]["published_at"], "20261031T120000Z")
        self.assertEqual(retrieved_at, self.now)
        self.assertEqual(status, "fresh")

    @patch("app.ingestion.live_context._download")
    def test_empty_gdelt_article_list_is_valid(self, download) -> None:
        download.return_value = (b'{"articles": []}', self.now, "fresh")

        articles, _, _ = fetch_global_news(self.now)

        self.assertEqual(articles, [])

    @patch("app.ingestion.live_context._download")
    def test_rejects_gdelt_error_payload_without_articles(self, download) -> None:
        download.return_value = (b'{"error": "rate limited"}', self.now, "fresh")

        with self.assertRaises(LiveContextFeedError):
            fetch_global_news(self.now)


if __name__ == "__main__":
    unittest.main()
