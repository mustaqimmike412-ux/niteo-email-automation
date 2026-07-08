"""
关键词拓展模块
基于用户输入的基础关键词，调用 Deepseek API 生成行业相关的拓展关键词列表，
用于扩大搜索范围，解决单一关键词搜索结果狭窄的问题。
"""
import json
from services.llm_client import LLMEmailClient


class KeywordExpander:
    """关键词拓展器"""

    def __init__(self):
        self.llm = LLMEmailClient()

    def is_available(self) -> bool:
        """检查 LLM API 是否可用"""
        return self.llm.is_available()

    def expand(self, base_keyword: str, location: str = '', max_keywords: int = 8) -> list:
        """
        将基础关键词拓展为多个相关关键词

        Args:
            base_keyword: 用户输入的基础关键词，如 "solar panel"
            location: 目标地区（可选），如 "USA"
            max_keywords: 最多生成的拓展关键词数量

        Returns:
            list: 拓展后的关键词列表（包含原始关键词）
        """
        if not self.is_available():
            print("[KeywordExpander] LLM API 不可用，跳过关键词拓展")
            return [base_keyword]

        system_prompt = """You are a B2B market research keyword strategist. Your task is to generate expanded search keywords based on a user's base keyword.

Rules:
1. Generate keywords that would help find potential B2B customers/distributors in the target industry
2. Include variations: product names, industry terms, business model terms (manufacturer, supplier, distributor, wholesaler)
3. DO NOT include any country names, region names, or location terms in the generated keywords (location filtering is handled separately)
4. Each keyword should be a practical search query (2-5 words)
5. Return ONLY a JSON array of strings, no markdown, no explanation

Example:
Base: "solar panel"
Output: ["solar panel manufacturer", "photovoltaic module supplier", "solar panel distributor", "PV module wholesaler", "solar energy company", "photovoltaic panel factory", "solar module OEM", "PV panel trading company"]"""

        user_prompt = f'Base keyword: "{base_keyword}"'
        # 不再传递 location 给 LLM，避免生成含国家词的关键词
        user_prompt += f'\n\nGenerate up to {max_keywords} expanded search keywords as a JSON array. Include the original keyword if relevant.'
        user_prompt += '\nIMPORTANT: Do NOT include any country names or geographic terms in keywords.'

        try:
            content, error = self.llm._call(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=500,
                temperature=0.5,
                label='keyword_expand'
            )

            if error or not content:
                print(f"[KeywordExpander] API 调用失败: {error}")
                return [base_keyword]

            # 解析 JSON
            # 清理可能的 markdown 代码块
            cleaned = content.strip()
            if cleaned.startswith('```json'):
                cleaned = cleaned[7:]
            if cleaned.startswith('```'):
                cleaned = cleaned[3:]
            if cleaned.endswith('```'):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            keywords = json.loads(cleaned)

            if not isinstance(keywords, list):
                print(f"[KeywordExpander] 返回格式错误，期望 list 得到 {type(keywords)}")
                return [base_keyword]

            # 去重、过滤空值、限制数量
            seen = set()
            result = []
            for k in keywords:
                if isinstance(k, str) and k.strip():
                    k_clean = k.strip().lower()
                    if k_clean not in seen:
                        seen.add(k_clean)
                        result.append(k.strip())

            # 确保原始关键词在列表中
            base_lower = base_keyword.strip().lower()
            if base_lower not in seen:
                result.insert(0, base_keyword.strip())

            final = result[:max_keywords]
            print(f"[KeywordExpander] '{base_keyword}' → {len(final)} 个关键词: {final}")
            return final

        except json.JSONDecodeError as e:
            print(f"[KeywordExpander] JSON 解析失败: {e}, content={content[:200]}")
            return [base_keyword]
        except Exception as e:
            print(f"[KeywordExpander] 拓展失败: {e}")
            return [base_keyword]
