import unittest

from app.routers.news import _parse_feed


class NewsImageTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
