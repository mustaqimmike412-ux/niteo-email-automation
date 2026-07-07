#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
邮箱分类器 - 智能识别公共邮箱和个人邮箱

核心规则：
1. 如果邮箱前缀在公共邮箱关键词列表中 → public
2. 如果邮箱前缀包含公共邮箱关键词 → public
3. 如果邮箱前缀看起来像姓名（firstname.lastname, firstname_lastname 等） → personal
4. 如果无法判断，默认归类为 public（安全策略）

支持从邮箱前缀推断联系人姓名
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
    'contracts', 'legal', 'compliance', 'regulatory',
    'quality', 'qa', 'qc', 'inspection', 'testing',
    'safety', 'environmental', 'sustainability', 'csr',
    'investor', 'shareholder', 'board', 'executive',
    'ceo', 'cfo', 'cto', 'coo', 'cmo', 'chio', 'clo',
    'president', 'vicepresident', 'vp', 'director', 'manager',
    'head', 'lead', 'chief', 'founder', 'co-founder',
}


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
    
    返回: 推断的姓名 或 None (如果是公共邮箱)
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
        # 尝试找到名字和姓氏的分界
        # 使用常见英文名字列表进行匹配
        match = _split_compound_name(prefix)
        if match:
            return match
    
    # 模式5: 首字母+姓氏 (jsmith, j.smith)
    match = re.match(r'^([a-z])\.?([a-z]+)$', prefix)
    if match:
        first_initial = match.group(1).upper()
        last = match.group(2).capitalize()
        return f"{first_initial}. {last}"
    
    # 模式6: 单名 (john)
    if len(prefix) >= 2 and prefix.isalpha() and prefix not in PUBLIC_EMAIL_KEYWORDS:
        return prefix.capitalize()
    
    # 无法推断，返回 None（安全策略：无法确认是个人邮箱时归类为公共邮箱）
    return None


def _split_compound_name(name: str) -> Optional[str]:
    """
    尝试分割复合姓名（如 johnsmith → John Smith）
    """
    # 常见英文名字列表（用于匹配）
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
        'alexander', 'emma', 'raymond', 'ruth', 'patrick', 'christine',
        'jack', 'catherine', 'dennis', 'debra', 'jerry', 'rachel', 'tyler',
        'carolyn', 'aaron', 'janet', 'jose', 'virginia', 'adam', 'maria',
        'nathan', 'heather', 'henry', 'diane', 'douglas', 'julie', 'zachary',
        'joyce', 'peter', 'victoria', 'kyle', 'olivia', 'walter', 'kelly',
        'ethan', 'christina', 'jeremy', 'lauren', 'harold', 'joan', 'keith',
        'evelyn', 'christian', 'judith', 'roger', 'megan', 'noah', 'cheryl',
        'gerald', 'andrea', 'carl', 'hannah', 'terry', 'martha', 'sean',
        'jacqueline', 'arthur', 'frances', 'austin', 'gloria', 'patrick',
        'ann', 'lawrence', 'teresa', 'joe', 'kathryn', 'andrew', 'sara',
        'jesse', 'janice', 'paul', 'jean', 'bobby', 'alice', 'philip',
        'madison', 'johnny', 'doris', 'mary', 'julie', 'dan', 'grace',
        'bryan', 'judy', 'billy', 'theresa', 'bruce', 'beverly', 'gabriel',
        'denise', 'logan', 'marilyn', 'albert', 'amber', 'ralph', 'danielle',
        'roy', 'abigail', 'randy', 'brittany', 'eugene', 'rose', 'wayne',
        'diana', 'jordan', 'natalie', 'louis', 'sophia', 'russell', 'alexis',
        'alan', 'kayla', 'philip', 'charlotte', 'harry', 'marie', 'randy',
        'tiffany', 'vincent', 'kathy', 'bobby', 'madison', 'dylan', 'courtney',
        'howard', 'joan', 'gabriel', 'evelyn', 'leonard', 'tracy', 'andrew',
        'julia', 'jesse', 'christine', 'martin', 'aubrey', 'isaac', 'leslie',
        'kyle', 'anna', 'juan', 'brianna', 'lucas', 'lily', 'mason', 'hailey',
    }
    
    # 尝试匹配常见名字前缀
    for first_name in common_first_names:
        if name.startswith(first_name):
            last_name = name[len(first_name):]
            if len(last_name) >= 2:
                return f"{first_name.capitalize()} {last_name.capitalize()}"
    
    # 尝试从中间分割（找到最长的常见名字前缀）
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

def classify_email(email: str) -> Tuple[str, Optional[str]]:
    """
    分类邮箱类型并推断联系人姓名
    
    Args:
        email: 邮箱地址
        
    Returns:
        (email_type, contact_name)
        - email_type: 'public' 或 'personal'
        - contact_name: 推断的姓名 或 None
    """
    if not email or '@' not in email:
        return 'public', None
    
    prefix = email.split('@')[0].lower().strip()
    
    # 1. 检查是否是公共邮箱关键词（精确匹配）
    if prefix in PUBLIC_EMAIL_KEYWORDS:
        return 'public', None
    
    # 2. 检查是否包含公共邮箱关键词
    for keyword in PUBLIC_EMAIL_KEYWORDS:
        if keyword in prefix:
            # 确保不是姓名中包含关键词（如 "salesman" 中的 "sales"）
            if prefix.startswith(keyword) or prefix.endswith(keyword):
                return 'public', None
    
    # 3. 尝试推断姓名
    inferred_name = infer_name_from_prefix(prefix)
    
    if inferred_name:
        return 'personal', inferred_name
    
    # 4. 无法判断时，默认归类为 public（安全策略）
    return 'public', None


def classify_email_batch(emails: list) -> list:
    """
    批量分类邮箱
    
    Args:
        emails: 邮箱地址列表
        
    Returns:
        [(email, email_type, contact_name), ...]
    """
    results = []
    for email in emails:
        email_type, contact_name = classify_email(email)
        results.append((email, email_type, contact_name))
    return results


# ==================== 便捷函数 ====================

def is_public_email(email: str) -> bool:
    """判断是否为公共邮箱"""
    email_type, _ = classify_email(email)
    return email_type == 'public'


def is_personal_email(email: str) -> bool:
    """判断是否为个人邮箱"""
    email_type, _ = classify_email(email)
    return email_type == 'personal'


def get_contact_name(email: str) -> Optional[str]:
    """获取邮箱对应的联系人姓名"""
    _, contact_name = classify_email(email)
    return contact_name


# ==================== 测试 ====================

if __name__ == '__main__':
    # 测试邮箱分类
    test_emails = [
        # 公共邮箱
        'info@example.com',
        'sales@example.com',
        'support@example.com',
        'contact@example.com',
        'admin@example.com',
        'hello@example.com',
        'team@example.com',
        'service@example.com',
        'help@example.com',
        'marketing@example.com',
        'office@example.com',
        'general@example.com',
        'enquiries@example.com',
        'inquiry@example.com',
        'business@example.com',
        'customerservice@example.com',
        'feedback@example.com',
        'hr@example.com',
        'careers@example.com',
        'jobs@example.com',
        'press@example.com',
        'media@example.com',
        'partners@example.com',
        'abuse@example.com',
        'webmaster@example.com',
        'postmaster@example.com',
        'hostmaster@example.com',
        'noc@example.com',
        'security@example.com',
        'billing@example.com',
        'account@example.com',
        'accounts@example.com',
        'finance@example.com',
        'legal@example.com',
        'privacy@example.com',
        'recruitment@example.com',
        'care@example.com',
        'customercare@example.com',
        'customerservicetz@example.com',
        'customerserviceug@example.com',
        'customerserviceke@example.com',
        'mediatz@example.com',
        'mediaug@example.com',
        'mediake@example.com',
        'careerstz@example.com',
        'careersug@example.com',
        'careerske@example.com',
        'partnershipstz@example.com',
        'partnershipsug@example.com',
        'partnershipske@example.com',
        'recruitmentke@example.com',
        'recruitmentug@example.com',
        'recruitmenttz@example.com',
        'global-hr@example.com',
        'global.partnerships@example.com',
        'global.media@example.com',
        'global.careers@example.com',
        'global-hrtz@example.com',
        'global-hrug@example.com',
        'global-hrke@example.com',
        'global.partnershipstz@example.com',
        'global.partnershipsug@example.com',
        'global.partnershipske@example.com',
        'batterymasters@example.com',
        'batterymasterstz@example.com',
        'batterymastersug@example.com',
        'rvice@example.com',
        'ervice@example.com',
        'procurement@example.com',
        'purchasing@example.com',
        'buyer@example.com',
        'sourcing@example.com',
        'supplychain@example.com',
        'vendor@example.com',
        'supplier@example.com',
        'logistics@example.com',
        'warehouse@example.com',
        'inventory@example.com',
        'techsupport@example.com',
        'technical@example.com',
        'engineering@example.com',
        'developer@example.com',
        'dev@example.com',
        'newsletter@example.com',
        'updates@example.com',
        'notifications@example.com',
        'alerts@example.com',
        'noreply@example.com',
        'no-reply@example.com',
        'donotreply@example.com',
        'automated@example.com',
        'system@example.com',
        'robot@example.com',
        'unsubscribe@example.com',
        'subscribe@example.com',
        'membership@example.com',
        'subscription@example.com',
        'events@example.com',
        'conference@example.com',
        'webinar@example.com',
        'training@example.com',
        'education@example.com',
        'volunteer@example.com',
        'donation@example.com',
        'fundraising@example.com',
        'sponsorship@example.com',
        'affiliate@example.com',
        'reseller@example.com',
        'distributor@example.com',
        'wholesale@example.com',
        'export@example.com',
        'import@example.com',
        'shipping@example.com',
        'delivery@example.com',
        'tracking@example.com',
        'returns@example.com',
        'refund@example.com',
        'warranty@example.com',
        'repair@example.com',
        'maintenance@example.com',
        'installation@example.com',
        'commissioning@example.com',
        'project@example.com',
        'consulting@example.com',
        'quotes@example.com',
        'pricing@example.com',
        'estimates@example.com',
        'tenders@example.com',
        'bids@example.com',
        'contracts@example.com',
        'compliance@example.com',
        'regulatory@example.com',
        'quality@example.com',
        'qa@example.com',
        'qc@example.com',
        'inspection@example.com',
        'testing@example.com',
        'safety@example.com',
        'environmental@example.com',
        'sustainability@example.com',
        'csr@example.com',
        'investor@example.com',
        'shareholder@example.com',
        'board@example.com',
        'executive@example.com',
        'ceo@example.com',
        'cfo@example.com',
        'cto@example.com',
        'coo@example.com',
        'cmo@example.com',
        'chio@example.com',
        'clo@example.com',
        'president@example.com',
        'vicepresident@example.com',
        'vp@example.com',
        'director@example.com',
        'manager@example.com',
        'head@example.com',
        'lead@example.com',
        'chief@example.com',
        'founder@example.com',
        'co-founder@example.com',
        
        # 个人邮箱
        'john.smith@example.com',
        'jane.doe@example.com',
        'mike.wilson@example.com',
        'sarah.johnson@example.com',
        'david.brown@example.com',
        'emily.davis@example.com',
        'james.miller@example.com',
        'linda.wilson@example.com',
        'robert.taylor@example.com',
        'patricia.anderson@example.com',
        'william.thomas@example.com',
        'elizabeth.jackson@example.com',
        'richard.white@example.com',
        'barbara.harris@example.com',
        'charles.martin@example.com',
        'jennifer.thompson@example.com',
        'joseph.garcia@example.com',
        'susan.martinez@example.com',
        'thomas.robinson@example.com',
        'jessica.clark@example.com',
        'christopher.rodriguez@example.com',
        'karen.lewis@example.com',
        'daniel.lee@example.com',
        'nancy.walker@example.com',
        'matthew.hall@example.com',
        'lisa.allen@example.com',
        'anthony.young@example.com',
        'margaret.hernandez@example.com',
        'mark.king@example.com',
        'betty.wright@example.com',
        'donald.lopez@example.com',
        'sandra.hill@example.com',
        'steven.scott@example.com',
        'ashley.green@example.com',
        'paul.adams@example.com',
        'kimberly.baker@example.com',
        'andrew.gonzalez@example.com',
        'emily.nelson@example.com',
        'joshua.carter@example.com',
        'donna.mitchell@example.com',
        'kevin.perez@example.com',
        'michelle.roberts@example.com',
        'brian.turner@example.com',
        'dorothy.phillips@example.com',
        'george.campbell@example.com',
        'carol.parker@example.com',
        'edward.evans@example.com',
        'amanda.edwards@example.com',
        'ronald.collins@example.com',
        'melissa.stewart@example.com',
        'timothy.sanchez@example.com',
        'deborah.morris@example.com',
        'jason.rogers@example.com',
        'stephanie.reed@example.com',
        'jeffrey.cook@example.com',
        'rebecca.morgan@example.com',
        'ryan.bell@example.com',
        'sharon.murphy@example.com',
        'jacob.bailey@example.com',
        'laura.rivera@example.com',
        'gary.cooper@example.com',
        'catherine.richardson@example.com',
        'nicholas.cox@example.com',
        'kathleen.ward@example.com',
        'eric.torres@example.com',
        'amy.peterson@example.com',
        'stephen.gray@example.com',
        'angela.ramirez@example.com',
        'jonathan.james@example.com',
        'anna.watson@example.com',
        'larry.brooks@example.com',
        'pamela.kelly@example.com',
        'frank.price@example.com',
        'katherine.bennett@example.com',
        'scott.wood@example.com',
        'nicole.barnes@example.com',
        'raymond.ross@example.com',
        'christine.henderson@example.com',
        'gregory.coleman@example.com',
        'samantha.jenkins@example.com',
        'samuel.perry@example.com',
        'kathryn.powell@example.com',
        'benjamin.long@example.com',
        'patricia.patterson@example.com',
        'patrick.hughes@example.com',
        'rachel.flores@example.com',
        'alexander.washington@example.com',
        'emma.butler@example.com',
        'jack.simmons@example.com',
        'maria.foster@example.com',
        'dennis.gonzales@example.com',
        'debra.bryant@example.com',
        'jerry.alexander@example.com',
        'doris.russell@example.com',
        'tyler.griffin@example.com',
        'cheryl.diaz@example.com',
        'aaron.hayes@example.com',
        'janice.myers@example.com',
        'jose.ford@example.com',
        'virginia.hamilton@example.com',
        'adam.graham@example.com',
        'maria.sullivan@example.com',
        'nathan.wallace@example.com',
        'heather.woods@example.com',
        'henry.cole@example.com',
        'diane.west@example.com',
        'douglas.jordan@example.com',
        'julie.owens@example.com',
        'zachary.reynolds@example.com',
        'evelyn.fisher@example.com',
        'christian.ellis@example.com',
        'judith.harrison@example.com',
        'roger.gibson@example.com',
        'megan.mcdonald@example.com',
        'noah.cruz@example.com',
        'cheryl.marshall@example.com',
        'gerald.ortiz@example.com',
        'andrea.gomez@example.com',
        'carl.murray@example.com',
        'hannah.freeman@example.com',
        'terry.wells@example.com',
        'martha.webb@example.com',
        'sean.simpson@example.com',
        'jacqueline.stevens@example.com',
        'arthur.tucker@example.com',
        'frances.porter@example.com',
        'austin.hunter@example.com',
        'gloria.hicks@example.com',
        'patrick.crawford@example.com',
        'ann.henry@example.com',
        'lawrence.boyd@example.com',
        'teresa.mason@example.com',
        'joe.morales@example.com',
        'kathryn.kennedy@example.com',
        'andrew.warren@example.com',
        'sara.dixon@example.com',
        'jesse.ramos@example.com',
        'janice.reyes@example.com',
        'paul.burns@example.com',
        'jean.gordon@example.com',
        'bobby.shaw@example.com',
        'alice.holmes@example.com',
        'philip.rice@example.com',
        'madison.robertson@example.com',
        'johnny.hunt@example.com',
        'doris.black@example.com',
        'mary.daniels@example.com',
        'julie.palmer@example.com',
        'dan.mills@example.com',
        'grace.nichols@example.com',
        'bryan.grant@example.com',
        'judy.knight@example.com',
        'billy.ferguson@example.com',
        'theresa.rose@example.com',
        'bruce.stone@example.com',
        'beverly.hawkins@example.com',
        'gabriel.dunn@example.com',
        'denise.perkins@example.com',
        'logan.hudson@example.com',
        'marilyn.spencer@example.com',
        'albert.gardner@example.com',
        'amber.stephens@example.com',
        'ralph.payne@example.com',
        'danielle.pierce@example.com',
        'roy.berry@example.com',
        'abigail.matthews@example.com',
        'randy.arnold@example.com',
        'brittany.wagner@example.com',
        'eugene.willis@example.com',
        'rose.ray@example.com',
        'wayne.watkins@example.com',
        'diana.olson@example.com',
        'jordan.carroll@example.com',
        'natalie.duncan@example.com',
        'louis.snyder@example.com',
        'sophia.hart@example.com',
        'russell.cunningham@example.com',
        'alexis.bradley@example.com',
        'alan.lane@example.com',
        'kayla.andrews@example.com',
        'philip.ruiz@example.com',
        'charlotte.harper@example.com',
        'harry.fox@example.com',
        'marie.riley@example.com',
        'randy.armstrong@example.com',
        'tiffany.carpenter@example.com',
        'vincent.weaver@example.com',
        'kathy.greene@example.com',
        'bobby.lawrence@example.com',
        'madison.elliott@example.com',
        'dylan.chavez@example.com',
        'courtney.sims@example.com',
        'howard.austin@example.com',
        'joan.peters@example.com',
        'gabriel.kelley@example.com',
        'evelyn.franklin@example.com',
        'leonard.lawson@example.com',
        'tracy.fields@example.com',
        'andrew.gutierrez@example.com',
        'julia.ryan@example.com',
        'jesse.schmidt@example.com',
        'christine.carr@example.com',
        'martin.vasquez@example.com',
        'aubrey.castillo@example.com',
        'isaac.wheeler@example.com',
        'leslie.chapman@example.com',
        'kyle.oliver@example.com',
        'anna.montgomery@example.com',
        'juan.richards@example.com',
        'brianna.kirk@example.com',
        'lucas.bradford@example.com',
        'lily.lambert@example.com',
        'mason.fleming@example.com',
        'hailey.bishop@example.com',
    ]
    
    print("=" * 60)
    print("邮箱分类器测试")
    print("=" * 60)
    
    public_count = 0
    personal_count = 0
    
    for email in test_emails:
        email_type, contact_name = classify_email(email)
        if email_type == 'public':
            public_count += 1
        else:
            personal_count += 1
    
    print(f"\n测试结果:")
    print(f"  公共邮箱: {public_count}")
    print(f"  个人邮箱: {personal_count}")
    print(f"  总计: {len(test_emails)}")
    
    # 显示一些示例
    print(f"\n公共邮箱示例:")
    for email in test_emails[:10]:
        email_type, _ = classify_email(email)
        if email_type == 'public':
            print(f"  {email}")
    
    print(f"\n个人邮箱示例:")
    for email in test_emails[150:160]:
        email_type, contact_name = classify_email(email)
        if email_type == 'personal':
            print(f"  {email} -> {contact_name}")
    
    print(f"\n{'='*60}")
    print("测试完成")
    print("=" * 60)
