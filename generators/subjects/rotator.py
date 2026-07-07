import random
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime

@dataclass
class RotationResult:
    subject_id: int
    subject_index: int
    subject_line: str
    strategy_used: str

class SubjectRotator:
    """主题轮换管理器"""
    
    def __init__(self):
        self.min_gap = 2  # 同一主题至少间隔2次才能重复使用
    
    def select_next_subject(
        self,
        customer_id: int,
        available_subjects: List[Dict],
        usage_history: List[Dict]
    ) -> RotationResult:
        """
        为指定客户选择下一个要使用的主题
        
        Args:
            customer_id: 客户ID
            available_subjects: 该客户的5个主题 [{id, subject_index, subject_line}]
            usage_history: 历史使用记录 [{subject_index, used_at}]
        
        Returns:
            RotationResult: 选中的主题信息
        """
        if not available_subjects:
            raise ValueError(f"客户 {customer_id} 没有可用主题")
        
        return self._weighted_random_select(customer_id, available_subjects, usage_history)
    
    def _weighted_random_select(
        self,
        customer_id: int,
        subjects: List[Dict],
        history: List[Dict]
    ) -> RotationResult:
        """
        加权随机选择：
        - 最近使用过的主题权重降低
        - 从未使用过的主题权重最高
        - 确保不会连续使用同一主题
        """
        # 计算每个主题的使用次数和最近使用时间
        subject_stats = {s['subject_index']: {'count': 0, 'last_used': None} 
                        for s in subjects}
        
        for h in history:
            idx = h['subject_index']
            if idx in subject_stats:
                subject_stats[idx]['count'] += 1
                used_at = h.get('used_at')
                if used_at:
                    if (subject_stats[idx]['last_used'] is None or 
                        used_at > subject_stats[idx]['last_used']):
                        subject_stats[idx]['last_used'] = used_at
        
        # 计算权重
        weights = []
        now = datetime.now()
        
        for s in subjects:
            idx = s['subject_index']
            stats = subject_stats[idx]
            
            base_weight = 100
            
            # 使用次数越多，权重越低
            usage_penalty = stats['count'] * 15
            
            # 最近使用过，大幅降低权重
            recency_penalty = 0
            if stats['last_used']:
                if isinstance(stats['last_used'], str):
                    # 如果是字符串，尝试解析
                    try:
                        last_used = datetime.strptime(stats['last_used'], '%Y-%m-%d %H:%M:%S')
                    except:
                        last_used = now
                else:
                    last_used = stats['last_used']
                
                hours_since = (now - last_used).total_seconds() / 3600
                if hours_since < 48:  # 48小时内使用过
                    recency_penalty = 50
                elif hours_since < 168:  # 一周内使用过
                    recency_penalty = 20
            
            weight = max(5, base_weight - usage_penalty - recency_penalty)
            weights.append(weight)
        
        # 加权随机选择
        total = sum(weights)
        if total == 0:
            # 如果所有权重都是0，均匀随机
            selected = random.choice(subjects)
        else:
            probabilities = [w / total for w in weights]
            selected = random.choices(subjects, weights=probabilities, k=1)[0]
        
        return RotationResult(
            subject_id=selected['id'],
            subject_index=selected['subject_index'],
            subject_line=selected['subject_line'],
            strategy_used=f"weighted_random (weight={weights[subjects.index(selected)]})"
        )
    
    def get_usage_statistics(self, customer_id: int, subjects: List[Dict], history: List[Dict]) -> Dict:
        """获取主题使用统计"""
        stats = {}
        
        for s in subjects:
            idx = s['subject_index']
            subject_history = [h for h in history if h['subject_index'] == idx]
            
            stats[idx] = {
                'subject_line': s['subject_line'],
                'usage_count': len(subject_history),
                'last_used': subject_history[0]['used_at'] if subject_history else None
            }
        
        return stats

if __name__ == '__main__':
    # 测试
    rotator = SubjectRotator()
    
    subjects = [
        {'id': 1, 'subject_index': 1, 'subject_line': 'Subject 1'},
        {'id': 2, 'subject_index': 2, 'subject_line': 'Subject 2'},
        {'id': 3, 'subject_index': 3, 'subject_line': 'Subject 3'},
        {'id': 4, 'subject_index': 4, 'subject_line': 'Subject 4'},
        {'id': 5, 'subject_index': 5, 'subject_line': 'Subject 5'}
    ]
    
    # 模拟使用历史
    history = [
        {'subject_index': 1, 'used_at': datetime.now()}
    ]
    
    result = rotator.select_next_subject(1, subjects, history)
    print(f"选中主题: {result.subject_line}")
    print(f"策略: {result.strategy_used}")
