# -*- coding: utf-8 -*-
"""FirefoxBase - 所有页面/标签页/Frame 的共享基类

提供：导航、元素查找、JS 执行、截图、Cookie、弹窗处理等。
"""

import time
import base64
import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING

from .._base.base import BasePage
from .._base.driver import ContextDriver
from .._bidi import browsing_context as bidi_context
from .._bidi import script as bidi_script
from .._functions.bidi_values import parse_value, make_shared_ref
from .._functions.locator import parse_locator
from .._functions.settings import Settings
from ..errors import ElementNotFoundError, JavaScriptError, WaitTimeoutError, BiDiError

logger = logging.getLogger("ruyipage")

if TYPE_CHECKING:
    from .._elements.firefox_element import FirefoxElement
    from .._elements.none_element import NoneElement
    from .._elements.static_element import StaticElement
    from .._units.actions import Actions
    from .._units.browser import BrowserManager
    from .._units.contexts import ContextManager
    from .._units.downloads import DownloadsManager
    from .._units.events import EventTracker
    from .._units.network_tools import NetworkManager
    from .._units.navigation import NavigationTracker
    from .._units.touch_actions import TouchActions
    from .._units.scroller import PageScroller
    from .._units.listener import Listener
    from .._units.interceptor import Interceptor
    from .._units.window import WindowManager
    from .._units.prefs import PrefsManager
    from .._units.realm_tracker import RealmTracker
    from .._units.config_manager import ConfigManager
    from .._units.waiter import PageWaiter
    from .._units.rect import TabRect
    from .._units.states import PageStates
    from .._units.setter import PageSetter
    from .._units.storage import StorageManager
    from .._units.console_listener import ConsoleListener
    from .._units.emulation import EmulationManager
    from .._units.extensions import ExtensionManager
    from .._base.browser import Firefox
    from .._pages.firefox_frame import FirefoxFrame


class FirefoxBase(BasePage):
    """Firefox 页面/标签页/Frame 的共享基类"""

    _type = "FirefoxBase"

    def __init__(self):
        self._browser = None
        self._context_id = None
        self._driver = None  # type: ContextDriver
        self._is_loading = False
        self._ready_state = None
        self._load_mode = "normal"
        self._ua_preload_script_id = None  # 用于 UA override 的 preload script ID

        # 惰性加载的 units
        self._scroll = None
        self._actions = None
        self._touch = None
        self._wait = None
        self._listener = None
        self._rect = None
        self._states = None
        self._setter = None
        self._local_storage = None
        self._session_storage = None
        self._console = None
        self._interceptor = None
        self._network_manager = None
        self._window = None
        self._browser_manager = None
        self._contexts = None
        self._emulation = None
        self._extensions = None
        self._downloads = None
        self._events = None
        self._navigation = None
        self._prefs = None
        self._realms = None
        self._config = None
        self._last_prompt_opened = None
        self._last_prompt_closed = None
        self._prompt_subscription_id = None
        self._prompt_handler_config = None

    def _init_context(self, browser, context_id):
        """初始化上下文连接

        Args:
            browser: Firefox 实例
            context_id: browsingContext ID
        """
        self._browser = browser
        self._context_id = context_id
        self._driver = ContextDriver(browser.driver, context_id)
        self._load_mode = browser.options.load_mode

    # ===== __call__ 快捷方式 =====

    def __call__(self, locator, index=1, timeout=None) -> "FirefoxElement | NoneElement":
        """快捷查找元素: page('locator') 等价于 page.ele('locator')

        Args:
            locator: 定位器（字符串或元组）
            index: 第几个（从1开始，负数从后数）
            timeout: 超时时间（秒）

        Returns:
            FirefoxElement 或 NoneElement
        """
        return self.ele(locator, index=index, timeout=timeout)

    # ===== 属性 =====

    @property
    def browser(self) -> "Firefox":
        """Firefox 浏览器实例"""
        return self._browser

    @property
    def tab_id(self) -> str:
        """当前 browsingContext ID"""
        return self._context_id

    @property
    def title(self) -> str:
        """页面标题"""
        return self.run_js("document.title") or ""

    @property
    def url(self) -> str:
        """当前 URL"""
        return self.run_js("location.href") or ""

    @property
    def html(self) -> str:
        """页面完整 HTML"""
        return self.run_js("document.documentElement.outerHTML") or ""

    @property
    def user_agent(self) -> str:
        """User-Agent 字符串"""
        return self.run_js("navigator.userAgent") or ""

    @property
    def ready_state(self) -> str:
        """页面加载状态: 'loading' / 'interactive' / 'complete'"""
        return self.run_js("document.readyState") or ""

    @property
    def cookies(self) -> list:
        """当前页面 Cookie（简单格式）"""
        return self.get_cookies()

    @property
    def scroll(self) -> "PageScroller":
        """滚动管理器"""
        if self._scroll is None:
            from .._units.scroller import PageScroller

            self._scroll = PageScroller(self)
        return self._scroll

    @property
    def actions(self) -> "Actions":
        """动作链管理器"""
        if self._actions is None:
            from .._units.actions import Actions

            self._actions = Actions(self)
        return self._actions

    @property
    def touch(self) -> "TouchActions":
        """BiDi 触摸动作链管理器"""
        if self._touch is None:
            from .._units.touch_actions import TouchActions

            self._touch = TouchActions(self)
        return self._touch

    @property
    def prefs(self) -> "PrefsManager":
        """about:config 运行时读写"""
        if self._prefs is None:
            from .._units.prefs import PrefsManager

            self._prefs = PrefsManager(self)
        return self._prefs

    @property
    def realms(self) -> "RealmTracker":
        """realm 生命周期追踪"""
        if self._realms is None:
            from .._units.realm_tracker import RealmTracker

            self._realms = RealmTracker(self)
        return self._realms

    @property
    def config(self) -> "ConfigManager":
        """about:config 完整控制系统（user.js / prefs.js / policies.json）"""
        if self._config is None:
            from .._units.config_manager import ConfigManager

            browser = self._browser
            profile = getattr(browser, "_auto_profile", None) or (
                browser.options.profile_path if hasattr(browser, "options") else None
            )
            self._config = ConfigManager(profile_path=profile)
        return self._config

    @property
    def wait(self) -> "PageWaiter":
        """等待条件管理器"""
        if self._wait is None:
            from .._units.waiter import PageWaiter

            self._wait = PageWaiter(self)
        return self._wait

    @property
    def listen(self) -> "Listener":
        """网络监听管理器"""
        if self._listener is None:
            from .._units.listener import Listener

            self._listener = Listener(self)
        return self._listener

    @property
    def rect(self) -> "TabRect":
        """页面位置/尺寸"""
        if self._rect is None:
            from .._units.rect import TabRect

            self._rect = TabRect(self)
        return self._rect

    @property
    def states(self) -> "PageStates":
        """页面状态查询"""
        if self._states is None:
            from .._units.states import PageStates

            self._states = PageStates(self)
        return self._states

    @property
    def set(self) -> "PageSetter":
        """属性设置器"""
        if self._setter is None:
            from .._units.setter import PageSetter

            self._setter = PageSetter(self)
        return self._setter

    @property
    def local_storage(self) -> "StorageManager":
        """localStorage 管理器"""
        if self._local_storage is None:
            from .._units.storage import StorageManager

            self._local_storage = StorageManager(self, "localStorage")
        return self._local_storage

    @property
    def session_storage(self) -> "StorageManager":
        """sessionStorage 管理器"""
        if self._session_storage is None:
            from .._units.storage import StorageManager

            self._session_storage = StorageManager(self, "sessionStorage")
        return self._session_storage

    @property
    def console(self) -> "ConsoleListener":
        """控制台日志监听器"""
        if self._console is None:
            from .._units.console_listener import ConsoleListener

            self._console = ConsoleListener(self)
        return self._console

    @property
    def intercept(self) -> "Interceptor":
        """网络请求拦截器"""
        if self._interceptor is None:
            from .._units.interceptor import Interceptor

            self._interceptor = Interceptor(self)
        return self._interceptor

    @property
    def network(self) -> "NetworkManager":
        """network 模块高层管理器。

        Returns:
            NetworkManager: 提供额外请求头、缓存行为、data collector 的高层入口。

        适用场景：
            - 设置额外请求头
            - 设置缓存行为
            - 创建和管理 network data collector

        说明：
            - 优先用 ``page.network``，而不是直接写
              ``network.xxx(page._driver, ...)``。
        """
        if self._network_manager is None:
            from .._units.network_tools import NetworkManager

            self._network_manager = NetworkManager(self)
        return self._network_manager

    @property
    def window(self) -> "WindowManager":
        """当前页面对应窗口的常用操作管理器。

        Returns:
            WindowManager: 面向当前页面窗口的高层操作对象。

        适用场景：
            - 想直接最大化、最小化、全屏当前窗口
            - 想设置当前窗口尺寸和位置

        与 ``browser_tools`` 的区别：
            - ``window`` 更偏“当前窗口怎么操作”
            - ``browser_tools`` 更偏“浏览器级有哪些窗口/用户上下文可以管理”
        """
        if self._window is None:
            from .._units.window import WindowManager

            self._window = WindowManager(self)
        return self._window

    @property
    def browser_tools(self) -> "BrowserManager":
        """浏览器级能力管理器。

        Returns:
            BrowserManager: 提供 user context 和 client window 管理能力。

        适用场景：
            - 创建、查询、删除 user context
            - 在指定 user context 中创建 tab
            - 枚举所有 client window 并切换窗口状态

        说明：
            - 这是 browser 模块的高层入口。
            - 当你需要的是“浏览器级资源管理”，优先用它，而不是直接调用
              ``_bidi.browser_module``。
        """
        if self._browser_manager is None:
            from .._units.browser import BrowserManager

            self._browser_manager = BrowserManager(self)
        return self._browser_manager

    @property
    def contexts(self) -> "ContextManager":
        """浏览上下文高层管理器。

        Returns:
            ContextManager: 提供 browsingContext 模块常用能力的简洁入口。

        适用场景：
            - 获取 context 树
            - 创建/关闭 tab 或 window
            - 对当前页面执行 reload、setViewport、setBypassCSP 等操作

        说明：
            - 这是面向使用者的 browsingContext 入口。
            - 优先用 ``page.contexts``，而不是直接写
              ``browsing_context.xxx(page._driver, ...)``。
        """
        if self._contexts is None:
            from .._units.contexts import ContextManager

            self._contexts = ContextManager(self)
        return self._contexts

    @property
    def emulation(self) -> "EmulationManager":
        """设备模拟管理器"""
        if self._emulation is None:
            from .._units.emulation import EmulationManager

            self._emulation = EmulationManager(self)
        return self._emulation

    @property
    def extensions(self) -> "ExtensionManager":
        """WebExtension 管理器。"""
        if self._extensions is None:
            from .._units.extensions import ExtensionManager

            self._extensions = ExtensionManager(self._driver)
        return self._extensions

    @property
    def downloads(self) -> "DownloadsManager":
        """下载管理器。

        Returns:
            DownloadsManager: 下载行为设置、下载事件等待、文件落盘检查的统一入口。

        适用场景：
            - 设置下载目录或 allow / deny 行为
            - 等待 ``downloadWillBegin`` / ``downloadEnd``
            - 验证文件是否真实落盘
        """
        if self._downloads is None:
            from .._units.downloads import DownloadsManager

            self._downloads = DownloadsManager(self)
        return self._downloads

    @property
    def events(self) -> "EventTracker":
        """通用 BiDi 事件跟踪器。

        Returns:
            EventTracker: 用于统一监听和等待各模块事件。

        适用场景：
            - 验证 ``browsingContext.contextCreated`` / ``userPromptOpened`` 等标准事件
            - 不想直接调用底层 ``session.subscribe`` 时
        """
        if self._events is None:
            from .._units.events import EventTracker

            self._events = EventTracker(self)
        return self._events

    @property
    def navigation(self) -> "NavigationTracker":
        """导航事件跟踪器。

        Returns:
            NavigationTracker: 用于订阅、记录、等待导航相关 BiDi 事件。

        适用场景：
            - 验证 ``navigationStarted`` / ``load`` / ``historyUpdated`` 等标准事件
            - 调试某次导航到底触发了哪些 BiDi 事件

        说明：
            - 这是“导航事件监听器”，不是导航命令本身。
            - 真正执行跳转仍然用 ``page.get()``、``page.back()``、``page.forward()``。
            - 当你想知道“跳转过程中浏览器发了什么事件”，再使用 ``page.navigation``。
        """
        if self._navigation is None:
            from .._units.navigation import NavigationTracker

            self._navigation = NavigationTracker(self)
        return self._navigation

    # ===== 导航 =====

    def get(self, url, wait=None, timeout=None) -> "FirefoxBase":
        """导航到指定 URL

        Uses browsingContext.navigate directly through the browser driver
        (not the context driver, since navigate already takes context as a param).

        Args:
            url: 目标 URL
            wait: 等待策略 'none'/'interactive'/'complete'，None 则根据 load_mode 决定
            timeout: 超时时间（秒）

        Returns:
            self
        """
        if wait is None:
            wait_map = {"normal": "complete", "eager": "interactive", "none": "none"}
            wait = wait_map.get(self._load_mode, "complete")

        if timeout:
            old_timeout = Settings.bidi_timeout
            Settings.bidi_timeout = timeout

        try:
            bidi_context.navigate(
                self._driver._browser_driver, self._context_id, url, wait=wait
            )
        except BiDiError as e:
            # navigate 失败不一定是错误（如 none 模式下立即返回）
            if "timeout" not in str(e.error).lower():
                logger.warning("导航错误: %s", e)
        finally:
            if timeout:
                Settings.bidi_timeout = old_timeout

        return self

    def back(self) -> "FirefoxBase":
        """后退

        Returns:
            self
        """
        bidi_context.traverse_history(
            self._driver._browser_driver, self._context_id, -1
        )
        return self

    def forward(self) -> "FirefoxBase":
        """前进

        Returns:
            self
        """
        bidi_context.traverse_history(self._driver._browser_driver, self._context_id, 1)
        return self

    def refresh(self, ignore_cache=False) -> "FirefoxBase":
        """刷新页面

        Args:
            ignore_cache: 是否忽略缓存

        Returns:
            self
        """
        wait_map = {"normal": "complete", "eager": "interactive", "none": "none"}
        wait = wait_map.get(self._load_mode, "complete")
        bidi_context.reload(
            self._driver._browser_driver,
            self._context_id,
            ignore_cache=ignore_cache,
            wait=wait,
        )
        return self

    def stop_loading(self) -> "FirefoxBase":
        """停止加载

        Returns:
            self
        """
        self.run_js("window.stop()")
        return self

    def wait_loading(self, timeout=None) -> "FirefoxBase":
        """等待页面 DOM 加载完成（domContentLoaded 事件）

        通过订阅 browsingContext.domContentLoaded 事件来等待。
        如果当前 readyState 已经是 interactive 或 complete 则立即返回。

        Args:
            timeout: 超时时间（秒），None 使用默认超时

        Returns:
            self

        Raises:
            WaitTimeoutError: 超时
        """
        if timeout is None:
            timeout = Settings.bidi_timeout

        # 先检查当前状态
        state = self.run_js("document.readyState")
        if state in ("interactive", "complete"):
            return self

        # 轮询等待
        end_time = time.time() + timeout
        while time.time() < end_time:
            state = self.run_js("document.readyState")
            if state in ("interactive", "complete"):
                return self
            time.sleep(0.1)

        raise WaitTimeoutError("等待页面加载超时 ({}s)".format(timeout))

    # ===== 元素查找 =====

    def ele(self, locator, index=1, timeout=None) -> "FirefoxElement | NoneElement":
        """查找单个元素。

        Args:
            locator: 定位器（字符串或元组）。
                最常用写法：
                ``'#kw'`` 按 CSS id；
                ``'.item'`` 按 CSS class；
                ``'css:div.card > a'`` 明确按 CSS；
                ``'xpath://input[@name="q"]'`` 按 XPath；
                ``'tag:input'`` 按标签名；
                ``'text:登录'`` 按文本；
                ``'text=登录'`` 也可作为文本定位简写。

                新手建议优先顺序：
                1. 先用 ``#id``
                2. 再用 ``css:...``
                3. 必要时再用 ``xpath:...``

                例子：
                ``page.ele('#search')``
                ``page.ele('css:.result-item a')``
                ``page.ele('xpath://button[text()="登录"]')``
                ``page.ele('tag:input', index=2)``
            index: 第几个匹配结果。
                单位：序号。
                常见值：``1`` 第一个、``2`` 第二个、``-1`` 最后一个。
            timeout: 查找超时时间。
                单位：秒。
                常见值：``1``、``3``、``5``。

        Returns:
            FirefoxElement 或 NoneElement。

        适用场景：
            - 你只想拿一个元素时
            - 页面上有多个同类元素，但你只关心其中一个
        """
        return self._find_element(locator, index=index, timeout=timeout)

    def eles(self, locator, timeout=None) -> "list[FirefoxElement]":
        """查找所有匹配的元素。

        Args:
            locator: 定位器（字符串或元组）。
                写法与 ``ele()`` 完全相同，例如：
                ``page.eles('css:.card')``
                ``page.eles('tag:a')``
                ``page.eles('xpath://ul/li')``
            timeout: 查找超时时间。
                单位：秒。
                常见值：``1``、``3``、``5``。

        Returns:
            list[FirefoxElement]: 所有匹配到的元素列表。

        适用场景：
            - 需要遍历结果列表时
            - 例如抓取搜索结果、表格行、商品卡片列表
        """
        return self._find_elements(locator, timeout=timeout)

    def s_ele(self, locator=None) -> "StaticElement | NoneElement":
        """获取静态元素（从当前 HTML 解析，不需要浏览器连接）

        Args:
            locator: 定位器，None 返回整个页面的静态元素

        Returns:
            StaticElement 或 NoneElement
        """
        from .._elements.static_element import StaticElement, make_static_ele

        html = self.html
        return make_static_ele(html, locator)

    def s_eles(self, locator) -> "list[StaticElement]":
        """获取所有匹配的静态元素

        Args:
            locator: 定位器

        Returns:
            StaticElement 列表
        """
        from .._elements.static_element import make_static_eles

        html = self.html
        return make_static_eles(html, locator)

    def _find_element(
        self, locator, index=1, timeout=None, raise_err=None, start_node=None
    ):
        """内部查找元素方法

        Args:
            locator: 定位器
            index: 索引
            timeout: 超时
            raise_err: 是否抛出异常
            start_node: 起始节点（用于相对查找）

        Returns:
            FirefoxElement 或 NoneElement
        """
        if timeout is None:
            timeout = Settings.element_find_timeout
        if raise_err is None:
            raise_err = Settings.raise_when_ele_not_found

        end_time = time.time() + timeout

        while True:
            elements = self._do_find(locator, start_node=start_node)
            if elements:
                if index > 0:
                    idx = index - 1
                elif index < 0:
                    idx = index
                else:
                    idx = 0
                try:
                    return elements[idx]
                except IndexError:
                    pass

            if time.time() >= end_time:
                break

            time.sleep(0.3)

        if raise_err:
            raise ElementNotFoundError("未找到元素: {}".format(locator))

        from .._elements.none_element import NoneElement

        return NoneElement(self, method="ele", args={"locator": locator})

    def _find_elements(self, locator, timeout=None):
        """内部查找多个元素方法"""
        if timeout is None:
            timeout = Settings.element_find_timeout

        end_time = time.time() + timeout

        while True:
            elements = self._do_find(locator)
            if elements:
                return elements

            if time.time() >= end_time:
                break

            time.sleep(0.3)

        return []

    def _do_find(self, locator, start_node=None):
        """执行实际的元素查找

        Args:
            locator: 定位器
            start_node: 起始节点（用于相对查找）

        Returns:
            FirefoxElement 列表
        """
        from .._elements.firefox_element import FirefoxElement

        bidi_locator = parse_locator(locator)

        # innerText 的 matchType 处理
        # BiDi 标准 innerText locator 默认是 full match
        # 我们需要 partial match 作为默认行为
        # 通过 JS 实现 partial text match
        match_type = bidi_locator.pop("matchType", None)

        params = {
            "context": self._context_id,
            "locator": bidi_locator,
        }

        if start_node:
            # 将 FirefoxElement 转换为 SharedReference 格式
            if hasattr(start_node, "_shared_id"):
                params["startNodes"] = [
                    {"type": "sharedReference", "sharedId": start_node._shared_id}
                ]
            else:
                params["startNodes"] = [start_node]

        # 设置序列化选项以获取节点属性
        params["serializationOptions"] = {"maxDomDepth": 0, "includeShadowTree": "open"}

        try:
            result = self._driver._browser_driver.run(
                "browsingContext.locateNodes", params
            )
            nodes = result.get("nodes", [])
        except BiDiError as e:
            # 定位器不支持时回退到 JS 查找
            err_str = str(e.error).lower()
            if (
                "invalid argument" in err_str
                or "invalid selector" in err_str
                or "unsupported" in err_str
            ):
                # innerText 类型回退到 JS 文本查找
                if bidi_locator.get("type") == "innerText":
                    return self._find_by_text_js(
                        bidi_locator.get("value", ""), start_node
                    )
                return self._find_by_js(locator, start_node)
            logger.debug("locateNodes 失败: %s", e)
            return []

        if not nodes:
            # 对于 innerText 类型，始终尝试 JS 回退实现部分匹配
            if bidi_locator.get("type") == "innerText":
                return self._find_by_text_js(bidi_locator.get("value", ""), start_node)
            return []

        elements = []
        for node in nodes:
            ele = FirefoxElement._from_node(self, node)
            if ele:
                elements.append(ele)

        return elements

    def _find_by_text_js(self, text, start_node=None):
        """通过 JS 实现文本部分匹配查找

        使用两轮策略：
        1. 先找所有 textContent 包含目标文本的"最深叶节点"
        2. 如果没找到叶节点，放宽条件找"最小包含节点"（自身文本包含但非所有子节点都包含）
        """
        from .._elements.firefox_element import FirefoxElement
        from .._functions.bidi_values import make_shared_ref

        js = """(text, rootNode) => {
            const root = rootNode || document.body || document.documentElement;
            const results = [];
            const seen = new Set();
            const skip = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'LINK', 'META']);

            // 策略1: 最深叶节点匹配（排除script/style）
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
            let node;
            while (node = walker.nextNode()) {
                if (skip.has(node.tagName)) continue;
                const nt = (node.textContent || '').trim();
                if (!nt.includes(text)) continue;
                let hasChildMatch = false;
                for (let ch of node.children) {
                    if (skip.has(ch.tagName)) continue;
                    if ((ch.textContent || '').trim().includes(text)) {
                        hasChildMatch = true;
                        break;
                    }
                }
                if (!hasChildMatch) {
                    results.push(node);
                    seen.add(node);
                }
            }
            if (results.length > 0) return results;

            // 策略2: 找直接文本包含目标的节点
            const walker2 = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
            while (node = walker2.nextNode()) {
                if (skip.has(node.tagName) || seen.has(node)) continue;
                const nt = (node.textContent || '').trim();
                if (!nt.includes(text)) continue;
                let directText = '';
                for (let cn of node.childNodes) {
                    if (cn.nodeType === 3) directText += cn.textContent;
                }
                if (directText.includes(text)) {
                    results.push(node);
                    continue;
                }
                try {
                    if ((node.innerText || '').includes(text)) {
                        results.push(node);
                    }
                } catch(e) {}
            }
            if (results.length > 0) return results;

            // 策略3: 兜底
            const walker3 = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
            while (node = walker3.nextNode()) {
                if (skip.has(node.tagName)) continue;
                const nt = (node.textContent || '').trim();
                if (nt.includes(text) && nt.length < text.length * 5) {
                    results.push(node);
                }
            }
            return results;
        }"""

        args = [{"type": "string", "value": text}]
        if start_node:
            # 将 start_node 作为第二个参数传递给 JS（使用 BiDi sharedReference 格式）
            args.append({"type": "sharedReference", "sharedId": start_node._shared_id})

        try:
            result = bidi_script.call_function(
                self._driver._browser_driver,
                self._context_id,
                js,
                arguments=args,
                serialization_options={"maxDomDepth": 0, "includeShadowTree": "open"},
            )

            if result.get("type") == "exception":
                return []

            rv = result.get("result", {})
            if rv.get("type") != "array":
                return []

            elements = []
            for node in rv.get("value", []):
                ele = FirefoxElement._from_node(self, node)
                if ele:
                    elements.append(ele)
            return elements

        except Exception as e:
            logger.debug("JS 文本查找失败: %s", e)
            return []

    def _find_by_js(self, locator, start_node=None):
        """通过 JS 回退查找（用于不支持的定位器类型）"""
        from .._elements.firefox_element import FirefoxElement

        bidi_locator = parse_locator(locator)
        loc_type = bidi_locator.get("type", "")
        loc_value = bidi_locator.get("value", "")

        if loc_type == "css":
            js = "(sel) => Array.from(document.querySelectorAll(sel))"
            args = [{"type": "string", "value": loc_value}]
        elif loc_type == "xpath":
            js = """(expr) => {
                const result = [];
                const xr = document.evaluate(expr, document, null,
                    XPathResult.ORDERED_NODE_ITERATOR_TYPE, null);
                let node;
                while (node = xr.iterateNext()) result.push(node);
                return result;
            }"""
            args = [{"type": "string", "value": loc_value}]
        else:
            return []

        try:
            result = bidi_script.call_function(
                self._driver._browser_driver,
                self._context_id,
                js,
                arguments=args,
                serialization_options={"maxDomDepth": 0, "includeShadowTree": "open"},
            )

            if result.get("type") == "exception":
                return []

            rv = result.get("result", {})
            if rv.get("type") != "array":
                return []

            elements = []
            for node in rv.get("value", []):
                ele = FirefoxElement._from_node(self, node)
                if ele:
                    elements.append(ele)
            return elements

        except Exception as e:
            logger.debug("JS 查找失败: %s", e)
            return []

    # ===== JavaScript 执行 =====

    def run_js(self, script, *args, as_expr=None, timeout=None, sandbox=None):
        """执行 JavaScript

        Args:
            script: JS 代码
            *args: 传递给脚本的参数
            as_expr: 是否作为表达式执行（None 自动判断）
            timeout: 超时时间（秒）
            sandbox: BiDi sandbox 名称（隔离执行上下文）

        Returns:
            JS 执行的返回值（自动转换为 Python 对象）
        """
        if timeout:
            old_timeout = Settings.bidi_timeout
            Settings.bidi_timeout = timeout

        try:
            return self._run_js(script, *args, as_expr=as_expr, sandbox=sandbox)
        finally:
            if timeout:
                Settings.bidi_timeout = old_timeout

    def run_js_loaded(self, script, *args, as_expr=None, timeout=None):
        """等待页面加载完成后执行 JavaScript

        Args:
            script: JS 代码
            *args: 参数
            as_expr: 是否作为表达式
            timeout: 超时

        Returns:
            JS 返回值
        """
        self.wait.doc_loaded(timeout=timeout)
        return self.run_js(script, *args, as_expr=as_expr, timeout=timeout)

    def _run_js(self, script, *args, as_expr=None, sandbox=None):
        """内部 JS 执行

        Detection rules (when ``as_expr is None``):
          1. If ``args`` are provided -> callFunction (always)
          2. If script starts with ``return `` -> wrap in function body, callFunction
          3. Otherwise -> evaluate as expression
        """
        script = script.strip()

        # ---------- determine mode ----------
        if as_expr is not None:
            use_expr = as_expr
        elif args:
            # args provided -> must use callFunction
            use_expr = False
        elif script.startswith("return "):
            # has 'return' keyword -> needs function wrapper
            use_expr = False
        else:
            # simple expression (no return, no function keyword, no args)
            use_expr = True

        if use_expr:
            # ---------- expression mode ----------
            result = bidi_script.evaluate(
                self._driver._browser_driver, self._context_id, script, sandbox=sandbox
            )
        else:
            # ---------- function / callFunction mode ----------
            func_body = script

            # Wrap bare statements that start with 'return ' into a function body
            if script.startswith("return "):
                func_body = "function(){" + script + "}"
            elif not script.startswith("function") and not script.startswith("("):
                func_body = "function(){" + script + "}"

            # 序列化参数
            from .._functions.bidi_values import serialize_value

            serialized_args = [serialize_value(a) for a in args] if args else None

            result = bidi_script.call_function(
                self._driver._browser_driver,
                self._context_id,
                func_body,
                sandbox=sandbox,
                arguments=serialized_args,
            )

        # 检查异常
        if result.get("type") == "exception":
            details = result.get("exceptionDetails", {})
            text = details.get("text", str(result))
            raise JavaScriptError(text, details)

        # 解析返回值
        return parse_value(result.get("result", {}))

    # ===== Document Node =====

    def _get_document_node_id(self):
        """获取当前文档的 document 节点 SharedReference

        通过 script.callFunction 获取 document 对象，返回其 sharedId，
        可用于后续元素操作中作为 startNode。

        Returns:
            dict: SharedReference 格式 {'type': 'sharedReference', 'sharedId': '...'}
                  或 None
        """
        try:
            result = bidi_script.call_function(
                self._driver._browser_driver,
                self._context_id,
                "() => document",
                serialization_options={"maxDomDepth": 0, "includeShadowTree": "open"},
            )

            if result.get("type") == "exception":
                return None

            rv = result.get("result", {})
            shared_id = rv.get("sharedId")
            if shared_id:
                return make_shared_ref(shared_id)
            return None
        except Exception as e:
            logger.debug("获取 document 节点失败: %s", e)
            return None

    # ===== Cookie 操作 =====

    def get_cookies(self, all_info=False) -> list:
        """获取当前页面的 Cookie。

        Args:
            all_info: True 返回完整 Cookie 信息

        Returns:
            list[CookieInfo]: Cookie 对象列表。

        适用场景：
            - 读取当前页面上下文下可见的 Cookie
            - 在示例中按属性访问 ``cookie.name`` / ``cookie.value``
        """
        from .._bidi import storage as bidi_storage
        from .._units.cookies import CookieInfo

        try:
            result = bidi_storage.get_cookies(
                self._driver._browser_driver, partition={"context": self._context_id}
            )
        except Exception:
            # 回退到 JS 获取
            cookie_str = self.run_js("document.cookie") or ""
            cookies = []
            for pair in cookie_str.split(";"):
                pair = pair.strip()
                if "=" in pair:
                    name, value = pair.split("=", 1)
                    cookies.append(
                        CookieInfo({"name": name.strip(), "value": value.strip()})
                    )
            return cookies

        raw_cookies = result.get("cookies", [])

        if not all_info:
            return [
                CookieInfo(
                    {
                        "name": c.get("name", ""),
                        "value": c.get("value", {}).get("value", "")
                        if isinstance(c.get("value"), dict)
                        else str(c.get("value", "")),
                    }
                )
                for c in raw_cookies
            ]

        return [CookieInfo(c) for c in raw_cookies]

    def get_cookies_filtered(self, name=None, domain=None, all_info=True):
        """按过滤条件读取当前页面 Cookie。

        Args:
            name: Cookie 名称过滤。
                常见值：``'session_id'``、``'user_id'``。传 ``None`` 表示不过滤名称。
            domain: 域名过滤。
                常见值：``'127.0.0.1'``、``'.example.com'``。传 ``None`` 表示不过滤域名。
            all_info: 是否返回完整 Cookie 信息。
                常见值：``True``、``False``。

        Returns:
            list[CookieInfo]: 过滤后的 Cookie 对象列表。

        适用场景：
            - 替代示例层直接调用 ``storage.getCookies(filter_=...)``
            - 新手按名称/域名筛选 Cookie
        """
        cookies = self.get_cookies(all_info=all_info)
        result = cookies
        if name is not None:
            result = [c for c in result if c.name == name]
        if domain is not None:
            result = [c for c in result if c.domain == domain]
        return result

    def set_cookies(self, cookies) -> None:
        """设置 Cookie

        Args:
            cookies: Cookie 字典或字典列表
                {'name': 'x', 'value': 'y', 'domain': '.example.com'}
        """
        from .._bidi import storage as bidi_storage

        if isinstance(cookies, dict):
            cookies = [cookies]

        for cookie in cookies:
            bidi_cookie = {
                "name": cookie.get("name", ""),
                "value": {"type": "string", "value": str(cookie.get("value", ""))},
                "domain": cookie.get("domain", ""),
            }

            # 可选字段
            for key in ("path", "httpOnly", "secure", "sameSite", "expiry"):
                py_key = key
                if py_key in cookie:
                    bidi_cookie[key] = cookie[py_key]

            try:
                bidi_storage.set_cookie(
                    self._driver._browser_driver,
                    bidi_cookie,
                    partition={"context": self._context_id},
                )
            except Exception:
                # 某些 Firefox 版本不支持 partition 参数
                bidi_storage.set_cookie(self._driver._browser_driver, bidi_cookie)

    def delete_cookies(self, name=None, domain=None) -> None:
        """删除 Cookie

        Args:
            name: Cookie 名称（None 删除所有）
            domain: 限定域名
        """
        from .._bidi import storage as bidi_storage

        filter_ = {}
        if name:
            filter_["name"] = name
        if domain:
            filter_["domain"] = domain

        try:
            bidi_storage.delete_cookies(
                self._driver._browser_driver,
                filter_=filter_ or None,
                partition={"context": self._context_id},
            )
        except Exception:
            bidi_storage.delete_cookies(
                self._driver._browser_driver, filter_=filter_ or None
            )

    # ===== 截图 / PDF =====

    def screenshot(self, path=None, full_page=False, as_bytes=None, as_base64=None):
        """截图

        Args:
            path: 保存路径（None 不保存文件）
            full_page: True 截取整个页面，False 仅视口
            as_bytes: True 返回 bytes（优先级高于 as_base64）
            as_base64: True 返回 base64 字符串

        Returns:
            根据参数返回文件路径/bytes/base64 字符串
        """
        origin = "document" if full_page else "viewport"
        result = bidi_context.capture_screenshot(
            self._driver._browser_driver, self._context_id, origin=origin
        )

        data_b64 = result.get("data", "")
        data_bytes = base64.b64decode(data_b64)

        if path:
            import os

            os.makedirs(
                os.path.dirname(os.path.abspath(path)), exist_ok=True
            ) if os.path.dirname(path) else None
            with open(path, "wb") as f:
                f.write(data_bytes)

        if as_bytes:
            return data_bytes
        if as_base64:
            return data_b64
        if path:
            return path

        return data_bytes

    def pdf(self, path=None, **kwargs):
        """打印为 PDF。

        Args:
            path: 保存路径。
                - 传字符串路径时：直接写入文件并返回该路径
                - 传 None 时：返回 PDF 的 bytes 数据
            **kwargs: 透传给 `browsingContext.print` 的打印参数，常用项如下：
                - background: 是否打印背景（bool）
                - margin: 页边距，单位 cm，例如
                  {'top': 1.2, 'bottom': 1.2, 'left': 1.0, 'right': 1.0}
                - orientation: 页面方向，'portrait' 或 'landscape'
                - page: 纸张尺寸，单位 cm，例如 A4 为
                  {'width': 21.0, 'height': 29.7}
                - page_ranges: 页码范围列表，例如 ['1-2']
                - scale: 缩放比例，例如 0.9
                - shrink_to_fit: 内容过宽时是否自动缩放（bool）

        Returns:
            path 或 bytes
        """
        result = bidi_context.print_(
            self._driver._browser_driver, self._context_id, **kwargs
        )

        data_b64 = result.get("data", "")
        data_bytes = base64.b64decode(data_b64)

        if path:
            with open(path, "wb") as f:
                f.write(data_bytes)
            return path

        return data_bytes

    def save_pdf(self, path, **kwargs):
        """新手友好别名：直接保存 PDF 到文件。

        Args:
            path: 输出 PDF 文件路径
            **kwargs: 与 `pdf()` 相同的打印参数

        Returns:
            str: 保存后的文件路径
        """
        return self.pdf(path=path, **kwargs)

    # ===== 弹窗处理 =====

    def handle_alert(self, action="accept", text=None, timeout=3) -> "str | None":
        """处理弹窗

        如果弹窗还没出现，会轮询等待直到 timeout。

        Args:
            action: 'accept' 接受 / 'dismiss' 拒绝
            text: 对于 prompt 弹窗填入的文本
            timeout: 等待弹窗出现的超时（秒）

        Returns:
            self
        """
        accept = action != "dismiss"
        end_time = time.time() + timeout
        drv = self._driver._browser_driver

        while time.time() < end_time:
            try:
                # 先等待 userPromptOpened 事件真正到达，避免“页面已调用 confirm，
                # 但浏览器侧 prompt 状态尚未建立”时过早处理。
                if not getattr(drv, "alert_flag", False):
                    time.sleep(0.05)
                    continue

                bidi_context.handle_user_prompt(
                    drv,
                    self._context_id,
                    accept=accept,
                    user_text=text,
                )
                return self
            except BiDiError as e:
                if "no such alert" in str(e.error).lower():
                    time.sleep(0.05)
                    continue
                raise

        return self

    def accept_alert(self, text=None, timeout=3):
        """接受当前弹窗（prompt 可选输入文本）。

        Args:
            text: prompt 输入文本
            timeout: 等待弹窗出现超时（秒）

        说明：
            - 这是 `handle_alert(action='accept', ...)` 的语义化别名。
            - 建议新手优先使用该方法，可读性更好。
        """
        return self.handle_alert(action="accept", text=text, timeout=timeout)

    def dismiss_alert(self, timeout=3):
        """拒绝/取消当前弹窗。

        说明：
            - 这是 `handle_alert(action='dismiss', ...)` 的语义化别名。
        """
        return self.handle_alert(action="dismiss", timeout=timeout)

    def get_user_prompt(self):
        """获取当前 context 的用户弹窗信息。

        Returns:
            dict 或 None
        """
        try:
            result = self._driver._browser_driver.run(
                "browsingContext.getTree", {"root": self._context_id}
            )
            contexts = result.get("contexts", [])
            if not contexts:
                return None
            prompt = contexts[0].get("userPrompt")
            return prompt if isinstance(prompt, dict) else None
        except Exception:
            return None

    def get_last_prompt_opened(self):
        """获取最近一次 userPromptOpened 事件参数。"""
        return (
            dict(self._last_prompt_opened)
            if isinstance(self._last_prompt_opened, dict)
            else None
        )

    def get_last_prompt_closed(self):
        """获取最近一次 userPromptClosed 事件参数。"""
        return (
            dict(self._last_prompt_closed)
            if isinstance(self._last_prompt_closed, dict)
            else None
        )

    def set_prompt_handler(
        self,
        *,
        alert="accept",
        confirm="accept",
        prompt="ignore",
        default="accept",
        prompt_text=None,
    ):
        """设置用户提示框自动处理策略（新手友好）。

        推荐：
            - alert/confirm 通常直接 accept/dismiss
            - prompt 需要写文本时：prompt='ignore' 且 prompt_text='你的文本'

        Returns:
            self

        说明：
            - alert/confirm 建议直接 accept 或 dismiss。
            - prompt 需要输入文本时，推荐 prompt='ignore' + prompt_text='你的文本'。
            - 该方法内部会订阅 userPromptOpened/Closed 事件。
        """
        from .._bidi import session as bidi_session
        from .._bidi import browsing_context as bidi_context

        self.clear_prompt_handler()
        self._prompt_handler_config = {
            "alert": alert,
            "confirm": confirm,
            "prompt": prompt,
            "default": default,
            "prompt_text": prompt_text,
        }

        def on_opened(params):
            if params.get("context") != self.tab_id:
                return
            self._last_prompt_opened = dict(params)
            if (
                params.get("type") == "prompt"
                and self._prompt_handler_config
                and self._prompt_handler_config.get("prompt") == "ignore"
                and self._prompt_handler_config.get("prompt_text") is not None
            ):
                try:
                    bidi_context.handle_user_prompt(
                        self._driver._browser_driver,
                        self.tab_id,
                        accept=True,
                        user_text=str(self._prompt_handler_config.get("prompt_text")),
                    )
                except Exception:
                    pass

        def on_closed(params):
            if params.get("context") != self.tab_id:
                return
            self._last_prompt_closed = dict(params)

        self._driver._browser_driver.set_callback(
            "browsingContext.userPromptOpened",
            on_opened,
            context=self.tab_id,
            immediate=True,
        )
        self._driver._browser_driver.set_callback(
            "browsingContext.userPromptClosed",
            on_closed,
            context=self.tab_id,
            immediate=True,
        )
        sub = bidi_session.subscribe(
            self._driver._browser_driver,
            ["browsingContext.userPromptOpened", "browsingContext.userPromptClosed"],
            contexts=[self.tab_id],
        )
        self._prompt_subscription_id = sub.get("subscription")
        return self

    def clear_prompt_handler(self):
        """清理用户提示框自动处理策略。"""
        from .._bidi import session as bidi_session

        try:
            if self._prompt_subscription_id:
                bidi_session.unsubscribe(
                    self._driver._browser_driver,
                    subscription=self._prompt_subscription_id,
                )
        except Exception:
            pass
        try:
            self._driver._browser_driver.remove_callback(
                "browsingContext.userPromptOpened",
                context=self.tab_id,
                immediate=True,
            )
            self._driver._browser_driver.remove_callback(
                "browsingContext.userPromptClosed",
                context=self.tab_id,
                immediate=True,
            )
        except Exception:
            pass
        self._prompt_subscription_id = None
        self._prompt_handler_config = None
        return self

    def wait_prompt(self, timeout=3):
        """等待当前 context 出现用户提示框。

        Returns:
            dict 或 None
        """
        end = time.time() + timeout
        initial_opened = self.get_last_prompt_opened()
        initial_closed = self.get_last_prompt_closed()

        while time.time() < end:
            # 优先读取事件缓存。某些实现里 userPromptOpened 事件比 getTree.userPrompt
            # 更早可见，用它能提高步骤式 API 的稳定性。
            opened = self.get_last_prompt_opened()
            closed = self.get_last_prompt_closed()
            if opened and opened != initial_opened and opened != closed:
                return opened

            prompt = self.get_user_prompt()
            if prompt:
                return prompt
            time.sleep(0.05)
        return None

    def handle_prompt(self, accept=True, text=None, timeout=3):
        """按步骤处理当前 prompt。

        这是比 handle_alert 更直观的高层封装：
        1) 等待 prompt 出现
        2) 调用 browsingContext.handleUserPrompt

        Args:
            accept: True=确认，False=取消
            text: prompt 输入文本（仅 prompt + accept=True 时有意义）
            timeout: 等待 prompt 出现超时

        Returns:
            self
        """
        from .._bidi import browsing_context as bidi_context

        prompt = self.wait_prompt(timeout=timeout)
        if not prompt:
            return self
        bidi_context.handle_user_prompt(
            self._driver._browser_driver,
            self._context_id,
            accept=accept,
            user_text=("" if text is None else str(text)),
        )
        return self

    def respond_prompt(self, *, accept=True, text=None, timeout=3):
        """步骤式处理 prompt 的统一入口。"""
        return self.handle_prompt(accept=accept, text=text, timeout=timeout)

    def accept_prompt(self, text=None, timeout=3):
        """等待并确认当前 prompt（可选输入文本）。"""
        return self.handle_prompt(accept=True, text=text, timeout=timeout)

    def dismiss_prompt(self, timeout=3):
        """等待并取消当前 prompt。"""
        return self.handle_prompt(accept=False, timeout=timeout)

    def input_prompt(self, text, timeout=3):
        """给 prompt 输入文本并确认。"""
        return self.handle_prompt(accept=True, text=text, timeout=timeout)

    def trigger_prompt_target(self, locator, trigger="mouse"):
        """触发会弹出 prompt 的目标元素。

        Args:
            locator: 元素定位器
            trigger: 'mouse' 或 'keyboard'

        说明：
            - mouse: 原生鼠标点击触发
            - keyboard: 聚焦后发送 Enter 触发
        """
        ele = self.ele(locator)
        if trigger == "keyboard":
            ele.click_self()
            self.actions.key_down("\ue007").key_up("\ue007").perform()
        else:
            ele.click_self()
        return self

    def prompt_login(
        self, trigger_locator, username, password, trigger="mouse", timeout=3
    ):
        """两步 prompt 登录流程：先用户名，再密码。

        这是事件驱动版本：
        - 点击触发目标后
        - 在 userPromptOpened 回调中立即注入用户名/密码
        - 避免 prompt 打开后阻塞后续动作链

        Args:
            trigger_locator: 触发登录 prompt 的元素定位器
            username: 用户名
            password: 密码
            trigger: 'mouse' 或 'keyboard'
            timeout: 总等待时间

        Returns:
            self
        """
        import threading
        from .._bidi import session as bidi_session
        from .._bidi import browsing_context as bidi_context

        # 临时移除已有自动策略，避免与本次登录流冲突
        self.clear_prompt_handler()

        opened_count = {"value": 0}
        done = threading.Event()
        sub_id = None

        def on_opened(params):
            if params.get("context") != self.tab_id:
                return
            if params.get("type") != "prompt":
                return

            opened_count["value"] += 1
            self._last_prompt_opened = dict(params)

            try:
                if opened_count["value"] == 1:
                    bidi_context.handle_user_prompt(
                        self._driver._browser_driver,
                        self.tab_id,
                        accept=True,
                        user_text=str(username),
                    )
                elif opened_count["value"] == 2:
                    bidi_context.handle_user_prompt(
                        self._driver._browser_driver,
                        self.tab_id,
                        accept=True,
                        user_text=str(password),
                    )
                    done.set()
            except Exception:
                pass

        def on_closed(params):
            if params.get("context") != self.tab_id:
                return
            self._last_prompt_closed = dict(params)

        self._driver._browser_driver.set_callback(
            "browsingContext.userPromptOpened",
            on_opened,
            context=self.tab_id,
            immediate=True,
        )
        self._driver._browser_driver.set_callback(
            "browsingContext.userPromptClosed",
            on_closed,
            context=self.tab_id,
            immediate=True,
        )
        sub = bidi_session.subscribe(
            self._driver._browser_driver,
            ["browsingContext.userPromptOpened", "browsingContext.userPromptClosed"],
            contexts=[self.tab_id],
        )
        sub_id = sub.get("subscription")

        try:
            self.trigger_prompt_target(trigger_locator, trigger=trigger)
            done.wait(timeout)
            time.sleep(0.2)
        finally:
            try:
                if sub_id:
                    bidi_session.unsubscribe(
                        self._driver._browser_driver,
                        subscription=sub_id,
                    )
            except Exception:
                pass
            try:
                self._driver._browser_driver.remove_callback(
                    "browsingContext.userPromptOpened",
                    context=self.tab_id,
                    immediate=True,
                )
                self._driver._browser_driver.remove_callback(
                    "browsingContext.userPromptClosed",
                    context=self.tab_id,
                    immediate=True,
                )
            except Exception:
                pass
        return self

    # ===== 视口 / 模拟 =====

    def set_viewport(self, width, height, device_pixel_ratio=None) -> "FirefoxBase":
        """设置当前页面视口大小。

        Args:
            width: 视口宽度。
                单位：CSS 像素。
                常见值：``800``、``1280``、``375``。
            height: 视口高度。
                单位：CSS 像素。
                常见值：``600``、``720``、``667``。
            device_pixel_ratio: 设备像素比。
                常见值：``1``、``2``、``3``。传 ``None`` 表示不改动当前 DPR。

        Returns:
            self: 原页面对象，便于链式调用。

        适用场景：
            - 快速调整页面可视区域
            - 与移动端模拟配合设置 viewport + DPR
        """
        bidi_context.set_viewport(
            self._driver._browser_driver,
            self._context_id,
            width=width,
            height=height,
            device_pixel_ratio=device_pixel_ratio,
        )
        return self

    def set_useragent(self, ua) -> "FirefoxBase":
        """设置 User-Agent

        Firefox stable 不支持 emulation.setUserAgentOverride，
        因此通过 script.addPreloadScript 注入 JS 来覆盖 navigator.userAgent。
        同时在当前页面立即执行覆盖脚本。

        Args:
            ua: User-Agent 字符串

        Returns:
            self
        """
        # 移除之前的 UA preload script（如果有）
        if self._ua_preload_script_id:
            try:
                bidi_script.remove_preload_script(
                    self._driver._browser_driver, self._ua_preload_script_id
                )
            except Exception:
                pass
            self._ua_preload_script_id = None

        # 构造注入脚本：覆盖 navigator.userAgent
        escaped_ua = ua.replace("\\", "\\\\").replace("'", "\\'")
        inject_js = (
            "() => {"
            "  Object.defineProperty(navigator, 'userAgent', "
            "{get: () => '" + escaped_ua + "'});"
            "}"
        )

        # 注册 preload script，后续导航也会生效
        result = bidi_script.add_preload_script(
            self._driver._browser_driver, inject_js, contexts=[self._context_id]
        )
        self._ua_preload_script_id = result.get("script", "")

        # 在当前页面立即生效
        try:
            bidi_script.call_function(
                self._driver._browser_driver, self._context_id, inject_js
            )
        except Exception as e:
            logger.debug("当前页面 UA 覆盖执行失败（preload 仍然生效）: %s", e)

        return self

    def set_bypass_csp(self, bypass=True) -> "FirefoxBase":
        """尝试绕过页面 CSP。

        说明：
            - 这是 ruyipage 的高层兼容入口，不等同于标准 ``browsingContext.setBypassCSP``。
            - 当前实现主要通过 preload script 移除页面里的 CSP meta 标签。
            - 它更适合处理“页面内 meta CSP”的场景，不能等价替代浏览器原生 CSP 绕过能力。

        Args:
            bypass: 是否启用兼容式 CSP 绕过。
                常见值：``True`` 启用、``False`` 不处理。

        Returns:
            self: 原页面对象，便于链式调用。

        适用场景：
            - 需要在不支持标准命令的 Firefox 版本上做最小兼容处理
            - 示例或测试中临时移除页面 meta CSP 限制
        """
        if bypass:
            # 注入移除 CSP meta 标签的 preload script
            inject_js = """() => {
                // 移除 CSP meta 标签
                const observer = new MutationObserver((mutations) => {
                    for (const mutation of mutations) {
                        for (const node of mutation.addedNodes) {
                            if (node.tagName === 'META' &&
                                node.httpEquiv &&
                                node.httpEquiv.toLowerCase() === 'content-security-policy') {
                                node.remove();
                            }
                        }
                    }
                });
                observer.observe(document.documentElement, {childList: true, subtree: true});
                // 移除已存在的 CSP meta 标签
                document.querySelectorAll('meta[http-equiv="Content-Security-Policy"]')
                    .forEach(el => el.remove());
            }"""
            self.add_preload_script(inject_js)
        return self

    def add_preload_script(self, script) -> str:
        """添加预加载脚本（每次导航前执行）。

        Args:
            script: JavaScript 函数声明字符串。
                常见值：``"() => { ... }"``、``"(arg) => { ... }"``。

        Returns:
            PreloadScript: 支持 ``id`` 属性访问的预加载脚本对象。

        适用场景：
            - 在每次页面导航前注入一段脚本
            - 配合 ``script.message`` 或页面初始化逻辑做事件测试
        """
        from .._units.script_tools import PreloadScript

        result = bidi_script.add_preload_script(
            self._driver._browser_driver, script, contexts=[self._context_id]
        )
        return PreloadScript(result.get("script", ""))

    def remove_preload_script(self, script_id) -> None:
        """移除预加载脚本。

        Args:
            script_id: 预加载脚本 ID。
                常见值：``preload.id``。也兼容直接传字符串 ID。

        Returns:
            self: 原页面对象，便于链式调用。

        适用场景：
            - 清理测试中临时注册的 preload script
            - 避免后续导航重复执行同一段注入脚本
        """
        script_id = getattr(script_id, "id", script_id)
        bidi_script.remove_preload_script(self._driver._browser_driver, script_id)
        return self

    # ===== Trusted 事件状态 =====

    def is_trusted(self, event_key):
        """读取测试页中记录的 isTrusted 标记。

        适用场景：
            - 示例页会把最近一次事件的 isTrusted 写到 window 变量
            - 例如 window.lastClickTrusted / window.lastMouseEnterTrusted

        Args:
            event_key: 事件键名，支持两种写法：
                1) 完整变量名：'lastClickTrusted'
                2) 简写键名：'click' / 'dblclick' / 'contextmenu' /
                   'keydown' / 'mouseenter' / 'mousedown'

        Returns:
            bool 或 None

        注意：
            - 该方法依赖页面已把 isTrusted 写入 window 变量。
            - 在普通业务页面中，如果未埋点对应变量，返回值通常为 None。
        """
        mapping = {
            "click": "lastClickTrusted",
            "dblclick": "lastDblClickTrusted",
            "contextmenu": "lastContextMenuTrusted",
            "keydown": "lastKeydownTrusted",
            "mouseenter": "lastMouseEnterTrusted",
            "mousedown": "lastMouseDownTrusted",
        }
        key = mapping.get(str(event_key).lower(), event_key)
        return self.run_js("return window[arguments[0]]", key, as_expr=False)

    # ===== Frame 访问 =====

    def get_frame(self, locator=None, index=None, context_id=None) -> "FirefoxFrame":
        """获取 iframe/frame

        Args:
            locator: iframe 元素定位器
            index: iframe 序号（从0开始）
            context_id: 直接指定 context ID

        Returns:
            FirefoxFrame

        匹配优先级：
            1) context_id（最精确）
            2) index
            3) locator（按 iframe src 与 child context URL 尝试匹配）
            4) 兜底返回第一个 child context

        说明：
            - BiDi 下每个 iframe 都有独立 context，可直接操作。
            - 对 srcdoc/动态 iframe，URL 匹配可能不可用，因此保留 index 与兜底策略。
        """
        from .._pages.firefox_frame import FirefoxFrame

        if context_id:
            return FirefoxFrame(self._browser, context_id, self)

        # 通过 browsingContext.getTree 获取子 context
        result = bidi_context.get_tree(
            self._driver._browser_driver, root=self._context_id
        )
        contexts = result.get("contexts", [])
        children = contexts[0].get("children", []) if contexts else []

        if index is not None:
            if 0 <= index < len(children):
                child_ctx = children[index]["context"]
                return FirefoxFrame(self._browser, child_ctx, self)
            return None

        if locator:
            # 查找 iframe 元素，获取其对应的 child context
            ele = self.ele(locator)
            if not ele:
                return None

            # 尝试通过 URL 匹配
            ele_src = ele.attr("src") or ""
            for child in children:
                child_url = child.get("url", "")
                if ele_src and ele_src in child_url:
                    return FirefoxFrame(self._browser, child["context"], self)

            # 如果只有一个 iframe，直接返回第一个 child
            if len(children) == 1:
                return FirefoxFrame(self._browser, children[0]["context"], self)

        # 返回第一个子 context
        if children:
            return FirefoxFrame(self._browser, children[0]["context"], self)

        return None

    def get_frames(self) -> "list[FirefoxFrame]":
        """获取所有 iframe/frame

        Returns:
            FirefoxFrame 列表
        """
        from .._pages.firefox_frame import FirefoxFrame

        result = bidi_context.get_tree(
            self._driver._browser_driver, root=self._context_id
        )
        contexts = result.get("contexts", [])
        children = contexts[0].get("children", []) if contexts else []

        return [FirefoxFrame(self._browser, c["context"], self) for c in children]

    @contextmanager
    def with_frame(self, locator=None, index=None, context_id=None):
        """使用 with 语法访问 iframe（更简洁）。

        用法::

            with page.with_frame('#test-iframe') as frame:
                print(frame.ele('tag:h1').text)

        Args:
            locator: iframe 元素定位器
            index: iframe 序号（从0开始）
            context_id: 直接指定 context ID

        Yields:
            FirefoxFrame

        设计目的：
            - 让新手避免在页面/iframe 间来回切换心智负担。
            - `with` 内专注操作 frame；退出后直接继续操作原 page。
        """
        frame = self.get_frame(locator=locator, index=index, context_id=context_id)
        if frame is None:
            raise RuntimeError("未找到目标 iframe/frame")
        yield frame

    # ===== Cloudflare 验证 =====

    def handle_cloudflare_challenge(self, timeout=30, check_interval=2):
        """自动处理 Cloudflare Turnstile 验证（5s 盾）

        通过 BiDi 查找 CF iframe 并在其内部触发点击，绕过 closed shadow root 限制。

        Args:
            timeout: 最大等待时间（秒）
            check_interval: 检测间隔（秒）

        Returns:
            bool: 是否成功通过验证

        Example:
            page.get('https://example.com')
            if page.handle_cloudflare_challenge():
                print('通过验证')
        """
        import random

        start_time = time.time()
        attempt = 0

        while time.time() - start_time < timeout:
            attempt += 1
            logger.info(f"CF 验证第 {attempt} 次尝试...")

            try:
                # 用 browsingContext.getTree 查找 CF iframe
                tree = self._driver._browser_driver.run("browsingContext.getTree", {})
                all_contexts = tree.get("contexts", [])

                def find_cf_context(ctxs):
                    """递归查找 CF iframe context"""
                    for c in ctxs:
                        url = c.get("url", "")
                        if (
                            "challenges.cloudflare.com" in url
                            or "turnstile" in url
                            or "cf-chl" in url
                        ):
                            return c
                        found = find_cf_context(c.get("children", []))
                        if found:
                            return found
                    return None

                cf_ctx = find_cf_context(all_contexts)

                if not cf_ctx:
                    logger.debug("未找到 CF iframe，继续等待...")
                    time.sleep(check_interval)
                    continue

                cf_ctx_id = cf_ctx["context"]
                logger.info(f"找到 CF iframe: {cf_ctx_id[:20]}")

                # 获取 iframe 尺寸
                result = self._driver._browser_driver.run(
                    "script.evaluate",
                    {
                        "expression": """(() => {
                        const rect = document.documentElement.getBoundingClientRect();
                        return {w: Math.round(rect.width), h: Math.round(rect.height)};
                    })()""",
                        "target": {"context": cf_ctx_id},
                        "awaitPromise": False,
                    },
                )

                # 解析 BiDi 嵌套对象格式
                raw_value = result.get("result", {}).get("value", [])
                size = {}
                if isinstance(raw_value, list):
                    for item in raw_value:
                        if isinstance(item, list) and len(item) == 2:
                            key = item[0]
                            val_obj = item[1]
                            if isinstance(val_obj, dict) and "value" in val_obj:
                                size[key] = val_obj["value"]

                if size.get("w", 0) == 0 or size.get("h", 0) == 0:
                    logger.warning("无法获取 iframe 尺寸")
                    time.sleep(check_interval)
                    continue

                logger.info(f"iframe 尺寸: {size['w']}×{size['h']}")

                # 在 CF iframe 内部查找 checkbox
                checkbox_result = self._driver._browser_driver.run(
                    "script.evaluate",
                    {
                        "expression": """(() => {
                        const checkbox = document.querySelector('input[type="checkbox"]') ||
                                       document.querySelector('[role="checkbox"]') ||
                                       document.querySelector('label');
                        if (checkbox) {
                            const rect = checkbox.getBoundingClientRect();
                            return {
                                found: true,
                                x: Math.round(rect.left + rect.width / 2),
                                y: Math.round(rect.top + rect.height / 2)
                            };
                        }
                        return {found: false};
                    })()""",
                        "target": {"context": cf_ctx_id},
                        "awaitPromise": False,
                    },
                )

                # 解析 checkbox 位置
                checkbox_raw = checkbox_result.get("result", {}).get("value", [])
                checkbox_data = {}
                if isinstance(checkbox_raw, list):
                    for item in checkbox_raw:
                        if isinstance(item, list) and len(item) == 2:
                            key = item[0]
                            val = item[1]
                            if isinstance(val, dict):
                                checkbox_data[key] = val.get("value", False)

                # 直接在 CF iframe 内部触发点击（绕过 closed shadow root）
                if checkbox_data.get("found"):
                    click_x = int(checkbox_data["x"])
                    click_y = int(checkbox_data["y"])
                    logger.info(f"在 iframe 内部点击 checkbox: ({click_x}, {click_y})")
                else:
                    # fallback: 点击 iframe 左侧（checkbox 通常在左边）
                    click_x = 35
                    click_y = size["h"] // 2
                    logger.info(f"在 iframe 内部点击左侧: ({click_x}, {click_y})")

                self._driver._browser_driver.run(
                    "input.performActions",
                    {
                        "context": cf_ctx_id,
                        "actions": [
                            {
                                "type": "pointer",
                                "id": "mouse_cf",
                                "parameters": {"pointerType": "mouse"},
                                "actions": [
                                    {
                                        "type": "pointerMove",
                                        "x": click_x,
                                        "y": click_y,
                                        "duration": 0,
                                    },
                                    {
                                        "type": "pause",
                                        "duration": random.randint(50, 150),
                                    },
                                    {"type": "pointerDown", "button": 0},
                                    {
                                        "type": "pause",
                                        "duration": random.randint(80, 160),
                                    },
                                    {"type": "pointerUp", "button": 0},
                                ],
                            }
                        ],
                    },
                )

                # 等待验证结果
                time.sleep(3)

                # 检查是否通过
                body_text = self.run_js("document.body.innerText") or ""
                if len(body_text) > 200 and "verify" not in body_text.lower()[:500]:
                    logger.info("成功通过 CF 验证")
                    return True

            except Exception as e:
                logger.warning(f"CF 验证失败: {e}")
                time.sleep(check_interval)
                continue

        logger.error(f"CF 验证超时（{timeout}秒）")
        return False

    # ===== Emulation 便捷方法 =====

    def set_geolocation(self, latitude, longitude, accuracy=100):
        """设置地理位置 (FF139+)

        Args:
            latitude: 纬度
            longitude: 经度
            accuracy: 精度（米）

        Returns:
            self
        """
        self.emulation.set_geolocation(latitude, longitude, accuracy)
        return self

    def set_timezone(self, timezone_id):
        """设置时区 (FF144+)，如 'Asia/Shanghai'

        Returns:
            self
        """
        self.emulation.set_timezone(timezone_id)
        return self

    def set_locale(self, locales):
        """设置语言 (FF142+)，如 ['zh-CN', 'zh'] 或 'zh-CN'

        Returns:
            self
        """
        self.emulation.set_locale(locales)
        return self

    def set_screen_orientation(self, orientation_type, angle=0):
        """设置屏幕方向 (FF144+)

        Args:
            orientation_type: 'portrait-primary'/'landscape-primary' 等
            angle: 0/90/180/270

        Returns:
            self
        """
        self.emulation.set_screen_orientation(orientation_type, angle)
        return self

    # ===== Script Realm =====

    def get_realms(self, type_=None):
        """获取当前 context 的所有 Realm（执行上下文）。

        Args:
            type_: 可选的 realm 类型过滤。
                常见值：``'window'``、``'dedicated-worker'``、``'service-worker'``。

        Returns:
            list[RealmInfo]: 支持属性访问的 realm 对象列表。

        适用场景：
            - 查看当前页面有哪些执行上下文
            - 区分 window realm 和 worker realm
            - 结合 script 相关测试验证 realm 数量和类型
        """
        from .._bidi import script as bidi_script
        from .._units.script_tools import RealmInfo

        result = bidi_script.get_realms(
            self._driver._browser_driver, context=self._context_id, type_=type_
        )
        return [RealmInfo(i) for i in result.get("realms", [])]

    def disown_handles(self, handles):
        """释放当前 context 下的远程对象句柄。

        Args:
            handles: 远程对象句柄列表。
                常见值：``[result.result.handle]`` 或多个 handle 组成的列表。

        Returns:
            self: 原页面对象，便于链式调用。

        适用场景：
            - 手动释放 ``script.evaluate`` / ``callFunction`` 返回的远程对象句柄
            - 验证 ``script.disown`` 生命周期行为

        说明：
            - ``handle`` 可以理解为浏览器端某个远程 JS 对象的引用。
            - 当你不再需要这个远程对象时，调用本方法可以通知浏览器释放它。
        """
        from .._bidi import script as bidi_script

        bidi_script.disown(
            self._driver._browser_driver,
            handles=list(handles),
            target={"context": self._context_id},
        )
        return self

    def eval_handle(self, expression, await_promise=True):
        """执行脚本并以高层结果对象形式返回远程值。

        Args:
            expression: JavaScript 表达式字符串。
            await_promise: 是否等待 Promise resolve。

        Returns:
            ScriptResult: 支持 ``success/result.handle/result.value`` 属性访问的结果对象。

        适用场景：
            - 需要拿到 script 远程对象 handle 再做 ``disown``
            - 避免示例继续直接处理底层返回字典

        说明：
            - 如果表达式返回的是对象，通常会得到一个 ``handle``。
            - 如果表达式返回的是普通值，通常看 ``result.value`` 即可。
        """
        from .._bidi import script as bidi_script
        from .._units.script_tools import ScriptResult

        result = bidi_script.evaluate(
            self._driver._browser_driver,
            context=self._context_id,
            expression=expression,
            await_promise=await_promise,
        )
        return ScriptResult(result)

    # ===== 缓存控制 =====

    def set_cache_behavior(self, behavior="bypass"):
        """设置缓存行为

        Args:
            behavior: 'default' 正常缓存 / 'bypass' 绕过缓存

        Returns:
            self
        """
        from .._bidi import network as bidi_network

        try:
            bidi_network.set_cache_behavior(
                self._driver._browser_driver,
                behavior=behavior,
                contexts=[self._context_id],
            )
        except Exception as e:
            logger.debug("set_cache_behavior 失败: %s", e)
        return self

    # ===== 下载控制 =====

    def set_download_path(self, path):
        """设置当前页面下载目录。

        Args:
            path: 下载目录路径。
                单位：文件系统路径字符串。
                常见值：项目内绝对路径，例如 ``'E:/ruyipage/examples/downloads'``。

        Returns:
            self: 原页面对象，便于链式调用。

        适用场景：
            - 希望当前 tab 的下载直接落到指定目录
            - 兼容旧调用方式，但内部统一走 ``page.downloads``
        """
        try:
            return self.downloads.set_path(path)
        except Exception as e:
            logger.debug("set_download_path 失败: %s", e)
        return self
