"""
AI 对话服务模块
支持免费本地对话和多 AI 模型 API 对话
"""
from __future__ import annotations

import random
import requests
from datetime import datetime
from typing import Optional

from db_manager import DBManager


class AIService:
    """
    AI 对话服务
    支持免费本地对话和 API 对话
    """

    # AI 模型配置
    AI_MODELS = {
        "本地对话 (免费)": {
            "default_url": "",
            "model": "",
            "is_free": True,
        },
        "DeepSeek": {
            "default_url": "https://api.deepseek.com/v1/chat/completions",
            "model": "deepseek-chat",
            "is_free": False,
        },
        "OpenAI": {
            "default_url": "https://api.openai.com/v1/chat/completions",
            "model": "gpt-3.5-turbo",
            "is_free": False,
        },
        "豆包 (Doubao)": {
            "default_url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
            "model": "doubao-chat",
            "is_free": False,
        },
        "通义千问 (Qwen)": {
            "default_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            "model": "qwen-turbo",
            "is_free": False,
        },
        "Kimi": {
            "default_url": "https://api.moonshot.cn/v1/chat/completions",
            "model": "moonshot-v1-8k",
            "is_free": False,
        },
    }

    # 本地对话回复库
    LOCAL_RESPONSES = {
        "问候": [
            "你好呀！有什么可以帮你的吗？😊",
            "嗨！很高兴见到你！",
            "你好！今天过得怎么样？",
            "哈喽！需要我帮忙吗？",
        ],
        "天气": [
            "今天天气不错呢！记得多喝水哦～",
            "天气变化无常，出门记得带伞！",
            "今天适合外出活动，要不要出去走走？",
        ],
        "系统": [
            "你的电脑运行正常，一切顺利！",
            "系统状态良好，可以放心使用。",
            "电脑性能不错，继续保持！",
        ],
        "心情": [
            "开心最重要！保持好心情～",
            "工作学习之余也要注意休息哦！",
            "加油！你是最棒的！💪",
        ],
        "默认": [
            "这是一个好问题！让我想想...",
            "我理解你的意思，不过我还在学习中。",
            "嗯，这个我需要更多时间思考。",
            "有趣的想法！你可以多告诉我一些吗？",
            "我明白你的意思了，还有什么其他问题吗？",
        ],
    }

    def __init__(self, db: DBManager):
        self.db = db
        self._current_model = self.db.get("current_ai_model", "本地对话 (免费)")

    @property
    def current_model(self) -> str:
        """获取当前 AI 模型名称"""
        return self._current_model

    @current_model.setter
    def current_model(self, model_name: str):
        """设置当前 AI 模型"""
        if model_name in self.AI_MODELS:
            self._current_model = model_name
            self.db.set("current_ai_model", model_name)

    def is_free_model(self) -> bool:
        """检查当前模型是否免费"""
        return self.AI_MODELS.get(self._current_model, {}).get("is_free", True)

    def get_api_key(self) -> str:
        """获取当前模型的 API Key"""
        if self.is_free_model():
            return ""
        model_key = self._current_model.split(" ")[0].lower()
        return self.db.get(f"{model_key}_api_key", "")

    def get_api_url(self) -> str:
        """获取当前模型的 API URL"""
        model_key = self._current_model.split(" ")[0].lower()
        default_url = self.AI_MODELS.get(self._current_model, {}).get("default_url", "")
        return self.db.get(f"{model_key}_api_url", default_url)

    def get_model_id(self) -> str:
        """获取当前模型 ID"""
        return self.AI_MODELS.get(self._current_model, {}).get("model", "")

    def _get_local_response(self, message: str) -> str:
        """获取本地回复"""
        message_lower = message.lower()

        # 关键词匹配
        keywords = {
            "问候": ["你好", "嗨", "哈喽", "hi", "hello", "早上好", "下午好", "晚上好"],
            "天气": ["天气", "下雨", "晴天", "温度", "冷", "热"],
            "系统": ["系统", "电脑", "性能", "状态", "运行"],
            "心情": ["开心", "难过", "累", "加油", "心情", "压力"],
        }

        for category, words in keywords.items():
            if any(word in message_lower for word in words):
                return random.choice(self.LOCAL_RESPONSES[category])

        return random.choice(self.LOCAL_RESPONSES["默认"])

    def chat(self, message: str, system_prompt: Optional[str] = None) -> str:
        """
        发送消息并获取回复

        Args:
            message: 用户消息
            system_prompt: 系统提示词（可选）

        Returns:
            AI 回复内容
        """
        # 免费本地对话
        if self.is_free_model():
            return self._get_local_response(message)

        # API 对话
        api_key = self.get_api_key()
        if not api_key:
            return "⚠️ 请先在设置中配置 API Key，或切换到免费的本地对话模式"

        api_url = self.get_api_url()
        model_id = self.get_model_id()

        if not api_url or not model_id:
            return "⚠️ AI 模型配置错误，请检查设置"

        # 构建请求头
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        # 构建消息列表
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": message})

        # 构建请求体
        payload = {
            "model": model_id,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 1024,
        }

        try:
            response = requests.post(
                api_url,
                headers=headers,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            # 提取回复内容
            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"]
            elif "error" in data:
                return f"⚠️ API 错误: {data['error'].get('message', '未知错误')}"
            else:
                return "⚠️ 无法解析 API 响应"

        except requests.exceptions.Timeout:
            return "⚠️ 请求超时，请检查网络连接"
        except requests.exceptions.RequestException as e:
            return f"⚠️ 网络错误: {str(e)}"
        except Exception as e:
            return f"⚠️ 发生错误: {str(e)}"

    def get_random_greeting(self) -> str:
        """获取随机问候语（用于双击宠物）"""
        hour = datetime.now().hour

        if hour < 6:
            time_greeting = "夜深了，注意休息哦～"
        elif hour < 9:
            time_greeting = "早上好！新的一天开始了！☀️"
        elif hour < 12:
            time_greeting = "上午好！工作学习加油！💪"
        elif hour < 14:
            time_greeting = "中午好！记得吃午饭哦～"
        elif hour < 17:
            time_greeting = "下午好！继续加油！"
        elif hour < 19:
            time_greeting = "傍晚好！辛苦一天了～"
        elif hour < 22:
            time_greeting = "晚上好！放松一下吧～"
        else:
            time_greeting = "夜深了，早点休息哦～🌙"

        greetings = [
            f"{time_greeting}",
            f"{time_greeting}\n有什么可以帮你的吗？",
            f"{time_greeting}\n记得多喝水，保持好心情！",
            f"{time_greeting}\n今天也要元气满满哦！",
        ]

        return random.choice(greetings)


# ─── 测试代码 ─────────────────────────────────────────────

if __name__ == "__main__":
    # 测试 AI 服务
    db = DBManager("test_ai.db")
    ai = AIService(db)

    print(f"当前模型: {ai.current_model}")
    print(f"是否免费: {ai.is_free_model()}")
    print(f"API Key: {ai.get_api_key()[:10]}..." if ai.get_api_key() else "API Key: 未配置")

    # 测试本地对话
    test_messages = ["你好", "今天天气怎么样？", "电脑性能如何？", "我有点累"]
    for msg in test_messages:
        response = ai.chat(msg)
        print(f"\n用户: {msg}")
        print(f"AI: {response}")

    # 测试随机问候
    print(f"\n随机问候: {ai.get_random_greeting()}")
