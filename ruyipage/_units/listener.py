# -*- coding: utf-8 -*-
"""Listener - 网络事件捕获

通过 BiDi network 模块事件监听网络请求/响应。
"""

import re
import time
import logging
import threading
from queue import Queue, Empty

from .._bidi import session as bidi_session

logger = logging.getLogger('ruyipage')


class DataPacket(object):
    """网络数据包"""

    def __init__(self, request=None, response=None, event_type='',
                 url='', method='', status=0, headers=None, body=None,
                 timestamp=0):
        self.request = request or {}
        self.response = response or {}
        self.event_type = event_type
        self.url = url
        self.method = method
        self.status = status
        self.headers = headers or {}
        self.body = body
        self.timestamp = timestamp

    @property
    def is_failed(self):
        return self.event_type == 'fetchError'

    def __repr__(self):
        return '<DataPacket {} {} {}>'.format(self.method, self.status, self.url[:60])


class Listener(object):
    """网络监听管理器

    用法::

        page.listen.start('api/data')
        page.ele('#load').click()
        packet = page.listen.wait(timeout=10)
        print(packet.url, packet.status)

        page.listen.stop()
    """

    def __init__(self, owner):
        self._owner = owner
        self._listening = False
        self._targets = None  # True=全部, set=URL模式匹配
        self._is_regex = False
        self._method_filter = None
        self._caught = Queue()
        self._packets = []
        self._subscription_id = None
        self._subscribed_events = []

    @property
    def listening(self):
        return self._listening

    @property
    def steps(self):
        """已捕获的所有数据包"""
        self._drain_queue()
        return self._packets[:]

    def start(self, targets=True, is_regex=False, method=None):
        """开始监听

        Args:
            targets: True 监听所有, str 匹配URL, list 多个URL模式
            is_regex: URL 模式是否是正则
            method: HTTP 方法过滤 ('GET', 'POST', 等)
        """
        if self._listening:
            self.stop()

        self._is_regex = is_regex
        self._method_filter = method.upper() if method else None

        if targets is True:
            self._targets = True
        elif isinstance(targets, str):
            self._targets = {targets}
        elif isinstance(targets, (list, tuple)):
            self._targets = set(targets)
        else:
            self._targets = True

        self._caught = Queue()
        self._packets = []

        # 订阅网络事件
        events = [
            'network.beforeRequestSent',
            'network.responseCompleted',
            'network.fetchError',
        ]

        try:
            result = bidi_session.subscribe(
                self._owner._driver._browser_driver,
                events,
                contexts=[self._owner._context_id]
            )
            self._subscription_id = result.get('subscription')
            self._subscribed_events = events
        except Exception as e:
            logger.warning('订阅网络事件失败: %s', e)
            return

        # 注册回调
        driver = self._owner._driver
        driver.set_callback('network.responseCompleted', self._on_response)
        driver.set_callback('network.fetchError', self._on_fetch_error)

        self._listening = True
        logger.debug('开始监听网络事件')

    def stop(self):
        """停止监听"""
        if not self._listening:
            return

        self._listening = False

        # 取消订阅
        if self._subscription_id:
            try:
                bidi_session.unsubscribe(
                    self._owner._driver._browser_driver,
                    subscription=self._subscription_id
                )
            except Exception:
                pass
            self._subscription_id = None

        # 移除回调
        driver = self._owner._driver
        driver.remove_callback('network.responseCompleted')
        driver.remove_callback('network.fetchError')

        logger.debug('停止监听网络事件')

    def wait(self, timeout=None, count=1):
        """等待捕获数据包

        Args:
            timeout: 超时时间（秒）
            count: 等待的数据包数量

        Returns:
            DataPacket（count=1时）或 list（count>1时）
        """
        if timeout is None:
            from .._functions.settings import Settings
            timeout = Settings.bidi_timeout

        end_time = time.time() + timeout
        results = []

        while len(results) < count:
            remaining = end_time - time.time()
            if remaining <= 0:
                break

            try:
                packet = self._caught.get(timeout=min(remaining, 0.5))
                results.append(packet)
            except Empty:
                continue

        if count == 1:
            return results[0] if results else None
        return results

    def clear(self):
        """清空已捕获的数据包"""
        while not self._caught.empty():
            try:
                self._caught.get_nowait()
            except Empty:
                break
        self._packets.clear()

    def _on_response(self, params):
        """处理响应完成事件"""
        if not self._listening:
            return

        request = params.get('request', {})
        response = params.get('response', {})
        url = request.get('url', '')
        method = request.get('method', '')

        if not self._match(url, method):
            return

        headers = {}
        for h in response.get('headers', []):
            name = h.get('name', '')
            value_obj = h.get('value', {})
            value = value_obj.get('value', '') if isinstance(value_obj, dict) else str(value_obj)
            headers[name.lower()] = value

        packet = DataPacket(
            request=request,
            response=response,
            event_type='responseCompleted',
            url=url,
            method=method,
            status=response.get('status', 0),
            headers=headers,
            timestamp=params.get('timestamp', 0),
        )

        self._caught.put(packet)
        self._packets.append(packet)

    def _on_fetch_error(self, params):
        """处理请求失败事件"""
        if not self._listening:
            return

        request = params.get('request', {})
        url = request.get('url', '')
        method = request.get('method', '')

        if not self._match(url, method):
            return

        packet = DataPacket(
            request=request,
            event_type='fetchError',
            url=url,
            method=method,
            timestamp=params.get('timestamp', 0),
        )

        self._caught.put(packet)
        self._packets.append(packet)

    def _match(self, url, method):
        """检查 URL 和方法是否匹配"""
        if self._method_filter and method.upper() != self._method_filter:
            return False

        if self._targets is True:
            return True

        for pattern in self._targets:
            if self._is_regex:
                if re.search(pattern, url):
                    return True
            else:
                if pattern in url:
                    return True

        return False

    def _drain_queue(self):
        """将队列中的数据包转移到列表"""
        while not self._caught.empty():
            try:
                packet = self._caught.get_nowait()
                if packet not in self._packets:
                    self._packets.append(packet)
            except Empty:
                break
