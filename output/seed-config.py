#!/usr/bin/env python3
"""
Open WebUI 论文生成器配置 seed 脚本。

使用方法:
  cd /home/dev/projects/open-webui/backend
  WEBUI_AUTH=false WEBUI_SECRET_KEY=noauth-dev \
  DEFAULT_MODEL_PARAMS='{"function_calling":"native"}' \
  /home/dev/projects/open-webui/.venv/bin/python -m uvicorn open_webui.main:app --port 8080 --host 0.0.0.0 &

  sleep 8 && python3 output/seed-config.py

此脚本自动完成:
1. 注册 generate_thesis_docx 工具
2. 创建 paper-generator 模型 (function_calling=native, builtin_tools=disabled)
3. 配置 System Prompt
"""

import json, requests, sys

BASE = "http://localhost:8080"
EMAIL = "admin@localhost"
PASSWORD = "admin"

# ── System Prompt ──────────────────────────────────────────────

SYSTEM_PROMPT = """调用 generate_thesis_docx 工具生成论文DOCX。

thesis_content 必须是包含 meta、styleSpec、sections 三个字段的对象：
{
  "meta": {"titleCn": "论文标题", "authorName": "作者"},
  "styleSpec": {
    "heading1": {"font": "黑体", "size": 32, "bold": true, "align": "center", "spaceBefore": 24, "spaceAfter": 18},
    "body": {"font": "宋体", "size": 24, "lineHeight": 1.5, "firstLineIndent": 2, "align": "justify"},
    "threeLineTable": {"topBorderWidth": 12, "bottomBorderWidth": 12, "headerBorderWidth": 6}
  },
  "sections": [
    {"key": "abstractCn", "blocks": [
      {"type": "heading", "level": 1, "title": "摘要", "variant": "frontMatter"},
      {"type": "paragraph", "styleHint": "abstractCn", "children": [
        {"type": "strong", "children": [{"type": "text", "text": "摘  要："}]},
        {"type": "text", "text": "内容（用「」代替引号）"}
      ]},
      {"type": "paragraph", "styleHint": "abstractCn", "children": [
        {"type": "strong", "children": [{"type": "text", "text": "关键词："}]},
        {"type": "text", "text": "词1；词2"}
      ]}
    ]},
    {"key": "body", "blocks": [
      {"type": "heading", "level": 1, "title": "第一章 绪论"},
      {"type": "paragraph", "children": [{"type": "text", "text": "正文..."}]},
      {"type": "heading", "level": 1, "title": "第二章 相关技术"},
      {"type": "paragraph", "children": [{"type": "text", "text": "正文..."}]}
    ]},
    {"key": "references", "blocks": [
      {"type": "heading", "level": 1, "title": "参考文献", "variant": "frontMatter"},
      {"type": "paragraph", "styleHint": "refItem", "children": [{"type": "text", "text": "[1] 作者. 标题[J]. 期刊, 2024."}]}
    ]}
  ]
}

直接调用工具。不要输出解释。不要用python-docx。"""

# ── Tool code ──────────────────────────────────────────────────

TOOL_CODE = """\"\"\"
title: 生成论文 DOCX
author: user
description: 将 ThesisContent JSON 发送到 docx-saas 渲染服务生成排版好的 DOCX 论文文件
version: 1.0.0
\"\"\"

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
        DOCX_RENDER_URL: str = \"http://localhost:3001\"

    class UserValves(BaseModel):
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
        render_url = getattr(self, 'valves', None)
        if render_url and hasattr(render_url, 'DOCX_RENDER_URL'):
            render_url = render_url.DOCX_RENDER_URL
        else:
            render_url = \"http://localhost:3001\"

        content = thesis_content
        for key in [\"meta\", \"sections\"]:
            if key not in content:
                return json.dumps({\"error\": f\"缺少必填字段: {key}\"}, ensure_ascii=False)

        try:
            timeout = aiohttp.ClientTimeout(total=120)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f\"{render_url}/render\",
                    json={\"content\": content},
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        return json.dumps(
                            {\"error\": f\"渲染服务返回 {resp.status}: {error_text[:300]}\"},
                            ensure_ascii=False,
                        )
                    docx_bytes = await resp.read()

            title = content.get('meta', {}).get('titleCn', '论文')
            safe_title = \"\".join(c for c in title if c.isalnum() or c in ('_', '-', ' ')).rstrip() or \"thesis\"
            safe_title = safe_title[:60]

            output_dir = Path(tempfile.gettempdir()) / \"open-webui-thesis\"
            output_dir.mkdir(parents=True, exist_ok=True)
            file_path = output_dir / f\"{safe_title}.docx\"
            file_path.write_bytes(docx_bytes)

            if __event_emitter__:
                await __event_emitter__({
                    \"type\": \"chat:message:files\",
                    \"data\": {
                        \"files\": [{
                            \"type\": \"file\",
                            \"url\": str(file_path),
                            \"name\": file_path.name,
                        }]
                    }
                })

            return json.dumps({
                \"status\": \"success\",
                \"message\": \"DOCX 已生成\",
                \"file_name\": file_path.name,
                \"file_size_bytes\": len(docx_bytes),
            }, ensure_ascii=False)

        except aiohttp.ClientError as e:
            log.exception(\"generate_thesis_docx 网络错误\")
            return json.dumps({\"error\": f\"无法连接到渲染服务\"}, ensure_ascii=False)
        except Exception as e:
            log.exception(\"generate_thesis_docx 错误\")
            return json.dumps({\"error\": \"生成失败，请稍后重试\"}, ensure_ascii=False)
"""


def main() -> int:
    s = requests.Session()

    # 1. Login
    r = s.post(f"{BASE}/api/v1/auths/signin", json={"email": EMAIL, "password": PASSWORD})
    if r.status_code != 200:
        print(f"❌ Login failed: {r.status_code}")
        return 1
    print("✅ Logged in")

    # 2. Create/update tool
    r = s.post(f"{BASE}/api/v1/tools/create", json={
        "id": "generate_thesis_docx",
        "name": "生成论文 DOCX",
        "content": TOOL_CODE,
        "meta": {"description": "将 ThesisContent 发送到 docx-saas 渲染服务生成 DOCX 论文", "manifest": {}},
        "access_grants": [],
    })
    if r.status_code in (200, 400):
        if r.status_code == 400 and "ID_TAKEN" in r.text:
            # Tool exists, update it
            r = s.post(f"{BASE}/api/v1/tools/id/generate_thesis_docx/update", json={
                "id": "generate_thesis_docx",
                "name": "生成论文 DOCX",
                "content": TOOL_CODE,
                "meta": {"description": "生成 DOCX 论文", "manifest": {}},
                "access_grants": [],
            })
            print(f"✅ Tool updated: {r.status_code}")
        else:
            print(f"✅ Tool created: {r.status_code}")
    else:
        print(f"❌ Tool failed: {r.status_code} {r.text[:200]}")
        return 1

    # 3. Set tool valves
    r = s.post(f"{BASE}/api/v1/tools/id/generate_thesis_docx/valves/update",
               json={"DOCX_RENDER_URL": "http://localhost:3001"})
    print(f"✅ Tool valves: {r.status_code}")

    # 4. Create/update paper-generator model
    model_payload = {
        "id": "paper-generator",
        "name": "论文生成器",
        "meta": {
            "profile_image_url": "",
            "description": "论文DOCX生成专用",
            "capabilities": {
                "vision": False, "file_upload": False, "web_search": False,
                "image_generation": False, "code_interpreter": False,
                "terminal": False, "builtin_tools": False,
            },
            "system": SYSTEM_PROMPT,
            "toolIds": ["generate_thesis_docx"],
        },
        "params": {"function_calling": "native"},
        "base_model_id": "deepseek-v4-flash",
        "access_grants": [],
        "is_active": True,
    }

    r = s.post(f"{BASE}/api/v1/models/create", json=model_payload)
    if r.status_code == 200:
        print(f"✅ Model created")
    elif r.status_code == 400 and "ID_TAKEN" in r.text:
        r = s.post(f"{BASE}/api/v1/models/model/update", json=model_payload)
        print(f"✅ Model updated: {r.status_code}")
    else:
        print(f"❌ Model failed: {r.status_code} {r.text[:200]}")

    # 5. Verify
    r = s.get(f"{BASE}/api/v1/models")
    for m in r.json().get("data", []):
        if m["id"] == "paper-generator":
            meta = m.get("info", {}).get("meta", {})
            print(f"   toolIds: {meta.get('toolIds', 'MISSING')}")
            sys_len = len(meta.get("system", ""))
            print(f"   system prompt: {sys_len} chars")
            print(f"   capabilities: {meta.get('capabilities', {})}")

    print("\n🎉 Seed complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
