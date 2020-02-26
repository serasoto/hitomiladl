#!/usr/bin/env python3

"""Use this script to test fetching web resources.

This is a script that can be used to test certain requests to fetch an asset.
It has UA and refer setup.
"""

import argparse
import urllib.request as urllib2
import logging

UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_4) '
      'AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/73.0.3683.103 Safari/537.36')


def Fetch(id, url):
    referer_url = 'https://hitomi.la/reader/' + str(id) + '.html'
    try:
        opener = urllib2.build_opener()
        opener.addheaders = [
            ('User-Agent', UA),
            ('Referer', referer_url),
            {'Sec-Fetch-Mode', 'no-cors'}]
        response = opener.open(url)
        length = int(response.headers['Content-Length'])

        logging.info('fetched %s successfully'.format(url))

    except urllib2.HTTPError as e:
        logging.error('HTTPError: code: [{0}]'.format(e.code), url)
        raise e


if __name__ == "__main__":
    # execute only if run as a script
    parser = argparse.ArgumentParser()
    parser.add_argument('--id', type=str, required=True)
    parser.add_argument('--url', type=str, required=True)
    args = parser.parse_args()
    Fetch(args.id, args.url)
