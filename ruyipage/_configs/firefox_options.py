# -*- coding: utf-8 -*-
"""Firefox 浏览器启动配置"""

import os
import sys


class FirefoxOptions(object):
    """Firefox 浏览器启动选项

    用法::

        opts = FirefoxOptions()
        opts.set_port(9222)
        opts.headless()
        opts.set_proxy('http://127.0.0.1:7890')
        opts.set_fpfile('/path/to/fingerprint.json')
        opts.set_window_size(1920, 1080)
        page = FirefoxPage(opts)

    新手最常改的基础项：
        1. 浏览器程序路径
           例如 Firefox 安装在非默认位置时，用 ``set_browser_path()``。
        2. 用户目录 / profile 目录
           例如想复用自己已有登录态、Cookie、扩展时，用 ``set_user_dir()``。
        3. 端口
           例如同机多开时，用 ``set_port()``。
    """

    def __init__(self):
        # 浏览器可执行文件路径
        if sys.platform == "win32":
            self._browser_path = r"C:\Program Files\Mozilla Firefox\firefox.exe"
        elif sys.platform == "darwin":
            self._browser_path = "/Applications/Firefox.app/Contents/MacOS/firefox"
        else:
            self._browser_path = "firefox"

        self._address = "127.0.0.1"
        self._port = 9222
        self._profile_path = None
        self._arguments = []
        self._preferences = {}
        self._headless = False
        self._download_path = "."
        self._load_mode = "normal"  # 'normal', 'eager', 'none'
        self._timeouts = {
            "base": 10,
            "page_load": 30,
            "script": 30,
        }
        self._existing_only = False
        self._retry_times = 10
        self._retry_interval = 2.0
        self._proxy = None
        self._auto_port = False
        self._user_context = None  # 容器标签页
        self._fpfile = None  # 指纹配置文件路径
        self._user_prompt_handler = None  # session.UserPromptHandler

    # ===== 属性读取 =====

    @property
    def browser_path(self):
        return self._browser_path

    @property
    def address(self):
        return "{}:{}".format(self._address, self._port)

    @property
    def host(self):
        return self._address

    @property
    def port(self):
        return self._port

    @property
    def profile_path(self):
        return self._profile_path

    @property
    def arguments(self):
        return self._arguments[:]

    @property
    def preferences(self):
        return self._preferences.copy()

    @property
    def is_headless(self):
        return self._headless

    @property
    def download_path(self):
        return self._download_path

    @property
    def load_mode(self):
        return self._load_mode

    @property
    def timeouts(self):
        return self._timeouts.copy()

    @property
    def is_existing_only(self):
        return self._existing_only

    @property
    def retry_times(self):
        return self._retry_times

    @property
    def retry_interval(self):
        return self._retry_interval

    @property
    def proxy(self):
        return self._proxy

    @property
    def auto_port(self):
        return self._auto_port

    @property
    def fpfile(self):
        """指纹配置文件路径"""
        return self._fpfile

    @property
    def user_prompt_handler(self):
        """session 级默认用户提示框处理策略。"""
        return (
            dict(self._user_prompt_handler)
            if isinstance(self._user_prompt_handler, dict)
            else None
        )

    # ===== 链式设置方法 =====

    def set_browser_path(self, path):
        """设置浏览器可执行文件路径。

        Args:
            path: Firefox 可执行文件路径。
                常见值：
                Windows: ``r'C:\\Program Files\\Mozilla Firefox\\firefox.exe'``
                macOS: ``'/Applications/Firefox.app/Contents/MacOS/firefox'``
                Linux: ``'/usr/bin/firefox'``

        Returns:
            self: 原配置对象，便于链式调用。

        适用场景：
            - Firefox 安装在非默认目录
            - 同时存在多个 Firefox 版本，想指定其中一个
            - 便携版 Firefox 需要显式指定 exe 路径
        """
        self._browser_path = path
        return self

    def set_address(self, address):
        """设置连接地址（host:port 或仅 host）

        Args:
            address: '127.0.0.1:9222' 或 '127.0.0.1'

        Returns:
            self
        """
        if ":" in str(address):
            parts = str(address).rsplit(":", 1)
            self._address = parts[0]
            self._port = int(parts[1])
        else:
            self._address = str(address)
        return self

    def set_port(self, port):
        """设置远程调试端口

        Args:
            port: 端口号

        Returns:
            self
        """
        self._port = int(port)
        return self

    def set_profile(self, path):
        """设置 Firefox 配置文件路径。

        Args:
            path: profile 目录路径。
                这就是很多人常说的 userdir / 用户目录。
                常见值：
                Windows: ``r'D:\firefox_profile'``
                Linux/macOS: ``'/Users/name/firefox_profile'``

        Returns:
            self: 原配置对象，便于链式调用。

        适用场景：
            - 想复用已有登录状态、Cookie、本地存储
            - 想让浏览器持久保存数据，而不是每次用临时目录
            - 想加载已安装到该 profile 的扩展、证书、首选项

        说明：
            - 如果不设置，ruyipage 会自动创建一个临时 profile。
            - 临时 profile 适合一次性测试，但关闭后通常会被清理。
            - 想长期复用浏览器数据时，建议显式设置这个路径。
        """
        self._profile_path = path
        return self

    def set_user_dir(self, path):
        """设置用户目录（userdir）。

        这是 ``set_profile()`` 的新手友好别名。

        Args:
            path: 用户目录 / profile 目录路径。
                常见值：``r'D:\\my_firefox_userdir'``。

        Returns:
            self: 原配置对象，便于链式调用。

        适用场景：
            - 你只知道“我要设置 userdir”，但不关心 Firefox 内部叫 profile
            - 教程和快速开始里希望用更直白的名字
        """
        return self.set_profile(path)

    def set_argument(self, arg, value=None):
        """添加启动参数

        Args:
            arg: 参数名，如 '--width'
            value: 参数值，如 '1920'

        Returns:
            self
        """
        if value is not None:
            self._arguments.append("{}={}".format(arg, value))
        else:
            if arg not in self._arguments:
                self._arguments.append(arg)
        return self

    def remove_argument(self, arg):
        """移除启动参数

        Args:
            arg: 参数名

        Returns:
            self
        """
        self._arguments = [
            a for a in self._arguments if a != arg and not a.startswith(arg + "=")
        ]
        return self

    def set_pref(self, key, value):
        """设置 Firefox 首选项（about:config）

        Args:
            key: 首选项名称
            value: 首选项值

        Returns:
            self
        """
        self._preferences[key] = value
        return self

    def set_user_prompt_handler(self, handler):
        """设置 session 级默认用户提示框处理策略。

        Args:
            handler: dict，键可包含 alert/beforeUnload/confirm/default/file/prompt
                     值必须为 'accept' / 'dismiss' / 'ignore'

        Returns:
            self
        """
        self._user_prompt_handler = dict(handler) if handler else None
        return self

    def headless(self, on_off=True):
        """设置无头模式

        Args:
            on_off: True 启用无头，False 禁用

        Returns:
            self
        """
        self._headless = on_off
        return self

    def set_proxy(self, proxy):
        """设置代理

        Args:
            proxy: 代理地址，如 'http://127.0.0.1:7890' 或 'socks5://127.0.0.1:1080'

        Returns:
            self
        """
        self._proxy = proxy
        return self

    def set_download_path(self, path):
        """设置下载路径

        Args:
            path: 下载目录路径

        Returns:
            self
        """
        self._download_path = os.path.abspath(path)
        return self

    def set_load_mode(self, mode):
        """设置加载模式

        Args:
            mode: 'normal' 完全加载 / 'eager' DOMContentLoaded / 'none' 不等待

        Returns:
            self
        """
        if mode not in ("normal", "eager", "none"):
            raise ValueError("load_mode 必须是 'normal', 'eager' 或 'none'")
        self._load_mode = mode
        return self

    def set_timeouts(self, base=None, page_load=None, script=None):
        """设置各种超时时间（秒）

        Args:
            base: 基础超时（元素查找等）
            page_load: 页面加载超时
            script: 脚本执行超时

        Returns:
            self
        """
        if base is not None:
            self._timeouts["base"] = base
        if page_load is not None:
            self._timeouts["page_load"] = page_load
        if script is not None:
            self._timeouts["script"] = script
        return self

    def existing_only(self, on_off=True):
        """仅连接已有浏览器，不启动新的

        Args:
            on_off: True 仅连接

        Returns:
            self
        """
        self._existing_only = on_off
        return self

    def set_auto_port(self, on_off=True):
        """自动寻找可用端口

        Args:
            on_off: True 自动端口 / int 指定范围起始端口

        Returns:
            self
        """
        self._auto_port = on_off
        return self

    def set_retry(self, times=None, interval=None):
        """设置连接重试

        Args:
            times: 重试次数
            interval: 重试间隔（秒）

        Returns:
            self
        """
        if times is not None:
            self._retry_times = times
        if interval is not None:
            self._retry_interval = interval
        return self

    def set_fpfile(self, path):
        """设置指纹配置文件路径

        指纹配置文件用于浏览器指纹伪装，通过 --fpfile 参数传递给 Firefox。

        Args:
            path: 指纹配置文件的路径

        Returns:
            self
        """
        self._fpfile = path
        return self

    def set_window_size(self, width, height):
        """设置浏览器窗口大小

        通过 --width 和 --height 启动参数设置窗口初始大小。

        Args:
            width: 窗口宽度（像素）
            height: 窗口高度（像素）

        Returns:
            self
        """
        # 先移除已有的 width/height 参数
        self._arguments = [
            a
            for a in self._arguments
            if not a.startswith("--width=") and not a.startswith("--height=")
        ]
        self._arguments.append("--width={}".format(int(width)))
        self._arguments.append("--height={}".format(int(height)))
        return self

    def quick_start(
        self,
        *,
        browser_path=None,
        user_dir=None,
        headless=False,
        window_size=(1280, 800),
        timeout_base=10,
        timeout_page_load=30,
        timeout_script=30,
    ):
        """小白友好的一键启动预设。

        该方法会一次性设置常用参数，便于快速开始。
        这是给“先跑起来再深入”的使用场景准备的快捷入口。

        Args:
            browser_path: Firefox 可执行文件路径。
                适用于 Firefox 安装在非默认目录时。
            user_dir: 用户目录 / profile 目录。
                适用于希望复用登录态、Cookie、扩展时。
            headless: 是否无头
            window_size: 窗口大小 (width, height)
            timeout_base: 基础超时
            timeout_page_load: 页面加载超时
            timeout_script: 脚本执行超时

        Returns:
            self

        典型用法::

            opts = FirefoxOptions().set_port(9222).quick_start(
                browser_path=r"D:\\FirefoxPortable\\firefox.exe",
                user_dir=r"D:\\my_firefox_userdir",
                headless=False,
            )
            page = FirefoxPage(opts)
        """
        if browser_path:
            self.set_browser_path(browser_path)
        if user_dir:
            self.set_user_dir(user_dir)
        self.headless(headless)
        if window_size and len(window_size) == 2:
            self.set_window_size(window_size[0], window_size[1])
        self.set_timeouts(
            base=timeout_base,
            page_load=timeout_page_load,
            script=timeout_script,
        )
        return self

    def build_command(self):
        """构建 Firefox 启动命令行

        Returns:
            命令参数列表
        """
        cmd = [self._browser_path]

        cmd.append("--remote-debugging-port={}".format(self._port))
        cmd.append("--no-remote")
        cmd.append("--marionette")

        if self._profile_path:
            cmd.append("--profile")
            cmd.append(self._profile_path)

        if self._headless:
            cmd.append("--headless")

        if self._fpfile:
            cmd.extend(["--fpfile", self._fpfile])

        for arg in self._arguments:
            cmd.append(arg)

        return cmd

    def write_prefs_to_profile(self):
        """将首选项和代理设置写入 profile 的 user.js

        如果设置了 preferences 或 proxy，需要写入 user.js 文件
        """
        if not self._profile_path:
            return

        prefs = dict(self._preferences)

        # 自动化推荐设置
        prefs.setdefault("remote.prefs.recommended", True)
        prefs.setdefault("datareporting.policy.dataSubmissionEnabled", False)
        prefs.setdefault("toolkit.telemetry.reportingpolicy.firstRun", False)
        prefs.setdefault("browser.shell.checkDefaultBrowser", False)
        prefs.setdefault("browser.startup.homepage_override.mstone", "ignore")
        prefs.setdefault("browser.tabs.warnOnClose", False)
        prefs.setdefault("browser.warnOnQuit", False)
        # 启用 Marionette（特权 JS 通道，用于 about:config 运行时读写）
        prefs.setdefault("marionette.enabled", True)

        # 下载设置
        if self._download_path:
            prefs["browser.download.dir"] = self._download_path
            prefs["browser.download.folderList"] = 2
            prefs["browser.download.useDownloadDir"] = True

        # 代理设置
        if self._proxy:
            proxy = self._proxy
            if "://" in proxy:
                scheme, addr = proxy.split("://", 1)
            else:
                scheme, addr = "http", proxy

            host, port = addr.rsplit(":", 1) if ":" in addr else (addr, "8080")

            if scheme.startswith("socks"):
                prefs["network.proxy.type"] = 1
                prefs["network.proxy.socks"] = host
                prefs["network.proxy.socks_port"] = int(port)
                prefs["network.proxy.socks_version"] = 5 if "5" in scheme else 4
            else:
                prefs["network.proxy.type"] = 1
                prefs["network.proxy.http"] = host
                prefs["network.proxy.http_port"] = int(port)
                prefs["network.proxy.ssl"] = host
                prefs["network.proxy.ssl_port"] = int(port)

        if not prefs:
            return

        os.makedirs(self._profile_path, exist_ok=True)
        user_js_path = os.path.join(self._profile_path, "user.js")

        lines = []
        for key, value in prefs.items():
            if isinstance(value, bool):
                val_str = "true" if value else "false"
            elif isinstance(value, int):
                val_str = str(value)
            elif isinstance(value, str):
                val_str = '"{}"'.format(value.replace("\\", "\\\\").replace('"', '\\"'))
            else:
                val_str = '"{}"'.format(value)
            lines.append('user_pref("{}", {});'.format(key, val_str))

        with open(user_js_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
