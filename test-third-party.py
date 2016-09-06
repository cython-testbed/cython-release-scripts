from __future__ import print_function

import argparse
import base64
import pprint
import re
import sys

import github  # pip install pygithub
import requests

try:
    raw_input
except NameError:
    # Python 3
    raw_input = input

ORG = 'cython-testbed'
EXCLUDE_REPOS = ('cython', 'cython-release-scripts')
TRAVIS_CONFIG = '.travis.yml'

test_config_files = {
    'grpc': 'tools/run_tests/build_python.sh',
    'scikit-learn': 'build_tools/travis/install.sh',
    'scikit-image': 'tools/travis_before_install.sh',
    'pandas': 'ci/install_travis.sh',
}

def error(msg, listing=None):
    print("ERROR", msg)
    if listing:
        listing.append(msg)

def main(argv):

    parser = argparse.ArgumentParser()
    parser.add_argument('--user')
    parser.add_argument('--token', default=None)
    parser.add_argument('--dry_run', action='store_true')
    parser.add_argument('--commit')
    options = parser.parse_args(argv)

    errors = []

    token = options.token or raw_input("Token: ")
    org = github.Github(options.user, token).get_organization(ORG)

    if options.commit:
        cython_commit = options.commit
    else:
        cython_repo = org.get_repo('cython')
        cython_commit = cython_repo.get_commits()[0].sha


    for repo in org.get_repos():
        if repo.name in EXCLUDE_REPOS:
            continue
        print()
        print(repo.name)

        current_sha = repo.get_commits()[0].sha
        upstream_sha = repo.parent.get_commits()[0].sha
        if current_sha != upstream_sha:
            print('Merge %s into master' % upstream_sha)
            if not options.dry_run:
                repo.merge('master', upstream_sha)
            repo.update()
        else:
            print('Up to date with upstream.')

        config_path = test_config_files.get(repo.name, TRAVIS_CONFIG)
        try:
            travis = repo.get_file_contents(config_path)
            old_travis = travis.decoded_content
        except Exception, exn:
            error("No travis configuration for %s" % repo.name, errors)
            continue
        if 'cython/archive' not in old_travis:
            error("Travis configuration for %s doesn't point to cython snapshot" % repo.name, errors)
            continue
        if '--no-cython-compile' not in old_travis:
            error("Travis configuration for %s doesn't specify --no-cython-compile" % repo.name, errors)
        new_travis = re.sub('cython/archive/.*?.zip', 'cython/archive/%s.zip' % cython_commit, old_travis)
        if old_travis != new_travis:
            print("Updating travis config at %s" % config_path)
            if not options.dry_run:
                r = requests.put('https://api.github.com/repos/%s/%s/contents/%s' % (ORG, repo.name, config_path),
                                 auth=(options.user, token),
                                 json={
                                     'path': config_path,
                                     'message': 'Update travis config to point to Cython at %s.' % cython_commit,
                                     'content': base64.b64encode(new_travis),
                                     'sha': travis.sha,
                                  })
                if r.status_code // 100 != 2:
                    errors.append('Error updating travis pointer for %s: %s' % (repo.name, r.json()))

#                 repo.update_file(
#                     config_path,
#                     'Update travis config to point to %s.' % cython_commit,
#                     new_travis,
#                     travis.sha)
        else:
            print("Already up to date.")

    if errors:
        print()
        print("ERRORS")
        print("\n".join(errors))


if __name__ == '__main__':
    main(sys.argv[1:])
