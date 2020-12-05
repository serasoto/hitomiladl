#!/usr/bin/env python3

from unittest.main import main
import unittest
from unittest.mock import patch, MagicMock

import ehentai
import os


class TestUrlopen(unittest.TestCase):
    def setUp(self):
        with open(os.path.join('test', 'book.html'), 'r') as f:
            self.test_html = f.read()

    def test_find_url(self):
        hitomila_url = ehentai.FindHitomiLa(self.test_html)
        self.assertEqual(hitomila_url,
                         'https://hitomi.la/galleries/1401451.html')

    def test_find_title(self):
        title = ehentai.FindTitle(self.test_html)
        self.assertEqual(
            title, '(C95) [八月二日 (ハル犬)] BOOK TSUKIOKA (アイドルマスター シャイニーカラーズ)')

    def test_read_urls_from_file(self):
        urls = ehentai._GetUrlsFromFile(os.path.join('test', 'url_list.txt'))
        self.assertCountEqual(urls, [
            'https://e-hentaidb.com/?id=207297',
            'https://e-hentaidb.com/?id=185797',
        ])

    def test_subdomain_calc(self):
        subdomain = ehentai._CalculcateSubdomainFromHash(
            'ea81fc2167036c9ab6f99c7fc9e02c7d12a29182461aa29db6644a5e7d92c1a4')
        self.assertEqual(subdomain, 'ab')


if __name__ == "__main__":
    unittest.main()