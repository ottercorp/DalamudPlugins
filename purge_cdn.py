#! -*- coding: utf-8 -*-
from argparse import Action
from email import header
from ensurepip import version
import json
import requests
import hashlib, hmac, json, os, sys, time
from datetime import datetime
import argparse

REPO_URL="https://api.github.com/repos/ottercorp/DalamudPlugins"
CDN_URL="http://cos-dalamudplugins.ffxiv.wang/cn-api5/"
def get_regen_commit_compared():
    r = requests.get(REPO_URL+"/commits")
    commits=json.loads(r.content)
    sha=[]
    for i in range(len(commits)):
        if (len(sha)==2):
            break
        if commits[i]["commit"]["message"]=="Regenerate PluginMaster":
            sha.append(commits[i]["sha"])
    # print(latest_commit_sha)
    if len(sha)!=2:
        print("Can not get last 2 Regenerate PluginMaster")
        exit(-1)
    url=REPO_URL+"/compare/"+sha[1]+"..."+sha[0]
    print(url)
    r = requests.get(url)
    return json.loads(r.content)

def get_files_changed(commit):
    status_to_purge=["removed","modified","renamed","changed"]
    files=commit["files"]
    files_to_purge=[]
    for f in files:
        # print(f["status"])
        if(f["status"] in status_to_purge):
            print(f["filename"])
            files_to_purge.append(f["filename"])
    return files_to_purge

def get_cdn_url(filename):
    return CDN_URL+filename

def get_signed_request(param,secret_id ,secret_key,action):
    # https://github.com/TencentCloud/signature-process-demo/blob/main/cvm/signature-v3/python/demo.py
    service = "cdn"
    host = "cdn.tencentcloudapi.com"
    algorithm = "TC3-HMAC-SHA256"
    # timestamp = 1551113065
    timestamp = int(time.time())
    date = datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d")
    version = "2018-06-06"
    # params = "Urls.0=http://cos-dalamudplugins.ffxiv.wang/cn-api5/1"
    # ************* 步骤 1：拼接规范请求串 *************
    http_request_method = "GET"
    canonical_uri = "/"
    canonical_querystring = param
    ct = "application/x-www-form-urlencoded"
    payload = ""
    canonical_headers = "content-type:%s\nhost:%s\n" % (ct, host)
    signed_headers = "content-type;host"
    hashed_request_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    canonical_request = (http_request_method + "\n" +
                        canonical_uri + "\n" +
                        canonical_querystring + "\n" +
                        canonical_headers + "\n" +
                        signed_headers + "\n" +
                        hashed_request_payload)
    # print(canonical_request)
    # ************* 步骤 2：拼接待签名字符串 *************
    credential_scope = date + "/" + service + "/" + "tc3_request"
    hashed_canonical_request = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    string_to_sign = (algorithm + "\n" +
                    str(timestamp) + "\n" +
                    credential_scope + "\n" +
                    hashed_canonical_request)
    # print(string_to_sign)


    # ************* 步骤 3：计算签名 *************
    # 计算签名摘要函数
    def sign(key, msg):
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()
    secret_date = sign(("TC3" + secret_key).encode("utf-8"), date)
    secret_service = sign(secret_date, service)
    secret_signing = sign(secret_service, "tc3_request")
    signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    # print(signature)

    # ************* 步骤 4：拼接 Authorization *************
    authorization = (algorithm + " " +
                    "Credential=" + secret_id + "/" + credential_scope + ", " +
                    "SignedHeaders=" + signed_headers + ", " +
                    "Signature=" + signature)
    # print(authorization)
    headers={   'Authorization':authorization,
                'Content-Type':ct,
                'Host':host,
                'X-TC-Action':action,
                'X-TC-Timestamp':str(timestamp),
                'X-TC-Version':version,
                }
    return headers

def purge_files(files,secret_id,secret_key):
    params=[]
    for i in range(len(files)):
        params.append(f"Urls.{str(i)}={get_cdn_url(files[i])}")
    url_param='&'.join(params)
    # print(url_param)
    headers=get_signed_request(url_param,secret_id,secret_key,'PurgeUrlsCache')
    # print(headers)
    # headers={}
    print("https://cdn.tencentcloudapi.com/?"+url_param)
    r = requests.get("https://cdn.tencentcloudapi.com/?"+url_param,headers=headers)
    print(r.status_code)
    print(r.content)

def cli():
    parser = argparse.ArgumentParser(description='Tencent CDN PurgeUrlsCache')
    parser.add_argument('-i', '--secret_id', type=str, required=True, help='secret_id')
    parser.add_argument('-k', '--secret_key', type=str, required=True, help='secret_key')
    args = parser.parse_args()
    purge(args)

def purge(args):
    secret_id=args.secret_id
    secret_key=args.secret_key
    files=get_files_changed(get_regen_commit_compared())
    purge_files(files,secret_id,secret_key)

if __name__ == '__main__':
    cli()
