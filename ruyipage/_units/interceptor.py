# -*- coding: utf-8 -*-
"""Interceptor - 网络请求拦截器

通过 BiDi network.addIntercept 实现请求拦截、修改、Mock。
"""

import time
import threading
from queue import Queue, Empty
from typing import Dict, Optional, List

from .._bidi import network as bidi_network
from .._bidi import session as bidi_session

import logging

logger = logging.getLogger("ruyipage")


class InterceptedRequest(object):
    """被拦截的请求对象。

    这是 network 拦截阶段暴露给用户的高层请求对象。

    你通常会在两类场景里接触它：
    1. ``req = page.intercept.wait()`` 后手动处理
    2. ``page.intercept.start(handler=...)`` 回调里自动处理

    常用属性：
        - ``request_id``: 当前请求的唯一 ID，可用于和 data collector 关联
        - ``url``: 请求 URL
        - ``method``: 请求方法，如 ``GET`` / ``POST``
        - ``headers``: 请求头字典，便于直接判断某个头是否已注入

    常用方法：
        - ``continue_request()`` 放行请求，可选修改 URL、方法、头、体
        - ``continue_with_auth()`` 处理 HTTP Basic/Digest 等认证挑战
        - ``fail()`` 直接中止请求
        - ``continue_response()`` 放行响应并可修改状态码/头
        - ``mock()`` 直接返回一份模拟响应
    """

    def __init__(self, params, driver):
        self._driver = driver
        self._params = params
        self._request = params.get("request", {})
        self._handled = False

        self.request_id: str = self._request.get("request", "")
        self.url: str = self._request.get("url", "")
        self.method: str = self._request.get("method", "")
        self.headers: Dict[str, str] = {
            h["name"]: h["value"].get("value", "")
            if isinstance(h.get("value"), dict)
            else str(h.get("value", ""))
            for h in self._request.get("headers", [])
        }
        self.phase: Optional[str] = (
            params.get("intercepts", [None])[0] if params.get("intercepts") else None
        )

    @property
    def handled(self):
        """当前请求是否已经被处理过。

        Returns:
            bool: ``True`` 表示已经执行过 continue/fail/mock 之一，不能再次处理。
        """
        return self._handled

    def continue_request(
        self,
        url: Optional[str] = None,
        method: Optional[str] = None,
        headers: Optional[List[dict]] = None,
        body=None,
    ):
        """继续请求，并可选修改请求参数。

        Args:
            url: 替换后的目标 URL。
                常见值：另一个接口地址。传 ``None`` 表示保持原 URL。
            method: 替换后的请求方法。
                常见值：``'GET'``、``'POST'``。传 ``None`` 表示保持原方法。
            headers: 替换后的请求头列表。
                常见值：BiDi header 结构列表，例如
                ``[{'name': 'X-Test', 'value': {'type': 'string', 'value': 'yes'}}]``。
                传 ``None`` 表示保持原请求头。
            body: 替换后的请求体。
                常见值：BiDi bytes value 结构。传 ``None`` 表示保持原请求体。

        Returns:
            None: 该方法直接向浏览器发送 continue 命令。

        适用场景：
            - 只想放行当前请求
            - 放行前顺手改 URL、Method、Headers、Body
        """
        if self._handled:
            return
        self._handled = True
        bidi_network.continue_request(
            self._driver,
            self.request_id,
            url=url,
            method=method,
            headers=headers,
            body=body,
        )

    def fail(self):
        """中止请求。

        Returns:
            None: 该方法直接向浏览器发送 fail 命令。

        适用场景：
            - 测试接口失败场景
            - 主动阻止某类请求继续发出
        """
        if self._handled:
            return
        self._handled = True
        bidi_network.fail_request(self._driver, self.request_id)

    def continue_with_auth(self, action="default", username=None, password=None):
        """处理 HTTP 认证挑战。

        Args:
            action: 认证处理动作。
                常见值：
                ``'default'`` 表示交给浏览器默认处理；
                ``'cancel'`` 表示取消认证；
                ``'provideCredentials'`` 表示显式提供用户名密码。
            username: 用户名。
                当 ``action='provideCredentials'`` 时使用。
            password: 密码。
                当 ``action='provideCredentials'`` 时使用。

        Returns:
            None: 该方法直接向浏览器发送 ``network.continueWithAuth`` 命令。

        适用场景：
            - 处理 ``network.authRequired`` 事件
            - 在示例或测试中验证 Basic Auth / Digest Auth 行为
        """
        if self._handled:
            return
        self._handled = True

        credentials = None
        if action == "provideCredentials":
            credentials = {
                "type": "password",
                "username": username or "",
                "password": password or "",
            }

        bidi_network.continue_with_auth(
            self._driver,
            self.request_id,
            action=action,
            credentials=credentials,
        )

    def continue_response(
        self,
        headers: Optional[List[dict]] = None,
        reason_phrase: Optional[str] = None,
        status_code: Optional[int] = None,
    ):
        """继续被拦截的响应（可修改状态码/头）。

        Args:
            headers: 替换后的响应头列表。
            reason_phrase: 替换后的状态文本。
                常见值：``'OK'``、``'Created'``、``'Forbidden'``。
            status_code: 替换后的 HTTP 状态码。
                常见值：``200``、``201``、``403``、``500``。

        适用阶段：
            仅在 phases 包含 responseStarted 时可用。
        """
        if self._handled:
            return
        self._handled = True
        bidi_network.continue_response(
            self._driver,
            self.request_id,
            headers=headers,
            reason_phrase=reason_phrase,
            status_code=status_code,
        )

    def mock(
        self,
        body="",
        status_code: int = 200,
        headers: Optional[List[dict]] = None,
        reason_phrase: str = "OK",
    ):
        """直接返回一份模拟响应。

        Args:
            body: 响应体内容。
                常见值：字符串、bytes。
            status_code: HTTP 状态码。
                常见值：``200``、``201``、``404``、``500``。
            headers: 响应头列表。
                传 ``None`` 时默认返回 ``content-type: text/plain``。
            reason_phrase: HTTP 状态文本。
                常见值：``'OK'``、``'Created'``、``'Not Found'``。

        Returns:
            None: 该方法直接向浏览器发送 mock response 命令。

        适用场景：
            - 不访问真实后端，直接 Mock 响应
            - 验证前端对不同状态码和响应体的处理
        """
        if self._handled:
            return
        self._handled = True
        import base64

        if isinstance(body, str):
            body_bytes = body.encode("utf-8")
        else:
            body_bytes = body
        encoded = base64.b64encode(body_bytes).decode("ascii")
        resp_headers = headers or [
            {"name": "content-type", "value": {"type": "string", "value": "text/plain"}}
        ]
        bidi_network.provide_response(
            self._driver,
            self.request_id,
            body={"type": "base64", "value": encoded},
            headers=resp_headers,
            status_code=status_code,
            reason_phrase=reason_phrase,
        )

    def __repr__(self):
        return "<InterceptedRequest {} {}>".format(self.method, self.url[:60])


class Interceptor(object):
    """网络拦截管理器

    用法::

        # 拦截并修改请求
        with page.intercept.on('api/data') as req:
            req.continue_request(headers=[...])

        # 回调模式
        def handler(req):
            if 'api' in req.url:
                req.mock('{"mocked": true}', status_code=200)
            else:
                req.continue_request()

        page.intercept.start(handler, phases=['beforeRequestSent'])
        page.get('https://example.com')
        page.intercept.stop()
    """

    def __init__(self, owner):
        self._owner = owner
        self._active = False
        self._intercept_id = None
        self._subscription_id = None
        self._handler = None
        self._queue = Queue()

    @property
    def active(self):
        return self._active

    def start(self, handler=None, url_patterns=None, phases=None):
        """开始拦截

        Args:
            handler: 回调函数 handler(InterceptedRequest)，None 则入队等待手动处理
            url_patterns: URL 模式列表，None 拦截所有
                [{'type': 'string', 'pattern': 'api/'}] 或
                [{'type': 'pattern', 'pathname': '/api/*'}]
            phases: 拦截阶段列表，默认 ['beforeRequestSent']
        """
        if self._active:
            self.stop()

        if phases is None:
            phases = ["beforeRequestSent"]

        self._handler = handler
        self._queue = Queue()

        # 注册拦截
        result = bidi_network.add_intercept(
            self._owner._driver._browser_driver,
            phases=phases,
            url_patterns=url_patterns,
            contexts=[self._owner._context_id],
        )
        self._intercept_id = result.get("intercept")

        # 订阅事件
        events = []
        if "beforeRequestSent" in phases:
            events.append("network.beforeRequestSent")
        if "responseStarted" in phases:
            events.append("network.responseStarted")
        if "authRequired" in phases:
            events.append("network.authRequired")

        if events:
            sub = bidi_session.subscribe(
                self._owner._driver._browser_driver,
                events,
                contexts=[self._owner._context_id],
            )
            self._subscription_id = sub.get("subscription")

        drv = self._owner._driver
        if "beforeRequestSent" in phases:
            drv.set_global_callback("network.beforeRequestSent", self._on_intercept)
        if "responseStarted" in phases:
            drv.set_global_callback("network.responseStarted", self._on_intercept)
        if "authRequired" in phases:
            drv.set_global_callback("network.authRequired", self._on_auth)

        self._active = True
        return self

    def start_requests(self, handler=None, url_patterns=None):
        """新手友好：仅拦截请求阶段。

        等价于 start(..., phases=['beforeRequestSent'])。
        """
        return self.start(
            handler=handler, url_patterns=url_patterns, phases=["beforeRequestSent"]
        )

    def start_responses(self, handler=None, url_patterns=None):
        """新手友好：仅拦截响应阶段。

        等价于 start(..., phases=['responseStarted'])。
        """
        return self.start(
            handler=handler, url_patterns=url_patterns, phases=["responseStarted"]
        )

    def stop(self):
        """停止拦截"""
        if not self._active:
            return
        self._active = False

        if self._intercept_id:
            try:
                bidi_network.remove_intercept(
                    self._owner._driver._browser_driver, self._intercept_id
                )
            except Exception:
                pass
            self._intercept_id = None

        if self._subscription_id:
            try:
                bidi_session.unsubscribe(
                    self._owner._driver._browser_driver,
                    subscription=self._subscription_id,
                )
            except Exception:
                pass
            self._subscription_id = None

        drv = self._owner._driver
        for ev in (
            "network.beforeRequestSent",
            "network.responseStarted",
            "network.authRequired",
        ):
            drv.remove_callback(ev)

        return self

    def wait(self, timeout=10):
        """等待下一个被拦截的请求

        Returns:
            InterceptedRequest 或 None
        """
        try:
            return self._queue.get(timeout=timeout)
        except Empty:
            return None

    def _on_intercept(self, params):
        if not self._active:
            return
        req = InterceptedRequest(params, self._owner._driver._browser_driver)
        if self._handler:
            try:
                self._handler(req)
            except Exception as e:
                logger.warning("拦截回调异常: %s", e)
            if not req.handled:
                req.continue_request()
        else:
            self._queue.put(req)

    def _on_auth(self, params):
        if not self._active:
            return
        req = InterceptedRequest(params, self._owner._driver._browser_driver)
        if self._handler:
            try:
                self._handler(req)
            except Exception as e:
                logger.warning("认证拦截回调异常: %s", e)
            if not req.handled:
                bidi_network.continue_with_auth(
                    self._owner._driver._browser_driver,
                    req.request_id,
                    action="default",
                )
        else:
            self._queue.put(req)
