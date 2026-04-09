# -*- coding: utf-8 -*-
"""示例39: 先启动 Firefox/指纹浏览器，再由 ruyipage 接管。

如果你使用的是 Firefox 指纹浏览器，请先在浏览器后台的默认启动参数里加入：
    --remote-debugging-port=9222

只有在浏览器暴露了 Firefox Remote Agent / WebDriver BiDi 调试端口后，
ruyipage 才能通过 find_exist_browsers() 和 attach_exist_browser() 接管它。

如果浏览器后台不允许固定端口，或者会像 ADS / FlowerBrowser 那样把
--remote-debugging-port=9222 改写成 --remote-debugging-port=0，
那么实际监听端口会变成随机值。这时可以改用
auto_attach_exist_browser(start_port=6000, end_port=20000, latest_tab=True)
在指定范围内暴力扫描可接管端口并自动接入。
"""

import sys
import os


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


from ruyipage import (
    attach_exist_browser,
    auto_attach_exist_browser,
    find_exist_browsers,
)


TARGET_URL = "https://0xshoulderlab.site/automation"


def demo_attach_exist_browser():
    print("=" * 60)
    print("示例39: 接管已启动浏览器")
    print("=" * 60)

    port = 6864

    print("1. 请先手工启动 Firefox 或 Firefox 指纹浏览器")
    print("   若是指纹浏览器，请在默认启动参数中加入:")
    print("   --remote-debugging-port={}".format(port))
    print("   启动后再运行本示例进行扫描和接管。")
    print("   若浏览器把固定端口改成随机端口，本示例会自动降级为暴力扫描。")
    print()

    print("2. 先扫描可接管浏览器...")
    browsers = find_exist_browsers(start_port=port, end_port=port + 10)
    for item in browsers:
        print(
            "   - {address} | ready={ready} | windows={window_count} | tabs={tab_count}".format(
                **item
            )
        )

    if browsers:
        print("3. 发现实例，直接接管...")
        page = attach_exist_browser(browsers[0]["address"], latest_tab=True)
    else:
        print("3. 未发现实例，开始暴力扫描...")
        print("   适用于 ADS / FlowerBrowser 这类会把 remote port 改成随机值的场景。")
        page = auto_attach_exist_browser(
            start_port=6800,
            end_port=6900,
            timeout=0.15,
            latest_tab=True,
        )
        print("   已自动接入:", page.browser.address)

    try:
        print("   当前标题:", page.title)
        print("   当前地址:", page.url)

        page.get(TARGET_URL)
        page.wait(2)
        print("   接管后已跳转到:", page.url)
        print("   当前标签页数量:", page.tabs_count)

        print("4. 打印可见标签页:")
        for index, tab_id in enumerate(page.tab_ids, start=1):
            tab = page.get_tab(index)
            print("   [{}] {} | {}".format(index, tab.title, tab.url))
    finally:
        print("\n示例结束。这里不自动关闭浏览器，便于继续手工观察。")


if __name__ == "__main__":
    demo_attach_exist_browser()
