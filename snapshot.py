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

import json
import logging
import requests
import hashlib

from dateutil.parser import parse as parsedate

from flask import Flask, jsonify, Response

app = Flask(__name__)
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

DEBIAN_SNAPSHOT = 'http://snapshot.debian.org'

class ApiError(Exception):
    status_code = 400

    def __init__(self, message, status_code=None, payload=None):
        super().__init__()
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv["message"] = self.message
        return rv


# begin flask app
@app.errorhandler(ApiError)
def handle_invalid_usage(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response


def get_file_info(url):
    info = {}
    resp = requests.get(url)
    info["status_code"] = resp.status_code
    if resp.ok:
        m = hashlib.md5()
        for data in resp.iter_content(8192):
            m.update(data)
        info["hash"] = m.hexdigest()
        info["first_seen"] = parsedate(
            resp.headers["last-modified"]).strftime("%y%m%dT%H%M%SZ")
        info["size"] = len(resp.content)

    return info


@app.route("/mr/package/<string:srcpkgname>/<string:srcpkgver>/srcfiles",
           methods=["GET"])
def get_src(srcpkgname, srcpkgver):
    """
    GET
    """

    result = {}
    status_code = 404

    debian_endpoint = '{base_url}/mr/package/{pkg_name}/{pkg_ver}/srcfiles?fileinfo=1'.format(
        base_url=DEBIAN_SNAPSHOT, pkg_name=srcpkgname, pkg_ver=srcpkgver)
    resp = requests.get(debian_endpoint)
    if resp.ok:
        result = resp.content
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
            "orig": ["%s_%s.orig.tar.%s" % (srcpkgname, srcpkgver.split('-')[0], ext) for ext in ('gz', 'xz', 'bz2')]
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

        if info["dsc"].get("hash", None) and info["debian"].get("hash", None) and info["orig"].get("hash", None):
            status_code = info["dsc"]["status_code"]
            result = {
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
            result = json.dumps(result, indent=4) + "\n"


    return Response(result, status=status_code,
                    mimetype="application/json")


@app.route("/mr/binary/<string:pkg_name>/<string:pkg_ver>/binfiles",
           methods=["GET"])
def get_bin(pkg_name, pkg_ver):
    """
    GET
    """
    result = {}
    status_code = 404

    debian_endpoint = '{base_url}/mr/binary/{pkg_name}/{pkg_ver}/binfiles?fileinfo=1'.format(
        base_url=DEBIAN_SNAPSHOT, pkg_name=pkg_name, pkg_ver=pkg_ver)
    resp = requests.get(debian_endpoint)
    if resp.ok:
        result = resp.content
        status_code = resp.status_code
    else:
        if pkg_name.startswith("lib"):
            prefix = pkg_name[0:4]
        else:
            prefix = pkg_name[0]
        deb = "%s_%s_amd64.deb" % (pkg_name, pkg_ver)
        path = "pool/main/{prefix}/{pkg_name}".format(
            prefix=prefix, pkg_name=pkg_name)
        url = "https://deb.qubes-os.org/r4.1/vm/{path}/{deb}".format(
            path=path, deb=deb)
        info = get_file_info(url)
        print(url)
        if info.get("hash", None):
            status_code = info["status_code"]
            result = {
                "binary_version": pkg_ver,
                "binary": pkg_name,
                "_comment": "foo",
                "result": [
                    {
                        "hash": info["hash"],
                        "architecture": "amd64",
                    }
                ],
                "fileinfo": {
                    info["hash"]: [
                        {
                            "name": deb,
                            "archive_name": "debian",
                            "path": "/%s" % path,
                            "first_seen": info["first_seen"],
                            "size": info["size"],
                        }
                    ],
                },
            }
            result = json.dumps(result, indent=4) + "\n"


    return Response(result, status=status_code,
                    mimetype="application/json")


if __name__ == "__main__":
    app.run(debug=True)
