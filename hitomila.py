#!/usr/bin/env python3

from typing import NamedTuple
from bs4 import BeautifulSoup
import urllib.request as urllib2
import logging
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
from rich import print
from rich.progress import Progress

UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_4) '
      'AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/73.0.3683.103 Safari/537.36')


def _HashAndNameToImagePath(hash, name):
    """Calculates the image path from hash value of the image

    This takes the last 3 characters of the hash string and creates a path by
    putting the last character followed by slash then the third to last and
    second to last followed by slash. Then appends the hash.
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

    Following is the original logic from javascript in common.js.
    Extra comments are added as notes.
    function subdomain_from_galleryid(g, number_of_frontends) {
        if (adapose) {
                return '0';
        }
        
        var o = g % number_of_frontends;

        // 97 is 'a' from ascii table.
        // Hence this entire function is
        // AsciiCharOf(97 + (gallery_id % num_front_end))
        return String.fromCharCode(97 + o);
    }

    function subdomain_from_url(url, base) {
        var retval = 'a';
        if (base) {
                retval = base;
        }
        
        var number_of_frontends = 3;
        var b = 16;
        
        var r = /\/[0-9a-f]\/([0-9a-f]{2})\//;
        var m = r.exec(url);
        if (!m) {
                return retval;
        }
        
        // This is the "gallery_id" variable below.
        var g = parseInt(m[1], b);
        if (!isNaN(g)) {
                if (g < 0x30) {
                        number_of_frontends = 2;
                }
                if (g < 0x09) {
                        g = 1;
                }
                retval = subdomain_from_galleryid(g, number_of_frontends) + retval;
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

    Since the hash is a hex string, there is no reason for g to be NaN.
    This function immitates the javascript function with the assumptions in the
    description above.
    """

    # This maps to the "retval" variable in subdomain_from_url() function.
    retval = 'b'

    number_of_frontends = 3
    _BASE = 16

    # Note that this isn't the "usual" gallery ID.
    gallery_id = int(hash[-3:-1], _BASE)
    if gallery_id < 0x30:
        number_of_frontends = 2
    if gallery_id < 0x09:
        gallery_id = 1

    # This part should behave the same way as subdomain_from_galleryid() function.
    modded_gallery_id = gallery_id % number_of_frontends
    return chr(97 + modded_gallery_id) + retval


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
            opener.addheaders = [('User-Agent', UA), ('Referer', referer_url),
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
                              str(os.stat(file).st_size) +
                              '  content-length:' + str(length))
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
            logging.error(
                'IOError:errno: [{0}] msg: [{1}]'.format(e.errno, e.strerror),
                url)
            raise e

    raise ex


class ImageInfo(NamedTuple):
    # The name of the image file.
    name: str
    # The URL of the image.
    url: str


class HitomiPage:
    def __init__(self, url):
        self.url = url
        ptr = re.compile('^https?:\/\/.*[^0-9]([0-9]*).html.*$')
        m = ptr.search(url.rstrip('\n'))
        if m:
            self.__id = m.group(1)

        self.__img_list = []
    
    def GetTitle(self):
        try:
            req = urllib2.Request(self.url)
            response = urllib2.urlopen(req)
        except:
            logging.error('Failed to get {}'.format(self.url))
            return None
        
        html_text = response.read().decode('utf-8')
        soup = BeautifulSoup(html_text, 'html.parser')
        gallery_info = soup.find('div', class_='gallery')
        if not gallery_info:
            logging.error('Failed to find galery info for {}'.format(self.url))
            return None
        
        h1 = gallery_info.find('h1')
        if not h1:
            return None

        tag_with_title = h1.find('a')
        if not tag_with_title:
            return None
        
        return tag_with_title.contents[0]


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
                # Look for subdomain_from_url in common.js on hitomi.la gallery
                # page. 
                for image_info in images_info_array['files']:
                    image_hash = image_info['hash']
                    path = _HashAndNameToImagePath(image_hash,
                                                   image_info['name'])
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
                logging.error('URLError: reason: [{0}]'.format(e.reason),
                              js_url)
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

        with Progress() as progress:
            total_images = len(list)
            task = progress.add_task('Downloading', total=total_images)
            for image_info in list:
                image_file_name = re.sub(r'^.+/([^/]+)$', r'\1',
                                         image_info.name)
                local_file = os.path.join(path, image_file_name)
                url = image_info.url
                logging.debug('Download url=' + url + '  To file=' +
                              local_file)
                progress.update(
                    task,
                    advance=0,
                    description='Downloading {}'.format(image_file_name))
                _DownloadImageToFile(url, referer_url, local_file)
                progress.update(task, advance=1)


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
    print('Wrote archive to ' + dest)


def _PrintFailures(not_found, failed):
    console = Console()

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Fail Status", style="dim", width=12)
    table.add_column("URL")

    for nf in not_found:
        table.add_row('Not Found', nf)

    for f in failed:
        table.add_row('Failed to find book URL', f)

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
        print('Start %s' % url)
        hitomi = HitomiPage(url)

        book_title = hitomi.GetTitle()
        if '/' in book_title:
            book_title = book_title.replace('/', '_')
            logging.info('Found / in book title, renamed to %s' % book_title)

        print('Fetching: %s' % book_title)

        zip_file_path = os.path.join(output_dir, book_title + '.zip')
        if os.path.exists(zip_file_path):
            print("%s already exists. Skipping." % book_title)
            continue

        h = hitomi
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
    parser.add_argument('-v',
                        '--verbose',
                        action='store_true',
                        default=False,
                        help='Enables verbose logging.')

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    urls = []

    if args.file:
        file_path = os.path.join(os.getcwd(), args.file)
        urls.extend(_GetUrlsFromFile(file_path))

    if args.urls:
        urls.extend(args.urls)

    # Print all the urls to stdout so that it's easier to copy past
    # if needed.
    for url in urls:
        print(url)

    DownloadFromHitomila(urls, args.output)
