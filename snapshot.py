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
        info["first_seen"] = parsedate(resp.headers["last-modified"]).strftime(
            "%y%m%dT%H%M%SZ"
        )
        info["size"] = len(resp.content)

    return info


@app.route("/mr/package/<string:srcpkgname>/<string:srcpkgver>/srcfiles",
           methods=["GET"])
def get_src(srcpkgname, srcpkgver):
    """
    GET
    """

    result = {}
    if srcpkgname.startswith("lib"):
        prefix = srcpkgname[0:4]
    else:
        prefix = srcpkgname[0]
    path = "pool/main/{prefix}/{srcpkgname}".format(
        prefix=prefix, srcpkgname=srcpkgname
    )

    dsc = "%s_%s+deb11u1.dsc" % (srcpkgname, srcpkgver)
    orig = "%s_%s.orig.tar.xz" % (srcpkgname, srcpkgver.split("-")[0])
    debian = "%s_%s+deb11u1.debian.tar.xz" % (srcpkgname, srcpkgver)

    info_dsc = get_file_info(
        "https://deb.qubes-os.org/r4.1/vm/{path}/{file}".format(
            path=path, file=dsc)
    )
    info_orig = get_file_info(
        "https://deb.qubes-os.org/r4.1/vm/{path}/{file}".format(
            path=path, file=orig)
    )
    info_debian = get_file_info(
        "https://deb.qubes-os.org/r4.1/vm/{path}/{file}".format(
            path=path, file=debian)
    )

    if info_dsc and info_orig and info_debian:
        result = {
            "package": srcpkgname,
            "version": srcpkgver,
            "_comment": "foo",
            "result": [
                {"hash": info_dsc["hash"]},
                {"hash": info_orig["hash"]},
                {"hash": info_debian["hash"]},
            ],
            "fileinfo": {
                info_dsc["hash"]: [
                    {
                        "name": dsc,
                        "archive_name": "debian",
                        "path": "/%s" % path,
                        "first_seen": info_dsc["first_seen"],
                        "size": info_dsc["size"],
                    }
                ],
                info_orig["hash"]: [
                    {
                        "name": orig,
                        "archive_name": "debian",
                        "path": "/%s" % path,
                        "first_seen": info_orig["first_seen"],
                        "size": info_orig["size"],
                    }
                ],
                info_debian["hash"]: [
                    {
                        "name": debian,
                        "archive_name": "debian",
                        "path": "/%s" % path,
                        "first_seen": info_debian["first_seen"],
                        "size": info_debian["size"],
                    }
                ],
            },
        }
    result = json.dumps(result, indent=4) + "\n"
    return Response(result, status=info_dsc["status_code"],
                    mimetype="application/json")


@app.route("/mr/binary/<string:pkg_name>/<string:pkg_ver>/binfiles",
           methods=["GET"])
def get_bin(pkg_name, pkg_ver):
    """
    GET
    """

    result = {}
    if pkg_name.startswith("lib"):
        prefix = pkg_name[0:4]
    else:
        prefix = pkg_name[0]
    deb = "%s_%s+deb11u1_amd64.deb" % (pkg_name, pkg_ver)
    path = "pool/main/{prefix}/{pkg_name}".format(
        prefix=prefix, pkg_name=pkg_name)
    url = "https://deb.qubes-os.org/r4.1/vm/{path}/{deb}".format(
        path=path, deb=deb)
    info = get_file_info(url)
    if info:
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
    return Response(result, status=info["status_code"],
                    mimetype="application/json")


if __name__ == "__main__":
    app.run(debug=True)
