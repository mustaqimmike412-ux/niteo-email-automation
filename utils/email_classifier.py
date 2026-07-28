#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
邮箱分类器 - 智能识别公共邮箱和个人邮箱

核心规则（按优先级）：
1. 如果有关联的联系人姓名 → personal（个人邮箱）
2. 如果邮箱前缀能推断出姓名 → personal（个人邮箱）
3. 如果邮箱前缀是公共关键词 → public（公共邮箱）
4. 无法判断 → public（安全策略）

关键定义：
- 个人邮箱：带有一个自己所属的名字（导入文件中关联了联系人姓名，或能从邮箱前缀推断出姓名）
- 公共邮箱：发送时不知道收件人名字，只能以公司名义发送
"""

import re
from typing import Tuple, Optional


# ==================== 公共邮箱关键词列表 ====================

PUBLIC_EMAIL_KEYWORDS = {
    # 通用公共邮箱
    'info', 'sales', 'support', 'contact', 'admin', 'hello', 'team',
    'service', 'help', 'marketing', 'office', 'general', 'enquiries',
    'inquiry', 'business', 'customerservice', 'feedback', 'hr', 'careers',
    'jobs', 'press', 'media', 'partners', 'abuse', 'webmaster', 'postmaster',
    'hostmaster', 'noc', 'security', 'billing', 'account', 'accounts',
    'finance', 'legal', 'privacy', 'recruitment', 'care', 'customercare',

    # 带地区后缀的公共邮箱
    'customerservicetz', 'customerserviceug', 'customerserviceke', 'customerservicegh',
    'customerserviceng', 'customerservicein', 'customerservicesa',
    'customercaretz', 'customercareug', 'customercareke', 'customercaregh',
    'customercareng', 'customercarein', 'customercaresa',
    'mediatz', 'mediaug', 'mediake', 'mediagh', 'mediang', 'mediain', 'mediasa',
    'mediasouthafrica', 'mediaglobal', 'mediaindia',
    'careerstz', 'careersug', 'careerske', 'careersgh', 'careersng', 'careersin', 'careerssa',
    'careersglobal', 'careersindia', 'careerssouthafrica',
    'partnershipstz', 'partnershipsug', 'partnershipske', 'partnershipsgh',
    'partnershipsng', 'partnershipsin', 'partnershipssa',
    'partnershipsglobal', 'partnershipsindia', 'partnershipssouthafrica',
    'recruitmentke', 'recruitmentug', 'recruitmenttz', 'recruitmentgh',
    'recruitmentng', 'recruitmentin', 'recruitmentsa',

    # 带 global 前缀的公共邮箱
    'global-hr', 'global.partnerships', 'global.media', 'global.careers',
    'global.sales', 'global.support', 'global.info', 'global.contact',
    'global-hrtz', 'global-hrug', 'global-hrke', 'global-hrgh', 'global-hrng',
    'global-hrin', 'global-hrsa',
    'global.partnershipstz', 'global.partnershipsug', 'global.partnershipske',
    'global.partnershipsgh', 'global.partnershipsng', 'global.partnershipsin',
    'global.partnershipssa',

    # 特殊公共邮箱
    'batterymasters', 'batterymasterstz', 'batterymastersug', 'batterymasterske',
    'rvice', 'ervice', 'servicetz', 'serviceug', 'serviceke',

    # 采购/供应链相关
    'procurement', 'purchasing', 'buyer', 'sourcing', 'supplychain',
    'vendor', 'supplier', 'logistics', 'warehouse', 'inventory',
    'procurementtz', 'procurementug', 'procurementke', 'procurementgh',

    # 技术支持相关
    'techsupport', 'technical', 'engineering', 'developer', 'dev',
    'techsupporttz', 'techsupportug', 'techsupportke',

    # 其他常见公共邮箱
    'newsletter', 'updates', 'notifications', 'alerts', 'noreply',
    'no-reply', 'donotreply', 'automated', 'system', 'robot',
    'unsubscribe', 'subscribe', 'membership', 'subscription',
    'events', 'conference', 'webinar', 'training', 'education',
    'volunteer', 'donation', 'fundraising', 'sponsorship',
    'affiliate', 'reseller', 'distributor', 'wholesale',
    'export', 'import', 'shipping', 'delivery', 'tracking',
    'returns', 'refund', 'warranty', 'repair', 'maintenance',
    'installation', 'commissioning', 'project', 'consulting',
    'quotes', 'pricing', 'estimates', 'tenders', 'bids',
    'contracts', 'compliance', 'regulatory',
    'quality', 'qa', 'qc', 'inspection', 'testing',
    'safety', 'environmental', 'sustainability', 'csr',
    'investor', 'shareholder', 'board', 'executive',
    'ceo', 'cfo', 'cto', 'coo', 'cmo', 'chio', 'clo',
    'president', 'vicepresident', 'vp', 'director', 'manager',
    'head', 'lead', 'chief', 'founder', 'co-founder',
}


# ==================== 姓名验证 ====================

def _is_valid_name(name: str) -> bool:
    """判断是否是有效的联系人姓名（非空、非占位符、非纯数字）"""
    if not name or not isinstance(name, str):
        return False
    name = name.strip()
    if not name or len(name) < 2:
        return False
    # 排除常见无效值
    invalid = {'n/a', 'na', 'null', 'none', 'unknown', '-', '--', 'n/a.', 'test', 'example', 'xxx', '未知', '无'}
    if name.lower() in invalid:
        return False
    # 纯数字或纯标点
    if name.replace(' ', '').replace('.', '').replace('-', '').replace(',', '').isdigit():
        return False
    # 至少包含一个字母
    if not any(c.isalpha() for c in name):
        return False
    return True


# ==================== 姓名推断规则 ====================

def infer_name_from_prefix(prefix: str) -> Optional[str]:
    """
    从邮箱前缀推断联系人姓名

    支持模式：
    - firstname.lastname → John Smith
    - firstname_lastname → John Smith
    - firstname-lastname → John Smith
    - firstnamelastname → John Smith (尝试分割)
    - firstinitiallastname → J. Smith
    - firstname → John (单名)

    返回: 推断的姓名 或 None (如果无法推断)
    """
    prefix = prefix.strip().lower()

    # 如果是公共邮箱关键词，不推断姓名
    if prefix in PUBLIC_EMAIL_KEYWORDS:
        return None

    # 如果包含公共邮箱关键词，不推断姓名
    for keyword in PUBLIC_EMAIL_KEYWORDS:
        if keyword in prefix and len(prefix) <= len(keyword) + 3:
            return None

    # 模式1: firstname.lastname (john.smith)
    if '.' in prefix:
        parts = prefix.split('.')
        if len(parts) == 2:
            first, last = parts[0], parts[1]
            if len(first) >= 2 and len(last) >= 2:
                return f"{first.capitalize()} {last.capitalize()}"
            elif len(first) == 1 and len(last) >= 2:  # j.smith
                return f"{first.upper()}. {last.capitalize()}"

    # 模式2: firstname_lastname (john_smith)
    if '_' in prefix:
        parts = prefix.split('_')
        if len(parts) == 2:
            first, last = parts[0], parts[1]
            if len(first) >= 2 and len(last) >= 2:
                return f"{first.capitalize()} {last.capitalize()}"

    # 模式3: firstname-lastname (john-smith)
    if '-' in prefix:
        parts = prefix.split('-')
        if len(parts) == 2:
            first, last = parts[0], parts[1]
            if len(first) >= 2 and len(last) >= 2:
                return f"{first.capitalize()} {last.capitalize()}"

    # 模式4: firstnamelastname (johnsmith) - 尝试分割
    if len(prefix) > 4 and prefix.isalpha():
        match = _split_compound_name(prefix)
        if match:
            return match

    # 模式5: 首字母+姓氏 (jsmith, j.smith)
    match = re.match(r'^([a-z])\.?([a-z]+)$', prefix)
    if match:
        first_initial = match.group(1).upper()
        last = match.group(2).capitalize()
        return f"{first_initial}. {last}"

    # 模式6: 单名 (john) — 只在 >=3 字符时才推断，避免误判
    if len(prefix) >= 3 and prefix.isalpha() and prefix not in PUBLIC_EMAIL_KEYWORDS:
        return prefix.capitalize()

    # 无法推断
    return None


def _split_compound_name(name: str) -> Optional[str]:
    """尝试分割复合姓名（如 johnsmith → John Smith）"""
    common_first_names = {
        'john', 'jane', 'michael', 'mary', 'david', 'sarah', 'james', 'emma',
        'robert', 'linda', 'william', 'patricia', 'richard', 'elizabeth',
        'thomas', 'jennifer', 'charles', 'barbara', 'daniel', 'susan',
        'matthew', 'jessica', 'joseph', 'karen', 'christopher', 'nancy',
        'mark', 'lisa', 'donald', 'betty', 'steven', 'margaret', 'paul',
        'sandra', 'andrew', 'ashley', 'kenneth', 'kimberly', 'joshua',
        'emily', 'kevin', 'donna', 'brian', 'michelle', 'george', 'dorothy',
        'edward', 'carol', 'ronald', 'amanda', 'timothy', 'melissa', 'jason',
        'deborah', 'jeffrey', 'stephanie', 'ryan', 'rebecca', 'jacob',
        'sharon', 'gary', 'laura', 'nicholas', 'cynthia', 'eric', 'kathleen',
        'jonathan', 'amy', 'stephen', 'shirley', 'larry', 'angela', 'justin',
        'helen', 'scott', 'anna', 'brandon', 'brenda', 'benjamin', 'pamela',
        'samuel', 'nicole', 'gregory', 'samantha', 'frank', 'katherine',
        'alexander', 'raymond', 'ruth', 'patrick', 'christine',
        'jack', 'catherine', 'dennis', 'debra', 'jerry', 'rachel', 'tyler',
        'carolyn', 'aaron', 'janet', 'jose', 'virginia', 'adam', 'maria',
        'nathan', 'heather', 'henry', 'diane', 'douglas', 'julie', 'zachary',
        'joyce', 'peter', 'victoria', 'kyle', 'olivia', 'walter', 'kelly',
        'ethan', 'christina', 'jeremy', 'lauren', 'harold', 'joan', 'keith',
        'evelyn', 'christian', 'judith', 'roger', 'megan', 'noah', 'cheryl',
        'gerald', 'andrea', 'carl', 'hannah', 'terry', 'martha', 'sean',
        'jacqueline', 'arthur', 'frances', 'austin', 'gloria',
        'ann', 'lawrence', 'teresa', 'joe', 'kathryn', 'sara',
        'jesse', 'janice', 'jean', 'bobby', 'alice', 'philip',
        'madison', 'johnny', 'doris', 'grace',
        'bryan', 'judy', 'billy', 'theresa', 'bruce', 'beverly', 'gabriel',
        'denise', 'logan', 'marilyn', 'albert', 'amber', 'ralph', 'danielle',
        'roy', 'abigail', 'randy', 'brittany', 'eugene', 'rose', 'wayne',
        'diana', 'jordan', 'natalie', 'louis', 'sophia', 'russell', 'alexis',
        'alan', 'kayla', 'charlotte', 'harry', 'marie',
        'tiffany', 'vincent', 'kathy', 'dylan', 'courtney',
        'howard', 'joan', 'gabriel', 'evelyn', 'leonard', 'tracy',
        'julia', 'jesse', 'christine', 'martin', 'aubrey', 'isaac', 'leslie',
        'lucas', 'lily', 'mason', 'hailey', 'craig', 'nicky', 'nick',
    }

    # 尝试匹配常见名字前缀
    for first_name in common_first_names:
        if name.startswith(first_name):
            last_name = name[len(first_name):]
            if len(last_name) >= 2:
                return f"{first_name.capitalize()} {last_name.capitalize()}"

    # 尝试从中间分割
    best_match = None
    for i in range(3, len(name) - 2):
        first = name[:i]
        last = name[i:]
        if first in common_first_names and len(last) >= 2:
            if best_match is None or len(first) > len(best_match[0]):
                best_match = (first, last)

    if best_match:
        return f"{best_match[0].capitalize()} {best_match[1].capitalize()}"

    return None


# ==================== 邮箱分类主函数 ====================

def classify_email(email: str, contact_name: str = None) -> Tuple[str, Optional[str]]:
    """
    分类邮箱类型并推断联系人姓名

    核心逻辑：
    1. 如果有关联的联系人姓名（contact_name 有效）→ personal（个人邮箱）
    2. 如果邮箱前缀能推断出姓名 → personal（个人邮箱）
    3. 如果邮箱前缀是公共关键词 → public（公共邮箱）
    4. 无法判断 → public（安全策略）

    Args:
        email: 邮箱地址
        contact_name: 导入文件中关联的联系人姓名（可选）

    Returns:
        (email_type, contact_name)
        - email_type: 'public' 或 'personal'
        - contact_name: 推断/使用的姓名 或 None
    """
    if not email or '@' not in email:
        return 'public', None

    prefix = email.split('@')[0].lower().strip()

    # 1. 如果有关联的联系人姓名，直接判定为个人邮箱
    if _is_valid_name(contact_name):
        return 'personal', contact_name.strip()

    # 2. 检查是否是公共邮箱关键词（精确匹配）
    if prefix in PUBLIC_EMAIL_KEYWORDS:
        return 'public', None

    # 3. 检查是否包含公共邮箱关键词
    for keyword in PUBLIC_EMAIL_KEYWORDS:
        if keyword in prefix:
            if prefix.startswith(keyword) or prefix.endswith(keyword):
                return 'public', None

    # 4. 尝试从前缀推断姓名
    inferred_name = infer_name_from_prefix(prefix)

    if inferred_name:
        return 'personal', inferred_name

    # 5. 无法判断时，默认归类为 public（安全策略）
    return 'public', None


def classify_email_batch(emails: list, contact_names: list = None) -> list:
    """
    批量分类邮箱

    Args:
        emails: 邮箱地址列表
        contact_names: 对应的联系人姓名列表（可选）

    Returns:
        [(email, email_type, contact_name), ...]
    """
    results = []
    for i, email in enumerate(emails):
        name = contact_names[i] if contact_names and i < len(contact_names) else None
        email_type, contact_name = classify_email(email, name)
        results.append((email, email_type, contact_name))
    return results


# ==================== 便捷函数 ====================

def is_public_email(email: str, contact_name: str = None) -> bool:
    """判断是否为公共邮箱"""
    email_type, _ = classify_email(email, contact_name)
    return email_type == 'public'


def is_personal_email(email: str, contact_name: str = None) -> bool:
    """判断是否为个人邮箱"""
    email_type, _ = classify_email(email, contact_name)
    return email_type == 'personal'


def get_contact_name(email: str, contact_name: str = None) -> Optional[str]:
    """获取邮箱对应的联系人姓名"""
    _, name = classify_email(email, contact_name)
    return name
