#!/usr/bin/env python

from public_conference import run_public_conference_maintain


if __name__ == "__main__":
    run_public_conference_maintain("sosp", description="维护入口：SOSP 抓取 + Supabase 同步。")
