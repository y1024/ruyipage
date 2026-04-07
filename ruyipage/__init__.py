# -*- coding: utf-8 -*-
"""
RuyiPage - 基于 WebDriver BiDi 协议的 Firefox 浏览器自动化框架

用法::

    from ruyipage import FirefoxPage, FirefoxOptions

    # 快速开始
    page = FirefoxPage()
    page.get('https://example.com')
    print(page.title)

    # 自定义配置
    opts = FirefoxOptions()
    opts.set_port(9222).headless()
    page = FirefoxPage(opts)
"""

from .version import __version__
from ._pages.firefox_page import FirefoxPage
from ._pages.firefox_tab import FirefoxTab
from ._pages.firefox_frame import FirefoxFrame
from ._base.browser import Firefox
from ._configs.firefox_options import FirefoxOptions
from ._elements.firefox_element import FirefoxElement
from ._elements.none_element import NoneElement
from ._elements.static_element import StaticElement
from ._functions.settings import Settings
from ._functions.keys import Keys
from ._functions.by import By
from ._units.extensions import ExtensionManager
from ._units.events import BidiEvent
from ._units.interceptor import InterceptedRequest
from ._units.listener import DataPacket
from ._units.network_tools import DataCollector, NetworkData
from ._units.cookies import CookieInfo
from ._units.script_tools import (
    RealmInfo,
    ScriptRemoteValue,
    ScriptResult,
    PreloadScript,
)
from .errors import (
    RuyiPageError,
    ElementNotFoundError,
    ElementLostError,
    ContextLostError,
    BiDiError,
    PageDisconnectedError,
    JavaScriptError,
    BrowserConnectError,
    BrowserLaunchError,
    AlertExistsError,
    WaitTimeoutError,
    NoRectError,
    CanNotClickError,
    LocatorError,
)


def launch(
    *,
    headless=False,
    port=9222,
    browser_path=None,
    user_dir=None,
    window_size=(1280, 800),
    timeout_base=10,
    timeout_page_load=30,
    timeout_script=30,
):
    """快速启动 FirefoxPage（小白友好入口）。

    Args:
        headless: 是否无头
        port: 远程调试端口
        browser_path: Firefox 可执行文件路径。
            适用于 Firefox 安装在非默认目录时。
        user_dir: 用户目录 / profile 目录。
            适用于希望复用登录态、Cookie、扩展时。
        window_size: 窗口大小 (width, height)
        timeout_base: 基础超时
        timeout_page_load: 页面加载超时
        timeout_script: 脚本执行超时

    Returns:
        FirefoxPage

    说明:
        - 推荐新手优先使用 launch()。
        - 内部自动创建 FirefoxOptions 并套用 quick_start 预设。
        - 当你不确定该配置哪些参数时，先从 launch() 开始。
    """
    opts = FirefoxOptions()
    opts.set_port(port).quick_start(
        headless=headless,
        window_size=window_size,
        timeout_base=timeout_base,
        timeout_page_load=timeout_page_load,
        timeout_script=timeout_script,
    )
    if browser_path:
        opts.set_browser_path(browser_path)
    if user_dir:
        opts.set_user_dir(user_dir)
    return FirefoxPage(opts)


def attach(address="127.0.0.1:9222"):
    """连接到已启动的 Firefox 调试地址（小白友好入口）。

    Args:
        address: 调试地址，例如 127.0.0.1:9222

    Returns:
        FirefoxPage

    说明:
        - 用于连接“已手动启动”的 Firefox 调试端口。
        - 内部启用 existing_only，避免重复启动浏览器进程。
    """
    opts = FirefoxOptions().set_address(address).existing_only(True)
    return FirefoxPage(opts)


__all__ = [
    # 核心类
    "FirefoxPage",
    "FirefoxTab",
    "FirefoxFrame",
    "Firefox",
    "FirefoxOptions",
    # 元素
    "FirefoxElement",
    "NoneElement",
    "StaticElement",
    # 配置
    "Settings",
    "Keys",
    "By",
    # 单元
    "ExtensionManager",
    "BidiEvent",
    "InterceptedRequest",
    "DataPacket",
    "DataCollector",
    "NetworkData",
    "CookieInfo",
    "RealmInfo",
    "ScriptRemoteValue",
    "ScriptResult",
    "PreloadScript",
    # 异常
    "RuyiPageError",
    "ElementNotFoundError",
    "ElementLostError",
    "ContextLostError",
    "BiDiError",
    "PageDisconnectedError",
    "JavaScriptError",
    "BrowserConnectError",
    "BrowserLaunchError",
    "AlertExistsError",
    "WaitTimeoutError",
    "NoRectError",
    "CanNotClickError",
    "LocatorError",
    # 便捷入口
    "launch",
    "attach",
    # 版本
    "__version__",
]
