import unittest
from unittest.mock import MagicMock, patch
from urllib.request import Request as UrlRequest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import news
from app.routers.news import _fetch_feed, _is_relevant_article, _parse_feed


class NewsImageTests(unittest.TestCase):
    def test_fetch_feed_uses_url_request_with_feed_headers(self):
        payload = b"""<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <item>
              <title>Berita</title>
              <link>https://example.test/berita</link>
            </item>
          </channel>
        </rss>
        """
        response = MagicMock()
        response.__enter__.return_value.read.return_value = payload

        with patch("app.routers.news.urlopen", return_value=response) as urlopen:
            articles = _fetch_feed("pernikahan dini")

        request = urlopen.call_args.args[0]
        self.assertIsInstance(request, UrlRequest)
        self.assertEqual(request.get_header("User-agent"), news.USER_AGENT)
        self.assertEqual(articles[0]["title"], "Berita")

    def test_extracts_each_article_image_from_its_own_rss_fields(self):
        payload = b"""<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
          <channel>
            <item>
              <title>Berita pertama</title>
              <link>https://example.test/berita-1</link>
              <media:thumbnail url="https://images.example.test/1.jpg" />
            </item>
            <item>
              <title>Berita kedua</title>
              <link>https://example.test/berita-2</link>
              <description>&lt;img src="https://images.example.test/2.jpg" /&gt;</description>
            </item>
          </channel>
        </rss>
        """

        articles = _parse_feed(payload)

        self.assertEqual(
            [article["image"] for article in articles],
            [
                "https://images.example.test/1.jpg",
                "https://images.example.test/2.jpg",
            ],
        )

    def test_extracts_atom_image_enclosure_link(self):
        payload = b"""<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <title>Berita Atom</title>
            <link href="https://example.test/berita" />
            <link rel="enclosure" type="image/jpeg" href="https://images.example.test/atom.jpg" />
          </entry>
        </feed>
        """

        articles = _parse_feed(payload)

        self.assertEqual(articles[0]["image"], "https://images.example.test/atom.jpg")

    def test_relevance_requires_child_marriage_and_west_java(self):
        self.assertTrue(
            _is_relevant_article(
                {
                    "title": "Dispensasi kawin meningkat di Garut",
                    "description": "",
                    "source": "Berita lokal",
                }
            )
        )
        self.assertFalse(
            _is_relevant_article(
                {
                    "title": "Pernikahan dini jadi sorotan nasional",
                    "description": "Berita ini tidak menyebut daerah setempat",
                    "source": "",
                }
            )
        )
        self.assertTrue(
            _is_relevant_article(
                {
                    "title": "Perkawinan anak di Jawa Barat",
                    "description": "",
                    "source": "",
                }
            )
        )
        self.assertFalse(
            _is_relevant_article(
                {
                    "title": "8 Provinsi dengan Angka Pernikahan Dini Tertinggi di Indonesia, Jawa Barat Urutan ke-2",
                    "description": "",
                    "source": "",
                }
            )
        )

    def test_news_without_feed_images_use_different_local_images(self):
        payload = b"""<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <item><title>Berita 1: Pernikahan dini di Jawa Barat</title><link>https://example.test/berita-1</link></item>
            <item><title>Berita 2: Pernikahan dini di Jawa Barat</title><link>https://example.test/berita-2</link></item>
            <item><title>Berita 3: Pernikahan dini di Jawa Barat</title><link>https://example.test/berita-3</link></item>
            <item><title>Berita 4: Pernikahan dini di Jawa Barat</title><link>https://example.test/berita-4</link></item>
            <item><title>Berita 5: Pernikahan dini di Jawa Barat</title><link>https://example.test/berita-5</link></item>
            <item><title>Berita 6: Pernikahan dini di Jawa Barat</title><link>https://example.test/berita-6</link></item>
            <item><title>Berita 7: Pernikahan dini di Jawa Barat</title><link>https://example.test/berita-7</link></item>
            <item><title>Berita 8: Pernikahan dini di Jawa Barat</title><link>https://example.test/berita-8</link></item>
            <item><title>Berita 9: Pernikahan dini di Jawa Barat</title><link>https://example.test/berita-9</link></item>
            <item><title>Berita 10: Pernikahan dini di Jawa Barat</title><link>https://example.test/berita-10</link></item>
            <item><title>Berita umum nasional</title><link>https://example.test/berita-irrelevan</link></item>
          </channel>
        </rss>
        """
        app = FastAPI()
        app.include_router(news.router, prefix="/api/v1")

        with patch("app.routers.news._fetch_feed", return_value=_parse_feed(payload)):
            with TestClient(app) as client:
                response = client.get("/api/v1/news?limit=9")
                self.assertEqual(response.status_code, 200)
                articles = response.json()
                self.assertEqual(len(articles), 9)
                self.assertTrue(all(news._is_relevant_article(article) for article in articles))
                image_urls = [article["image"] for article in articles]
                self.assertEqual(len(set(image_urls)), 9)

                for image_url in image_urls:
                    image_response = client.get(image_url)
                    self.assertEqual(image_response.status_code, 200)
                    self.assertTrue(image_response.headers["content-type"].startswith("image/"))
                    self.assertGreater(len(image_response.content), 0)

                invalid_image_response = client.get("/api/v1/news/images/../../main.py")

        self.assertEqual(invalid_image_response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
