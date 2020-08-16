#!/usr/bin/env python

from __future__ import print_function
import socket

import base64
import calendar
import codecs
import datetime
import errno
import getpass
import json
import logging
import os
import re
import select
import subprocess
import sys
import time
import platform
PY2 = False
try:
    # python 3
    from urllib.parse import urlparse
    from urllib.parse import quote as urlquote
    from urllib.parse import urlencode
    from urllib.error import HTTPError, URLError
    from urllib.request import urlopen
    from urllib.request import Request
    from urllib.request import HTTPRedirectHandler
    from urllib.request import build_opener
    from subprocess import SubprocessError
except ImportError:
    # python 2
    PY2 = True
    from subprocess import CalledProcessError as SubprocessError
    from urlparse import urlparse
    from urllib import quote as urlquote
    from urllib import urlencode
    from urllib2 import HTTPError, URLError
    from urllib2 import urlopen
    from urllib2 import Request
    from urllib2 import HTTPRedirectHandler
    from urllib2 import build_opener

try:
    from . import __version__
    VERSION = __version__
except ImportError:
    VERSION = 'unknown'

FNULL = open(os.devnull, 'w')


def _get_log_date():
    return datetime.datetime.isoformat(datetime.datetime.now())


def log_error(message):
    """
    Log message (str) or messages (List[str]) to stderr and exit with status 1
    """
    log_warning(message)
    sys.exit(1)


def log_info(message):
    """
    Log message (str) or messages (List[str]) to stdout
    """
    if type(message) == str:
        message = [message]

    for msg in message:
        sys.stdout.write("{0}: {1}\n".format(_get_log_date(), msg))


def log_warning(message):
    """
    Log message (str) or messages (List[str]) to stderr
    """
    if type(message) == str:
        message = [message]

    for msg in message:
        sys.stderr.write("{0}: {1}\n".format(_get_log_date(), msg))


def logging_subprocess(popenargs,
                       logger,
                       stdout_log_level=logging.DEBUG,
                       stderr_log_level=logging.ERROR,
                       **kwargs):
    """
    Variant of subprocess.call that accepts a logger instead of stdout/stderr,
    and logs stdout messages via logger.debug and stderr messages via
    logger.error.
    """
    child = subprocess.Popen(popenargs, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, **kwargs)
    if sys.platform == 'win32':
        log_info("Windows operating system detected - no subprocess logging will be returned")

    log_level = {child.stdout: stdout_log_level,
                 child.stderr: stderr_log_level}

    def check_io():
        if sys.platform == 'win32':
            return
        ready_to_read = select.select([child.stdout, child.stderr],
                                      [],
                                      [],
                                      1000)[0]
        for io in ready_to_read:
            line = io.readline()
            if not logger:
                continue
            if not (io == child.stderr and not line):
                logger.log(log_level[io], line[:-1])

    # keep checking stdout/stderr until the child exits
    while child.poll() is None:
        check_io()

    check_io()  # check again to catch anything after the process exits

    rc = child.wait()

    if rc != 0:
        print('{} returned {}:'.format(popenargs[0], rc), file=sys.stderr)
        print('\t', ' '.join(popenargs), file=sys.stderr)

    return rc


def mkdir_p(*args):
    for path in args:
        try:
            os.makedirs(path)
        except OSError as exc:  # Python >2.5
            if exc.errno == errno.EEXIST and os.path.isdir(path):
                pass
            else:
                raise


def mask_password(url, secret='*****'):
    parsed = urlparse(url)

    if not parsed.password:
        return url
    elif parsed.password == 'x-oauth-basic':
        return url.replace(parsed.username, secret)

    return url.replace(parsed.password, secret)


def get_auth(args, encode=True, for_git_cli=False):
    auth = None

    if args.osx_keychain_item_name:
        if not args.osx_keychain_item_account:
            log_error('You must specify both name and account fields for osx keychain password items')
        else:
            if platform.system() != 'Darwin':
                log_error("Keychain arguments are only supported on Mac OSX")
            try:
                with open(os.devnull, 'w') as devnull:
                    token = (subprocess.check_output([
                        'security', 'find-generic-password',
                        '-s', args.osx_keychain_item_name,
                        '-a', args.osx_keychain_item_account,
                        '-w'], stderr=devnull).strip())
                if not PY2:
                    token = token.decode('utf-8')
                auth = token + ':' + 'x-oauth-basic'
            except SubprocessError:
                log_error('No password item matching the provided name and account could be found in the osx keychain.')
    elif args.osx_keychain_item_account:
        log_error('You must specify both name and account fields for osx keychain password items')
    elif args.token:
        _path_specifier = 'file://'
        if args.token.startswith(_path_specifier):
            args.token = open(args.token[len(_path_specifier):],
                              'rt').readline().strip()
        if not args.as_app:
            auth = args.token + ':' + 'x-oauth-basic'
        else:
            if not for_git_cli:
                auth = args.token
            else:
                auth = 'x-access-token:' + args.token
    elif args.username:
        if not args.password:
            args.password = getpass.getpass()
        if encode:
            password = args.password
        else:
            password = urlquote(args.password)
        auth = args.username + ':' + password
    elif args.password:
        log_error('You must specify a username for basic auth')

    if not auth:
        return None

    if not encode:
        return auth

    return base64.b64encode(auth.encode('ascii'))


def get_github_api_host(args):
    if args.github_host:
        host = args.github_host + '/api/v3'
    else:
        host = 'api.github.com'

    return host


def get_github_host(args):
    if args.github_host:
        host = args.github_host
    else:
        host = 'github.com'

    return host


def get_github_repo_url(args, repository):
    if repository.get('is_gist'):
        if args.prefer_ssh:
            # The git_pull_url value is always https for gists, so we need to transform it to ssh form
            repo_url = re.sub(r'^https?:\/\/(.+)\/(.+)\.git$', r'git@\1:\2.git', repository['git_pull_url'])
            repo_url = re.sub(r'^git@gist\.', 'git@', repo_url)  # strip gist subdomain for better hostkey compatibility
        else:
            repo_url = repository['git_pull_url']
        return repo_url

    if args.prefer_ssh:
        return repository['ssh_url']

    auth = get_auth(args, encode=False, for_git_cli=True)
    if auth and repository['private'] is True:
        repo_url = 'https://{0}@{1}/{2}/{3}.git'.format(
            auth,
            get_github_host(args),
            repository['owner']['login'],
            repository['name'])
    else:
        repo_url = repository['clone_url']

    return repo_url


def retrieve_data_gen(args, template, query_args=None, single_request=False):
    auth = get_auth(args, encode=not args.as_app)
    query_args = get_query_args(query_args)
    per_page = 100
    page = 0

    while True:
        page = page + 1
        request = _construct_request(per_page, page, query_args, template, auth, as_app=args.as_app)  # noqa
        r, errors = _get_response(request, auth, template)

        status_code = int(r.getcode())
        # be gentle with API request limit and throttle requests if remaining requests getting low
        limit_remaining = int(r.headers.get('x-ratelimit-remaining', 0))
        if args.throttle_limit and limit_remaining <= args.throttle_limit:
            log_info(
                'API request limit hit: {} requests left, pausing further requests for {}s'.format(
                    limit_remaining,
                    args.throttle_pause))
            time.sleep(args.throttle_pause)

        retries = 0
        while retries < 3 and status_code == 502:
            log_warning('API request returned HTTP 502: Bad Gateway. Retrying in 5 seconds')
            retries += 1
            time.sleep(5)
            request = _construct_request(per_page, page, query_args, template, auth, as_app=args.as_app)  # noqa
            r, errors = _get_response(request, auth, template)

            status_code = int(r.getcode())

        if status_code != 200:
            template = 'API request returned HTTP {0}: {1}'
            errors.append(template.format(status_code, r.reason))
            log_error(errors)

        response = json.loads(r.read().decode('utf-8'))
        if len(errors) == 0:
            if type(response) == list:
                for resp in response:
                    yield resp
                if len(response) < per_page:
                    break
            elif type(response) == dict and single_request:
                yield response

        if len(errors) > 0:
            log_error(errors)

        if single_request:
            break


def retrieve_data(args, template, query_args=None, single_request=False):
    return list(retrieve_data_gen(args, template, query_args, single_request))


def get_query_args(query_args=None):
    if not query_args:
        query_args = {}
    return query_args


def _get_response(request, auth, template):
    retry_timeout = 3
    errors = []
    # We'll make requests in a loop so we can
    # delay and retry in the case of rate-limiting
    while True:
        should_continue = False
        try:
            r = urlopen(request)
        except HTTPError as exc:
            errors, should_continue = _request_http_error(exc, auth, errors)  # noqa
            r = exc
        except URLError as e:
            log_warning(e.reason)
            should_continue = _request_url_error(template, retry_timeout)
            if not should_continue:
                raise
        except socket.error as e:
            log_warning(e.strerror)
            should_continue = _request_url_error(template, retry_timeout)
            if not should_continue:
                raise

        if should_continue:
            continue

        break
    return r, errors


def _construct_request(per_page, page, query_args, template, auth, as_app=None):
    querystring = urlencode(dict(list({
        'per_page': per_page,
        'page': page
    }.items()) + list(query_args.items())))

    request = Request(template + '?' + querystring)
    if auth is not None:
        if not as_app:
            request.add_header('Authorization', 'Basic '.encode('ascii') + auth)
        else:
            if not PY2:
                auth = auth.encode('ascii')
            request.add_header('Authorization', 'token '.encode('ascii') + auth)
            request.add_header('Accept', 'application/vnd.github.machine-man-preview+json')
    log_info('Requesting {}?{}'.format(template, querystring))
    return request


def _request_http_error(exc, auth, errors):
    # HTTPError behaves like a Response so we can
    # check the status code and headers to see exactly
    # what failed.

    should_continue = False
    headers = exc.headers
    limit_remaining = int(headers.get('x-ratelimit-remaining', 0))

    if exc.code == 403 and limit_remaining < 1:
        # The X-RateLimit-Reset header includes a
        # timestamp telling us when the limit will reset
        # so we can calculate how long to wait rather
        # than inefficiently polling:
        gm_now = calendar.timegm(time.gmtime())
        reset = int(headers.get('x-ratelimit-reset', 0)) or gm_now
        # We'll never sleep for less than 10 seconds:
        delta = max(10, reset - gm_now)

        limit = headers.get('x-ratelimit-limit')
        log_warning('Exceeded rate limit of {} requests; waiting {} seconds to reset'.format(limit, delta))  # noqa

        if auth is None:
            log_info('Hint: Authenticate to raise your GitHub rate limit')

        time.sleep(delta)
        should_continue = True
    return errors, should_continue


def _request_url_error(template, retry_timeout):
    # Incase of a connection timing out, we can retry a few time
    # But we won't crash and not back-up the rest now
    log_info('{} timed out'.format(template))
    retry_timeout -= 1

    if retry_timeout >= 0:
        return True

    log_error('{} timed out to much, skipping!')
    return False


class S3HTTPRedirectHandler(HTTPRedirectHandler):
    """
    A subclassed redirect handler for downloading Github assets from S3.

    urllib will add the Authorization header to the redirected request to S3, which will result in a 400,
    so we should remove said header on redirect.
    """
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if PY2:
            # HTTPRedirectHandler is an old style class
            request = HTTPRedirectHandler.redirect_request(self, req, fp, code, msg, headers, newurl)
        else:
            request = super(S3HTTPRedirectHandler, self).redirect_request(req, fp, code, msg, headers, newurl)
        del request.headers['Authorization']
        return request


def download_file(url, path, auth):
    # Skip downloading release assets if they already exist on disk so we don't redownload on every sync
    if os.path.exists(path):
        return

    request = Request(url)
    request.add_header('Accept', 'application/octet-stream')
    request.add_header('Authorization', 'Basic '.encode('ascii') + auth)
    opener = build_opener(S3HTTPRedirectHandler)

    try:
        response = opener.open(request)

        chunk_size = 16 * 1024
        with open(path, 'wb') as f:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
    except HTTPError as exc:
        # Gracefully handle 404 responses (and others) when downloading from S3
        log_warning('Skipping download of asset {0} due to HTTPError: {1}'.format(url, exc.reason))
    except URLError as e:
        # Gracefully handle other URL errors
        log_warning('Skipping download of asset {0} due to URLError: {1}'.format(url, e.reason))
    except socket.error as e:
        # Gracefully handle socket errors
        # TODO: Implement retry logic
        log_warning('Skipping download of asset {0} due to socker error: {1}'.format(url, e.strerror))


def get_authenticated_user(args):
    template = 'https://{0}/user'.format(get_github_api_host(args))
    data = retrieve_data(args, template, single_request=True)
    return data[0]


def check_git_lfs_install():
    exit_code = subprocess.call(['git', 'lfs', 'version'])
    if exit_code != 0:
        log_error('The argument --lfs requires you to have Git LFS installed.\nYou can get it from https://git-lfs.github.com.')


def retrieve_repositories(args, authenticated_user):
    log_info('Retrieving repositories')
    single_request = False
    if args.user == authenticated_user['login']:
        # we must use the /user/repos API to be able to access private repos
        template = 'https://{0}/user/repos'.format(
            get_github_api_host(args))
    else:
        if args.private and not args.organization:
            log_warning('Authenticated user is different from user being backed up, thus private repositories cannot be accessed')
        template = 'https://{0}/users/{1}/repos'.format(
            get_github_api_host(args),
            args.user)

    if args.organization:
        template = 'https://{0}/orgs/{1}/repos'.format(
            get_github_api_host(args),
            args.user)

    if args.repository:
        single_request = True
        template = 'https://{0}/repos/{1}/{2}'.format(
            get_github_api_host(args),
            args.user,
            args.repository)

    repos = retrieve_data(args, template, single_request=single_request)

    if args.all_starred:
        starred_template = 'https://{0}/users/{1}/starred'.format(get_github_api_host(args), args.user)
        starred_repos = retrieve_data(args, starred_template, single_request=False)
        # flag each repo as starred for downstream processing
        for item in starred_repos:
            item.update({'is_starred': True})
        repos.extend(starred_repos)

    if args.include_gists:
        gists_template = 'https://{0}/users/{1}/gists'.format(get_github_api_host(args), args.user)
        gists = retrieve_data(args, gists_template, single_request=False)
        # flag each repo as a gist for downstream processing
        for item in gists:
            item.update({'is_gist': True})
        repos.extend(gists)

    if args.include_starred_gists:
        starred_gists_template = 'https://{0}/gists/starred'.format(get_github_api_host(args))
        starred_gists = retrieve_data(args, starred_gists_template, single_request=False)
        # flag each repo as a starred gist for downstream processing
        for item in starred_gists:
            item.update({'is_gist': True,
                         'is_starred': True})
        repos.extend(starred_gists)

    return repos


def filter_repositories(args, unfiltered_repositories):
    log_info('Filtering repositories')

    repositories = []
    for r in unfiltered_repositories:
        # gists can be anonymous, so need to safely check owner
        if r.get('owner', {}).get('login') == args.user or r.get('is_starred'):
            repositories.append(r)

    name_regex = None
    if args.name_regex:
        name_regex = re.compile(args.name_regex)

    languages = None
    if args.languages:
        languages = [x.lower() for x in args.languages]

    if not args.fork:
        repositories = [r for r in repositories if not r.get('fork')]
    if not args.private:
        repositories = [r for r in repositories if not r.get('private') or r.get('public')]
    if languages:
        repositories = [r for r in repositories if r.get('language') and r.get('language').lower() in languages]  # noqa
    if name_regex:
        repositories = [r for r in repositories if name_regex.match(r['name'])]

    return repositories


def backup_repositories(args, output_directory, repositories):
    log_info('Backing up repositories')
    repos_template = 'https://{0}/repos'.format(get_github_api_host(args))

    if args.incremental:
        last_update = max(list(repository['updated_at'] for repository in repositories) or [time.strftime('%Y-%m-%dT%H:%M:%SZ', time.localtime())])  # noqa
        last_update_path = os.path.join(output_directory, 'last_update')
        if os.path.exists(last_update_path):
            args.since = open(last_update_path).read().strip()
        else:
            args.since = None
    else:
        args.since = None

    for repository in repositories:
        if repository.get('is_gist'):
            repo_cwd = os.path.join(output_directory, 'gists', repository['id'])
        elif repository.get('is_starred'):
            # put starred repos in -o/starred/${owner}/${repo} to prevent collision of
            # any repositories with the same name
            repo_cwd = os.path.join(output_directory, 'starred', repository['owner']['login'], repository['name'])
        else:
            repo_cwd = os.path.join(output_directory, 'repositories', repository['name'])

        repo_dir = os.path.join(repo_cwd, 'repository')
        repo_url = get_github_repo_url(args, repository)

        include_gists = (args.include_gists or args.include_starred_gists)
        if (args.include_repository or args.include_everything) \
                or (include_gists and repository.get('is_gist')):
            repo_name = repository.get('name') if not repository.get('is_gist') else repository.get('id')
            fetch_repository(repo_name,
                             repo_url,
                             repo_dir,
                             skip_existing=args.skip_existing,
                             bare_clone=args.bare_clone,
                             lfs_clone=args.lfs_clone)

            if repository.get('is_gist'):
                # dump gist information to a file as well
                output_file = '{0}/gist.json'.format(repo_cwd)
                with codecs.open(output_file, 'w', encoding='utf-8') as f:
                    json_dump(repository, f)

                continue  # don't try to back anything else for a gist; it doesn't exist

        download_wiki = (args.include_wiki or args.include_everything)
        if repository['has_wiki'] and download_wiki:
            fetch_repository(repository['name'],
                             repo_url.replace('.git', '.wiki.git'),
                             os.path.join(repo_cwd, 'wiki'),
                             skip_existing=args.skip_existing,
                             bare_clone=args.bare_clone,
                             lfs_clone=args.lfs_clone)

        if args.include_issues or args.include_everything:
            backup_issues(args, repo_cwd, repository, repos_template)

        if args.include_pulls or args.include_everything:
            backup_pulls(args, repo_cwd, repository, repos_template)

        if args.include_milestones or args.include_everything:
            backup_milestones(args, repo_cwd, repository, repos_template)

        if args.include_labels or args.include_everything:
            backup_labels(args, repo_cwd, repository, repos_template)

        if args.include_hooks or args.include_everything:
            backup_hooks(args, repo_cwd, repository, repos_template)

        if args.include_releases or args.include_everything:
            backup_releases(args, repo_cwd, repository, repos_template,
                            include_assets=args.include_assets or args.include_everything)

    if args.incremental:
        open(last_update_path, 'w').write(last_update)


def backup_issues(args, repo_cwd, repository, repos_template):
    has_issues_dir = os.path.isdir('{0}/issues/.git'.format(repo_cwd))
    if args.skip_existing and has_issues_dir:
        return

    log_info('Retrieving {0} issues'.format(repository['full_name']))
    issue_cwd = os.path.join(repo_cwd, 'issues')
    mkdir_p(repo_cwd, issue_cwd)

    issues = {}
    issues_skipped = 0
    issues_skipped_message = ''
    _issue_template = '{0}/{1}/issues'.format(repos_template,
                                              repository['full_name'])

    should_include_pulls = args.include_pulls or args.include_everything
    issue_states = ['open', 'closed']
    for issue_state in issue_states:
        query_args = {
            'filter': 'all',
            'state': issue_state
        }
        if args.since:
            query_args['since'] = args.since

        _issues = retrieve_data(args,
                                _issue_template,
                                query_args=query_args)
        for issue in _issues:
            # skip pull requests which are also returned as issues
            # if retrieving pull requests is requested as well
            if 'pull_request' in issue and should_include_pulls:
                issues_skipped += 1
                continue

            issues[issue['number']] = issue

    if issues_skipped:
        issues_skipped_message = ' (skipped {0} pull requests)'.format(
            issues_skipped)

    log_info('Saving {0} issues to disk{1}'.format(
        len(list(issues.keys())), issues_skipped_message))
    comments_template = _issue_template + '/{0}/comments'
    events_template = _issue_template + '/{0}/events'
    for number, issue in list(issues.items()):
        if args.include_issue_comments or args.include_everything:
            template = comments_template.format(number)
            issues[number]['comment_data'] = retrieve_data(args, template)
        if args.include_issue_events or args.include_everything:
            template = events_template.format(number)
            issues[number]['event_data'] = retrieve_data(args, template)

        issue_file = '{0}/{1}.json'.format(issue_cwd, number)
        with codecs.open(issue_file, 'w', encoding='utf-8') as f:
            json_dump(issue, f)


def backup_pulls(args, repo_cwd, repository, repos_template):
    has_pulls_dir = os.path.isdir('{0}/pulls/.git'.format(repo_cwd))
    if args.skip_existing and has_pulls_dir:
        return

    log_info('Retrieving {0} pull requests'.format(repository['full_name']))  # noqa
    pulls_cwd = os.path.join(repo_cwd, 'pulls')
    mkdir_p(repo_cwd, pulls_cwd)

    pulls = {}
    _pulls_template = '{0}/{1}/pulls'.format(repos_template,
                                             repository['full_name'])
    query_args = {
        'filter': 'all',
        'state': 'all',
        'sort': 'updated',
        'direction': 'desc',
    }

    if not args.include_pull_details:
        pull_states = ['open', 'closed']
        for pull_state in pull_states:
            query_args['state'] = pull_state
            _pulls = retrieve_data_gen(
                args,
                _pulls_template,
                query_args=query_args
            )
            for pull in _pulls:
                if args.since and pull['updated_at'] < args.since:
                    break
                if not args.since or pull['updated_at'] >= args.since:
                    pulls[pull['number']] = pull
    else:
        _pulls = retrieve_data_gen(
            args,
            _pulls_template,
            query_args=query_args
        )
        for pull in _pulls:
            if args.since and pull['updated_at'] < args.since:
                break
            if not args.since or pull['updated_at'] >= args.since:
                pulls[pull['number']] = retrieve_data(
                    args,
                    _pulls_template + '/{}'.format(pull['number']),
                    single_request=True
                )[0]

    log_info('Saving {0} pull requests to disk'.format(
        len(list(pulls.keys()))))
    comments_template = _pulls_template + '/{0}/comments'
    commits_template = _pulls_template + '/{0}/commits'
    for number, pull in list(pulls.items()):
        if args.include_pull_comments or args.include_everything:
            template = comments_template.format(number)
            pulls[number]['comment_data'] = retrieve_data(args, template)
        if args.include_pull_commits or args.include_everything:
            template = commits_template.format(number)
            pulls[number]['commit_data'] = retrieve_data(args, template)

        pull_file = '{0}/{1}.json'.format(pulls_cwd, number)
        with codecs.open(pull_file, 'w', encoding='utf-8') as f:
            json_dump(pull, f)


def backup_milestones(args, repo_cwd, repository, repos_template):
    milestone_cwd = os.path.join(repo_cwd, 'milestones')
    if args.skip_existing and os.path.isdir(milestone_cwd):
        return

    log_info('Retrieving {0} milestones'.format(repository['full_name']))
    mkdir_p(repo_cwd, milestone_cwd)

    template = '{0}/{1}/milestones'.format(repos_template,
                                           repository['full_name'])

    query_args = {
        'state': 'all'
    }

    _milestones = retrieve_data(args, template, query_args=query_args)

    milestones = {}
    for milestone in _milestones:
        milestones[milestone['number']] = milestone

    log_info('Saving {0} milestones to disk'.format(
        len(list(milestones.keys()))))
    for number, milestone in list(milestones.items()):
        milestone_file = '{0}/{1}.json'.format(milestone_cwd, number)
        with codecs.open(milestone_file, 'w', encoding='utf-8') as f:
            json_dump(milestone, f)


def backup_labels(args, repo_cwd, repository, repos_template):
    label_cwd = os.path.join(repo_cwd, 'labels')
    output_file = '{0}/labels.json'.format(label_cwd)
    template = '{0}/{1}/labels'.format(repos_template,
                                       repository['full_name'])
    _backup_data(args,
                 'labels',
                 template,
                 output_file,
                 label_cwd)


def backup_hooks(args, repo_cwd, repository, repos_template):
    auth = get_auth(args)
    if not auth:
        log_info("Skipping hooks since no authentication provided")
        return
    hook_cwd = os.path.join(repo_cwd, 'hooks')
    output_file = '{0}/hooks.json'.format(hook_cwd)
    template = '{0}/{1}/hooks'.format(repos_template,
                                      repository['full_name'])
    try:
        _backup_data(args,
                     'hooks',
                     template,
                     output_file,
                     hook_cwd)
    except SystemExit:
        log_info("Unable to read hooks, skipping")


def backup_releases(args, repo_cwd, repository, repos_template, include_assets=False):
    repository_fullname = repository['full_name']

    # give release files somewhere to live & log intent
    release_cwd = os.path.join(repo_cwd, 'releases')
    log_info('Retrieving {0} releases'.format(repository_fullname))
    mkdir_p(repo_cwd, release_cwd)

    query_args = {}

    release_template = '{0}/{1}/releases'.format(repos_template, repository_fullname)
    releases = retrieve_data(args, release_template, query_args=query_args)

    # for each release, store it
    log_info('Saving {0} releases to disk'.format(len(releases)))
    for release in releases:
        release_name = release['tag_name']
        output_filepath = os.path.join(release_cwd, '{0}.json'.format(release_name))
        with codecs.open(output_filepath, 'w+', encoding='utf-8') as f:
            json_dump(release, f)

        if include_assets:
            assets = retrieve_data(args, release['assets_url'])
            if len(assets) > 0:
                # give release asset files somewhere to live & download them (not including source archives)
                release_assets_cwd = os.path.join(release_cwd, release_name)
                mkdir_p(release_assets_cwd)
                for asset in assets:
                    download_file(asset['url'], os.path.join(release_assets_cwd, asset['name']), get_auth(args))


def fetch_repository(name,
                     remote_url,
                     local_dir,
                     skip_existing=False,
                     bare_clone=False,
                     lfs_clone=False):
    if bare_clone:
        if os.path.exists(local_dir):
            clone_exists = subprocess.check_output(['git',
                                                    'rev-parse',
                                                    '--is-bare-repository'],
                                                   cwd=local_dir) == b"true\n"
        else:
            clone_exists = False
    else:
        clone_exists = os.path.exists(os.path.join(local_dir, '.git'))

    if clone_exists and skip_existing:
        return

    masked_remote_url = mask_password(remote_url)

    initialized = subprocess.call('git ls-remote ' + remote_url,
                                  stdout=FNULL,
                                  stderr=FNULL,
                                  shell=True)
    if initialized == 128:
        log_info("Skipping {0} ({1}) since it's not initialized".format(
            name, masked_remote_url))
        return

    if clone_exists:
        log_info('Updating {0} in {1}'.format(name, local_dir))

        remotes = subprocess.check_output(['git', 'remote', 'show'],
                                          cwd=local_dir)
        remotes = [i.strip() for i in remotes.decode('utf-8').splitlines()]

        if 'origin' not in remotes:
            git_command = ['git', 'remote', 'rm', 'origin']
            logging_subprocess(git_command, None, cwd=local_dir)
            git_command = ['git', 'remote', 'add', 'origin', remote_url]
            logging_subprocess(git_command, None, cwd=local_dir)
        else:
            git_command = ['git', 'remote', 'set-url', 'origin', remote_url]
            logging_subprocess(git_command, None, cwd=local_dir)

        if lfs_clone:
            git_command = ['git', 'lfs', 'fetch', '--all', '--prune']
        else:
            git_command = ['git', 'fetch', '--all', '--force', '--tags', '--prune']
        logging_subprocess(git_command, None, cwd=local_dir)
    else:
        log_info('Cloning {0} repository from {1} to {2}'.format(
            name,
            masked_remote_url,
            local_dir))
        if bare_clone:
            if lfs_clone:
                git_command = ['git', 'lfs', 'clone', '--mirror', remote_url, local_dir]
            else:
                git_command = ['git', 'clone', '--mirror', remote_url, local_dir]
        else:
            if lfs_clone:
                git_command = ['git', 'lfs', 'clone', remote_url, local_dir]
            else:
                git_command = ['git', 'clone', remote_url, local_dir]
        logging_subprocess(git_command, None)


def backup_account(args, output_directory):
    account_cwd = os.path.join(output_directory, 'account')

    if args.include_starred or args.include_everything:
        output_file = "{0}/starred.json".format(account_cwd)
        template = "https://{0}/users/{1}/starred".format(get_github_api_host(args), args.user)
        _backup_data(args,
                     "starred repositories",
                     template,
                     output_file,
                     account_cwd)

    if args.include_watched or args.include_everything:
        output_file = "{0}/watched.json".format(account_cwd)
        template = "https://{0}/users/{1}/subscriptions".format(get_github_api_host(args), args.user)
        _backup_data(args,
                     "watched repositories",
                     template,
                     output_file,
                     account_cwd)

    if args.include_followers or args.include_everything:
        output_file = "{0}/followers.json".format(account_cwd)
        template = "https://{0}/users/{1}/followers".format(get_github_api_host(args), args.user)
        _backup_data(args,
                     "followers",
                     template,
                     output_file,
                     account_cwd)

    if args.include_following or args.include_everything:
        output_file = "{0}/following.json".format(account_cwd)
        template = "https://{0}/users/{1}/following".format(get_github_api_host(args), args.user)
        _backup_data(args,
                     "following",
                     template,
                     output_file,
                     account_cwd)


def _backup_data(args, name, template, output_file, output_directory):
    skip_existing = args.skip_existing
    if not skip_existing or not os.path.exists(output_file):
        log_info('Retrieving {0} {1}'.format(args.user, name))
        mkdir_p(output_directory)
        data = retrieve_data(args, template)

        log_info('Writing {0} {1} to disk'.format(len(data), name))
        with codecs.open(output_file, 'w', encoding='utf-8') as f:
            json_dump(data, f)


def json_dump(data, output_file):
    json.dump(data,
              output_file,
              ensure_ascii=False,
              sort_keys=True,
              indent=4,
              separators=(',', ': '))
