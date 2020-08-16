#!/usr/bin/env python

import argparse


try:
    from . import __version__
    VERSION = __version__
except ImportError:
    VERSION = 'unknown'


def parse_args():
    parser = argparse.ArgumentParser(description='Backup a github account')
    parser.add_argument('user',
                        metavar='USER',
                        type=str,
                        help='github username')
    parser.add_argument('-u',
                        '--username',
                        dest='username',
                        help='username for basic auth')
    parser.add_argument('-p',
                        '--password',
                        dest='password',
                        help='password for basic auth. '
                             'If a username is given but not a password, the '
                             'password will be prompted for.')
    parser.add_argument('-t',
                        '--token',
                        dest='token',
                        help='personal access, OAuth, or JSON Web token, or path to token (file://...)')  # noqa
    parser.add_argument('--as-app',
                        action='store_true',
                        dest='as_app',
                        help='authenticate as github app instead of as a user.')
    parser.add_argument('-o',
                        '--output-directory',
                        default='.',
                        dest='output_directory',
                        help='directory at which to backup the repositories')
    parser.add_argument('-i',
                        '--incremental',
                        action='store_true',
                        dest='incremental',
                        help='incremental backup')
    parser.add_argument('--starred',
                        action='store_true',
                        dest='include_starred',
                        help='include JSON output of starred repositories in backup')
    parser.add_argument('--all-starred',
                        action='store_true',
                        dest='all_starred',
                        help='include starred repositories in backup [*]')
    parser.add_argument('--watched',
                        action='store_true',
                        dest='include_watched',
                        help='include JSON output of watched repositories in backup')
    parser.add_argument('--followers',
                        action='store_true',
                        dest='include_followers',
                        help='include JSON output of followers in backup')
    parser.add_argument('--following',
                        action='store_true',
                        dest='include_following',
                        help='include JSON output of following users in backup')
    parser.add_argument('--all',
                        action='store_true',
                        dest='include_everything',
                        help='include everything in backup (not including [*])')
    parser.add_argument('--issues',
                        action='store_true',
                        dest='include_issues',
                        help='include issues in backup')
    parser.add_argument('--issue-comments',
                        action='store_true',
                        dest='include_issue_comments',
                        help='include issue comments in backup')
    parser.add_argument('--issue-events',
                        action='store_true',
                        dest='include_issue_events',
                        help='include issue events in backup')
    parser.add_argument('--pulls',
                        action='store_true',
                        dest='include_pulls',
                        help='include pull requests in backup')
    parser.add_argument('--pull-comments',
                        action='store_true',
                        dest='include_pull_comments',
                        help='include pull request review comments in backup')
    parser.add_argument('--pull-commits',
                        action='store_true',
                        dest='include_pull_commits',
                        help='include pull request commits in backup')
    parser.add_argument('--pull-details',
                        action='store_true',
                        dest='include_pull_details',
                        help='include more pull request details in backup [*]')
    parser.add_argument('--labels',
                        action='store_true',
                        dest='include_labels',
                        help='include labels in backup')
    parser.add_argument('--hooks',
                        action='store_true',
                        dest='include_hooks',
                        help='include hooks in backup (works only when authenticated)')  # noqa
    parser.add_argument('--milestones',
                        action='store_true',
                        dest='include_milestones',
                        help='include milestones in backup')
    parser.add_argument('--repositories',
                        action='store_true',
                        dest='include_repository',
                        help='include repository clone in backup')
    parser.add_argument('--bare',
                        action='store_true',
                        dest='bare_clone',
                        help='clone bare repositories')
    parser.add_argument('--lfs',
                        action='store_true',
                        dest='lfs_clone',
                        help='clone LFS repositories (requires Git LFS to be installed, https://git-lfs.github.com) [*]')
    parser.add_argument('--wikis',
                        action='store_true',
                        dest='include_wiki',
                        help='include wiki clone in backup')
    parser.add_argument('--gists',
                        action='store_true',
                        dest='include_gists',
                        help='include gists in backup [*]')
    parser.add_argument('--starred-gists',
                        action='store_true',
                        dest='include_starred_gists',
                        help='include starred gists in backup [*]')
    parser.add_argument('--skip-existing',
                        action='store_true',
                        dest='skip_existing',
                        help='skip project if a backup directory exists')
    parser.add_argument('-L',
                        '--languages',
                        dest='languages',
                        help='only allow these languages',
                        nargs='*')
    parser.add_argument('-N',
                        '--name-regex',
                        dest='name_regex',
                        help='python regex to match names against')
    parser.add_argument('-H',
                        '--github-host',
                        dest='github_host',
                        help='GitHub Enterprise hostname')
    parser.add_argument('-O',
                        '--organization',
                        action='store_true',
                        dest='organization',
                        help='whether or not this is an organization user')
    parser.add_argument('-R',
                        '--repository',
                        dest='repository',
                        help='name of repository to limit backup to')
    parser.add_argument('-P', '--private',
                        action='store_true',
                        dest='private',
                        help='include private repositories [*]')
    parser.add_argument('-F', '--fork',
                        action='store_true',
                        dest='fork',
                        help='include forked repositories [*]')
    parser.add_argument('--prefer-ssh',
                        action='store_true',
                        help='Clone repositories using SSH instead of HTTPS')
    parser.add_argument('-v', '--version',
                        action='version',
                        version='%(prog)s ' + VERSION)
    parser.add_argument('--keychain-name',
                        dest='osx_keychain_item_name',
                        help='OSX ONLY: name field of password item in OSX keychain that holds the personal access or OAuth token')
    parser.add_argument('--keychain-account',
                        dest='osx_keychain_item_account',
                        help='OSX ONLY: account field of password item in OSX keychain that holds the personal access or OAuth token')
    parser.add_argument('--releases',
                        action='store_true',
                        dest='include_releases',
                        help='include release information, not including assets or binaries'
                        )
    parser.add_argument('--assets',
                        action='store_true',
                        dest='include_assets',
                        help='include assets alongside release information; only applies if including releases')
    parser.add_argument('--throttle-limit',
                        dest='throttle_limit',
                        type=int,
                        default=0,
                        help='start throttling of GitHub API requests after this amount of API requests remain')
    parser.add_argument('--throttle-pause',
                        dest='throttle_pause',
                        type=float,
                        default=30.0,
                        help='wait this amount of seconds when API request throttling is active (default: 30.0, requires --throttle-limit to be set)')
    return parser.parse_args()
