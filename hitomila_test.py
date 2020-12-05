#!/usr/bin/env python3

from unittest.main import main
import unittest
from unittest.mock import patch, MagicMock

import hitomila
import os


class TestUrlopen(unittest.TestCase):
    def test_read_urls_from_file(self):
        urls = hitomila._GetUrlsFromFile(os.path.join('test', 'url_list.txt'))
        self.assertCountEqual(urls, [
            'https://e-hentaidb.com/?id=207297',
            'https://e-hentaidb.com/?id=185797',
        ])

    def test_subdomain_calc(self):
        subdomain = hitomila._CalculcateSubdomainFromHash(
            'ea81fc2167036c9ab6f99c7fc9e02c7d12a29182461aa29db6644a5e7d92c1a4')
        self.assertEqual(subdomain, 'ab')


if __name__ == "__main__":
    unittest.main()