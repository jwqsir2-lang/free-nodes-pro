# -*- coding: utf-8 -*-
"""mihomo 内核管理：自动查找 / 引导下载，保证双击即用。"""

import io
import json
import os
import stat
import subprocess
import sys
import urllib.request
import zipfile

MIHOMO_VERSION = "v1.19.31"
WIN_URL = (f"https://github.com/MetaCubeX/mihomo/releases/download/"
           f"{MIHOMO_VERSION}/mihomo-windows-amd64-{MIHOMO_VERSION}.zip")
LINUX_URL = (f"https://github.com/MetaCubeX/mihomo/releases/download/"
             f"{MIHOMO_VERSION}/mihomo-linux-amd64-{MIHOMO_VERSION}.gz")
# 兼容老 CPU 的备用包（GitHub Actions runner 用现代 CPU，主包够用）
LINUX_URL_COMPAT = (f"https://github.com/MetaCubeX/mihomo/releases/download/"
                    f"{MIHOMO_VERSION}/mihomo-linux-amd64-compatible-{MIHOMO_VERSION}.gz")

_EXE = "mihomo.exe" if os.name == "nt" else "mihomo"


def kernel_dir():
    """内核存放目录：跟用户数据放一起，不需要管理员权限。"""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "FreeNodesPro", "kernel")


def find_kernel():
    """返回可用的 mihomo 可执行路径，找不到返回 None。"""
    d = kernel_dir()
    p = os.path.join(d, _EXE)
    if os.path.isfile(p):
        return p
    # PyInstaller 单文件包：内核被 --add-data 打进了 kernel/ 目录
    try:
        base = sys._MEIPASS  # PyInstaller 解包临时目录
        p2 = os.path.join(base, "kernel", _EXE)
        if os.path.isfile(p2):
            return p2
    except AttributeError:
        pass
    # 开发环境：项目内
    for cand in (os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "mihomo-bin", _EXE),
                 os.path.join(os.path.dirname(os.path.abspath(__file__)), _EXE),
                 os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "kernel", _EXE)):
        if os.path.isfile(cand):
            return cand
    return None


def download_kernel(on_progress=None):
    """下载并解压内核（Windows 下 zip 包，Linux 下 gzip 单文件）。失败抛异常。"""
    import gzip
    import shutil
    import urllib.request as ur
    d = kernel_dir()
    os.makedirs(d, exist_ok=True)
    dest = os.path.join(d, _EXE)
    is_win = os.name == "nt"
    tmp = os.path.join(d, "mihomo.zip" if is_win else "mihomo.gz")
    url = WIN_URL if is_win else LINUX_URL
    req = ur.Request(url, headers={"User-Agent": "FreeNodesPro/1.0"})
    try:
        r = ur.urlopen(req, timeout=60)
    except Exception:
        if is_win:
            raise
        # Linux 主包偶尔在老内核上跑不动，退到兼容包
        r = ur.urlopen(ur.Request(LINUX_URL_COMPAT,
                                  headers={"User-Agent": "FreeNodesPro/1.0"}),
                       timeout=60)
    with r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            chunk = r.read(1 << 18)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if on_progress:
                on_progress(got, total)
    if is_win:
        with zipfile.ZipFile(tmp) as z:
            for n in z.namelist():
                if n.lower().endswith(_EXE) or n.lower().endswith(".exe"):
                    with z.open(n) as src, open(dest, "wb") as out:
                        shutil.copyfileobj(src, out)
                    break
    else:
        # Linux 发布物是 gzip 压缩的单个可执行文件
        with gzip.open(tmp, "rb") as src, open(dest, "wb") as out:
            shutil.copyfileobj(src, out)
    try:
        os.chmod(dest, os.stat(dest).st_mode | stat.S_IEXEC)
    except Exception:
        pass
    os.remove(tmp)
    if not os.path.isfile(dest):
        raise RuntimeError("压缩包里没有找到 mihomo 可执行文件")
    return dest


def version(p=None):
    p = p or find_kernel()
    if not p:
        return ""
    try:
        r = subprocess.run([p, "-v"], capture_output=True, text=True, timeout=15,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0)
        return (r.stdout or r.stderr).split("\n")[0].strip()
    except Exception:
        return ""
