# -*- coding: utf-8 -*-
"""通过 GitHub Git Data API 推送本地提交。

为什么不用 git push：
  - git@github.com 的公钥还没绑到 jidixueqiao 账号（Permission denied publickey）
  - github.com:443 在本机被封，只有 ghproxy.net 这类第三方镜像能通
    —— 而把 OAuth 令牌交给第三方镜像等于泄露令牌
  - api.github.com 本机可直连，所以走 GitHub 官方 API 推，token 只到 GitHub 自己

做法是复刻 git 的对象模型：先建 blob，再建 tree，再建 commit，最后更新 ref。
提交元数据（树/父/作者/时间/消息）与本地 HEAD 完全一致，
因此服务端生成的 commit sha 应与本地一致，本地仓库无需 rebase。
"""
import base64
import datetime
import json
import os
import subprocess
import sys
import urllib.request

REPO = "jidixueqiao/jidixueqiao"
API = "https://api.github.com"


def git(*args, binary=False):
    p = subprocess.run(["git", *args], cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       capture_output=True, check=True)
    return p.stdout if binary else p.stdout.decode("utf-8")


def token():
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    p = subprocess.run(["git", "credential", "fill"],
                       input=b"protocol=https\nhost=github.com\n\n",
                       capture_output=True, env=env)
    for line in p.stdout.decode("utf-8", "replace").splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("凭据管理器里没有 github.com 的凭据")


TOK = token()


def api(method, path, payload=None):
    url = path if path.startswith("http") else f"{API}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {TOK}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "dsh-push")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        raise SystemExit(f"{method} {path} -> HTTP {e.code}\n{detail}")


def parse_commit(raw):
    """解析原始 commit 对象：头部字段 + 原始消息字节。"""
    head, _, message = raw.partition(b"\n\n")
    meta = {}
    for line in head.decode("utf-8").splitlines():
        k, _, v = line.partition(" ")
        if k in ("tree", "parent"):
            meta.setdefault(k, []).append(v)
        elif k in ("author", "committer"):
            # 格式：Name <email> <unix_ts> <tz>
            name, _, rest = v.partition(" <")
            email, _, rest = rest.partition("> ")
            ts, _, tz = rest.partition(" ")
            meta[k] = {
                "name": name,
                "email": email,
                "ts": int(ts),
                "tz": tz,
            }
    return meta, message


def iso(ts, tz):
    sign = 1 if tz[0] == "+" else -1
    hh, mm = int(tz[1:3]), int(tz[3:5])
    delta = datetime.timedelta(hours=hh, minutes=mm) * sign
    dt = datetime.datetime.fromtimestamp(ts, datetime.timezone(delta))
    return dt.isoformat()


def main():
    raw = git("cat-file", "commit", "HEAD", binary=True)
    meta, message = parse_commit(raw)
    local_commit = git("rev-parse", "HEAD").strip()
    local_tree = meta["tree"][0]
    parent = meta["parent"][0]
    print(f"本地提交 {local_commit}")
    print(f"  tree   {local_tree}")
    print(f"  parent {parent}")
    print(f"  author {meta['author']['name']} <{meta['author']['email']}> {iso(meta['author']['ts'], meta['author']['tz'])}")

    # 远端当前状态
    ref = api("GET", f"/repos/{REPO}/git/ref/heads/main")
    remote_commit = ref["object"]["sha"]
    print(f"\n远端 main 当前为 {remote_commit}")
    if remote_commit != parent:
        raise SystemExit(f"远端与本地父提交不一致（{remote_commit} != {parent}），先处理分歧")

    # 1) 上传 blob
    entries = []
    for line in git("ls-files", "-s").splitlines():
        mode, sha, stage, path = line.split(None, 3)
        if stage != "0":
            continue
        content = git("cat-file", "blob", sha, binary=True)
        got = api("POST", f"/repos/{REPO}/git/blobs",
                  {"content": base64.b64encode(content).decode("ascii"), "encoding": "base64"})
        if got["sha"] != sha:
            raise SystemExit(f"blob sha 不一致 {path}: 服务端 {got['sha']} 本地 {sha}")
        entries.append({"path": path, "mode": mode, "type": "blob", "sha": sha})
        print(f"  blob ok {sha[:8]}  {path}")

    # 2) 建 tree
    parent_tree = api("GET", f"/repos/{REPO}/git/commits/{parent}")["tree"]["sha"]
    tree = api("POST", f"/repos/{REPO}/git/trees",
               {"base_tree": parent_tree, "tree": entries})
    print(f"\n新 tree {tree['sha']}  (本地 {local_tree})")
    if tree["sha"] != local_tree:
        raise SystemExit(f"tree sha 不一致：服务端 {tree['sha']} 本地 {local_tree}")

    # 3) 建 commit
    commit = api("POST", f"/repos/{REPO}/git/commits", {
        "message": message.decode("utf-8"),
        "tree": tree["sha"],
        "parents": [parent],
        "author": {
            "name": meta["author"]["name"],
            "email": meta["author"]["email"],
            "date": iso(meta["author"]["ts"], meta["author"]["tz"]),
        },
        "committer": {
            "name": meta["committer"]["name"],
            "email": meta["committer"]["email"],
            "date": iso(meta["committer"]["ts"], meta["committer"]["tz"]),
        },
    })
    print(f"新 commit {commit['sha']}  (本地 {local_commit})")
    if commit["sha"] != local_commit:
        print("  ! sha 与本地不同，远端已接受，稍后把本地重置到远端即可")

    # 4) 更新 ref
    api("PATCH", f"/repos/{REPO}/git/refs/heads/main",
        {"sha": commit["sha"], "force": False})
    print("\n已更新 refs/heads/main -> " + commit["sha"])


if __name__ == "__main__":
    main()
