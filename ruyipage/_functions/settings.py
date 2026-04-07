# -*- coding: utf-8 -*-
"""全局设置"""


class Settings(object):
    """全局配置，类属性直接使用，无需实例化"""

    # 元素未找到时是否抛出异常
    raise_when_ele_not_found = False

    # 点击失败时是否抛出异常
    raise_when_click_failed = False

    # 等待失败时是否抛出异常
    raise_when_wait_failed = False

    # 是否使用单例模式管理标签页对象
    singleton_tab_obj = True

    # BiDi 命令默认超时（秒）
    bidi_timeout = 30

    # 浏览器连接默认超时（秒）
    browser_connect_timeout = 30

    # 元素查找默认超时（秒）
    element_find_timeout = 10

    # 页面加载默认超时（秒）
    page_load_timeout = 30

    # 脚本执行默认超时（秒）
    script_timeout = 30
