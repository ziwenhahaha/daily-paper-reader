"""显式构建既有分支型 Pages；不创建站点、不改变用户发布配置。"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import time

import requests


def request_build(api, repository, branch, commit, *, timeout=600, sleep=time.sleep):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("非法 GitHub 仓库名")
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("Pages 验证需要完整提交 SHA")
    base = "/repos/" + repository
    site = api("GET", base + "/pages")
    if site.get("build_type") != "legacy":
        raise RuntimeError(
            "现有 Pages 不是分支构建模式，未修改配置；需要为该仓库接入独立 Pages 部署步骤"
        )
    source = site.get("source") or {}
    if source.get("branch") != branch or source.get("path") != "/":
        raise RuntimeError(
            "当前分支或站点根目录与 Pages 发布源不一致，未请求错误目标的构建"
        )
    repo = api("GET", base)
    if repo.get("default_branch") != branch:
        raise RuntimeError("Pages REST 构建要求默认分支，当前分支不匹配；未改变配置")
    api("POST", base + "/pages/builds")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        build = api("GET", base + "/pages/builds/latest")
        # POST 仅返回 latest 地址，旧版本构建完成不等于本次提交已发布。
        if build.get("commit") == commit:
            status = build.get("status")
            if status == "built":
                print(f"Pages 构建已完成，提交 {commit[:12]}", flush=True)
                return build
            if status in {"errored", "failed", "cancelled"}:
                raise RuntimeError(
                    "本次提交的 Pages 构建失败，请查看仓库 Pages 构建日志"
                )
        print("等待 Pages 构建本次提交……", flush=True)
        sleep(min(10, max(0, deadline - time.monotonic())))
    raise TimeoutError("等待 Pages 本次提交构建超时；代码已推送，但未确认线上更新")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    token = os.getenv("GITHUB_TOKEN") or ""
    if not token:
        raise RuntimeError("缺少 GitHub Pages 构建凭据")
    session = requests.Session()
    session.headers.update(
        {
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
        }
    )

    def api(method, path):
        # 固定官方API域名，不向响应返回的URL转发凭据，也不输出响应正文。
        response = session.request(
            method, "https://api.github.com" + path, timeout=30, allow_redirects=False
        )
        if not 200 <= response.status_code < 300:
            raise RuntimeError(
                f"GitHub Pages API 返回 HTTP {response.status_code}；请检查 Pages 权限或站点状态"
            )
        return response.json()

    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    request_build(
        api,
        os.getenv("GITHUB_REPOSITORY", ""),
        os.getenv("GITHUB_REF_NAME", ""),
        commit,
        timeout=args.timeout,
    )


if __name__ == "__main__":
    main()
