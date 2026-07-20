#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI素材分析器
利用 DeepSeek 大模型自动识别文件内容类型，提取结构化素材信息，
自动归类到素材库中。

支持的素材类型映射：
  - product_advantage → material_type='advantage'
  - case_study → material_type='case_study'
  - product_specification → material_type='brochure'
  - company_profile → material_type='advantage' (company_intro)
  - certification → material_type='advantage' (certification)
  - market_research → material_type='rule'
  - other → material_type='advantage'
"""

import json
import os
import time
from typing import Dict, Optional, Tuple
from services.llm_client import LLMEmailClient
from services.file_content_extractor import extract_from_bytes
from database.material_models import (
    create_material, get_materials_by_type, invalidate_cache
)
from utils.ai_analysis_cache import AIMaterialAnalysisCache

# 素材类型中英文映射
MATERIAL_TYPE_MAP = {
    'product_advantage': 'advantage',
    'case_study': 'case_study',
    'product_specification': 'brochure',
    'company_profile': 'advantage',
    'certification': 'advantage',
    'market_research': 'rule',
    'other': 'advantage',
}

# 支持的文件扩展名
SUPPORTED_EXTENSIONS = {
    '.docx', '.pdf', '.txt', '.xlsx', '.xls', '.csv',
    '.html', '.htm', '.pptx'
}

# 全局语言配置（默认中文，后期可通过数据库或配置文件修改，无需前端按钮）
DEFAULT_LANGUAGE = os.environ.get('AI_ANALYSIS_LANGUAGE', 'zh')  # 'zh' 或 'en'


class AIMaterialAnalyzer:
    """AI素材分析器"""

    def __init__(self):
        self.llm = LLMEmailClient()
        self.cache = AIMaterialAnalysisCache()

    def is_available(self) -> bool:
        """检查AI分析服务是否可用"""
        return self.llm.is_available()

    def analyze_file(self, file_bytes: bytes, filename: str) -> Dict:
        """
        分析单个文件，返回AI识别结果

        Args:
            file_bytes: 文件字节数据
            filename: 文件名

        Returns:
            {
                'success': bool,
                'filename': str,
                'text_preview': str,       # 提取的文本预览（前500字）
                'text_length': int,          # 提取的文本总长度
                'analysis': {                # AI分析结果
                    'material_type': str,    # 识别的素材类型
                    'name': str,             # 建议的素材名称
                    'summary': str,          # 内容摘要
                    'tags': list,            # 推荐标签
                    'scope': str,            # 适用范围（small_power/large_power/all）
                    'track': str,            # 适用赛道
                    'region': str,           # 适用地区
                    'priority': int,         # 建议优先级
                    'confidence': float,     # AI置信度 0-1
                    'structured_content': dict,  # 结构化提取的内容
                    'reason': str,           # 分类理由
                },
                'error': str or None
            }
        """
        # 检查缓存
        cached = self.cache.get(file_bytes)
        if cached and cached.get('analysis'):
            cached['filename'] = filename
            return cached

        # 1. 提取文本
        text, error = extract_from_bytes(file_bytes, filename)
        if error:
            return {
                'success': False,
                'filename': filename,
                'text_preview': '',
                'text_length': 0,
                'analysis': {},
                'error': f'文件内容提取失败: {error}'
            }

        if not text or len(text.strip()) < 20:
            return {
                'success': False,
                'filename': filename,
                'text_preview': text[:500],
                'text_length': len(text),
                'analysis': {},
                'error': '文件内容过少（少于20字符），无法分析'
            }

        # 2. AI分析
        analysis, ai_error = self._call_llm_analysis(text, filename)

        if ai_error:
            return {
                'success': False,
                'filename': filename,
                'text_preview': text[:500],
                'text_length': len(text),
                'analysis': {},
                'error': f'AI分析失败: {ai_error}'
            }

        result = {
            'success': True,
            'filename': filename,
            'text_preview': text[:500],
            'text_length': len(text),
            'analysis': analysis,
            'error': None
        }

        # 写入缓存
        self.cache.set(file_bytes, result, filename, len(file_bytes))

        return result

    def _call_llm_analysis(self, text: str, filename: str) -> Tuple[Optional[Dict], Optional[str]]:
        """调用LLM进行素材分析"""
        lang = DEFAULT_LANGUAGE

        if lang == 'zh':
            system_prompt = """你是 Niteo Solar 的 B2B 太阳能材料分析专家。
你的任务是分析文档内容并将其分类到素材库系统中。

【关于标签的重要规则】
每份文档可以同时属于多个分类。请分析文档中涉及的所有主题，为每个主题打上标签。
标签体系包含三个层级：

1. 分区标签（必须根据内容选择，可多选）：
   - 个人信息：包含发信人介绍、个人背景、联系方式
   - 公司简介：包含公司历史、生产能力、工厂信息、主营业务
   - 产品优势：包含技术特性、性能数据、竞争优势
   - 客户案例：包含成功案例、项目参考、安装实例
   - 产品规格：包含技术参数、数据表、产品目录
   - 认证资质：包含CE、RoHS、UL、TUV、ISO等认证
   - 市场分析：包含行业趋势、竞争对手、定价
   - 储能方案：包含储能产品、储能系统方案

2. 主题标签（根据内容具体主题，如"太阳能电池板"、"离网系统"、"IP66防护"、"安装服务"等）

3. 属性标签（可选）：大功率、小功率、户外、商用、家用、工业级等

【素材主分类】（用于系统归档，选最主要的一个）：
- product_advantage: 产品技术特性、性能数据、竞争优势
- case_study: 客户成功案例、项目参考、安装实例
- product_specification: 产品规格、数据表、技术参数
- company_profile: 公司介绍、历史、生产能力
- certification: 质量认证（CE、RoHS、UL、TUV、ISO）
- market_research: 市场分析、行业趋势
- other: 其他

请只输出有效的 JSON，不要 markdown，不要解释。JSON 结构：
{
  "material_type": "主分类（上述类别之一）",
  "name": "简洁的素材名称（中文，最多80字）",
  "summary": "内容摘要（中文，1-3句话）",
  "tags": ["标签1", "标签2", "标签3", "标签4", "标签5"],
  "scope": "small_power" | "large_power" | "all",
  "track": "安防与智能家居硬件" | "户外与便携电源" | "自动化与门禁系统" | "农业与畜牧业" | "储能" | "消费电子" | ""（如不明确则留空）",
  "region": "欧洲" | "北美" | "亚洲" | "中东" | "非洲" | "南美" | "大洋洲" | ""（如不明确则留空）",
  "priority": 1-5,
  "confidence": 0.0-1.0,
  "structured_content": {
    "key_points": ["要点1", "要点2", "要点3"],
    "technical_specs": {"参数名": "值"} 或 {},
    "products_mentioned": ["产品1"],
    "customer_value": ["价值1", "价值2"]
  },
  "reason": "分类说明（中文）"
}

规则：
- 全面分析内容，不要只看标题
- tags 必须包含 3-8 个标签，其中至少有 1 个分区标签（如"公司简介"、"产品优势"等）
- 如果文档同时包含公司简介和产品信息，tags 中应同时包含"公司简介"和"产品优势"
- 标签应为简洁关键词（中文），避免重复和过于宽泛的词汇
- key_points: 提取最重要的3个要点（中文）
- technical_specs: 提取关键数值规格，如果没有则 {}
- products_mentioned: 列出具体产品名称/型号
- customer_value: 提取客户价值/利益（中文）
- confidence: 分类确信程度（清晰情况0.7+）
- priority: 标准素材为3，高价值内容为4，关键差异化内容为5
- 所有文本字段必须使用中文"""

            user_prompt = f"""文件名：{filename}

--- 文档内容 ---
{text[:8000]}

请分析此文档并将其分类到 Niteo Solar 素材库中。"""
        else:
            system_prompt = """You are a professional B2B solar energy material analyst for Niteo Solar.
Your task is to analyze document content and classify it into the material library system.

The material library has these categories:
1. product_advantage: Product technical features, performance data, competitive advantages, certifications
2. case_study: Customer success stories, project references, installation examples, partnership cases
3. product_specification: Product specs, datasheets, technical parameters, catalog/brochure content
4. company_profile: Company introduction, history, production capabilities, factory information
5. certification: Quality certifications (CE, RoHS, UL, TUV, ISO), compliance documents
6. market_research: Market analysis, industry trends, competitor information, pricing data
7. other: Content that doesn't fit above categories

Output ONLY valid JSON, no markdown, no explanation. JSON structure:
{
  "material_type": "one of the above categories",
  "name": "concise material name (English, max 80 chars)",
  "summary": "brief content summary in English (1-3 sentences)",
  "tags": ["tag1", "tag2", "tag3"],
  "scope": "small_power" | "large_power" | "all",
  "track": "Security & Smart Home Hardware" | "Outdoor & Portable Power" | "Automation & Gate Systems" | "Agriculture & Livestock" | "Energy Storage" | "Consumer Electronics" | "" (empty if not specific)",
  "region": "Europe" | "North America" | "Asia" | "Middle East" | "Africa" | "South America" | "Oceania" | "" (empty if not specific)",
  "priority": 1-5,
  "confidence": 0.0-1.0,
  "structured_content": {
    "key_points": ["point1", "point2", "point3"],
    "technical_specs": {"spec_name": "value"} or {},
    "products_mentioned": ["product1"],
    "customer_value": ["value1", "value2"]
  },
  "reason": "brief explanation of why this classification was chosen"
}

Rules:
- Analyze the FULL content, not just the title
- If the document is a solar product datasheet → product_specification
- If it describes a customer project/installation → case_study
- If it lists technical advantages → product_advantage
- Tags should be concise keywords (max 5)
- structured_content.key_points: extract the top 3 most important points
- structured_content.technical_specs: extract key numerical specs if present, else {}
- structured_content.products_mentioned: list any specific product names/models found
- structured_content.customer_value: extract customer-facing benefits mentioned
- confidence: how certain you are about this classification (0.7+ for clear cases)
- priority: 3 for standard materials, 4 for high-value cases/specs, 5 for critical differentiators"""

            user_prompt = f"""Filename: {filename}

--- Document Content ---
{text[:8000]}

Analyze this document and classify it for the Niteo Solar material library."""

        content, error = self.llm._call(
            system_prompt, user_prompt,
            max_tokens=1500,
            temperature=0.3,
            label=f'material_analysis:{filename}'
        )

        if error or not content:
            return None, error or 'AI返回空结果'

        try:
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                content = content.split('```')[1].split('```')[0]
            result = json.loads(content.strip())
            return result, None
        except json.JSONDecodeError as e:
            return None, f'AI返回JSON解析失败: {str(e)}'

    def import_analyzed_material(self, analysis_result: Dict,
                                   source_file: str = None,
                                   overwrite: bool = False,
                                   user_id: int = None) -> Dict:
        """
        将AI分析结果导入素材库

        Args:
            analysis_result: analyze_file() 的返回值（必须包含 analysis 字段）
            source_file: 来源文件路径
            overwrite: 是否覆盖同 key 素材
            user_id: 用户ID（None表示系统公共素材）

        Returns:
            {
                'success': bool,
                'material_id': int or None,
                'material_key': str,
                'action': 'created' | 'skipped' | 'error',
                'message': str
            }
        """
        if not analysis_result.get('success'):
            return {
                'success': False,
                'material_id': None,
                'material_key': '',
                'action': 'error',
                'message': analysis_result.get('error', '分析结果无效')
            }

        analysis = analysis_result['analysis']
        filename = analysis_result['filename']

        # 1. 生成素材 key
        name = analysis.get('name', os.path.splitext(filename)[0])
        base_key = _generate_material_key(name, filename)

        # 2. 检查是否已存在（按用户隔离）
        existing = get_materials_by_type('all', user_id=user_id, admin=True)
        for mat in existing:
            if mat.get('material_key') == base_key:
                # 检查是否属于同一用户
                mat_user_id = mat.get('user_id')
                if mat_user_id == user_id:
                    if not overwrite:
                        return {
                            'success': True,
                            'material_id': mat.get('id'),
                            'material_key': base_key,
                            'action': 'skipped',
                            'message': f'素材已存在（ID: {mat.get("id")}），跳过导入'
                        }
                # overwrite=True 时直接创建新版本（不删除旧的）
                break

        # 3. 映射素材类型
        ai_type = analysis.get('material_type', 'other')
        material_type = MATERIAL_TYPE_MAP.get(ai_type, 'advantage')

        # 4. 构建内容
        structured = analysis.get('structured_content', {})
        content_json = {
            'name': name,
            'summary': analysis.get('summary', ''),
            'key_points': structured.get('key_points', []),
            'technical_specs': structured.get('technical_specs', {}),
            'products_mentioned': structured.get('products_mentioned', []),
            'customer_value': structured.get('customer_value', []),
            'source_file': source_file or filename,
            'analyzed_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        }

        # 如果是产品优势类型，尝试构建更结构化的内容
        if material_type == 'advantage' and ai_type == 'product_advantage':
            content_json.update({
                'tech_features': '; '.join(structured.get('key_points', [])),
                'scope': analysis.get('scope', 'all'),
                'customer_value': structured.get('customer_value', []),
            })

        # 5. 创建素材
        data = {
            'material_key': base_key,
            'name': name,
            'material_type': material_type,
            'category': analysis.get('material_type', 'other'),
            'scope': analysis.get('scope', ''),
            'track': analysis.get('track', ''),
            'region': analysis.get('region', ''),
            'content_json': content_json,
            'content_summary': analysis.get('summary', ''),
            'priority': analysis.get('priority', 3),
            'is_active': 1,
            'tags': ', '.join(analysis.get('tags', [])) if analysis.get('tags') else '',
            'source': 'ai_import',
        }

        try:
            material_id = create_material(data, user_id=user_id)

            # 更新 source_file 和 ai_confidence 字段
            if source_file or analysis.get('confidence'):
                from database.connection import get_connection
                conn = get_connection()
                cursor = conn.cursor()
                update_fields = []
                update_params = []
                if source_file:
                    update_fields.append('source_file = ?')
                    update_params.append(source_file)
                if analysis.get('confidence'):
                    update_fields.append('ai_confidence = ?')
                    update_params.append(analysis.get('confidence'))
                if update_fields:
                    update_params.append(material_id)
                    cursor.execute(
                        f"UPDATE materials SET {', '.join(update_fields)} WHERE id = ?",
                        update_params
                    )
                    conn.commit()
                conn.close()

            return {
                'success': True,
                'material_id': material_id,
                'material_key': base_key,
                'action': 'created',
                'message': f'素材导入成功（ID: {material_id}）'
            }
        except Exception as e:
            return {
                'success': False,
                'material_id': None,
                'material_key': base_key,
                'action': 'error',
                'message': f'数据库写入失败: {str(e)}'
            }

    def batch_analyze(self, files: list) -> Dict:
        """
        批量分析多个文件

        Args:
            files: list of {'bytes': bytes, 'filename': str}

        Returns:
            {
                'results': [analysis_result, ...],
                'total': int,
                'success_count': int,
                'failed_count': int
            }
        """
        results = []
        for f in files:
            result = self.analyze_file(f['bytes'], f['filename'])
            results.append(result)
            # AI调用间隔，避免频率限制
            time.sleep(1)

        success_count = sum(1 for r in results if r['success'])
        return {
            'results': results,
            'total': len(files),
            'success_count': success_count,
            'failed_count': len(files) - success_count
        }


def _generate_material_key(name: str, filename: str) -> str:
    """生成唯一的素材 key"""
    import re
    # 从名称生成slug
    slug = re.sub(r'[^a-zA-Z0-9_\-\s]', '', name.lower())
    slug = re.sub(r'\s+', '_', slug).strip('_')
    # 添加时间戳后缀避免冲突
    timestamp = str(int(time.time()))[-6:]
    base_name = os.path.splitext(filename)[0]
    file_slug = re.sub(r'[^a-zA-Z0-9_\-\s]', '', base_name.lower())
    file_slug = re.sub(r'\s+', '_', file_slug).strip('_')
    if slug:
        return f"ai_{slug}_{timestamp}"
    elif file_slug:
        return f"ai_{file_slug}_{timestamp}"
    else:
        return f"ai_import_{timestamp}"


# 导入任务管理
def create_import_task(task_name: str = None) -> int:
    """创建批量导入任务"""
    from database.connection import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO import_tasks (task_name, status, total_files)
        VALUES (?, 'pending', 0)
    ''', (task_name or f'批量导入_{time.strftime("%Y%m%d_%H%M%S")}',))
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return task_id


def update_import_task(task_id: int, **fields):
    """更新导入任务状态"""
    from database.connection import get_connection
    conn = get_connection()
    cursor = conn.cursor()

    allowed_fields = [
        'status', 'total_files', 'processed_files',
        'imported_count', 'skipped_count', 'failed_count',
        'error_details', 'started_at', 'completed_at'
    ]

    set_clauses = []
    params = []
    for key, value in fields.items():
        if key in allowed_fields:
            set_clauses.append(f"{key} = ?")
            params.append(value)

    if set_clauses:
        params.append(task_id)
        cursor.execute(
            f"UPDATE import_tasks SET {', '.join(set_clauses)} WHERE id = ?",
            params
        )
        conn.commit()
    conn.close()


def get_import_task(task_id: int) -> Optional[Dict]:
    """获取导入任务状态"""
    from database.connection import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM import_tasks WHERE id = ?', (task_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    cols = ['id', 'task_name', 'status', 'total_files', 'processed_files',
            'imported_count', 'skipped_count', 'failed_count',
            'error_details', 'created_at', 'started_at', 'completed_at']
    return dict(zip(cols, row))


def get_import_tasks_list(status=None, limit=20) -> list:
    """获取导入任务列表"""
    from database.connection import get_connection
    conn = get_connection()
    cursor = conn.cursor()

    if status:
        cursor.execute(
            'SELECT * FROM import_tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?',
            (status, limit)
        )
    else:
        cursor.execute(
            'SELECT * FROM import_tasks ORDER BY created_at DESC LIMIT ?',
            (limit,)
        )

    cols = ['id', 'task_name', 'status', 'total_files', 'processed_files',
            'imported_count', 'skipped_count', 'failed_count',
            'error_details', 'created_at', 'started_at', 'completed_at']
    rows = cursor.fetchall()
    conn.close()

    return [dict(zip(cols, row)) for row in rows]
