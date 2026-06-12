"""
title: 生成论文 DOCX
author: user
description: 将 ThesisContent JSON 发送到 docx-saas 渲染服务生成排版好的 DOCX 论文文件
version: 1.0.0

---

将此文件内容粘贴到 Open WebUI Admin UI:
  Workspace → Tools → 点击 + (Create) → 粘贴代码 → Save

管理员在 Admin UI 中配置 Valves.DOCX_RENDER_URL 指向 docx-saas 服务地址。
"""

import asyncio
import json
import logging
import tempfile
from pathlib import Path

import aiohttp
from fastapi import Request
from pydantic import BaseModel

log = logging.getLogger(__name__)


class Tools:
    class Valves(BaseModel):
        """管理员可配置参数"""
        DOCX_RENDER_URL: str = "http://localhost:3001"

    class UserValves(BaseModel):
        """用户可配置参数"""
        pass

    def __init__(self):
        self.valves = self.Valves()

    async def generate_thesis_docx(
        self,
        thesis_content: dict,
        __request__: Request = None,
        __user__: dict = None,
        __event_emitter__: callable = None,
        __id__: str = None,
        __chat_id__: str = None,
        __message_id__: str = None,
    ) -> str:
        """
        生成论文 DOCX 文件。

        将 ThesisContent 发送到 docx-saas 渲染服务，
        生成的 DOCX 通过文件消息在对话中显示下载入口。

        :param thesis_content: ThesisContent 对象 (dict)
        :return: 状态 JSON
        """
        # ── 读取 Valves ──
        render_url = getattr(self, 'valves', None)
        if render_url and hasattr(render_url, 'DOCX_RENDER_URL'):
            render_url = render_url.DOCX_RENDER_URL
        else:
            render_url = "http://localhost:3001"

        # ── 校验输入 ──
        content = thesis_content  # Already parsed by Open WebUI from tool call args

        for key in ["meta", "sections"]:
            if key not in content:
                return json.dumps({"error": f"缺少必填字段: {key}"}, ensure_ascii=False)

        try:
            # ── 调用 docx-saas 渲染服务 ──
            timeout = aiohttp.ClientTimeout(total=120)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{render_url}/render",
                    json={"content": content},
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        return json.dumps(
                            {"error": f"渲染服务返回 {resp.status}: {error_text[:300]}"},
                            ensure_ascii=False,
                        )
                    docx_bytes = await resp.read()

            # ── 保存文件 ──
            title = content.get('meta', {}).get('titleCn', '论文')
            safe_title = "".join(c for c in title if c.isalnum() or c in ('_', '-', ' ')).rstrip() or "thesis"
            safe_title = safe_title[:60]

            output_dir = Path("/home/dev/projects/open-webui/output")
            output_dir.mkdir(parents=True, exist_ok=True)
            file_path = output_dir / f"{safe_title}.docx"
            file_path.write_bytes(docx_bytes)

            # ── 通过 event_emitter 发送文件给用户 ──
            if __event_emitter__:
                await __event_emitter__({
                    "type": "chat:message:files",
                    "data": {
                        "files": [{
                            "type": "file",
                            "url": str(file_path),
                            "name": file_path.name,
                        }]
                    }
                })

            return json.dumps({
                "status": "success",
                "message": "DOCX 已生成，用户可在对话中查看下载链接。请告诉用户文件已准备好。",
                "file_name": file_path.name,
                "file_size_bytes": len(docx_bytes),
            }, ensure_ascii=False)

        except aiohttp.ClientError as e:
            log.exception("generate_thesis_docx 网络错误")
            return json.dumps({"error": f"无法连接到渲染服务 ({render_url}): {e}"}, ensure_ascii=False)
        except Exception as e:
            log.exception("generate_thesis_docx 错误")
            return json.dumps({"error": str(e)}, ensure_ascii=False)
