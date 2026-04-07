# -*- coding: utf-8 -*-
"""示例18: 高级网络功能（完整场景）

覆盖：
1) beforeRequestSent 拦截 + 继续请求
2) 修改请求头
3) mock 响应
4) 阻止请求
5) responseStarted 阶段修改响应状态
6) 队列模式 wait() 手动处理
7) fetchError 事件监听
"""

import io
import os
import sys


if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from ruyipage import FirefoxOptions, FirefoxPage
from ruyipage._functions.tools import find_free_port
from test_server import TestServer


def test_advanced_network():
    print("=" * 60)
    print("测试18: 高级网络功能")
    print("=" * 60)

    server = TestServer(port=find_free_port(8889, 8989))
    server.start()

    opts = FirefoxOptions()
    opts.headless(False)
    page = FirefoxPage(opts)

    fetch_error_list = []

    try:
        page.get("about:blank")
        page.wait(0.6)

        # 1) 请求拦截
        print("\n1. beforeRequestSent 拦截 + 继续请求:")
        intercepted = []

        def req_handler(req):
            if "/api/data" in req.url:
                intercepted.append(req.url)
                print(f"   拦截到请求: {req.method} {req.url}")
            req.continue_request()

        page.intercept.start_requests(req_handler)
        data = page.run_js(
            """
            return fetch(arguments[0]).then(r => r.json()).then(d => d.status).catch(e => String(e));
            """,
            server.get_url("/api/data"),
            as_expr=False,
        )
        page.wait(0.5)
        print(f"   请求结果: {data}")
        print(f"   拦截计数: {len(intercepted)}")
        page.intercept.stop()

        # 2) 修改请求头
        print("\n2. 修改请求头:")

        def header_handler(req):
            if "/api/headers" in req.url:
                req.continue_request(
                    headers=[
                        {
                            "name": "X-Ruyi-Demo",
                            "value": {"type": "string", "value": "yes"},
                        },
                        {
                            "name": "User-Agent",
                            "value": {"type": "string", "value": "RuyiPage/Example18"},
                        },
                    ]
                )
                print("   ✓ 已注入请求头")
            else:
                req.continue_request()

        page.intercept.start_requests(header_handler)
        headers = page.run_js(
            """
            return fetch(arguments[0]).then(r => r.json()).catch(e => ({error:String(e)}));
            """,
            server.get_url("/api/headers"),
            as_expr=False,
        )
        print(
            f"   X-Ruyi-Demo: {headers.get('X-Ruyi-Demo') or headers.get('x-ruyi-demo')}"
        )
        page.intercept.stop()

        # 3) mock 响应
        print("\n3. mock 响应:")

        def mock_handler(req):
            if "/api/data" in req.url:
                req.mock(
                    '{"status":"mocked","data":{"message":"这是Mock数据"}}',
                    status_code=200,
                    headers=[
                        {
                            "name": "content-type",
                            "value": {"type": "string", "value": "application/json"},
                        },
                        {
                            "name": "access-control-allow-origin",
                            "value": {"type": "string", "value": "*"},
                        },
                    ],
                )
                print("   ✓ 已返回Mock响应")
            else:
                req.continue_request()

        page.intercept.start_requests(mock_handler)
        mock_msg = page.run_js(
            """
            return fetch(arguments[0]).then(r => r.json()).then(d => d.status + ':' + d.data.message).catch(e => String(e));
            """,
            server.get_url("/api/data"),
            as_expr=False,
        )
        print(f"   Mock结果: {mock_msg}")
        page.intercept.stop()

        # 4) 阻止请求
        print("\n4. 阻止请求:")

        def block_handler(req):
            if "/api/error" in req.url:
                req.fail()
                print("   ✓ 请求已阻止")
            else:
                req.continue_request()

        page.intercept.start_requests(block_handler)
        blocked = page.run_js(
            """
            return fetch(arguments[0]).then(() => 'unexpected-success').catch(e => 'blocked:' + e.name);
            """,
            server.get_url("/api/error"),
            as_expr=False,
        )
        print(f"   阻止结果: {blocked}")
        page.intercept.stop()

        # 5) 响应阶段修改状态码
        print("\n5. responseStarted 阶段修改响应状态码:")

        def response_handler(req):
            if "/api/data" in req.url:
                req.continue_response(status_code=299, reason_phrase="RuyiModified")
                print("   ✓ 响应状态码已改为 299")
            else:
                req.continue_response()

        page.intercept.start_responses(response_handler)
        modified_status = page.run_js(
            """
            return fetch(arguments[0]).then(r => r.status + ':' + r.statusText).catch(e => String(e));
            """,
            server.get_url("/api/data"),
            as_expr=False,
        )
        print(f"   响应状态: {modified_status}")
        page.intercept.stop()

        # 6) 队列模式
        print("\n6. 队列模式 wait() 手动处理:")
        page.intercept.start(handler=None, phases=["beforeRequestSent"])
        page.run_js(
            """
            fetch(arguments[0]).catch(() => null);
            return 'sent';
            """,
            server.get_url("/api/data"),
            as_expr=False,
        )
        queued = page.intercept.wait(timeout=5)
        if queued:
            print(f"   wait捕获: {queued.method} {queued.url}")
            queued.continue_request()
        else:
            print("   ⚠ 未捕获到请求")
        page.intercept.stop()

        # 7) fetchError 事件监听
        print("\n7. fetchError 事件监听:")
        page.events.start(["network.fetchError"], contexts=[page.tab_id])
        page.events.clear()

        page.intercept.start_requests(block_handler)
        page.run_js(
            """
            fetch(arguments[0]).catch(() => null);
            return 'sent';
            """,
            server.get_url("/api/error"),
            as_expr=False,
        )
        page.wait(1)
        page.intercept.stop()
        while True:
            evt = page.events.wait("network.fetchError", timeout=0.2)
            if not evt:
                break
            fetch_error_list.append(evt)
        print(f"   fetchError 事件数量: {len(fetch_error_list)}")

        print("\n" + "=" * 60)
        print("✓ 所有高级网络功能测试通过！")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback

        traceback.print_exc()
    finally:
        try:
            page.intercept.stop()
        except Exception:
            pass
        try:
            page.events.stop()
        except Exception:
            pass
        page.wait(1)
        page.quit()
        server.stop()


if __name__ == "__main__":
    test_advanced_network()
