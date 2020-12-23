#!flask/bin/python3
# -*- encoding: utf8 -*-
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2020 Frédéric Pierret <frederic.pierret@qubes-os.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import os
import json
import logging
import requests
import hashlib
import subprocess

from dateutil.parser import parse as parsedate
from flask import Flask, Response
from flask_caching import Cache

app = Flask(__name__)
cache = Cache(app, config={'CACHE_TYPE': 'simple'})

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

DEBIAN_SNAPSHOT = 'http://snapshot.debian.org'


# Useful function to get snapshot content type
def get_file_info(url):
    info = {}
    try:
        resp = requests.get(url)
        info["status_code"] = resp.status_code
        if resp.ok:
            m = hashlib.md5()
            for data in resp.iter_content(8192):
                m.update(data)
            info["hash"] = m.hexdigest()
            info["first_seen"] = parsedate(
                resp.headers["last-modified"]).strftime("%Y%m%dT%H%M%SZ")
            info["size"] = len(resp.content)
    except requests.exceptions.ConnectionError:
        pass

    return info


# WIP: Get Qubes repo Debian content
# This is to be modified to include Fedora, Archlinux etc.
@cache.cached(timeout=300, key_prefix='all_files')
def get_repo_files():
    files = []
    cmd = ["rsync", "--list-only", "--recursive",
           "rsync://deb.qubes-os.org/qubes-mirror/repo/deb/"]
    result = subprocess.check_output(cmd)
    lines = result.decode('utf8').strip('\n').split('\n')
    for line in lines:
        line = line.split()
        if not line[-1].startswith('r4.1'):
            continue
        if line[-1].endswith('.deb') or \
                line[-1].endswith('.dsc') or \
                line[-1].endswith('.deb') or \
                line[-1].endswith('.tar.xz') or \
                line[-1].endswith('.tar.bz2') or \
                line[-1].endswith('.tar.gz'):
            files.append(line[-1].strip())
    return files


@app.route("/mr/package/<string:srcpkgname>/<string:srcpkgver>/srcfiles",
           methods=["GET"])
@cache.cached(timeout=3600)
def get_src(srcpkgname, srcpkgver):
    api_result = {}
    status_code = 404

    debian_endpoint = \
        '{base_url}/mr/package/{pkg_name}/{pkg_ver}/srcfiles?fileinfo=1'.format(
            base_url=DEBIAN_SNAPSHOT, pkg_name=srcpkgname, pkg_ver=srcpkgver)
    try:
        resp = requests.get(debian_endpoint)
    except requests.exceptions.ConnectionError:
        return Response(api_result, status=status_code,
                        mimetype="application/json")

    if resp.ok:
        api_result = resp.content
        status_code = resp.status_code
    else:
        if srcpkgname.startswith("lib"):
            prefix = srcpkgname[0:4]
        else:
            prefix = srcpkgname[0]
        path = "pool/main/{prefix}/{srcpkgname}".format(
            prefix=prefix, srcpkgname=srcpkgname
        )

        files = {
            "dsc": ["%s_%s.dsc" % (srcpkgname, srcpkgver)],
            "debian": ["%s_%s.debian.tar.xz" % (srcpkgname, srcpkgver)],
            "orig": [
                "%s_%s.orig.tar.%s" % (srcpkgname, srcpkgver.split('-')[0], ext)
                for ext in ('gz', 'xz', 'bz2')]
        }
        info = {
            "dsc": {},
            "debian": {},
            "orig": {}
        }

        for key in files.keys():
            for f in files[key]:
                url = "https://deb.qubes-os.org/r4.1/vm/{path}/{file}".format(
                    path=path, file=f)
                res = get_file_info(url)
                if res.get("hash"):
                    res["file"] = f
                    info[key] = res
                    break

        if info["dsc"].get("hash", None) and \
                info["debian"].get("hash", None) and \
                info["orig"].get("hash", None):
            status_code = info["dsc"]["status_code"]
            api_result = {
                "package": srcpkgname,
                "version": srcpkgver,
                "_comment": "foo",
                "result": [
                    {"hash": info["dsc"]["hash"]},
                    {"hash": info["debian"]["hash"]},
                    {"hash": info["orig"]["hash"]},
                ],
                "fileinfo": {
                    info["dsc"]["hash"]: [
                        {
                            "name": info["dsc"]["file"],
                            "archive_name": "debian",
                            "path": "/%s" % path,
                            "first_seen": info["dsc"]["first_seen"],
                            "size": info["dsc"]["size"],
                        }
                    ],
                    info["orig"]["hash"]: [
                        {
                            "name": info["orig"]["file"],
                            "archive_name": "debian",
                            "path": "/%s" % path,
                            "first_seen": info["orig"]["first_seen"],
                            "size": info["orig"]["size"],
                        }
                    ],
                    info["debian"]["hash"]: [
                        {
                            "name": info["debian"]["file"],
                            "archive_name": "debian",
                            "path": "/%s" % path,
                            "first_seen": info["debian"]["first_seen"],
                            "size": info["debian"]["size"],
                        }
                    ],
                },
            }
            api_result = json.dumps(api_result, indent=4) + "\n"

    return Response(api_result, status=status_code,
                    mimetype="application/json")


@app.route("/mr/binary/<string:pkg_name>/<string:pkg_ver>/binfiles",
           methods=["GET"])
@cache.cached(timeout=3600)
def get_bin(pkg_name, pkg_ver):
    api_result = {}
    status_code = 404
    debian_endpoint = \
        '{base_url}/mr/binary/{pkg_name}/{pkg_ver}/binfiles?fileinfo=1'.format(
            base_url=DEBIAN_SNAPSHOT, pkg_name=pkg_name, pkg_ver=pkg_ver)
    try:
        resp = requests.get(debian_endpoint)
    except requests.exceptions.ConnectionError:
        return Response(api_result, status=status_code,
                        mimetype="application/json")

    if resp.ok:
        api_result = resp.content
        status_code = resp.status_code
    else:
        base_url = "https://deb.qubes-os.org/"
        # to be changed to remote content

        data = {}
        info = {}
        for arch in ("amd64", "all"):
            deb = "%s_%s_%s.deb" % (pkg_name, pkg_ver, arch)
            for f in get_repo_files():
                if os.path.basename(f) == deb:
                    url = base_url + f
                    info = get_file_info(url)
                    if info.get("hash", None):
                        data[arch] = {}
                        data[arch]["info"] = info
                        data[arch]["file"] = deb
                        data[arch]["url"] = url
                        break

        if data:
            status_code = info["status_code"]
            result = [{"hash": data[arch]["info"]["hash"], "architecture": arch}
                      for arch in data.keys()]
            fileinfo = {}
            for arch in data.keys():
                fileinfo.update({
                    data[arch]["info"]["hash"]: [
                        {
                            "name": data[arch]["file"],
                            "archive_name": "debian",
                            "path": "%s" % data[arch]["url"].replace(
                                base_url, ''),
                            "first_seen": data[arch]["info"]["first_seen"],
                            "size": data[arch]["info"]["size"],
                        }
                    ],
                }
                )
            api_result = {
                "binary_version": pkg_ver,
                "binary": pkg_name,
                "_comment": "foo",
                "result": result,
                "fileinfo": fileinfo
            }
            api_result = json.dumps(api_result, indent=4) + "\n"

    return Response(api_result, status=status_code,
                    mimetype="application/json")


if __name__ == "__main__":
    app.run(debug=True)
