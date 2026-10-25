"""Download every file of a *public* Google Drive folder (recursively), keeping the sub-folder names.

Usage:
    python3 tools/download_drive_folder.py <folder-id> <out-dir>

The folder id is the last part of the share link: https://drive.google.com/drive/folders/<folder-id>
Only works for folders shared as "anyone with the link"; files over ~100 MB need Drive's virus-scan
confirmation and are skipped by this simple downloader.
"""
import html
import os
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor


def list_folder(folder_id):
    page = urllib.request.urlopen(f'https://drive.google.com/embeddedfolderview?id={folder_id}').read().decode('utf-8', 'ignore')
    return [(fid, html.unescape(name)) for fid, name in
            re.findall(r'<div class="flip-entry" id="entry-([^"]+)".*?<div class="flip-entry-title">(.*?)</div>', page, re.S)]


def walk(folder_id, rel=''):
    for fid, name in list_folder(folder_id):
        if '.' in name[-6:]:  # looks like a file
            yield fid, os.path.join(rel, name)
        else:
            yield from walk(fid, os.path.join(rel, name))


def download(job, out):
    fid, rel = job
    path = os.path.join(out, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        urllib.request.urlretrieve(f'https://drive.google.com/uc?export=download&id={fid}', path)
    return rel


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    folder_id, out = sys.argv[1], sys.argv[2]
    jobs = list(walk(folder_id))
    print(f'{len(jobs)} files')
    with ThreadPoolExecutor(8) as ex:
        for rel in ex.map(lambda j: download(j, out), jobs):
            print('  ', rel)


if __name__ == '__main__':
    main()
