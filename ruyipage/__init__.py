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
from ._base.browser import Firefox, find_existing_browsers
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


def attach_exist_browser(address="127.0.0.1:9222", tab_index=1, latest_tab=False):
    """接管一个已经启动的 Firefox 浏览器。

    Args:
        address: 调试地址，例如 127.0.0.1:9222
        tab_index: 接管后默认切到第几个 tab，按 1 开始计数
        latest_tab: True 时优先切到最新 tab，忽略 tab_index

    Returns:
        FirefoxPage
    """
    page = attach(address)
    target_tab = None

    if latest_tab:
        target_tab = page.latest_tab
    elif tab_index is not None:
        target_tab = page.get_tab(tab_index)

    if target_tab:
        page.browser.activate_tab(target_tab)
        page._context_id = target_tab.tab_id
        page._driver = type(page._driver)(page.browser.driver, target_tab.tab_id)

    return page


def auto_attach_exist_browser(
    address=None,
    host="127.0.0.1",
    start_port=9222,
    end_port=65535,
    timeout=0.2,
    tab_index=1,
    latest_tab=False,
):
    """自动接管一个已经启动的 Firefox 浏览器。

    优先连接显式 address；若未提供或连接失败，则暴力扫描端口范围，
    适合某些 Firefox 指纹浏览器把 ``--remote-debugging-port`` 改成随机端口的场景。

    Args:
        address: 已知调试地址，例如 127.0.0.1:9222。传入后先尝试直连。
        host: 扫描主机，默认 127.0.0.1
        start_port: 扫描起始端口
        end_port: 扫描结束端口
        timeout: 单端口探测超时（秒）
        tab_index: 接管后默认切到第几个 tab，按 1 开始计数
        latest_tab: True 时优先切到最新 tab，忽略 tab_index

    Returns:
        FirefoxPage
    """
    if address:
        try:
            return attach_exist_browser(
                address=address,
                tab_index=tab_index,
                latest_tab=latest_tab,
            )
        except Exception:
            pass

    browsers = find_exist_browsers(
        host=host,
        start_port=start_port,
        end_port=end_port,
        timeout=timeout,
    )
    if not browsers:
        raise RuntimeError(
            "没有发现可接管的 Firefox 浏览器，请检查调试端口是否开启，"
            "或扩大扫描端口范围。"
        )

    return attach_exist_browser(
        address=browsers[0]["address"],
        tab_index=tab_index,
        latest_tab=latest_tab,
    )


def find_exist_browsers(host="127.0.0.1", start_port=9222, end_port=9322, timeout=0.5):
    """发现当前机器上可接管的 Firefox 浏览器列表。"""
    return find_existing_browsers(
        host=host, start_port=start_port, end_port=end_port, timeout=timeout
    )


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
    "attach_exist_browser",
    "auto_attach_exist_browser",
    "find_exist_browsers",
    # 版本
    "__version__",
]
