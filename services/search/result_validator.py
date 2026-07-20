"""
搜索结果精度验证引擎 — 五层漏斗式校验系统
在搜索结果进入高成本操作（深度爬取、AI分析、邮箱搜索）之前进行多道过滤
"""
import re
import time
import requests
from urllib.parse import urlparse
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

from services.search.base import SearchResult


@dataclass
class ValidationResult:
    """验证结果"""
    is_valid: bool = True
    confidence_score: float = 0.0
    layer_scores: dict = field(default_factory=dict)
    rejection_reason: str = ''
    probe_data: dict = field(default_factory=dict)


class ResultValidator:
    """搜索结果验证器 — 五层漏斗校验"""

    # ===== 国家/地区同义词库（仅用于过滤，不参与文本匹配打分）=====
    COUNTRY_SYNONYMS = {
        'usa': {'usa', 'us', 'united states', 'united states of america', 'america', 'american',
                'u.s.a', 'u.s.a.', 'unitedstates', 'u.s.', 'us of a', 'the states', 'stateside'},
        'uk': {'uk', 'united kingdom', 'britain', 'great britain', 'england', 'english', 'scotland', 'wales',
               'northern ireland', 'british', 'u.k.', 'u.k', 'gb', 'g.b.', 'unitedkingdom'},
        'germany': {'germany', 'german', 'deutschland', 'de', 'bundesrepublik deutschland', 'federal republic of germany',
                   'alemania', 'allemagne'},
        'france': {'france', 'french', 'république française', 'republic of france', 'française', 'francaise'},
        'china': {'china', 'chinese', 'prc', "people's republic of china", 'pr of china',
                  'zhongguo', 'mainland china', 'shenzhen', 'guangzhou', 'beijing', 'shanghai',
                  'dongguan', 'yiwu'},
        'india': {'india', 'indian', 'bharat', 'republic of india', 'hindustan'},
        'japan': {'japan', 'japanese', 'nippon', 'nihon'},
        'australia': {'australia', 'australian', 'aussie', 'oz', 'commonwealth of australia'},
        'canada': {'canada', 'canadian', 'ca'},
        'italy': {'italy', 'italian', 'italia', 'republic of italy'},
        'spain': {'spain', 'spanish', 'españa', 'espana', 'es'},
        'brazil': {'brazil', 'brazilian', 'brasil', 'br', 'federative republic of brazil'},
        'mexico': {'mexico', 'mexican', 'méxico', 'mx', 'united mexican states'},
        'south korea': {'south korea', 'korean', 'republic of korea', 'rok', 'korea'},
        'netherlands': {'netherlands', 'dutch', 'holland', 'nederland', 'the netherlands', 'nl'},
        'turkey': {'turkey', 'turkish', 'türkiye', 'türkiye cumhuriyeti'},
        'thailand': {'thailand', 'thai', 'kingdom of thailand'},
        'vietnam': {'vietnam', 'vietnamese', 'viet nam', 'socialist republic of vietnam'},
        'indonesia': {'indonesia', 'indonesian', 'id'},
        'malaysia': {'malaysia', 'malaysian', 'my'},
        'singapore': {'singapore', 'singaporean', 'sg'},
        'uae': {'uae', 'united arab emirates', 'dubai', 'abu dhabi', 'emirates', 'emirati'},
        'saudi arabia': {'saudi arabia', 'saudi', 'ksa', 'kingdom of saudi arabia'},
        'russia': {'russia', 'russian', 'russian federation', 'ru', 'russa'},
        'poland': {'poland', 'polish', 'polska', 'republic of poland', 'pl'},
        'switzerland': {'switzerland', 'swiss', 'schweiz', 'suisse', 'svizzera', 'ch'},
        'sweden': {'sweden', 'swedish', 'sverige', 'kingdom of sweden', 'se'},
        'norway': {'norway', 'norwegian', 'norge', 'kingdom of norway', 'no'},
        'denmark': {'denmark', 'danish', 'danmark', 'kingdom of denmark', 'dk'},
        'finland': {'finland', 'finnish', 'suomi', 'republic of finland', 'fi'},
        'ireland': {'ireland', 'irish', 'republic of ireland', 'eire', 'ie'},
        'austria': {'austria', 'austrian', 'österreich', 'oesterreich', 'at'},
        'belgium': {'belgium', 'belgian', 'belgique', 'belgië', 'be'},
        'portugal': {'portugal', 'portuguese', 'república portuguesa', 'pt'},
        'czech republic': {'czech republic', 'czech', 'czechia', 'češka', 'cz'},
        'argentina': {'argentina', 'argentine', 'argentino'},
        'south africa': {'south africa', 'south african', 'sa', 'za', 'republic of south africa'},
        'egypt': {'egypt', 'egyptian', 'arab republic of egypt', 'eg'},
        'philippines': {'philippines', 'filipino', 'ph', 'republic of the philippines'},
        'colombia': {'colombia', 'colombian', 'co'},
        'chile': {'chile', 'chilean', 'cl'},
        'israel': {'israel', 'israeli', 'il', 'state of israel'},
        'new zealand': {'new zealand', 'nz', 'aotearoa', 'kiwi'},
        'taiwan': {'taiwan', 'taiwanese', 'tw', 'roc'},
        'hong kong': {'hong kong', 'hk', 'hongkong'},
        'europe': {'europe', 'european', 'eu', 'eurozone'},
        'asia': {'asia', 'asian'},
        'africa': {'africa', 'african'},
        'middle east': {'middle east', 'mena', 'gulf', 'gcc'},
        'southeast asia': {'southeast asia', 'sea', 'asean'},
        'latin america': {'latin america', 'latam', 'latinoamérica'},
        'worldwide': {'worldwide', 'global', 'international', 'world', 'all countries'},
    }

    def _build_country_word_set(self, location: str = '') -> set:
        """根据目标地区构建国家同义词集合，用于从匹配关键词中排除"""
        country_words = set()
        if location:
            loc_lower = location.lower().strip()
            for key, synonyms in self.COUNTRY_SYNONYMS.items():
                if loc_lower in synonyms or loc_lower == key:
                    country_words.update(synonyms)
            # 如果没找到精确匹配，直接把 location 本身加入
            if not country_words:
                loc_words = [w for w in re.findall(r'[a-z]+', loc_lower) if len(w) >= 2]
                country_words.update(loc_words)
                country_words.add(loc_lower)
        return country_words

    # ===== Layer 1: 域名黑名单 =====
    DOMAIN_BLACKLIST = {
        # 论坛类
        'reddit.com', 'quora.com', 'stackexchange.com', 'stackoverflow.com',
        'medium.com', 'tumblr.com', 'discord.com', 'slack.com',
        # 目录/黄页类
        'yelp.com', 'bbb.org', 'yellowpages.com', 'tripadvisor.com',
        'angieslist.com', 'homeadvisor.com', 'thumbtack.com', 'houzz.com',
        'crunchbase.com', 'owler.com', 'zoominfo.com', 'clutch.co',
        'goodfirms.co', 'designrush.com', 'g2.com', 'capterra.com',
        'trustpilot.com', 'glassdoor.com', 'indeed.com',
        # 电商集市
        'amazon.com', 'ebay.com', 'alibaba.com', 'aliexpress.com',
        'etsy.com', 'shopify.com', 'walmart.com', 'wayfair.com',
        # 新闻聚合/博客平台
        'news.google.com', 'flipboard.com', 'feedly.com',
        # 分类广告
        'craigslist.org', 'gumtree.com', 'olx.com', 'kijiji.ca',
        # 通用博客/建站平台
        'blogspot.com', 'wordpress.com', 'wixsite.com', 'weebly.com',
        'squarespace.com', 'google.com', 'sites.google.com',
    }

    # 子域名黑名单模式 (通配符)
    SUBDOMAIN_BLACKLIST_PATTERNS = [
        r'.*\.blogspot\.com',
        r'.*\.wordpress\.com',
        r'.*\.wixsite\.com',
        r'.*\.weebly\.com',
        r'.*\.squarespace\.com',
        r'.*\.github\.io',
        r'.*\.webflow\.io',
        r'.*\.netlify\.app',
        r'.*\.vercel\.app',
    ]

    # URL路径黑名单
    URL_PATH_BLACKLIST = {
        '/forum/', '/forums/', '/community/',
        '/directory/', '/directories/', '/list/',
        '/reviews/', '/review/', '/rating/',
        '/profile/', '/profiles/', '/user/',
        '/search?', '/tag/', '/category/', '/author/',
        '/page/', '/pages/', '/post/', '/posts/',
        '/product-category/', '/shop/', '/store/',
        '/job/', '/jobs/', '/career/', '/careers/',
        '/event/', '/events/', '/news/', '/article/',
        '/blog/', '/blogs/', '/wiki/',
    }

    # ===== Layer 5: 聚合器信号词 =====
    AGGREGATOR_SIGNALS = {
        'directory', 'directories', 'list of', 'top 10', 'top 20', 'top 50',
        'best', 'compare', 'comparison', 'reviews', 'review site',
        'forum', 'forums', 'community', 'discussion',
        'aggregator', 'aggregator site', 'listing',
        'classifieds', 'classified ads', 'marketplace',
        'social media', 'social network', 'profile page',
    }

    # 公司名中的通用词（去掉这些再和域名比较）
    COMPANY_STOP_WORDS = {
        'inc', 'llc', 'ltd', 'limited', 'corp', 'corporation',
        'co', 'company', 'gmbh', 'sarl', 'sa', 'bv', 'nv',
        'plc', 'ag', 'kg', 'ohg', 'kgaa',
        'the', 'and', '&', 'of', 'for', 'in', 'at',
        'solar', 'energy', 'power', 'electric', 'renewable',
    }

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.user_agent = self.config.get('user_agent', 'NiteoSolar-LeadBot/1.0')
        self.enabled = self.config.get('validation_enabled', True)
        # 加载自定义黑名单/白名单
        self.custom_blacklist = set(self.config.get('custom_domain_blacklist', []))
        self.custom_whitelist = set(self.config.get('custom_domain_whitelist', []))
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': self.user_agent})

    # ========== Layer 1: 域名黑名单过滤 ==========

    def _check_domain_blacklist(self, url: str) -> Tuple[bool, str]:
        """检查域名是否在黑名单中。返回 (是否通过, 原因)"""
        if not url:
            return True, ''

        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith('www.'):
            domain = domain[4:]

        # 白名单优先
        if domain in self.custom_whitelist:
            return True, ''

        # 自定义黑名单
        if domain in self.custom_blacklist:
            return False, f'custom_blacklist: {domain}'

        # 内置黑名单（完全匹配或后缀匹配）
        for black_domain in self.DOMAIN_BLACKLIST:
            if domain == black_domain or domain.endswith('.' + black_domain):
                return False, f'domain_blacklist: {black_domain}'

        # 子域名模式黑名单
        for pattern in self.SUBDOMAIN_BLACKLIST_PATTERNS:
            if re.match(pattern, domain):
                return False, f'subdomain_blacklist: {pattern}'

        # URL路径黑名单
        path = parsed.path.lower()
        for bad_path in self.URL_PATH_BLACKLIST:
            if bad_path in path:
                return False, f'path_blacklist: {bad_path}'

        return True, ''

    # ========== Layer 2: 名称-域名一致性 ==========

    def _check_name_domain_consistency(self, company_name: str, website: str) -> float:
        """
        检查公司名称关键词是否出现在域名中。
        返回 0.0-1.0 的一致性分数
        """
        if not company_name or not website:
            return 0.5  # 信息不足，给中性分

        parsed = urlparse(website)
        domain = parsed.netloc.lower()
        if domain.startswith('www.'):
            domain = domain[4:]
        # 去掉TLD
        domain_base = domain.split('.')[0] if '.' in domain else domain

        # 提取公司名称关键词
        name_lower = company_name.lower()
        # 去掉通用词
        for stop in self.COMPANY_STOP_WORDS:
            name_lower = re.sub(r'\b' + re.escape(stop) + r'\b', '', name_lower)
        # 提取字母数字词
        name_words = [w for w in re.findall(r'[a-z0-9]+', name_lower) if len(w) >= 2]

        if not name_words:
            return 0.5

        # 检查每个关键词是否在域名中出现
        matched = 0
        for word in name_words:
            if word in domain_base:
                matched += 1
            elif len(word) >= 4:
                # 模糊匹配：前4个字符匹配也算
                if domain_base.startswith(word[:4]):
                    matched += 0.5

        score = matched / len(name_words)
        # 映射到 0.3-1.0 范围
        return 0.3 + score * 0.7

    # ========== Layer 3: HTTP轻量预检 ==========

    def quick_probe(self, url: str) -> Optional[dict]:
        """
        轻量级HTTP预检：仅获取title和meta description
        返回: {status_code, title, description, is_alive, error}
        """
        if not url or not url.startswith('http'):
            return None

        try:
            resp = self.session.get(
                url,
                timeout=self.config.get('probe_timeout_seconds', 5),
                allow_redirects=True,
                headers={'User-Agent': self.user_agent},
                verify=True
            )
            return self._parse_probe_response(resp)

        except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
            # SSL/连接错误：尝试关闭证书验证重试
            try:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                resp = self.session.get(
                    url,
                    timeout=self.config.get('probe_timeout_seconds', 5),
                    allow_redirects=True,
                    headers={'User-Agent': self.user_agent},
                    verify=False
                )
                return self._parse_probe_response(resp)
            except Exception as e2:
                return {'status_code': 0, 'title': '', 'description': '',
                        'is_alive': False, 'error': f'ssl_retry_failed: {e2}'}

        except requests.exceptions.Timeout:
            return {'status_code': 0, 'title': '', 'description': '', 'is_alive': False, 'error': 'timeout'}
        except Exception as e:
            return {'status_code': 0, 'title': '', 'description': '', 'is_alive': False, 'error': str(e)}

    def _parse_probe_response(self, resp) -> dict:
        """解析HTTP响应，提取title和description"""
        # 状态码检查
        if resp.status_code >= 400:
            return {
                'status_code': resp.status_code,
                'title': '',
                'description': '',
                'is_alive': False,
                'error': f'HTTP {resp.status_code}'
            }

        # 提取title
        title_match = re.search(r'<title[^>]*>(.*?)</title>', resp.text, re.IGNORECASE | re.DOTALL)
        title = self._clean_text(title_match.group(1)) if title_match else ''

        # 提取meta description
        desc_match = re.search(
            r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)["\']',
            resp.text, re.IGNORECASE
        )
        if not desc_match:
            desc_match = re.search(
                r'<meta[^>]*content=["\']([^"\']*)["\'][^>]*name=["\']description["\']',
                resp.text, re.IGNORECASE
            )
        description = self._clean_text(desc_match.group(1)) if desc_match else ''

        # 检测失效信号
        dead_signals = ['404', 'error', 'forbidden', 'suspended', 'domain for sale',
                       'page not found', 'account suspended', 'this domain']
        title_lower = title.lower()
        for sig in dead_signals:
            if sig in title_lower:
                return {
                    'status_code': resp.status_code,
                    'title': title,
                    'description': description,
                    'is_alive': False,
                    'error': f'dead signal: {sig}'
                }

        return {
            'status_code': resp.status_code,
            'title': title,
            'description': description,
            'is_alive': True,
            'error': ''
        }

    # ========== Layer 4: 内容相关性评分 ==========

    def calculate_relevance_score(self, query: str, title: str, description: str, location: str = '') -> float:
        """
        计算搜索查询与页面内容的相关性分数
        返回 0.0-1.0
        重要：国家/地区词汇不参与匹配打分
        """
        if not query:
            return 0.5

        query_words = [w for w in re.findall(r'[a-z0-9]+', query.lower()) if len(w) >= 2]
        if not query_words:
            return 0.5

        content = f"{title} {description}".lower()
        if not content.strip():
            return 0.3  # 无内容，较低分

        # 构建国家词排除集
        country_words = self._build_country_word_set(location)

        # 仅使用非国家词进行匹配
        product_words = [w for w in query_words if w not in country_words]
        if not product_words:
            product_words = query_words  # 如果所有词都被排除了，仍用原始词（兜底）

        matched = 0
        for word in product_words:
            if word in content:
                matched += 1

        score = matched / len(product_words) if product_words else 0.5
        # 映射到 0.2-1.0
        return 0.2 + score * 0.8

    # ========== Layer 5: 聚合器/目录站检测 ==========

    def detect_aggregator(self, title: str = '', description: str = '', url: str = '') -> Tuple[bool, str]:
        """
        检测页面是否为聚合器/目录站/论坛
        返回 (是否聚合器, 原因)
        """
        text = f"{title} {description}".lower()

        # 信号词检测
        for signal in self.AGGREGATOR_SIGNALS:
            if signal in text:
                return True, f'aggregator_signal: {signal}'

        # 域名检测
        if url:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            aggregator_domains = ['directory', 'reviews', 'forum', 'list', 'compare',
                                  'aggregator', 'marketplace', 'classifieds']
            for ad in aggregator_domains:
                if ad in domain:
                    return True, f'aggregator_domain: {ad}'

        return False, ''

    def detect_social_profile(self, url: str) -> Tuple[bool, str]:
        """检测是否为社交个人页（非公司主页）"""
        if not url:
            return False, ''

        url_lower = url.lower()
        social_patterns = [
            ('linkedin.com/in/', 'linkedin_profile'),
            ('facebook.com/profile.php', 'facebook_profile'),
            ('facebook.com/groups/', 'facebook_group'),
            ('twitter.com/', 'twitter_profile'),
            ('x.com/', 'x_profile'),
            ('instagram.com/', 'instagram_profile'),
            ('tiktok.com/@', 'tiktok_profile'),
        ]
        for pattern, reason in social_patterns:
            if pattern in url_lower:
                return True, reason

        return False, ''

    # ========== 综合验证入口 ==========

    def validate(self, result: SearchResult, query: str = '', location: str = '') -> ValidationResult:
        """
        对单个搜索结果执行完整五层验证
        """
        if not self.enabled:
            return ValidationResult(is_valid=True, confidence_score=0.5)

        vr = ValidationResult()
        scores = {}

        # Layer 1: 域名黑名单
        passed, reason = self._check_domain_blacklist(result.website)
        scores['layer1_blacklist'] = 1.0 if passed else 0.0
        if not passed:
            vr.is_valid = False
            vr.rejection_reason = reason
            vr.confidence_score = 0.0
            vr.layer_scores = scores
            return vr

        # Layer 2: 名称-域名一致性
        consistency = self._check_name_domain_consistency(result.company_name, result.website)
        scores['layer2_consistency'] = consistency

        # Layer 3+4: HTTP预检（如果启用）
        if self.config.get('layer3_http_probe_enabled', True) and result.website:
            probe = self.quick_probe(result.website)
            if probe:
                vr.probe_data = probe
                if not probe['is_alive']:
                    error = probe.get('error', '')
                    # 网络错误（SSL、超时）不应直接reject，降低confidence即可
                    network_errors = ['ssl_retry_failed', 'timeout', 'ConnectionError',
                                      'ConnectTimeout', 'ReadTimeout']
                    is_network_error = any(ne in error for ne in network_errors)
                    if is_network_error:
                        scores['layer3_probe'] = 0.4
                        scores['layer4_relevance'] = 0.3
                        # 继续后续检测，不return
                    else:
                        # 内容错误（404、dead signal等）才reject
                        scores['layer3_probe'] = 0.0
                        vr.is_valid = False
                        vr.rejection_reason = f"probe_failed: {error}"
                        vr.confidence_score = 0.0
                        vr.layer_scores = scores
                        return vr
                else:
                    scores['layer3_probe'] = 1.0
                    # Layer 4: 相关性评分
                    relevance = self.calculate_relevance_score(
                        query, probe.get('title', ''), probe.get('description', ''), location
                    )
                    scores['layer4_relevance'] = relevance
            else:
                scores['layer3_probe'] = 0.5
                scores['layer4_relevance'] = 0.5
        else:
            scores['layer3_probe'] = 0.5
            scores['layer4_relevance'] = 0.5

        # Layer 5: 聚合器检测
        title = vr.probe_data.get('title', '') if vr.probe_data else ''
        desc = vr.probe_data.get('description', '') if vr.probe_data else ''
        is_agg, agg_reason = self.detect_aggregator(title, desc, result.website)
        is_social, social_reason = self.detect_social_profile(result.source_url)

        if is_agg:
            scores['layer5_aggregator'] = 0.0
            vr.is_valid = False
            vr.rejection_reason = agg_reason
            vr.confidence_score = 0.0
            vr.layer_scores = scores
            return vr

        # 社交个人页不做拒绝，仅降低置信度（用户要求保留社交平台数据）
        if is_social:
            scores['layer5_aggregator'] = 0.3
        else:
            scores['layer5_aggregator'] = 1.0

        # 计算综合置信度
        # 权重: L1=0.2, L2=0.3, L3=0.2, L4=0.2, L5=0.1
        weights = {'layer1_blacklist': 0.2, 'layer2_consistency': 0.3,
                   'layer3_probe': 0.2, 'layer4_relevance': 0.2, 'layer5_aggregator': 0.1}
        total_weight = sum(weights.values())
        weighted_sum = sum(scores.get(k, 0) * weights[k] for k in weights)
        vr.confidence_score = round(weighted_sum / total_weight, 3)
        vr.layer_scores = scores

        # 如果置信度过低，标记为 needs_review
        if vr.confidence_score < 0.3:
            vr.is_valid = False
            vr.rejection_reason = f'low_confidence: {vr.confidence_score}'

        return vr

    def validate_crawl_content(self, result: SearchResult, crawl_data: dict, query: str = '', location: str = '') -> Tuple[bool, float]:
        """
        基于网站爬取内容二次验证
        返回 (是否通过, 置信度)
        """
        title = crawl_data.get('title', '')
        about_text = crawl_data.get('about_text', '')
        contact_info = crawl_data.get('contact_info', {})

        # 检测聚合器信号
        is_agg, _ = self.detect_aggregator(title, about_text[:500])
        if is_agg:
            return False, 0.1

        # about_text 过短可能是聚合页
        if len(about_text) < 100:
            return False, 0.2

        # 检查公司名称是否在页面内容中
        if result.company_name and result.company_name.lower() in about_text.lower():
            return True, 0.8

        # 检查搜索关键词是否在页面内容中（排除国家词）
        if query:
            country_words = self._build_country_word_set(location)
            query_words = [w for w in re.findall(r'[a-z0-9]+', query.lower()) if len(w) >= 3 and w not in country_words]
            matched = sum(1 for w in query_words if w in about_text.lower())
            if query_words and matched / len(query_words) >= 0.5:
                return True, 0.7

        # 检查是否有足够的联系信息（公司官网通常有）
        has_contact = bool(contact_info.get('emails') or contact_info.get('phones') or contact_info.get('address'))
        if has_contact and len(about_text) > 300:
            return True, 0.6

        return True, 0.4

    # ========== 批量验证 ==========

    def run_pre_crawl_validation(self, results: List[SearchResult], query: str = '', location: str = '') -> List[SearchResult]:
        """
        对搜索结果列表执行预爬取验证（Layer 1-5）
        更新每个结果的 validation_status 和 confidence_score
        """
        if not self.enabled:
            for r in results:
                r.validation_status = 'validated'
                r.confidence_score = 0.5
            return results

        for result in results:
            vr = self.validate(result, query, location)
            result.confidence_score = vr.confidence_score
            result.probe_data = vr.probe_data

            if not vr.is_valid:
                result.validation_status = 'rejected'
                result.validation_reason = vr.rejection_reason
            elif vr.confidence_score < 0.5:
                result.validation_status = 'needs_review'
                result.validation_reason = f'low_confidence: {vr.confidence_score}'
            else:
                result.validation_status = 'validated'
                result.validation_reason = ''

        return results

    # ========== 工具方法 ==========

    @staticmethod
    def _clean_text(text: str) -> str:
        """清理HTML文本"""
        if not text:
            return ''
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def is_blacklisted_domain(self, url: str) -> bool:
        """公开方法：检查域名是否在黑名单中"""
        passed, _ = self._check_domain_blacklist(url)
        return not passed

    # ========== Layer 6: 地区匹配验证 ==========

    def verify_location_match(self, result_country: str, target_location: str) -> Tuple[bool, str]:
        """
        验证搜索结果的实际国家是否匹配用户指定的目标地区。
        返回 (是否匹配, 原因)
        """
        if not target_location or not target_location.strip():
            return True, 'no_target_location'  # 未指定目标地区，放行

        if not result_country or not result_country.strip():
            return True, 'country_unknown'  # 实际国家未知，放行（不误杀）

        target_lower = target_location.lower().strip()
        country_lower = result_country.lower().strip()

        # 获取目标地区的同义词集
        target_synonyms = set()
        for key, synonyms in self.COUNTRY_SYNONYMS.items():
            if target_lower in synonyms or target_lower == key:
                target_synonyms = synonyms
                break

        # 如果没找到精确匹配，把目标地区本身加入
        if not target_synonyms:
            target_synonyms = {target_lower}
            # 尝试模糊匹配
            for key, synonyms in self.COUNTRY_SYNONYMS.items():
                if target_lower in key or key in target_lower:
                    target_synonyms = synonyms
                    break

        # 获取实际国家的同义词集
        country_synonyms = set()
        for key, synonyms in self.COUNTRY_SYNONYMS.items():
            if country_lower in synonyms or country_lower == key:
                country_synonyms = synonyms
                break

        # 如果实际国家没有同义词集，用它本身
        if not country_synonyms:
            country_synonyms = {country_lower}

        # 检查是否有交集
        if target_synonyms & country_synonyms:
            return True, 'matched'

        # 特殊情况：如果目标地区是 "europe" 等宽泛地区
        broad_regions = {
            'europe': {'germany', 'france', 'italy', 'spain', 'netherlands', 'poland', 'switzerland',
                       'sweden', 'norway', 'denmark', 'finland', 'ireland', 'austria', 'belgium',
                       'portugal', 'czech republic', 'uk', 'united kingdom', 'greece', 'hungary',
                       'romania', 'bulgaria', 'croatia', 'slovakia', 'slovenia', 'lithuania',
                       'latvia', 'estonia', 'luxembourg', 'iceland', 'malta', 'cyprus'},
            'asia': {'china', 'japan', 'south korea', 'korea', 'india', 'thailand', 'vietnam',
                     'indonesia', 'malaysia', 'singapore', 'philippines', 'taiwan', 'hong kong',
                     'pakistan', 'bangladesh', 'sri lanka', 'kazakhstan', 'saudi arabia', 'uae',
                     'israel', 'turkey'},
            'middle east': {'saudi arabia', 'uae', 'israel', 'turkey', 'egypt', 'qatar', 'kuwait',
                           'bahrain', 'oman', 'jordan', 'lebanon', 'iran', 'iraq'},
            'southeast asia': {'thailand', 'vietnam', 'indonesia', 'malaysia', 'singapore',
                              'philippines', 'myanmar', 'cambodia', 'laos'},
            'latin america': {'brazil', 'mexico', 'argentina', 'colombia', 'chile', 'peru',
                             'venezuela', 'ecuador', 'uruguay', 'paraguay', 'bolivia'},
        }

        for region_name, member_countries in broad_regions.items():
            if target_lower in self.COUNTRY_SYNONYMS.get(region_name, set()):
                # 目标是宽泛地区，检查实际国家是否属于该地区
                for mc in member_countries:
                    mc_synonyms = self.COUNTRY_SYNONYMS.get(mc, {mc})
                    if country_synonyms & mc_synonyms:
                        return True, f'matched_broad_region:{region_name}'

        return False, f'location_mismatch: target={target_location}, actual={result_country}'
