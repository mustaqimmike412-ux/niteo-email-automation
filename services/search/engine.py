"""
搜索任务执行引擎
管理搜索任务的创建、执行、状态追踪
"""
import threading
import time
import uuid
from typing import List, Dict, Optional
from datetime import datetime

from services.search.registry import SearcherRegistry
from services.search.ai_enricher import SearchAIEnricher
from services.search.website_crawler import WebsiteCrawler
from services.search.email_finder import EmailFinder
from services.search.result_validator import ResultValidator
from services.search.keyword_expander import KeywordExpander
from database.search_models import (
    create_search_task, update_search_task, save_search_result,
    get_search_task, import_result_to_customer
)


class SearchTaskEngine:
    """搜索任务执行引擎"""

    def __init__(self):
        self.registry = SearcherRegistry()
        self.enricher = SearchAIEnricher()
        self.crawler = WebsiteCrawler()
        self.email_finder = EmailFinder()
        self.validator = ResultValidator()
        self.keyword_expander = KeywordExpander()
        self._tasks: Dict[str, dict] = {}  # 内存中的任务状态
        self._lock = threading.Lock()
        self._running_count = 0
        self._max_concurrent = 3

    def create_and_run(self, query: str, location: str, platforms: List[str],
                       config: dict = None, task_name: str = None,
                       queries: List[str] = None,
                       user_id: int = None) -> str:
        """创建并启动搜索任务"""
        task_id = f"search_{uuid.uuid4().hex[:8]}"
        cfg = config or {}

        # 创建数据库记录
        create_search_task(task_id, query, location, platforms, cfg, task_name, user_id=user_id)

        # 检查并发限制
        with self._lock:
            if self._running_count >= self._max_concurrent:
                update_search_task(task_id, status='pending',
                                   error_message='等待其他任务完成（并发限制）')
                return task_id

        # 启动后台线程
        thread = threading.Thread(
            target=self._execute_search,
            args=(task_id, query, location, platforms, cfg, queries, user_id),
            daemon=True
        )
        with self._lock:
            self._tasks[task_id] = {
                'status': 'running',
                'started_at': datetime.now().isoformat(),
            }
            self._running_count += 1

        update_search_task(task_id, status='running', started_at=datetime.now().isoformat())
        thread.start()
        return task_id

    def _execute_search(self, task_id: str, query: str, location: str,
                        platforms: List[str], config: dict,
                        preset_queries: List[str] = None,
                        user_id: int = None):
        """实际执行搜索任务"""
        max_results = config.get('max_results_per_platform', 20)
        enable_ai = config.get('enable_ai_enrich', True)
        enable_crawl = config.get('enable_website_crawl', True)
        auto_import_threshold = config.get('auto_import_threshold', 0)
        delay = config.get('request_delay_seconds', 2)
        max_duration = config.get('max_task_duration_seconds', 1800)

        start_time = time.time()
        all_results: List = []
        found_count = 0
        enriched_count = 0
        imported_count = 0

        # 加载拉黑名单
        try:
            from database.search_models import get_blacklisted_websites, get_blacklisted_names
            blacklist_websites = get_blacklisted_websites()
            blacklist_names = get_blacklisted_names()
            print(f"[SearchEngine] 加载拉黑名单: {len(blacklist_websites)} 个域名, {len(blacklist_names)} 个公司名")
        except Exception:
            blacklist_websites = set()
            blacklist_names = set()

        try:
            # === AI 关键词拓展（或直接使用预设关键词）===
            if preset_queries:
                queries = preset_queries
                update_search_task(task_id, expanded_keywords=','.join(queries))
                print(f"[SearchEngine] {task_id} 使用预设关键词列表: {queries}")
            else:
                queries = [query]
                enable_expand = config.get('enable_keyword_expand', False)
                if enable_expand:
                    print(f"[SearchEngine] {task_id} 启用关键词拓展...")
                    expanded = self.keyword_expander.expand(query, location, max_keywords=config.get('max_expanded_keywords', 8))
                    if len(expanded) > 1:
                        queries = expanded
                        update_search_task(task_id, expanded_keywords=','.join(queries))
                        print(f"[SearchEngine] {task_id} 关键词拓展完成: {queries}")

            # 计算预计目标数：用户设置的 max_results 是总量上限，不是每个关键词的上限
            total_targets = len(platforms) * max_results
            update_search_task(task_id, total_targets=total_targets)

            # === 阶段1：收集 — 用所有关键词搜索，每个关键词获取更多候选 ===
            raw_results = []  # 收集所有原始结果（未截断）
            for platform in platforms:
                for q in queries:
                    # 检查是否超时
                    if time.time() - start_time > max_duration:
                        update_search_task(task_id, status='completed',
                                           error_message='任务因超时而终止')
                        break

                    # 检查任务状态
                    task = get_search_task(task_id)
                    if task and task.get('status') == 'cancelled':
                        break

                    try:
                        searcher = self.registry.get_searcher(platform, config)
                        if not searcher.is_available():
                            print(f"[SearchEngine] {platform} 不可用，跳过")
                            continue

                        print(f"[SearchEngine] {task_id} 搜索 {platform}: '{q}' in '{location}'")
                        # 获取更多候选用于后续筛选（最多30个/关键词，避免过多）
                        results = searcher.search(q, location, min(max_results * 3, 30))
                        print(f"[SearchEngine] {platform} 找到 {len(results)} 条原始结果")
                    except Exception as e:
                        print(f"[SearchEngine] {platform} 搜索失败: {e}")
                        continue

                    # === 第一层漏斗：预爬取验证（Layer 1-5）===
                    pre_filter_count = len(results)
                    results = self.validator.run_pre_crawl_validation(results, query, location)
                    filtered_count = pre_filter_count - len([r for r in results if r.validation_status != 'rejected'])
                    print(f"[SearchEngine] {platform} 验证过滤: {pre_filter_count} → {len(results)} 条")

                    for r in results:
                        r.search_keyword = q
                        r.search_location = location
                        raw_results.append(r)

                    time.sleep(delay)

            # === 阶段2：全局去重 + 截断 — 所有关键词的结果合并后只保留最好的 max_results 个 ===
            print(f"[SearchEngine] {task_id} 收集完成: {len(raw_results)} 条原始结果，去重并截断到 {max_results} 条...")

            # 全局去重（基于 website 域名）
            seen_websites = set()
            deduped_results = []
            for r in raw_results:
                norm_web = (r.website or '').lower().strip().replace('http://', '').replace('https://', '').replace('www.', '')
                if not norm_web:
                    continue
                if norm_web in seen_websites:
                    continue
                seen_websites.add(norm_web)

                # 拉黑过滤
                r_name = (r.raw_data.get('name') or '').lower().strip()
                if norm_web in blacklist_websites:
                    print(f"[SearchEngine] 跳过拉黑域名: {norm_web}")
                    continue
                if r_name and r_name in blacklist_names:
                    print(f"[SearchEngine] 跳过拉黑公司: {r_name}")
                    continue

                deduped_results.append(r)

            print(f"[SearchEngine] {task_id} 去重后: {len(deduped_results)} 条")

            # 按 confidence_score 排序，取前 max_results 个
            if len(deduped_results) > max_results:
                deduped_results.sort(key=lambda r: r.confidence_score or 0, reverse=True)
                all_results = deduped_results[:max_results]
                print(f"[SearchEngine] {task_id} 截断到前 {max_results} 条（按置信度排序）")
            else:
                all_results = deduped_results

            found_count = len(all_results)
            update_search_task(task_id, found_count=found_count)

            # 网站二次爬取 — 仅对验证通过或待审核的结果执行
            crawl_rejected = 0
            if enable_crawl:
                crawl_targets = [r for r in all_results
                                 if r.validation_status in ('validated', 'needs_review')
                                 and r.confidence_score >= config.get('min_confidence_for_crawl', 0.3)]
                print(f"[SearchEngine] {task_id} 开始网站爬取（{len(crawl_targets)}/{len(all_results)} 条通过预检）...")
                for i, result in enumerate(crawl_targets):
                    if time.time() - start_time > max_duration:
                        break
                    if result.website and result.website.startswith('http'):
                        try:
                            crawl_data = self.crawler.crawl(result.website)
                            if crawl_data:
                                # 爬取后二次校验
                                passed, crawl_score = self.validator.validate_crawl_content(
                                    result, crawl_data, query, location)
                                if passed:
                                    result.confidence_score = max(result.confidence_score, crawl_score)
                                    # 补充爬取到的信息
                                    if crawl_data.get('emails'):
                                        result.raw_data['crawled_emails'] = crawl_data['emails']
                                        if not result.email:
                                            result.email = crawl_data['emails'][0]
                                    if crawl_data.get('phones') and not result.phone:
                                        result.phone = crawl_data['phones'][0]
                                    if crawl_data.get('title') and not result.company_name:
                                        result.company_name = crawl_data['title']
                                    result.raw_data['crawl_data'] = crawl_data
                                else:
                                    result.validation_status = 'rejected'
                                    result.validation_reason = 'crawl_content_not_company_site'
                                    crawl_rejected += 1
                                    print(f"[SearchEngine] 爬取内容校验失败: {result.website}")
                        except Exception as e:
                            print(f"[SearchEngine] 爬取失败 {result.website}: {e}")
                    time.sleep(delay)
                print(f"[SearchEngine] 爬取完成: {len(crawl_targets) - crawl_rejected} 条通过, {crawl_rejected} 条被拒绝")

            # AI分析 - 仅对高置信度结果执行
            ai_skipped = 0
            if enable_ai and self.enricher.is_available():
                ai_targets = [r for r in all_results
                              if r.validation_status != 'rejected'
                              and r.confidence_score >= config.get('min_confidence_for_ai_enrich', 0.3)]
                ai_skipped = len(all_results) - len(ai_targets)
                print(f"[SearchEngine] {task_id} 开始AI分析（{len(ai_targets)}/{len(all_results)} 条符合门槛，跳过 {ai_skipped} 条）...")
                ai_start_time = time.time()
                ai_max_duration = 1800  # AI分析单独给30分钟

                for i, result in enumerate(ai_targets):
                    # AI阶段单独超时检查
                    if time.time() - ai_start_time > ai_max_duration:
                        print(f"[SearchEngine] AI分析阶段超时，已分析 {enriched_count}/{i} 条")
                        break

                    try:
                        company_name = result.company_name or result.raw_data.get('name', '未知')
                        print(f"[SearchEngine] AI分析 {i+1}/{len(ai_targets)}: {company_name[:40]}")

                        # 如果有爬取数据，使用增强分析
                        crawl_data = result.raw_data.get('crawl_data')
                        # 若无爬取数据但预检有 title/description，构造轻量数据供深度分析
                        if not crawl_data:
                            probe = result.probe_data or {}
                            if probe.get('title') or probe.get('description'):
                                crawl_data = {
                                    'title': probe.get('title', ''),
                                    'description': probe.get('description', ''),
                                    'all_text': f"{probe.get('title', '')}\n{probe.get('description', '')}",
                                    'about_text': probe.get('description', ''),
                                    'emails': [],
                                    'phones': [],
                                }
                                print(f"[SearchEngine]   -> 使用深度分析（基于预检数据）")

                        if crawl_data:
                            print(f"[SearchEngine]   -> 使用深度分析（含网站爬取）")
                            analysis = self.enricher.enrich_with_crawl(result, crawl_data)
                        else:
                            print(f"[SearchEngine]   -> 使用基础分析")
                            analysis = self.enricher.enrich_result(result)

                        if analysis:
                            result.company_name = analysis.get('company_name', result.company_name)
                            result.website = analysis.get('website', result.website)
                            result.country = analysis.get('country', result.country)
                            result.address = analysis.get('address', result.address)
                            result.phone = analysis.get('phone', result.phone)
                            result.email = analysis.get('email', result.email)
                            result.industry_type = analysis.get('industry_type', result.industry_type)
                            result.business_model = analysis.get('business_model', result.business_model)
                            result.raw_data['ai_analysis'] = analysis
                            enriched_count += 1
                            print(f"[SearchEngine]   -> 成功 (confidence={analysis.get('confidence_score')})")
                        else:
                            print(f"[SearchEngine]   -> 分析返回空，尝试基础分析兜底...")
                            # 兜底：至少尝试基础分析
                            analysis = self.enricher.enrich_result(result)
                            if analysis:
                                result.raw_data['ai_analysis'] = analysis
                                enriched_count += 1
                                print(f"[SearchEngine]   -> 兜底成功")
                            else:
                                print(f"[SearchEngine]   -> 兜底也失败，跳过")
                    except Exception as e:
                        print(f"[SearchEngine] AI分析失败 {i+1}: {e}")
                        import traceback
                        traceback.print_exc()

                    # AI分析间隔稍长，避免API限流
                    time.sleep(delay)

                print(f"[SearchEngine] AI分析完成: {enriched_count}/{len(ai_targets)} 条成功, {ai_skipped} 条因置信度不足跳过")
                update_search_task(task_id, ai_enriched_count=enriched_count)

            # 保存结果到数据库
            print(f"[SearchEngine] {task_id} 保存 {len(all_results)} 条结果到数据库...")
            for result in all_results:
                ai_analysis = result.raw_data.get('ai_analysis')
                confidence = ai_analysis.get('confidence_score') if ai_analysis else None

                # 全网搜索邮箱 — 仅对高置信度结果执行
                emails_json = None
                if (result.company_name
                    and result.validation_status != 'rejected'
                    and result.confidence_score >= config.get('min_confidence_for_email_finder', 0.5)):
                    try:
                        print(f"[SearchEngine]   -> 搜索邮箱: {result.company_name}")
                        emails = self.email_finder.find_emails(
                            company_name=result.company_name,
                            website=result.website,
                            country=result.country
                        )
                        if emails:
                            emails_json = emails
                            # 同时更新主email字段（取第一个职位邮箱或第一个邮箱）
                            if not result.email:
                                role_emails = [e for e in emails if e['type'] == 'role']
                                if role_emails:
                                    result.email = role_emails[0]['email']
                                else:
                                    result.email = emails[0]['email']
                            print(f"[SearchEngine]   -> 找到 {len(emails)} 个邮箱")
                    except Exception as e:
                        print(f"[SearchEngine] 邮箱搜索失败: {e}")
                elif result.validation_status == 'rejected':
                    print(f"[SearchEngine]   -> 跳过邮箱搜索（结果已拒绝）")
                elif result.confidence_score < config.get('min_confidence_for_email_finder', 0.5):
                    print(f"[SearchEngine]   -> 跳过邮箱搜索（置信度 {result.confidence_score:.2f} < 0.5）")

                save_search_result(
                    task_id=task_id,
                    platform=result.platform,
                    source_url=result.source_url,
                    raw_data=result.raw_data,
                    company_name=result.company_name,
                    website=result.website,
                    country=result.country,
                    address=result.address,
                    phone=result.phone,
                    email=result.email,
                    industry_type=result.industry_type,
                    business_model=result.business_model,
                    confidence_score=result.confidence_score if result.confidence_score is not None else confidence,
                    ai_analysis=ai_analysis,
                    search_keyword=query,
                    search_location=location,
                    emails_json=emails_json,
                    validation_status=result.validation_status,
                    validation_reason=result.validation_reason,
                    pre_crawl_score=result.confidence_score,
                    crawl_validation_passed=result.validation_status == 'validated',
                    probe_title=result.probe_data.get('title', '') if result.probe_data else '',
                    probe_description=result.probe_data.get('description', '') if result.probe_data else '',
                    user_id=user_id
                )

                # 自动导入（高置信度）
                if auto_import_threshold > 0 and confidence and confidence >= auto_import_threshold:
                    try:
                        # 获取刚保存的结果ID
                        conn = get_search_task(task_id)  # 这里只是为了保持连接，实际逻辑在下面
                        # 由于save_search_result返回了result_id，但我们在循环中没保存
                        # 自动导入改为在保存后通过API触发更合理
                        pass
                    except Exception:
                        pass

            # 统计被拒绝的结果数
            pre_filtered = len([r for r in all_results if r.validation_status == 'rejected'])

            # 更新任务完成状态（含验证统计）
            update_search_task(
                task_id,
                status='completed',
                found_count=found_count,
                ai_enriched_count=enriched_count,
                pre_filtered_count=pre_filtered,
                crawl_rejected_count=crawl_rejected,
                ai_skipped_count=ai_skipped,
                completed_at=datetime.now().isoformat()
            )
            print(f"[SearchEngine] {task_id} 完成: 找到{found_count}条, 预过滤{pre_filtered}条, 爬取拒绝{crawl_rejected}条, AI跳过{ai_skipped}条, AI分析{enriched_count}条")

        except Exception as e:
            print(f"[SearchEngine] {task_id} 执行异常: {e}")
            update_search_task(task_id, status='failed', error_message=str(e)[:500])

        finally:
            with self._lock:
                self._running_count = max(0, self._running_count - 1)
                if task_id in self._tasks:
                    self._tasks[task_id]['status'] = 'completed'

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        task = get_search_task(task_id)
        if not task or task.get('status') not in ('pending', 'running'):
            return False
        update_search_task(task_id, status='cancelled')
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id]['status'] = 'cancelled'
        return True

    def get_task_status(self, task_id: str) -> Optional[dict]:
        """获取任务状态（内存+数据库合并）"""
        task = get_search_task(task_id)
        if not task:
            return None

        # 合并内存状态
        with self._lock:
            mem_status = self._tasks.get(task_id, {})

        return {
            **task,
            'memory_status': mem_status.get('status', task.get('status')),
        }

    def cleanup_completed(self, max_age_hours: int = 24):
        """清理内存中已完成的任务状态"""
        with self._lock:
            to_remove = []
            for tid, info in self._tasks.items():
                if info.get('status') in ('completed', 'failed', 'cancelled'):
                    started = info.get('started_at')
                    if started:
                        try:
                            from datetime import datetime
                            start_dt = datetime.fromisoformat(started)
                            hours_ago = (datetime.now() - start_dt).total_seconds() / 3600
                            if hours_ago > max_age_hours:
                                to_remove.append(tid)
                        except Exception:
                            to_remove.append(tid)
            for tid in to_remove:
                del self._tasks[tid]


# 全局引擎实例
_search_engine = None

def get_search_engine() -> SearchTaskEngine:
    """获取全局搜索引擎实例"""
    global _search_engine
    if _search_engine is None:
        _search_engine = SearchTaskEngine()
    return _search_engine
