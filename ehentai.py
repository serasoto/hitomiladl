#!/usr/bin/env python3

from typing import NamedTuple
from bs4 import BeautifulSoup
import urllib.request as urllib2
import logging
import shutil
import argparse
import os
import zipfile
import urllib
import tempfile
import re
import json
import time
import http
from rich.console import Console
from rich.table import Column, Table

UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_4) '
      'AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/73.0.3683.103 Safari/537.36')


def FindHitomiLa(html_text):
    """Finds the link to hitomi.la from html"""
    soup = BeautifulSoup(html_text, 'html.parser')
    found_elements = soup.find_all('a', text='hitomi.la')

    num_found = len(found_elements)
    if num_found == 0:
        logging.error('Failed to find matching element')
        return None

    if num_found > 1:
        logging.warning('Found %d elements that matched.' % len(num_found))
    target_elem = found_elements[0]
    url = target_elem['href']
    logging.info('Found Hitomi.la url: ' + url)
    return url


def FindTitle(html_text):
    """Finds the title of the book from html"""
    soup = BeautifulSoup(html_text, 'html.parser')
    title_elems = soup.find_all('h2', class_='title_jp')
    if not title_elems:
        # If there is no JP title, then there's only EN title which is actually
        # in JP.
        title_elems = soup.find_all('h2', class_='title_en')
    target_elem = title_elems[0]
    title = target_elem.contents[0]
    logging.info('Found title: ' + title)
    return title


def _FetchPage(url):
    try:
        req = urllib2.Request(url)
        response = urllib2.urlopen(req)
        return response.read()
    except urllib.error.URLError as e:
        logging.error('Failed to get %s reason: %s\n' % (url, e.reason))
        return ""


def FindHitomiLaUrl(ehentai_db_url):
    page_html = _FetchPage(ehentai_db_url)
    return FindHitomiLa(page_html)


def _HashAndNameToImagePath(hash, name):
    """Calculates the image path from hash value of the image

    This takes the last 3 characters of the hash string and creates a path by
    putting the last character followed by slash then the third to last and
    secont to last followed by slash. Then appends the hash.
    e.g.
    9a9c4953baf0cc84486a546e24da2edc61ba2864852bf11da6a07e4f63d037cb
    is changed to
    images/b/7c/9a9c4953baf0cc84486a546e24da2edc61ba2864852bf11da6a07e4f63d037cb

    |name| is used to get the file extension.
    """
    # Note that |ext| contains a dot.
    ext = os.path.splitext(name)[1]
    second_part = hash[-3:-1]
    first_part = hash[-1:]
    return 'images/{}/{}/{}{}'.format(first_part, second_part, hash, ext)


def _CalculcateSubdomainFromHash(hash):
    """Calculates the 

    Following is the original logic from javascript
    function subdomain_from_galleryid(g) {
        if (adapose) {
            return '0';
        }

        var o = g % number_of_frontends;

        return String.fromCharCode(97 + o);
    }

    function subdomain_from_url(url, base) {
        var retval = 'a';
        if (base) {
                retval = base;
        }

        var b = 16;
        var r = /\/[0-9a-f]\/([0-9a-f]{2})\//;
        var m = r.exec(url);
        if (!m) {
                return retval;
        }

        var g = parseInt(m[1], b);
        if (!isNaN(g)) {
                if (g < 0x20) {
                        g = 1;
                }
                retval = subdomain_from_galleryid(g) + retval;
        }

        return retval;
    }
    Note that AFAICT base will not be set.
    The regex is basically looking for the third to last and second to last
    character of the hash.
    e.g.
    For hash
    9a9c4953baf0cc84486a546e24da2edc61ba2864852bf11da6a07e4f63d037cb
    it is
    7c

    |adapose| is always false.
    |number_of_frontends| is 3.

    Since the hash is a hex string, there is no reason for g to be NaN.
    This function immitates the javascript function with the assumptions in the
    description above.
    """
    _NUM_FRONTENDS = 3
    _BASE = 16

    # Note that this isn't the "usual" gallery ID.
    gallery_id = int(hash[-3:-1], _BASE)
    if gallery_id < 0x20:
        gallery_id = 1
    modded_gallery_id = gallery_id % _NUM_FRONTENDS
    return chr(97 + modded_gallery_id) + 'a'


def _DownloadImageToFile(url, referer_url, file):
    """Downloads image to the file.

    Args:
      url is the image URL to be downloaded.
      referer_url is the referer that should be used.
      file is the local file path where the image should be saved.

    Raises:
      HTTPError on 404.
    """
    _MAX_RETRY = 5
    for loop in range(1, _MAX_RETRY):
        time.sleep(2)
        try:
            opener = urllib2.build_opener()
            opener.addheaders = [
                ('User-Agent', UA),
                ('Referer', referer_url),
                {'Sec-Fetch-Mode', 'no-cors'}]
            response = opener.open(url)

            length = int(response.headers['Content-Length'])

            if (os.path.exists(file)) and (os.stat(file).st_size == length):
                logging.info(file + 'file already exists.')
                return
            else:
                img = response.read()
                with open(file, 'wb') as f:
                    f.write(img)

            if length == os.stat(file).st_size:
                return
            else:
                logging.error('Download size mismatch ' + 'file size:' +
                              str(os.stat(file).st_size) + '  content-length:' + str(length))
                continue

        except urllib2.HTTPError as e:
            print('HTTPError: code: [{0}]'.format(e.code), url)
            if e.code == 404:
                raise e
            ex = e

        except http.client.IncompleteRead as e:
            logging.error('http: IncompleteRead')
            ex = e

        except urllib2.URLError as e:
            logging.error('URLError: reason: [{0}]'.format(e.reason), url)
            ex = e

        except IOError as e:
            logging.error('IOError:errno: [{0}] msg: [{1}]'.format(
                e.errno, e.strerror), url)
            raise e

    raise ex


class ImageInfo(NamedTuple):
    # The name of the image file.
    name: str
    # The URL of the image.
    url: str


class HitomiPage:
    def __init__(self, url):
        ptr = re.compile('^https?:\/\/.*[^0-9]([0-9]*).html.*$')
        m = ptr.search(url.rstrip('\n'))
        if m:
            self.__id = m.group(1)

        self.__img_list = []

    def GetImageInfo(self):
        """Gets the list of image's information.

        Returns:
          A list of ImageInfo object in the order of the images in the book.

        Raises:
          HTTPError on HTTP Status 404.
          URLError on other errors.
        """
        _MAX_RETRY = 5
        js_url = 'https://ltn.hitomi.la/galleries/' + self.__id + '.js'

        for _ in range(1, _MAX_RETRY):
            try:
                req = urllib2.Request(js_url)
                response = urllib2.urlopen(req)
                js = response.read().decode('utf_8')

                # The content is not a JSON only, so strip stuff that gets in
                # the way of parsing it as JSON.
                prefix = 'var galleryinfo = '
                prefix_index = js.find(prefix)
                js = js[prefix_index + len(prefix):]
                images_info_array = json.loads(js)

                # A JSON entry looks like
                # {
                #   width: 212
                #   hash: "5bf94d9914ae784830586fc08f1e1dc5cce550fe4d2c551e5d16377708458c2c"
                #   haswebp: 1
                #   name: "marie2_003.jpg"
                #   height: 300
                # }
                # This now requires calculating the subdomain for each image.
                # The previous step has added the last 3 digits of the hash as
                # part of the URL.
                # Use the the last letter to see if it can be base 16 decoded
                # (I don't see why it cannot be), and use it to calculate the
                # domain.
                for image_info in images_info_array['files']:
                    image_hash = image_info['hash']
                    path = _HashAndNameToImagePath(
                        image_hash, image_info['name'])
                    subdomain = _CalculcateSubdomainFromHash(image_hash)
                    domain = subdomain + '.hitomi.la'
                    imgurl = 'https://{}/{}'.format(domain, path)
                    imginfo = ImageInfo(image_info['name'], imgurl)
                    self.__img_list.append(imginfo)

                return self.__img_list

            except urllib2.HTTPError as e:
                logging.error('HTTPError: code: [{0}]'.format(e.code), js_url)
                if e.code == 404:
                    # 404 Not Foundはリトライする必要が無いため即復帰
                    raise e
                ex = e

            except urllib2.URLError as e:
                logging.error(
                    'URLError: reason: [{0}]'.format(e.reason), js_url)
                ex = e
        raise ex

    def DownloadImagesTo(self, path):
        """Downloads images to the specified path.

        Donloads images to the specified path.

        Args:
          path must be a directory. Images are downloaded to the path.
        """
        if not self.__img_list:
            self.GetImageInfo()

        list = self.__img_list
        if not os.path.exists(path):
            os.makedirs(path)

        logging.debug('image list: ' + str(list))
        referer_url = 'https://hitomi.la/reader/' + self.__id + '.html'

        for image_info in list:
            image_file_name = re.sub(r'^.+/([^/]+)$', r'\1', image_info.name)
            local_file = os.path.join(path, image_file_name)
            url = image_info.url
            print('Download url=' + url + '  To file=' + local_file)
            _DownloadImageToFile(url, referer_url, local_file)


class EhentaiDbPage:
    def __init__(self, url):
        self.__page_html = _FetchPage(url)
        self.__hitomila_url = FindHitomiLa(self.__page_html)
        self.__title = FindTitle(self.__page_html)

    def title(self):
        return self.__title

    def hitomila(self):
        return self.__hitomila_url


def _ZipImageFiles(image_dir, dest):
    assert os.path.exists(image_dir)

    dir_with_images = image_dir
    image_files = [
        os.path.join(dir_with_images, f) for f in os.listdir(dir_with_images)
    ]
    with zipfile.ZipFile(dest, 'w') as dest_zip:
        for f in image_files:
            # The second arg is the archive name, so just use the files' name.
            dest_zip.write(f, os.path.basename(f))
    logging.info('Wrote archive to ' + dest)


def _PrintFailures(not_found, failed):
    console = Console()

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Fail Status", style="dim", width=12)
    table.add_column("URL")

    for nf in not_found:
        table.add_row(
            'Not Found', nf
        )
    
    for f in failed:
        table.add_row(
            'Failed to find book URL', f
        )

    console.print(table)
    pass


def DownloadFromHitomila(urls, output_dir):
    """Downloads assets and put them in output directory.

    Args:
      urls is the URLs of the assets to download.
      output_dir is where the dowloaded files are put. The directory must exist.
    """
    failed = []
    not_found = []
    for url in urls:
        logging.info('Start %s' % url)
        ehentai = EhentaiDbPage(url)

        if not ehentai.hitomila():
            logging.warning('Failed to find Hitomila url for %s, skipping.' %
                            url)
            failed.append(url)
            continue

        book_title = ehentai.title()
        if '/' in book_title:
            book_title = book_title.replace('/', '_')
            logging.info('Found / in book title, renamed to %s' % book_title)

        logging.info('Fetching: %s' % book_title)

        zip_file_path = os.path.join(output_dir, book_title + '.zip')
        if os.path.exists(zip_file_path):
            logging.info("%s already exists." % book_title)
            continue

        # Check whether the page is accessible. Especially bad when 404.
        try:
            req = urllib2.Request(ehentai.hitomila())
            response = urllib2.urlopen(req)
            response.read()
        except urllib.error.HTTPError as e:
            logging.error('Failed to get page %s with code %d. Skipping.' %
                          (url, e.code))
            if e.code == 404:
                not_found.append(url)
            else:
                failed.append(url)
            continue

        h = HitomiPage(ehentai.hitomila())
        with tempfile.TemporaryDirectory() as images_dir:
            try:
                h.DownloadImagesTo(images_dir)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    not_found.append(url)
                else:
                    failed.append(url)
                continue

            _ZipImageFiles(images_dir, zip_file_path)
            print('Saved to %s' % zip_file_path)

    _PrintFailures(not_found, failed)


def _GetUrlsFromFile(path):
    with open(path, 'r') as f:
        return filter(None, [line.strip() for line in f])


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    parser = argparse.ArgumentParser()
    parser.add_argument('urls',
                        metavar='URLs',
                        type=str,
                        nargs='*',
                        help='List or URLs to download.')
    parser.add_argument('-o',
                        '--output',
                        type=str,
                        default='.',
                        help='Output directory.')
    parser.add_argument('-f', '--file', type=str, help='File with URLs.')

    args = parser.parse_args()
    urls = []

    if args.file:
        file_path = os.path.join(os.getcwd(), args.file)
        urls.extend(_GetUrlsFromFile(file_path))

    if args.urls:
        urls.extend(args.urls)

    logging.info(urls)
    # Print all the urls to stdout so that it's easier to copy past
    # if needed.
    for url in urls:
        print(url)

    DownloadFromHitomila(urls, args.output)
