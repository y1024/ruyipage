# -*- coding: utf-8 -*-
"""BiDi storage 模块命令"""


def get_cookies(driver, filter_=None, partition=None):
    """获取 Cookie

    Args:
        filter_: Cookie 过滤条件 {'name': str, 'domain': str, ...}
        partition: 分区 {'context': str} 或 {'userContext': str, 'sourceOrigin': str}

    Returns:
        {'cookies': [CookieInfo...], 'partitionKey': dict}
    """
    params = {}
    if filter_:
        params['filter'] = filter_
    if partition:
        params['partition'] = partition
    return driver.run('storage.getCookies', params)


def set_cookie(driver, cookie, partition=None):
    """设置 Cookie

    Args:
        cookie: Cookie 字典
            {
                'name': str,
                'value': {'type': 'string', 'value': str},
                'domain': str,
                'path': str,  # 可选
                'httpOnly': bool,  # 可选
                'secure': bool,  # 可选
                'sameSite': 'strict'|'lax'|'none',  # 可选
                'expiry': int,  # 可选，Unix 时间戳
            }
        partition: 分区

    Returns:
        {'partitionKey': dict}
    """
    params = {'cookie': cookie}
    if partition:
        params['partition'] = partition
    return driver.run('storage.setCookie', params)


def delete_cookies(driver, filter_=None, partition=None):
    """删除 Cookie

    Args:
        filter_: Cookie 过滤条件
        partition: 分区

    Returns:
        {'partitionKey': dict}
    """
    params = {}
    if filter_:
        params['filter'] = filter_
    if partition:
        params['partition'] = partition
    return driver.run('storage.deleteCookies', params)
