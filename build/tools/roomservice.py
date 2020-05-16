#!/usr/bin/env python

# Copyright (C) 2013 Cybojenix <anthonydking@gmail.com>
# Copyright (C) 2013 The OmniROM Project
# Copyright (C) 2019 The Dirty Unicorns Project
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import sys
sys.dont_write_bytecode = True
import os
import os.path
import sys

if sys.version_info < (3, 8):
    import urllib2
    from urllib2 import urlopen, Request
else:
    import urllib
    import urllib.request

import json
import re
import cprint
from subprocess import Popen, PIPE
from xml.etree import ElementTree

# Default properties
DEFAULT_REMOTE = 'github'
DEFAULT_ORG = 'DirtyUnicorns'
DEFAULT_BRANCH = 'q10x'
GERRIT_REMOTE = 'gerrit'
# Dependency file name
DEPENDENCY_FILE = 'du.dependencies'
# Where the local manifest path is located
LOCAL_MANIFEST_PATH = '.repo/local_manifests'
LOCAL_MANIFEST= LOCAL_MANIFEST_PATH + '/du_manifest.xml'
# Github api
GITHUB_API = 'https://api.github.com/users/%s/repos?page=%d&per_page=100'

# XML header for local_manifest
XML_HEADER = '<?xml version="1.0" encoding="UTF-8"?>\n'

"""
Regex pattern that can either match:
- http(s)://github.com/DirtyUnicorns/android_device_google_taimen
- DirtyUnicorns/android_device_google_taimen
if the repository format is different from these examples, the repo gets rejected.
"""
REPO_PATTERN = re.compile(r'(?:https?:\/\/www\.)?(?P<remote>\w+)\.\w+\/([\w-]+)\/([\w-]+)$|(^[\w-]+)\/([\w-]+)$')

# Error message when user exits from processes
USER_ABORT_MSG = '\nBailing out, process aborted by the user.\n'
# Documentation for getting a personal access token
GH_TOKEN_HELP = 'https://help.github.com/en/github/authenticating-to-github/creating-a-personal-access-token-for-the-command-line'

def get_github_token():
    """ Allows to get the GitHub access token from file """
    token = ''

    api_file = os.getenv('HOME') + '/api_token'

    if os.path.isfile(api_file):
        with open(api_file, 'r') as f:
            token = f.readline().strip()
            f.close()

    return token

def gather_device_repo(device_name):
    # Initial page to check
    page = 1
    # Access token for GitHub
    token = get_github_token()
    while True:
        if sys.version_info < (3, 8):
            req = Request(GITHUB_API % (DEFAULT_ORG, page))
        else:
            req = urllib.request.Request(GITHUB_API % (DEFAULT_ORG, page))

        if token:
            req.add_header('Authorization', 'token %s' % token)

        try:
            if sys.version_info < (3, 8):
                resp = json.loads(urllib2.urlopen(req).read())
            else:
                resp = json.loads(urllib.request.urlopen(req).read().decode())

        except urllib2.HTTPError as e:
            if e.code == 403:
                color_exit('You were limited by GitHub, create a personal access token and write it inside $HOME/api_token\ncat $HOME/api_token >> <YOUR_API_TOKEN>\nFor more information on access token visit:\n%s' % GH_TOKEN_HELP)
            elif e.code == 401:
                color_exit('The GitHub access token you have used is invalid.\n')
            else:
                color_exit('%d: %s' % (e.code, e.reason))
        except urllib2.URLError as e:
            color_exit(e.reason)

        # If we do not have more items, get out.
        if not resp:
            break

        for e in resp:
            repo_name = e['name']
            if re.match('android_device_.*_%s$' % device_name, repo_name):
                return repo_name

        # We need moar
        page += 1

    return None

def exists_in_tree(lm, repository):
    for child in lm.getchildren():
        if child.attrib['path'].endswith(repository):
            return child
    return None

def exists_in_tree_device(lm, repository):
    for child in lm.getchildren():
        if child.attrib['name'].endswith(repository):
            return child
    return None

# in-place prettyprint formatter
def indent(elem, level=0):
    i = "\n" + level*"  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for elem in elem:
            indent(elem, level+1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

def get_from_manifest(devicename):
    try:
        lm = ElementTree.parse(LOCAL_MANIFEST)
        lm = lm.getroot()
    except:
        lm = ElementTree.Element('manifest')

    for localpath in lm.findall('project'):
        if re.search('android_device_.*_%s$' % device, localpath.get('name')):
            return localpath.get('path')

    # Devices originally from AOSP are in the main manifest
    try:
        mm = ElementTree.parse('.repo/manifest.xml')
        mm = mm.getroot()
    except:
        mm = ElementTree.Element('manifest')

    for localpath in mm.findall("project"):
        if re.search('android_device_.*_%s$' % device, localpath.get('name')):
            return localpath.get('path')

    return None

def is_in_manifest(projectname, branch):
    try:
        lm = ElementTree.parse(LOCAL_MANIFEST)
        lm = lm.getroot()
    except:
        lm = ElementTree.Element('manifest')

    for localpath in lm.findall('project'):
        if localpath.get('name') == projectname and localpath.get('revision') == branch:
            return True

    return None

def add_to_manifest(repositories):
    try:
        lm = ElementTree.parse(LOCAL_MANIFEST)
        lm = lm.getroot()
    except:
        lm = ElementTree.Element('manifest')

    for repo in repositories:
        name, remote = process_repo(repo['repository'])

        branch = repo['branch']
        target = repo['target_path']

        existing_project = exists_in_tree_device(lm, name)
        if existing_project != None:
            if existing_project.attrib['revision'] != branch:
                print('-- Updating branch for %s to %s' % (name, branch))
                existing_project.set('revision', branch)
            continue

        cprint.success('-- Adding dependency: %s' % (name))


        project = ElementTree.Element('project', attrib = {'path': target,
            'remote': remote, 'name': name, 'revision': branch})

        lm.append(project)

    indent(lm, 0)
    if sys.version_info < (3, 8):
        raw_xml = XML_HEADER + ElementTree.tostring(lm)
    else:
        raw_xml = XML_HEADER + ElementTree.tostring(lm).decode()

    # Write on file
    f = open(LOCAL_MANIFEST, 'w')
    f.write(raw_xml)
    f.close()

def fetch_dependencies(repo_path):
    cprint.bold('\n- Looking for dependencies..')

    dependencies_path = repo_path + '/' + DEPENDENCY_FILE

    # List containing only the target_path(s), i.e: 'vendor/google'
    syncable_repos = []
    if os.path.exists(dependencies_path):
        # Load up *.dependencies
        dependencies = None
        with open(dependencies_path, 'r') as dep_file:
            dependencies = json.loads(dep_file.read())
            dep_file.close()

        if len(dependencies) == 0:
            color_exit('%s exists but it is empty.' % DEPENDENCY_FILE)

        # List containing the repositories to be added inside LOCAL_MANIFEST
        fetch_list = []
        for dep in dependencies:
            name, remote = process_repo(dep['repository'])

            # If the dependency is not inside the LOCAL_MANIFEST
            if not is_in_manifest(name, dep['branch']):
                fetch_list.append(dep)

            # If the repository doesn't exist, append it to the syncable repos
            if not os.path.exists(dep['target_path']):
                syncable_repos.append(dep['target_path'])

        # If new manifest entries have to be added
        if fetch_list:
            cprint.bold('\n- Adding dependencies to local manifest..')
            add_to_manifest(fetch_list)

        # Synchronise repos
        if syncable_repos:
            cprint.bold('\n- Syncing dependencies..')
            sync_repos(syncable_repos)

    else:
        color_exit('Dependencies file not found, bailing out.')

def process_repo(repo):
    # Apply regex
    m = re.match(REPO_PATTERN, repo)
    # Initializing elements
    name = remote = None

    # Fill elements with splitted values
    if (m):
        if m.group('remote'):
            # org/repository
            name = m.group(2) + '/' + m.group(3)
            remote = m.group('remote')
        else:
            name = m.group(4) + '/' + m.group(5)
            remote = DEFAULT_REMOTE
    # If it doesn't match the regex, use gerrit for syncing
    else:
        name = repo
        remote = GERRIT_REMOTE

    return (name, remote)

def sync_repos(repos):
    try:
        # If it's a list, we need to unpack it
        if type(repos) == list:
            p = Popen(['repo', 'sync', '--force-sync'] + repos)
        else:
            p = Popen(['repo', 'sync', '--force-sync', repos])

        out, err = p.communicate()
    except KeyboardInterrupt:
        color_exit(USER_ABORT_MSG)

if __name__ == "__main__":
    cprint.bold('\n~ Welcome to roomservice, setting up device\n')

    # Target to build
    product = sys.argv[1]

    # If the target is i.e du_taimen, we just need to get taimen
    try:
        device = product[product.index("_") + 1:]
    except ValueError:
        exit("The target you entered wouldn't work, use instead du_{0}\n".format(product))

    # Whether we need to just fetch dependencies or not
    if len(sys.argv) > 2:
        depsonly = sys.argv[2]
    else:
        depsonly = None

    # Setting up local_manifests folder
    if not os.path.exists(LOCAL_MANIFEST_PATH):
        os.makedirs(LOCAL_MANIFEST_PATH)

    # If the device lunched doesn't exist in a local directory, try to sync it from the remote repo
    if not depsonly:
        cprint.warn('Device not found in local repositories.\nAttempting to retrieve it from %s..' % DEFAULT_ORG)

        # Construct Organisation/android_device_<product>_<device> string
        device_repo = gather_device_repo(device)

        if device_repo:
                cprint.success('Device repository exists on remote, preparing synchronization..')

                # product can be get from device_repo by splitting
                product = device_repo.split('_')[2]
                # Target path
                repo_path = 'device/%s/%s' % (product, device)

                cprint.bold('\n- Adding device to local manifest..')
                add_to_manifest([{'repository': DEFAULT_ORG + '/' + device_repo, 'target_path': repo_path,'branch': DEFAULT_BRANCH}])

                cprint.bold('\n- Syncing device tree..')
                sync_repos(repo_path)

                # Fetch dependencies
                fetch_dependencies(repo_path)
        else:
            # Repo not found
            cprint.fail('\nRepository for %s not found in the DU Github repository list.\nIf this is in error, you may need to manually add it to the %s\n' % (device, LOCAL_MANIFEST_PATH))
    else:
        repo_path = get_from_manifest(device)
        if repo_path:
            fetch_dependencies(repo_path)
        else:
            cprint.fail('Trying dependencies-only mode on a non-existing device tree?\n')
