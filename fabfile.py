# Copyright 2011 GRNET S.A. All rights reserved.
#
# Redistribution and use in source and binary forms, with or
# without modification, are permitted provided that the following
# conditions are met:
#
#   1. Redistributions of source code must retain the above
#      copyright notice, this list of conditions and the following
#      disclaimer.
#
#   2. Redistributions in binary form must reproduce the above
#      copyright notice, this list of conditions and the following
#      disclaimer in the documentation and/or other materials
#      provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY GRNET S.A. ``AS IS'' AND ANY EXPRESS
# OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL GRNET S.A OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF
# USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED
# AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# The views and conclusions contained in the software and
# documentation are those of the authors and should not be
# interpreted as representing official policies, either expressed
# or implied, of GRNET S.A.
#

import os
import sys

from contextlib import contextmanager
from fabric.api import *
from fabric.colors import *

env.project_root = "./"
env.develop = False
env.autoremove = True
env.packages = ['snf-pithos-lib', 'snf-pithos-backend', 'snf-pithos-app',
                        'snf-pithos-tools']
env.capture = False
env.colors = True
env.pypi_root = 'pypi'
env.roledefs = {
    'docs': ['docs.dev.grnet.gr'],
    'pypi': ['docs.dev.grnet.gr']
}


# colored logging
notice = lambda x: sys.stdout.write(yellow(x) + "\n")
info = lambda x: sys.stdout.write(green(x) + "\n")
error = lambda x: sys.stdout.write(red(x) + "\n")


def dev():
    env.develop = True


# wrap local to respect global capturing setting from env.capture
oldlocal = local
def local(cmd, capture="default"):
    if capture != "default":
        capture = capture
    else:
        capture = env.capture
    return oldlocal(cmd, capture=capture)


def package_root(p):
    return os.path.join(env.project_root, p)


def remove_pkg(p):
    notice("uninstalling package: %s" % p)
    with lcd(package_root(p)):
        with settings(warn_only=True):
            local("pip uninstall %s -y" % p, env.capture)


def build_pkg(p):
    info ("building package: %s" % p)
    with lcd(package_root(p)):
        try:
            local("rm -r dist build")
        except:
            pass
        local("python setup.py egg_info -d sdist")


def install_pkg(p):
    info("installing package: %s" % p)
    with lcd(package_root(p)):
        if env.develop:
            local("python setup.py develop")
        else:
            local("python setup.py install")


def install(*packages):
    for p in packages:
        install_pkg("snf-%s" % p)


def buildall():
    for p in env.packages:
        build_pkg(p)
    collectdists()


def installall():
    for p in env.packages:
        install_pkg(p)


def collectdists():
    if os.path.exists("./packages"):
        notice("removing 'packages' directory")
        local("rm -r packages");

    local("mkdir packages");
    for p in env.packages:
        local("cp %s/dist/*.tar.gz ./packages/" % package_root(p));


def removeall():
    for p in env.packages:
        remove_pkg(p)


def remove(*packages):
    for p in packages:
        remove_pkg("snf-%s" % p)


#
# GIT helpers
#


def git(params, locl=True):
    cmd = local if locl else run
    return cmd("git %s" % params, capture=True)


def branch():
    return git("symbolic-ref HEAD").split("/")[-1]


@contextmanager
def co(c):
    current_branch = branch();
    git("checkout %s" % c)
    # Use a try block to make sure we checkout the original branch.
    try:
        yield
    finally:
        try:
            git("checkout %s" % current_branch)
        except Exception:
            error("Could not checkout %s, you're still left at %s" % c)

#
# Debian packaging helpers
#

env.debian_branch = 'debian-0.9'
env.deb_packages = ['snf-pithos-lib', 'snf-pithos-backend',
                    'snf-pithos-tools', 'snf-pithos-app']
env.signdebs = False
env.debrelease = False  # Increase release number in Debian changelogs
env.upstream = 'packaging'


def _last_commit(f):
    return local("git rev-list --all --date-order --max-count=1 %s" % f,
            capture=True).strip()


def _diff_from_master(c,f):
    return local("git log --oneline %s..%s %s" \
                 " | wc -l" % (c, env.upstream, f), capture=True)


def dch(p):
    with co(env.debian_branch):
        local("git merge %s" % env.upstream)
        with lcd(package_root(p)):
            local("if [ ! -d .git ]; then mkdir .git; fi")

            # FIXME:
            # Checking for new changes in packages
            # has been removed temporarily.
            # Always create a new Debian changelog entry.
            ## Check for new changes in package dir
            #diff = _diff_from_master(_last_commit("debian/changelog"), ".")
            #vercmd  = "git describe --tags --abbrev=0"\
            #          " | sed -rn '\''s/^v(.*)/\\1/p'\''"
            #version = local(vercmd, capture=True)
            #if int(diff) > 0:
            if True:
                # Run git-dch in snapshot mode.
                # TODO: Support a --release mode in fabfile
                local(("git-dch --debian-branch=%s --auto %s" %
                       (env.debian_branch,
                        "--release" if env.debrelease else "--snapshot")))
                local(("git commit debian/changelog"
                       " -m 'Updated %s changelog'" % p))
                notice(("Make sure to tag Debian release in %s" %
                        env.debian_branch))

            local("rmdir .git")


def debrelease():
    env.debrelease = True


def signdebs():
    env.signdebs = True


def builddeb(p, master="packaging", branch="debian-0.9"):
    with co(branch):
        info("Building debian package for %s" % p)
        with lcd(package_root(p)):
            local("git merge %s" % master)
            local("if [ ! -d .git ]; then mkdir .git; fi")
            local("python setup.py clean")
            local("git add ./*/*/version.py -f")
            local(("git-buildpackage --git-upstream-branch=%s --git-debian-branch=%s"
                   " --git-export=INDEX --git-ignore-new %s") %
                   (master, branch, "" if env.signdebs else "-us -uc"))
            local("rm -rf .git")
            local("git reset ./*/*/version.py")
        info("Done building debian package for %s" % p)


def builddeball(b="debian-0.9"):
    for p in env.deb_packages:
        builddeb(p=p, branch=b)



@roles('pypi')
def uploadtars():
    put("packages/*.tar.gz", 'www/pypi/')

