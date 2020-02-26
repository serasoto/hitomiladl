# e-hentaidb Downloader

Downloads items from e-hentaidb page.

Specifying an e-hentaidb page will attempt to download the item from hitomi.
If there isn't a hitomi link, this will skip it.

## Requirements
An environment that runs pipenv.
Tested on macOS and WSL.
Only tested with python3 (with pipenv).

## Setup

```
pipenv install
```

## Usage
### Specifying one URL

```
pipenv run python ./ehentai.py URL
```

Once downloaded, a zip file is created with the name of the asset,
in the current directory.

### Multiple URLs

```
pipenv run python ./ehentai.py URL1 URL2 ... URLN
```

The behavior is the same as specifying one URL, except that it does all the
downloads in one command. Multiple zip files are created.

### Mulitple URLs from a file

You can specify a list of URLs in a file, instead of putting them on the
command line.

```
pipenv run python ./ehentai.py -f urllist.txt
```

URL list may only contain one URL per line.
Empty lines are allowed and are skipped.
Every line is `strip`ed so it may contain extraneous spaces before and after
the URL.

### Specifying output directory

```
pipenv run python ./ehentai.py -o output/dir URLs
```

The output directory must exist.