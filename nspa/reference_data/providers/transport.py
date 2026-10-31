"""Bounded, certificate-verified network access with cooperative cancellation."""

import socket
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

from ..models import ReferenceError, check_cancel


def fetch(url, data=None, *, mode="direct", cancel=None, headers=None):
    if mode not in {"direct", "system"}:
        raise ReferenceError("未知网络连接方式。")
    client = build_opener(ProxyHandler({} if mode == "direct" else None),
                          HTTPSHandler(context=ssl.create_default_context()))
    request = Request(url, data=data, headers={"User-Agent": "Mozilla/5.0", **(headers or {})})
    for attempt in range(2):
        check_cancel(cancel)
        try:
            with client.open(request, timeout=20) as response:
                if response.status != 200 or not response.url.startswith("https://"):
                    raise ReferenceError(f"服务返回异常状态：{response.status}")
                chunks, size = [], 0
                while True:
                    check_cancel(cancel)
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > 30_000_000:
                        raise ReferenceError("下载超过 30 MB，请缩小时间或天区范围。")
                    chunks.append(chunk)
                return b"".join(chunks), response.headers.get_content_charset() or "utf-8"
        except HTTPError as exc:
            if exc.code < 500 or attempt:
                raise ReferenceError(f"参考数据服务返回 HTTP {exc.code}") from exc
        except (URLError, TimeoutError, socket.timeout, OSError) as exc:
            if attempt:
                raise ReferenceError(f"参考数据下载失败：{exc}；可切换直连/系统代理后重试。") from exc
        if cancel is not None and cancel.wait(0.5):
            check_cancel(cancel)
    raise ReferenceError("参考数据服务暂不可用。")
