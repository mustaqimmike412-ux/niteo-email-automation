"""
搜索任务执行引擎（优化版）
管理搜索任务的创建、执行、状态追踪
关键优化：
  - 搜索/爬取/AI分析均采用 ThreadPoolExecutor 并行化
  - 数据库批量插入替代逐条插入
  - 取消状态内存缓存减少 DB 往返
  - 精简超时和延迟配置
"""
import threading
import time
import uuid
from typing import List, Dict, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from services.search.registry import SearcherRegistry
from services.search.ai_enricher import SearchAIEnricher
from services.search.website_crawler import WebsiteCrawler
from services.search.email_finder import EmailFinder
from services.search.result_validator import ResultValidator
from services.search.keyword_expander import KeywordExpander
from database.search_models import (
    create_search_task, update_search_task, save_search_result,
    save_search_results_batch, get_search_task, import_result_to_customer
)
from database.connection import get_connection


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

    def _is_task_cancelled(self, task_id: str, cache: dict) -> bool:
        """内存缓存的取消状态检查，减少 DB 往返"""
        if task_id in cache:
            return cache[task_id]
        task = get_search_task(task_id)
        cancelled = task and task.get('status') == 'cancelled'
        cache[task_id] = cancelled
        return cancelled

    def _execute_search(self, task_id: str, query: str, location: str,
                        platforms: List[str], config: dict,
                        preset_queries: List[str] = None,
                        user_id: int = None):
        """实际执行搜索任务（并行优化版）"""
        cancel_cache = {}
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

            total_targets = len(platforms) * max_results
            update_search_task(task_id, total_targets=total_targets)

            # ========== 阶段1：并行搜索 + 预验证 ==========
            raw_results = []
            search_jobs = []
            for platform in platforms:
                for q in queries:
                    search_jobs.append((platform, q))

            def _do_search(job):
                platform, q = job
                if time.time() - start_time > max_duration:
                    return []
                try:
                    searcher = self.registry.get_searcher(platform, config)
                    if not searcher.is_available():
                        return []
                    results = searcher.search(q, location, min(max_results * 3, 30))
                    # 预验证
                    pre_count = len(results)
                    results = self.validator.run_pre_crawl_validation(results, query, location)
                    for r in results:
                        r.search_keyword = q
                        r.search_location = location
                    return results
                except Exception as e:
                    print(f"[SearchEngine] {platform} 搜索失败 ({q}): {e}")
                    return []

            with ThreadPoolExecutor(max_workers=min(len(search_jobs), 5)) as pool:
                futures = {pool.submit(_do_search, job): job for job in search_jobs}
                for future in as_completed(futures):
                    if self._is_task_cancelled(task_id, cancel_cache):
                        break
                    raw_results.extend(future.result())

            if self._is_task_cancelled(task_id, cancel_cache):
                update_search_task(task_id, status='cancelled')
                return

            print(f"[SearchEngine] {task_id} 收集完成: {len(raw_results)} 条原始结果")

            # 阶段2：全局去重 + 截断
            seen_websites = set()
            deduped_results = []
            for r in raw_results:
                norm_web = (r.website or '').lower().strip().replace('http://', '').replace('https://', '').replace('www.', '')
                if not norm_web or norm_web in seen_websites:
                    continue
                seen_websites.add(norm_web)
                r_name = (r.raw_data.get('name') or '').lower().strip()
                if norm_web in blacklist_websites or (r_name and r_name in blacklist_names):
                    continue
                deduped_results.append(r)

            if len(deduped_results) > max_results:
                deduped_results.sort(key=lambda r: r.confidence_score or 0, reverse=True)
                all_results = deduped_results[:max_results]
            else:
                all_results = deduped_results

            found_count = len(all_results)
            update_search_task(task_id, found_count=found_count)
            print(f"[SearchEngine] {task_id} 去重截断后: {found_count} 条")

            # ========== 阶段3：并行网站爬取 ==========
            crawl_rejected = 0
            if enable_crawl:
                crawl_targets = [r for r in all_results
                                 if r.validation_status in ('validated', 'needs_review')
                                 and r.confidence_score >= config.get('min_confidence_for_crawl', 0.3)]
                print(f"[SearchEngine] {task_id} 并行爬取 {len(crawl_targets)} 条...")

                def _do_crawl(result):
                    nonlocal crawl_rejected
                    if time.time() - start_time > max_duration:
                        return result
                    if not (result.website and result.website.startswith('http')):
                        return result
                    try:
                        crawl_data = self.crawler.crawl(result.website)
                        if crawl_data:
                            passed, crawl_score = self.validator.validate_crawl_content(
                                result, crawl_data, query, location)
                            if passed:
                                result.confidence_score = max(result.confidence_score, crawl_score)
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
                    except Exception as e:
                        print(f"[SearchEngine] 爬取失败 {result.website}: {e}")
                    return result

                with ThreadPoolExecutor(max_workers=min(len(crawl_targets), 5)) as pool:
                    futures = {pool.submit(_do_crawl, r): r for r in crawl_targets}
                    for future in as_completed(futures):
                        if self._is_task_cancelled(task_id, cancel_cache):
                            break
                        future.result()

                print(f"[SearchEngine] 爬取完成: {len(crawl_targets) - crawl_rejected} 条通过, {crawl_rejected} 条被拒绝")

            if self._is_task_cancelled(task_id, cancel_cache):
                update_search_task(task_id, status='cancelled')
                return

            # ========== 阶段4：并行 AI 分析 ==========
            ai_skipped = 0
            if enable_ai and self.enricher.is_available():
                ai_targets = [r for r in all_results
                              if r.validation_status != 'rejected'
                              and r.confidence_score >= config.get('min_confidence_for_ai_enrich', 0.3)]
                ai_skipped = len(all_results) - len(ai_targets)
                print(f"[SearchEngine] {task_id} 并行AI分析 {len(ai_targets)} 条（跳过 {ai_skipped} 条）...")
                ai_start_time = time.time()
                ai_max_duration = 1800

                def _do_ai(result):
                    if time.time() - ai_start_time > ai_max_duration:
                        return result
                    try:
                        crawl_data = result.raw_data.get('crawl_data')
                        if not crawl_data:
                            probe = result.probe_data or {}
                            if probe.get('title') or probe.get('description'):
                                crawl_data = {
                                    'title': probe.get('title', ''),
                                    'description': probe.get('description', ''),
                                    'all_text': f"{probe.get('title', '')}\n{probe.get('description', '')}",
                                    'about_text': probe.get('description', ''),
                                    'emails': [], 'phones': [],
                                }
                        if crawl_data:
                            analysis = self.enricher.enrich_with_crawl(result, crawl_data)
                        else:
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
                    except Exception as e:
                        print(f"[SearchEngine] AI分析失败: {e}")
                    return result

                with ThreadPoolExecutor(max_workers=min(len(ai_targets), 4)) as pool:
                    futures = {pool.submit(_do_ai, r): r for r in ai_targets}
                    for future in as_completed(futures):
                        if self._is_task_cancelled(task_id, cancel_cache):
                            break
                        future.result()
                        enriched_count += 1

                print(f"[SearchEngine] AI分析完成: {enriched_count}/{len(ai_targets)} 条")
                update_search_task(task_id, ai_enriched_count=enriched_count)

            # ========== 阶段5：邮箱搜索 + 批量保存 ==========
            print(f"[SearchEngine] {task_id} 保存 {len(all_results)} 条结果...")
            batch_records = []
            for result in all_results:
                ai_analysis = result.raw_data.get('ai_analysis')
                confidence = ai_analysis.get('confidence_score') if ai_analysis else None

                emails_json = None
                if (result.company_name
                    and result.validation_status != 'rejected'
                    and result.confidence_score >= config.get('min_confidence_for_email_finder', 0.5)):
                    try:
                        emails = self.email_finder.find_emails(
                            company_name=result.company_name,
                            website=result.website,
                            country=result.country
                        )
                        if emails:
                            emails_json = emails
                            if not result.email:
                                role_emails = [e for e in emails if e['type'] == 'role']
                                result.email = role_emails[0]['email'] if role_emails else emails[0]['email']
                    except Exception:
                        pass

                batch_records.append({
                    'task_id': task_id,
                    'platform': result.platform,
                    'source_url': result.source_url,
                    'raw_data': result.raw_data,
                    'company_name': result.company_name,
                    'website': result.website,
                    'country': result.country,
                    'address': result.address,
                    'phone': result.phone,
                    'email': result.email,
                    'industry_type': result.industry_type,
                    'business_model': result.business_model,
                    'confidence_score': result.confidence_score if result.confidence_score is not None else confidence,
                    'ai_analysis': ai_analysis,
                    'search_keyword': query,
                    'search_location': location,
                    'emails_json': emails_json,
                    'validation_status': result.validation_status,
                    'validation_reason': result.validation_reason,
                    'pre_crawl_score': result.confidence_score,
                    'crawl_validation_passed': result.validation_status == 'validated',
                    'probe_title': result.probe_data.get('title', '') if result.probe_data else '',
                    'probe_description': result.probe_data.get('description', '') if result.probe_data else '',
                    'user_id': user_id
                })

            if batch_records:
                try:
                    save_search_results_batch(batch_records)
                except Exception as e:
                    print(f"[SearchEngine] 批量保存失败: {e}，回退逐条")
                    for item in batch_records:
                        try:
                            save_search_result(**item)
                        except Exception:
                            pass

            pre_filtered = len([r for r in all_results if r.validation_status == 'rejected'])
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
