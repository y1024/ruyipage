# -*- coding: utf-8 -*-
"""NetworkManager - network 模块高层管理器。"""

from .._bidi import network as bidi_network


class NetworkData(object):
    """单次 network.getData 结果对象。

    Args:
        data: ``network.getData`` 原始返回字典。

    Returns:
        NetworkData: 支持属性访问的数据对象。

    适用场景：
        - 让编辑器可以跳转和补全结果字段
        - 在示例中避免反复写 ``result.get(...)``
    """

    def __init__(self, data):
        self.raw = dict(data or {})
        self.bytes = self.raw.get("bytes")
        self.base64 = self.raw.get("base64")

    @property
    def has_data(self):
        """是否拿到了可用网络数据。"""
        return self.bytes is not None or self.base64 is not None


class DataCollector(object):
    """网络数据收集器句柄。

    这是 ``network.addDataCollector`` 的高层结果对象。

    你可以把它理解为“服务器返回数据的临时托管器”。
    浏览器把命中的网络数据交给 collector 保留，然后你可以用：
    - ``get()`` 读取
    - ``disown()`` 释放
    - ``remove()`` 删除整个 collector
    """

    def __init__(self, manager, collector_id):
        self._manager = manager
        self.id = collector_id

    def get(self, request_id, data_type="response"):
        """获取收集器持有的数据。

        Args:
            request_id: 请求 ID。
                常见值：拦截到的 ``InterceptedRequest.request_id``。
            data_type: 数据类型。
                常见值：``'request'``、``'response'``。

        Returns:
            NetworkData: 支持属性访问的结果对象。
        """
        return self._manager.get_data(self.id, request_id, data_type=data_type)

    def disown(self, request_id, data_type="response"):
        """释放已收集的数据。"""
        return self._manager.disown_data(self.id, request_id, data_type=data_type)

    def remove(self):
        """移除当前收集器。"""
        return self._manager.remove_data_collector(self.id)


class NetworkManager(object):
    """network 模块高层管理器。

    主要解决四类问题：
    1. 设置额外请求头
    2. 设置缓存行为
    3. 创建和管理 data collector
    4. 让示例不再直接碰 ``_bidi.network`` 与 ``page._driver``
    """

    def __init__(self, owner):
        self._owner = owner

    def _ctx(self):
        return [self._owner.tab_id]

    def set_extra_headers(self, headers):
        """设置额外请求头。

        Args:
            headers: 请求头字典。
                常见值：``{'X-Test': 'yes'}``。

        Returns:
            owner: 原页面对象，便于链式调用。

        适用场景：
            - 为当前页面所有后续请求附加自定义请求头
            - 配合拦截或 data collector 验证头部是否真实发出
        """
        bidi_headers = []
        for name, value in headers.items():
            bidi_headers.append(
                {"name": name, "value": {"type": "string", "value": str(value)}}
            )
        bidi_network.set_extra_headers(
            self._owner._driver,
            headers=bidi_headers,
            contexts=self._ctx(),
        )
        return self._owner

    def clear_extra_headers(self):
        """清空当前页面的额外请求头。"""
        bidi_network.set_extra_headers(
            self._owner._driver, headers=[], contexts=self._ctx()
        )
        return self._owner

    def set_cache_behavior(self, behavior="default"):
        """设置缓存行为。

        Args:
            behavior: 缓存策略。
                常见值：
                ``'default'`` 表示使用浏览器默认缓存策略，命中缓存时可能不再发起真实网络请求；
                ``'bypass'`` 表示尽量绕过缓存，强制重新向服务器请求资源。

        Returns:
            owner: 原页面对象，便于链式调用。

        适用场景：
            - 验证是否真的发起了新的网络请求
            - 在网络测试中减少缓存干扰
            - 配合 data collector 或 response 监听，避免因缓存命中导致没有网络事件
        """
        bidi_network.set_cache_behavior(
            self._owner._driver,
            behavior=behavior,
            contexts=self._ctx(),
        )
        return self._owner

    def add_data_collector(
        self, events, *, data_types=None, max_encoded_data_size=10485760
    ):
        """注册网络数据收集器。

        Args:
            events: 收集阶段列表。
                常见值：
                ``['beforeRequestSent']`` 表示在请求发出阶段收集数据；
                ``['responseCompleted']`` 表示在响应完成阶段收集数据。
            data_types: 数据类型列表。
                常见值：
                ``['request']`` 表示只保留请求体数据；
                ``['response']`` 表示只保留响应体数据；
                ``['request', 'response']`` 表示两者都保留。
            max_encoded_data_size: 最大编码数据大小。
                单位：字节。
                常见值：``10485760`` 表示 10 MB。

        Returns:
            DataCollector: 收集器高层对象，包含 ``id/get/disown/remove``。

        适用场景：
            - 采集请求体或响应体
            - 结合 request id 验证 ``network.getData`` / ``disownData``
            - 验证浏览器是否真的把命中的网络数据交给 collector 保存了
        """
        result = bidi_network.add_data_collector(
            self._owner._driver,
            events=events,
            contexts=self._ctx(),
            max_encoded_data_size=max_encoded_data_size,
            data_types=data_types,
        )
        return DataCollector(self, result.get("collector"))

    def remove_data_collector(self, collector_id):
        """移除数据收集器。"""
        bidi_network.remove_data_collector(self._owner._driver, collector_id)
        return self._owner

    def get_data(self, collector_id, request_id, data_type="response"):
        """获取收集器持有的数据。

        Args:
            collector_id: 收集器 ID。
                常见值：``page.network.add_data_collector(...).id``。
            request_id: 请求 ID。
                常见值：拦截到的 ``InterceptedRequest.request_id``。
            data_type: 数据类型。
                常见值：
                ``'request'`` 表示读取该请求对应的请求体；
                ``'response'`` 表示读取该请求对应的响应体。

        Returns:
            NetworkData: 支持属性访问的网络数据结果对象。

        适用场景：
            - 读取 collector 收集到的请求体或响应体
            - 验证 collector 与 request id 是否真正关联成功
            - 在请求已完成后取回真实网络数据用于断言
        """
        result = bidi_network.get_data(
            self._owner._driver,
            collector_id,
            request_id,
            data_type=data_type,
        )
        return NetworkData(result)

    def disown_data(self, collector_id, request_id, data_type="response"):
        """释放收集器持有的数据。

        Args:
            collector_id: 收集器 ID。
            request_id: 请求 ID。
            data_type: 数据类型。
                常见值：
                ``'request'`` 表示释放该请求对应的请求体数据；
                ``'response'`` 表示释放该请求对应的响应体数据。

        Returns:
            dict: BiDi 命令返回结果，通常为空字典。

        适用场景：
            - collector 数据已用完后主动释放内存
            - 测试 ``network.disownData`` 的生命周期行为
        """
        return bidi_network.disown_data(
            self._owner._driver,
            collector_id,
            request_id,
            data_type=data_type,
        )
