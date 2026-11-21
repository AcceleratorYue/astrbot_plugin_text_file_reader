"""astrbot_plugin_text_file_reader 的单元测试。

用 stub 替换 astrbot 框架模块，直接加载 main.py，不依赖真实 AstrBot 进程。
运行：python -m unittest discover -s tests -v
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any


PLUGIN_PATH = Path(__file__).resolve().parents[1] / "main.py"


class _Logger:
    def __getattr__(self, _name: str):
        return lambda *args, **kwargs: None


class _Star:
    def __init__(self, context):
        self.context = context


class _File:
    def __init__(self, name="", file="", url=""):
        self.name = name
        self.file_ = file
        self.url = url
        self.component = self

    async def get_file(self, allow_return_url: bool = False) -> str:
        return self.file_


class _Reply:
    def __init__(self, chain=None, **kwargs):
        self.chain = chain or []


class _TextPart:
    def __init__(self, text: str):
        self.text = text
        self.is_temp = False

    def mark_as_temp(self):
        self.is_temp = True
        return self


def _decorator(*args: Any, **kwargs: Any):
    def wrapper(func):
        return func

    return wrapper


def load_plugin_module(with_textpart: bool = True):
    astrbot = types.ModuleType("astrbot")
    api = types.ModuleType("astrbot.api")
    api.logger = _Logger()
    event_mod = types.ModuleType("astrbot.api.event")
    filter_mod = types.ModuleType("astrbot.api.event.filter")
    components_mod = types.ModuleType("astrbot.api.message_components")
    star_mod = types.ModuleType("astrbot.api.star")

    class AstrMessageEvent:  # noqa: N801
        pass

    for name in ("event_message_type", "on_llm_request", "on_decorating_result"):
        setattr(filter_mod, name, _decorator)
    filter_mod.EventMessageType = types.SimpleNamespace(
        ALL=object(),
        GROUP_MESSAGE=object(),
        PRIVATE_MESSAGE=object(),
    )
    event_mod.AstrMessageEvent = AstrMessageEvent
    event_mod.filter = filter_mod
    components_mod.File = _File
    components_mod.Reply = _Reply
    star_mod.Context = object
    star_mod.Star = _Star
    api.event = event_mod
    api.message_components = components_mod
    api.star = star_mod

    modules = {
        "astrbot": astrbot,
        "astrbot.api": api,
        "astrbot.api.event": event_mod,
        "astrbot.api.event.filter": filter_mod,
        "astrbot.api.message_components": components_mod,
        "astrbot.api.star": star_mod,
    }
    if with_textpart:
        core = types.ModuleType("astrbot.core")
        agent = types.ModuleType("astrbot.core.agent")
        message_mod = types.ModuleType("astrbot.core.agent.message")
        message_mod.TextPart = _TextPart
        modules.update(
            {
                "astrbot.core": core,
                "astrbot.core.agent": agent,
                "astrbot.core.agent.message": message_mod,
            }
        )

    old = {name: sys.modules.get(name) for name in modules}
    sys.modules.update(modules)
    try:
        spec = importlib.util.spec_from_file_location("text_file_reader_main", PLUGIN_PATH)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        # 保留模块本身供测试使用，但恢复被替换的 stub
        for name, value in old.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


class FakeEvent:
    def __init__(
        self,
        messages: list[Any],
        session: str = "aiocqhttp:GroupMessage:10001",
        message_id: str = "m1",
        private: bool = False,
        wake: bool = False,
        raw_message: Any = None,
    ):
        self.message_obj = SimpleNamespace(
            message=messages, message_id=message_id, raw_message=raw_message
        )
        self.unified_msg_origin = session
        self.is_at_or_wake_command = wake
        self._private = private
        self.sent: list[str] = []
        self.call_llm: bool | None = None

    def get_messages(self) -> list[Any]:
        return self.message_obj.message

    def is_private_chat(self) -> bool:
        return self._private

    def plain_result(self, text: str) -> str:
        self.sent.append(text)
        return text

    def should_call_llm(self, call_llm: bool) -> None:
        self.call_llm = call_llm

    def request_llm(self, prompt: str = "", **kwargs):
        self.llm_prompt = prompt
        return SimpleNamespace(prompt=prompt)


class FakeRequest:
    def __init__(self) -> None:
        self.prompt = "帮我看看这个文件"
        self.extra_user_content_parts: list[Any] = []


def _make_plugin(module, config: dict | None = None):
    return module.TextFileReader(context=SimpleNamespace(), config=config or {})


def _write_tmp(text: str, suffix: str = ".md", encoding: str = "utf-8") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    with open(path, "w", encoding=encoding, newline="") as fp:
        fp.write(text)
    return path


class DecodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_plugin_module()

    def test_utf8(self):
        text, enc = self.module.decode_text("你好，世界".encode())
        self.assertEqual(text, "你好，世界")
        self.assertEqual(enc, "utf-8")

    def test_utf8_bom(self):
        text, enc = self.module.decode_text(b"\xef\xbb\xbfhello")
        self.assertEqual(text, "hello")
        self.assertEqual(enc, "utf-8-sig")

    def test_gbk(self):
        text, enc = self.module.decode_text("中文编码测试".encode("gbk"))
        self.assertEqual(text, "中文编码测试")
        self.assertIn(enc, ("gb18030", "big5"))

    def test_utf16_bom(self):
        text, enc = self.module.decode_text("宽字符".encode("utf-16"))
        self.assertEqual(text, "宽字符")
        self.assertEqual(enc, "utf-16")

    def test_binary_rejected(self):
        self.assertIsNone(self.module.decode_text(b"\x00\x01\x02\xff\xfe" * 10))

    def test_empty(self):
        self.assertEqual(self.module.decode_text(b""), ("", "utf-8"))

    def test_printable_ratio(self):
        self.assertGreater(self.module._printable_ratio("abc\n def"), 0.9)
        self.assertLess(self.module._printable_ratio("\x01\x02\x03\x04"), 0.5)


class ExtensionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_plugin_module()

    def test_normalize(self):
        self.assertEqual(
            self.module.normalize_extensions(["TXT", " .Md ", "", ".markdown"]),
            {".txt", ".md", ".markdown"},
        )

    def test_normalize_invalid(self):
        self.assertEqual(
            self.module.normalize_extensions("not-a-list"),
            set(self.module.DEFAULT_EXTENSIONS),
        )
        self.assertEqual(
            self.module.normalize_extensions([]), set(self.module.DEFAULT_EXTENSIONS)
        )

    def test_safe_basename(self):
        self.assertEqual(self.module.safe_basename("a\\b\\c.txt"), "c.txt")
        self.assertEqual(self.module.safe_basename("  x.md  "), "x.md")

    def test_extension(self):
        self.assertEqual(self.module.file_extension("C:\\tmp\\笔记.MD"), ".md")


class ReadFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_plugin_module()

    def setUp(self):
        self.plugin = _make_plugin(self.module)
        self.tmp_paths: list[str] = []

    def tearDown(self):
        for path in self.tmp_paths:
            try:
                os.remove(path)
            except OSError:
                pass

    def _read(self, comp, config=None, event=None):
        plugin = _make_plugin(self.module, config) if config else self.plugin
        event = event or FakeEvent([comp])
        return asyncio.run(plugin._read_components(event, [comp]))

    def test_reads_markdown(self):
        path = _write_tmp("# 标题\n正文内容", suffix=".md")
        self.tmp_paths.append(path)
        comp = _File(name="笔记.md", file=path)
        files, errors = self._read(comp)
        self.assertEqual(errors, [])
        self.assertEqual(len(files), 1)
        self.assertIn("正文内容", files[0].text)
        self.assertEqual(files[0].encoding, "utf-8")
        self.assertFalse(files[0].truncated)

    def test_skips_non_text_extension(self):
        path = _write_tmp("dummy", suffix=".mp4")
        self.tmp_paths.append(path)
        comp = _File(name="movie.mp4", file=path)
        files, errors = self._read(comp)
        self.assertEqual(files, [])
        self.assertEqual(errors, [])

    def test_chars_truncated(self):
        path = _write_tmp("x" * 500, suffix=".txt")
        self.tmp_paths.append(path)
        comp = _File(name="big.txt", file=path)
        files, _ = self._read(comp, config={"max_chars_per_file": 100})
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].truncated)
        self.assertLess(len(files[0].text), 400)

    def test_binary_skipped(self):
        path = _write_tmp("")  # 先建空文件
        self.tmp_paths.append(path)
        with open(path, "wb") as fp:
            fp.write(b"\x00\x01\x02\x03" * 100)
        comp = _File(name="blob.txt", file=path)
        files, errors = self._read(comp)
        self.assertEqual(files, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("不是纯文本", errors[0])

    def test_missing_file(self):
        comp = _File(name="gone.md", file="")
        files, errors = self._read(comp)
        self.assertEqual(files, [])
        self.assertEqual(len(errors), 1)

    def test_quoted_file(self):
        path = _write_tmp("被引用的内容", suffix=".md")
        self.tmp_paths.append(path)
        comp = _File(name="引用.md", file=path)
        event = FakeEvent([_Reply(chain=[comp])])
        files, errors = asyncio.run(self.plugin._read_components(event, [comp]))
        self.assertEqual(errors, [])
        self.assertEqual(len(files), 1)

    def test_duplicate_component_deduped(self):
        path = _write_tmp("同一份", suffix=".md")
        self.tmp_paths.append(path)
        comp = _File(name="dup.md", file=path)
        files, _ = asyncio.run(
            self.plugin._read_components(FakeEvent([comp]), [comp, comp])
        )
        self.assertEqual(len(files), 1)


class InjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_plugin_module()

    def setUp(self):
        self.plugin = _make_plugin(self.module)
        self.tmp_paths: list[str] = []

    def tearDown(self):
        for path in self.tmp_paths:
            try:
                os.remove(path)
            except OSError:
                pass

    def _tmp(self, text: str, suffix=".md") -> str:
        path = _write_tmp(text, suffix=suffix)
        self.tmp_paths.append(path)
        return path

    def test_injects_current_file(self):
        path = self._tmp("第一章内容")
        event = FakeEvent([_File(name="story.md", file=path)], wake=True)
        req = FakeRequest()
        asyncio.run(self.plugin.inject_file_content(event, req))
        self.assertEqual(len(req.extra_user_content_parts), 1)
        part = req.extra_user_content_parts[0]
        self.assertIn("第一章内容", part.text)
        self.assertTrue(part.is_temp)

    def test_no_file_no_injection(self):
        event = FakeEvent([SimpleNamespace(text="普通聊天")], wake=True)
        req = FakeRequest()
        asyncio.run(self.plugin.inject_file_content(event, req))
        self.assertEqual(req.extra_user_content_parts, [])

    def test_cache_reuse_after_file_message(self):
        path = self._tmp("先发文件后提问")
        plugin = _make_plugin(self.module, {"reuse_seconds": 600})
        file_event = FakeEvent([_File(name="a.md", file=path)], message_id="f1")
        asyncio.run(_consume(plugin.cache_file_messages(file_event)))

        ask_event = FakeEvent(
            [SimpleNamespace(text="总结一下")],
            message_id="q1",
            wake=True,
        )
        req = FakeRequest()
        asyncio.run(plugin.inject_file_content(ask_event, req))
        self.assertEqual(len(req.extra_user_content_parts), 1)
        self.assertIn("先发文件后提问", req.extra_user_content_parts[0].text)

    def test_cache_expires(self):
        path = self._tmp("会过期的内容")
        plugin = _make_plugin(self.module, {"reuse_seconds": 0})
        file_event = FakeEvent([_File(name="a.md", file=path)], message_id="f1")
        asyncio.run(_consume(plugin.cache_file_messages(file_event)))
        ask_event = FakeEvent(
            [SimpleNamespace(text="再说说")], message_id="q1", wake=True
        )
        req = FakeRequest()
        asyncio.run(plugin.inject_file_content(ask_event, req))
        self.assertEqual(req.extra_user_content_parts, [])

    def test_reuse_max_requests(self):
        path = self._tmp("最多复用几次")
        plugin = _make_plugin(self.module, {"reuse_seconds": 600, "reuse_max_requests": 1})
        asyncio.run(_consume(plugin.cache_file_messages(FakeEvent([_File(name="a.md", file=path)]))))
        first = FakeRequest()
        asyncio.run(plugin.inject_file_content(FakeEvent([], message_id="q1", wake=True), first))
        self.assertEqual(len(first.extra_user_content_parts), 1)
        second = FakeRequest()
        asyncio.run(plugin.inject_file_content(FakeEvent([], message_id="q2", wake=True), second))
        self.assertEqual(second.extra_user_content_parts, [])

    def test_failure_note_injected(self):
        event = FakeEvent([_File(name="bad.md", file="")])
        req = FakeRequest()
        asyncio.run(self.plugin.inject_file_content(event, req))
        self.assertEqual(len(req.extra_user_content_parts), 1)
        self.assertIn("未能读取", req.extra_user_content_parts[0].text)

    def test_failure_note_can_be_disabled(self):
        plugin = _make_plugin(self.module, {"notify_failures": False})
        event = FakeEvent([_File(name="bad.md", file="")])
        req = FakeRequest()
        asyncio.run(plugin.inject_file_content(event, req))
        self.assertEqual(req.extra_user_content_parts, [])

    def test_fallback_to_prompt(self):
        plugin = _make_plugin(self.module)
        path = self._tmp("兜底内容")
        req = SimpleNamespace(prompt="问题", extra_user_content_parts=None)
        event = FakeEvent([_File(name="x.md", file=path)])
        asyncio.run(plugin.inject_file_content(event, req))
        self.assertIn("兜底内容", req.prompt)

    def test_send_ack_only_when_not_woken(self):
        plugin = _make_plugin(self.module, {"send_ack": True})
        path = self._tmp("确认内容")
        event = FakeEvent([_File(name="a.md", file=path)], wake=False)
        asyncio.run(_consume(plugin.cache_file_messages(event)))
        self.assertTrue(event.sent)
        self.assertIn("a.md", event.sent[0])

        event2 = FakeEvent([_File(name="b.md", file=path)], wake=True)
        asyncio.run(_consume(plugin.cache_file_messages(event2)))
        self.assertEqual(event2.sent, [])

    def test_unreadable_current_file_does_not_reuse_cache(self):
        path = self._tmp("旧文件内容")
        plugin = _make_plugin(self.module, {"reuse_seconds": 600})
        old_event = FakeEvent(
            [_File(name="old.md", file=path)], message_id="f1"
        )
        asyncio.run(_consume(plugin.cache_file_messages(old_event)))

        bad_event = FakeEvent(
            [_File(name="bad.txt", file="")], message_id="q1", wake=True
        )
        req = FakeRequest()
        asyncio.run(plugin.inject_file_content(bad_event, req))
        self.assertEqual(len(req.extra_user_content_parts), 1)
        text = req.extra_user_content_parts[0].text
        self.assertIn("未能读取", text)
        self.assertNotIn("旧文件内容", text)

    def test_auto_summary_triggers_llm(self):
        plugin = _make_plugin(self.module, {"auto_summary": True})
        path = self._tmp("自动总结内容")
        event = FakeEvent([_File(name="a.md", file=path)], wake=False)

        async def collect():
            return [item async for item in plugin.cache_file_messages(event)]

        results = asyncio.run(collect())
        self.assertEqual(len(results), 1)
        self.assertEqual(event.call_llm, True)
        self.assertIn("文件", event.llm_prompt)

    def test_auto_summary_off_by_default(self):
        path = self._tmp("默认不主动")
        event = FakeEvent([_File(name="a.md", file=path)], wake=False)
        asyncio.run(_consume(self.plugin.cache_file_messages(event)))
        self.assertFalse(getattr(event, "llm_prompt", ""))
        self.assertEqual(event.sent, [])

    def test_oversized_file_skipped_before_download(self):
        path = self._tmp("太大")
        raw = {
            "message": [
                {"type": "file", "data": {"file": "big.txt", "file_size": "9999999"}}
            ]
        }
        event = FakeEvent(
            [_File(name="big.txt", file=path)], wake=True, raw_message=raw
        )
        files, errors = asyncio.run(
            self.plugin._read_components(event, event.get_messages())
        )
        self.assertEqual(files, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("文件过大", errors[0])

    def test_known_file_size_parsing(self):
        raw = {
            "message": [
                {"type": "file", "data": {"file": "a.md", "file_size": "1234"}}
            ]
        }
        event = FakeEvent([], raw_message=raw)
        self.assertEqual(self.plugin._known_file_size(event, "a.md"), 1234)
        self.assertIsNone(self.plugin._known_file_size(event, "b.md"))
        self.assertIsNone(
            self.plugin._known_file_size(FakeEvent([], raw_message=None), "a.md")
        )

    def test_group_and_private_switches(self):
        path = self._tmp("作用域")
        plugin = _make_plugin(self.module, {"enable_in_groups": False})
        event = FakeEvent([_File(name="a.md", file=path)], private=False, wake=True)
        req = FakeRequest()
        asyncio.run(plugin.inject_file_content(event, req))
        self.assertEqual(req.extra_user_content_parts, [])

        plugin2 = _make_plugin(self.module, {"enable_in_private": False})
        event2 = FakeEvent([_File(name="a.md", file=path)], private=True, wake=True)
        req2 = FakeRequest()
        asyncio.run(plugin2.inject_file_content(event2, req2))
        self.assertEqual(req2.extra_user_content_parts, [])

    def test_total_chars_cap(self):
        plugin = _make_plugin(
            self.module, {"max_chars_per_file": 500, "max_chars_total": 600}
        )
        path1 = self._tmp("A" * 3000)
        path2 = self._tmp("B" * 3000)
        event = FakeEvent(
            [_File(name="1.txt", file=path1), _File(name="2.txt", file=path2)],
            wake=True,
        )
        req = FakeRequest()
        asyncio.run(plugin.inject_file_content(event, req))
        self.assertEqual(len(req.extra_user_content_parts), 1)
        text = req.extra_user_content_parts[0].text
        self.assertIn("总长度超出上限", text)


async def _consume(agen):
    async for _ in agen:
        pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
