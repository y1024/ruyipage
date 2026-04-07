# -*- coding: utf-8 -*-
"""nsIPrefBranch 运行时读写适配

Firefox 内容沙箱（BiDi script.evaluate）无法访问 Services.prefs（nsIPrefBranch）。
本模块提供三种降级策略：

优先级：
  1. Marionette getPrefs（无需 session，只读）
  2. user.js 文件读取（只读已持久化的值）
  3. BiDi addPreloadScript 注入（下次导航后生效）

写入策略：
  - 唯一可靠方案：写入 profile/user.js，重启后生效
  - 运行时写入：user.js + reload（当前页面立即生效）
"""

import os
import re
import logging

logger = logging.getLogger('ruyipage')


class PrefBranch:
    """nsIPrefBranch 适配器

    统一封装三种读写策略，对上层透明。
    """

    def __init__(self, profile_path=None, marionette_host='127.0.0.1',
                 marionette_port=2828):
        self._profile = profile_path
        self._marionette_host = marionette_host
        self._marionette_port = marionette_port
        self._marionette = None  # 惰性初始化

    def _get_marionette(self):
        if self._marionette is None:
            from .marionette import MarionetteClient
            self._marionette = MarionetteClient(
                self._marionette_host, self._marionette_port)
        return self._marionette

    def _user_js(self):
        if not self._profile:
            return None
        return os.path.join(self._profile, 'user.js')

    # ── 读取 ──────────────────────────────────────────────────────────────

    def get(self, key):
        """读取 pref 值

        策略：Marionette → user.js → None
        """
        # 1. Marionette（运行时值，最准确）
        try:
            m = self._get_marionette()
            val = m.get_pref(key)
            if val is not None:
                return val
        except Exception:
            pass

        # 2. user.js 文件
        return self._read_user_js(key)

    def get_all(self, prefix=''):
        """从 user.js 读取所有匹配前缀的 prefs"""
        path = self._user_js()
        if not path or not os.path.exists(path):
            return {}
        content = open(path, encoding='utf-8', errors='ignore').read()
        result = {}
        for m in re.finditer(
                r'user_pref\s*\(\s*["\'](.+?)["\'],\s*(.+?)\s*\)', content):
            k, v = m.group(1), m.group(2).strip()
            if not k.startswith(prefix):
                continue
            result[k] = _parse_pref_value(v)
        return result

    def _read_user_js(self, key):
        path = self._user_js()
        if not path or not os.path.exists(path):
            return None
        content = open(path, encoding='utf-8', errors='ignore').read()
        pattern = (r'user_pref\s*\(\s*["\']'
                   + re.escape(key) + r'["\'],\s*(.+?)\s*\)')
        m = re.search(pattern, content)
        return _parse_pref_value(m.group(1).strip()) if m else None

    # ── 写入 ──────────────────────────────────────────────────────────────

    def set(self, key, value):
        """写入 pref 到 user.js（持久化，重启后生效）"""
        path = self._user_js()
        if not path:
            raise RuntimeError('未设置 profile 路径，无法写入 pref')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        content = open(path, encoding='utf-8', errors='ignore').read() \
            if os.path.exists(path) else ''
        line = 'user_pref("{}", {});'.format(key, _format_pref_value(value))
        pattern = r'user_pref\s*\(\s*["\']' + re.escape(key) + r'["\'].*?\);'
        if re.search(pattern, content):
            content = re.sub(pattern, line, content)
        else:
            content = content.rstrip('\n') + '\n' + line + '\n'
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)

    def reset(self, key):
        """从 user.js 移除 pref（恢复默认）"""
        path = self._user_js()
        if not path or not os.path.exists(path):
            return
        content = open(path, encoding='utf-8', errors='ignore').read()
        pattern = (r'\nuser_pref\s*\(\s*["\']'
                   + re.escape(key) + r'["\'].*?\);\n?')
        content = re.sub(pattern, '\n', content)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)


def _parse_pref_value(v):
    """解析 user.js 中的 pref 值字符串"""
    if v == 'true':
        return True
    if v == 'false':
        return False
    if v.startswith('"') or v.startswith("'"):
        return v[1:-1]
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        return v


def _format_pref_value(value):
    """将 Python 值格式化为 user.js pref 值字符串"""
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    return '"{}"'.format(str(value).replace('\\', '\\\\').replace('"', '\\"'))
