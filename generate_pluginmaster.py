import json
import os
import codecs
from time import time
from sys import argv
from pathlib import Path
from os import listdir
from os.path import getmtime, isfile, join, exists
from zipfile import ZipFile, ZIP_DEFLATED
import requests
import hashlib
import copy
import re

md5 = hashlib.md5()

def get_md5(text: str):
    md5.update(text.encode())
    return md5.hexdigest()

# DOWNLOAD_URL = 'https://dalamudplugins-1253720819.cos.ap-nanjing.myqcloud.com/plugins/{plugin_name}/latest.zip'
DOWNLOAD_URL = 'https://service-knj2phup-1253720819.sh.apigw.tencentcs.com/release/dalamudcounter-1623520723?plugin={plugin_name}&isUpdate={is_update}&isTesting={is_testing}&branch=cn-api5'
IMAGE_URL = 'https://dalamudplugins-1253720819.cos.ap-nanjing.myqcloud.com/cn-api5/plugins/{plugin_name}/images/{image_file}'

DEFAULTS = {
    'IsHide': False,
    'IsTestingExclusive': False,
    'ApplicableVersion': 'any',
}

DUPLICATES = {
    'DownloadLinkInstall': ['DownloadLinkTesting', 'DownloadLinkUpdate'],
}

TRIMMED_KEYS = [
    'Author',
    'Name',
    'Description',
    'InternalName',
    'AssemblyVersion',
    'RepoUrl',
    'ApplicableVersion',
    'Tags',
    'DalamudApiLevel',
    'Punchline',
    'ImageUrls',
    'IconUrl'
]


def main():
    # extract the manifests from inside the zip files
    master = extract_manifests()

    # trim the manifests
    master = [trim_manifest(manifest) for manifest in master]

    # download images to local
    handle_images(master)

    # convert the list of manifests into a master list
    add_extra_fields(master)

    # write the master
    write_master(master)

    # update the LastUpdated field in master
    last_updated()

    # update the Markdown
    update_md(master)

def download_image(plugin_name, image_urls):
    image_dir = f"./plugins/{plugin_name}/images/"
    Path(image_dir).mkdir(parents=True, exist_ok=True)
    images_map = {}
    allowed_images = []
    for url in image_urls:
        if not url: continue
        url_md5 = get_md5(url)
        image_filename = f"{url_md5}.{url.split('.')[-1]}"
        image_filepath = join(image_dir, image_filename)
        allowed_images.append(image_filename)
        if not exists(image_filepath):
            with open(image_filepath, "wb") as f:
                print(f"Downloading {url} -> {image_filepath}")
                img = requests.get(url, timeout=5)
                f.write(img.content)
        images_map[url] = IMAGE_URL.format(plugin_name=plugin_name, image_file=image_filename)
    all_files = [f for f in listdir(image_dir) if isfile(join(image_dir, f))]
    for f in all_files:
        if f not in allowed_images:
            os.remove(join(image_dir, f))
    return images_map

def handle_images(manifests):
    return
    for manifest in manifests:
        image_urls = manifest.get('ImageUrls', []) + [manifest.get('IconUrl', '')]
        images_map = download_image(manifest["InternalName"], image_urls)
        if 'ImageUrls' in manifest:
            manifest['ImageUrls'] = list(map(lambda x: images_map.get(x, x), manifest['ImageUrls']))
        if 'IconUrl' in manifest:
            manifest['IconUrl'] = images_map.get(manifest['IconUrl'], manifest['IconUrl'])

def extract_manifests():
    manifests = []
    testing_manifests = []

    for dirpath, dirnames, filenames in os.walk('./plugins'):
        if len(filenames) == 0 or 'latest.zip' not in filenames:
            continue
        plugin_name = dirpath.split('/')[-1].split('\\')[-1]
        latest_json = f'{dirpath}/{plugin_name}.json'
        with codecs.open(latest_json, "r", "utf-8") as f:
            content = f.read()
            if content.startswith(u'\ufeff'):
                content = content.encode('utf8')[3:].decode('utf8')
            content=clean_json(content)
            manifests.append(json.loads(content))

    for dirpath, dirnames, filenames in os.walk('./testing'):
        if len(filenames) == 0 or 'latest.zip' not in filenames:
            continue
        plugin_name = dirpath.split('/')[-1].split('\\')[-1]
        latest_json = f'{dirpath}/{plugin_name}.json'
        with codecs.open(latest_json, "r", "utf-8") as f:
            content = f.read()
            if content.startswith(u'\ufeff'):
                content = content.encode('utf8')[3:].decode('utf8')
            content=clean_json(content)
            testing_manifests.append(json.loads(content))

    translations = {}
    for manifest in manifests + testing_manifests:
        translations[manifest["InternalName"]] = manifest.get('Description')
        if manifest.get('Punchline'):
            translations[manifest["InternalName"] + "-Punchline"] = manifest.get('Punchline')
    with codecs.open("translations/en.json", "w", "utf-8") as f:
        json.dump(translations, f, indent=4)

    with codecs.open("translations/cn.json", "r", "utf-8") as f:
        cn_translations = json.load(f)
        for manifest in manifests + testing_manifests:
            if manifest["InternalName"] in cn_translations:
                cn_desc = cn_translations[manifest["InternalName"]]
                if cn_desc:
                    manifest['Description'] = cn_desc
            if (manifest["InternalName"] + "-Punchline") in cn_translations:
                cn_punch = cn_translations[manifest["InternalName"] + "-Punchline"]
                if cn_punch:
                    manifest['Punchline'] = cn_punch

    return manifests

def add_extra_fields(manifests):
    downloadcounts = {}
    if os.path.exists('downloadcounts.json'):
        with open('downloadcounts.json', 'r') as f:
            downloadcounts = json.load(f) 
    categorymap = {}
    if os.path.exists('categoryfallbacks.json'):
        with open('categoryfallbacks.json', 'r') as f:
            categorymap = json.load(f) 
    for manifest in manifests:
        # generate the download link from the internal assembly name
        manifest['DownloadLinkInstall'] = DOWNLOAD_URL.format(plugin_name=manifest["InternalName"], is_update=False, is_testing=False)
        manifest['DownloadLinkUpdate'] = DOWNLOAD_URL.format(plugin_name=manifest["InternalName"], is_update=True, is_testing=False)
        manifest['DownloadLinkTesting'] = DOWNLOAD_URL.format(plugin_name=manifest["InternalName"], is_update=False, is_testing=True)
        # add default values if missing
        for k, v in DEFAULTS.items():
            if k not in manifest:
                manifest[k] = v
        # duplicate keys as specified in DUPLICATES
        for source, keys in DUPLICATES.items():
            for k in keys:
                if k not in manifest:
                    manifest[k] = manifest[source]
        manifest['DownloadCount'] = downloadcounts.get(manifest["InternalName"], 0)
        manifest['CategoryTags'] = categorymap.get(manifest["InternalName"], categorymap.get(manifest["Name"], []))

def write_master(master):
    # write as pretty json
    with open('pluginmaster.json', 'w') as f:
        json.dump(master, f, indent=4)

def trim_manifest(plugin):
    return {k: plugin[k] for k in TRIMMED_KEYS if k in plugin}

def last_updated():
    with open('pluginmaster.json') as f:
        master = json.load(f)

    for plugin in master:
        latest = f'plugins/{plugin["InternalName"]}/latest.zip'
        modified = int(getmtime(latest))

        if 'LastUpdated' not in plugin or modified != int(plugin['LastUpdated']):
            plugin['LastUpdated'] = str(modified)

    with open('pluginmaster.json', 'w') as f:
        json.dump(master, f, indent=4)

def update_md(master):
    with codecs.open('mdtemplate.txt', 'r', 'utf8') as mdt:
        md = mdt.read().strip()
        for plugin in master:
            desc = plugin.get('Description', '')
            desc = desc.replace('\n', '<br>')
            md += f"\n| {plugin['Name']} | {plugin['Author']} | {desc} |"
        with codecs.open('plugins.md', 'w', 'utf8') as f:
            f.write(md)

def clean_json(str):
    str = re.sub(r",\s*}", "}", str)
    str = re.sub(r",\s*]", "]", str)
    # print(str)
    return str

if __name__ == '__main__':
    main()
