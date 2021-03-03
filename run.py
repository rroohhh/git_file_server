import secrets
from git import Repo
from flask import Flask, Response, redirect, abort
from mimetypes import guess_type
import threading
import config
import hashlib
from pathlib import Path

app = Flask(__name__)

lock = threading.Lock()


if not Path(config.repo).exists():
    repo = Repo.clone_from(config.remote, config.repo)
else:
    repo = Repo(config.repo)

if not Path(config.secret_file).exists():
    Path(config.secret_file).write_bytes(secrets.token_bytes(16))

secret = Path(config.secret_file).read_bytes()


def gen_token(secret, id: str):
    m = hashlib.sha256()
    m.update(secret)
    m.update(str.encode('utf-8'))
    return f"{id}-{m.hexdigest()}"


update_hook = f'/{gen_token(secret, "update")}'
print("update endpoint:", update_hook)


def local_redirect(loc):
    redir = redirect(loc)
    redir.headers['location'] = loc
    redir.autocorrect_location_header = False
    return redir

def branch_ref():
    return f"refs/remotes/origin/{config.branch}"

@app.route('/')
def root_latest_redirect():
    return local_redirect('commit/latest')

@app.route('/commit/<wanted_commit>/')
@app.route('/commit/<wanted_commit>/<path:subpath>')
def return_versioned_path(wanted_commit, subpath=None):
    with lock:
        if wanted_commit == "latest":
            commit = next(repo.iter_commits(branch_ref()))
        else:
            commit = repo.commit(wanted_commit)

        data = commit.tree
        if subpath is not None:
            try:
                data = data[subpath]
            except KeyError:
                abort(404)
        elif config.root_file is not None:
            if config.root_file in data:
                return local_redirect(f"{config.root_file}")
        if data.type == "blob":
            mimetype = guess_type(subpath)[0]
            if mimetype is None:
                mimetype = "text/plain;charset=UTF-8"
            return Response(data.data_stream.read(), mimetype=mimetype)
        elif config:
            return '<br />'.join(f"<a href={entry.path}>{entry.path}</a>" for entry in data)


@app.route('/commit/')
def return_commit_list():
    with lock:
        return "<br />".join(f"<a href={commit}><tt>{commit}</tt> {commit.message}</a>" for commit in repo.iter_commits(branch_ref()))


@app.route(update_hook)
def update_repo():
    with lock:
        repo.remotes.origin.fetch()
        repo.head.reference = repo.remotes.origin.refs[config.branch]
        repo.head.reset(index=True, working_tree=True)
    return "Ok"
