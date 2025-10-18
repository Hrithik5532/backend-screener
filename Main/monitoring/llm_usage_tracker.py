from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from datetime import datetime
import json
from enum import Enum
import uuid

class LLMType(Enum):
    QUERY_DECOMPOSITION = "query_decomposition"
    TABLE_FILTERING = "table_filtering" 
    DATA_RETRIEVAL = "data_retrieval"
    FORMULA_GENERATION = "formula_generation"
    RESPONSE_GENERATION = "response_generation"

@dataclass
class LLMUsageRecord:
    """Enhanced record for individual LLM call usage with recursion tracking"""
    llm_type: LLMType
    call_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])  # Unique call ID
    parent_call_id: Optional[str] = None  # Parent call for recursion tracking
    company_slug: Optional[str] = None
    metric_name: Optional[str] = None
    recursion_depth: int = 0
    recursion_path: List[str] = field(default_factory=list)  # Path of metric names in recursion
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_ms: float = 0.0
    tokens_used: Dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0
    model_name: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None
    additional_info: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'call_id': self.call_id,
            'parent_call_id': self.parent_call_id,
            'llm_type': self.llm_type.value,
            'company_slug': self.company_slug,
            'metric_name': self.metric_name,
            'recursion_depth': self.recursion_depth,
            'recursion_path': self.recursion_path,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'duration_ms': self.duration_ms,
            'tokens_used': self.tokens_used,
            'cost_usd': self.cost_usd,
            'model_name': self.model_name,
            'success': self.success,
            'error_message': self.error_message,
            'additional_info': self.additional_info
        }

@dataclass
class RecursionTrace:
    """Track recursion chains and call relationships"""
    root_metric: str
    call_chain: List[str] = field(default_factory=list)  # Chain of call IDs
    metric_chain: List[str] = field(default_factory=list)  # Chain of metric names
    depth: int = 0
    total_calls: int = 0
    successful_calls: int = 0

@dataclass
class LLMUsageSummary:
    """Enhanced summary with recursion analysis"""
    session_id: str
    query: str
    start_time: datetime
    end_time: Optional[datetime] = None
    total_duration_ms: float = 0.0
    records: List[LLMUsageRecord] = field(default_factory=list)
    recursion_traces: Dict[str, RecursionTrace] = field(default_factory=dict)
    call_relationships: Dict[str, List[str]] = field(default_factory=dict)  # parent_id -> [child_ids]
    
    def analyze_recursion(self) -> Dict[str, Any]:
        """Analyze recursion patterns"""
        analysis = {
            'total_recursive_chains': 0,
            'max_recursion_depth': 0,
            'recursive_metrics': set(),
            'call_tree': {},
            'depth_distribution': {},
            'recursive_costs': 0.0
        }
        
        # Build call tree and analyze patterns
        for record in self.records:
            if record.recursion_depth > 0:
                analysis['recursive_metrics'].add(record.metric_name)
                analysis['max_recursion_depth'] = max(analysis['max_recursion_depth'], record.recursion_depth)
                analysis['recursive_costs'] += record.cost_usd
                
                # Count by depth
                depth_key = f"depth_{record.recursion_depth}"
                analysis['depth_distribution'][depth_key] = analysis['depth_distribution'].get(depth_key, 0) + 1
        
        analysis['total_recursive_chains'] = len(analysis['recursive_metrics'])
        analysis['recursive_metrics'] = list(analysis['recursive_metrics'])
        
        return analysis
    
    def get_recursion_summary_by_type(self) -> Dict[str, Dict[str, Any]]:
        """Get usage summary with recursion breakdown by LLM type"""
        summary = {}
        
        for llm_type in LLMType:
            type_records = [r for r in self.records if r.llm_type == llm_type]
            if type_records:
                # Separate root and recursive calls
                root_calls = [r for r in type_records if r.recursion_depth == 0]
                recursive_calls = [r for r in type_records if r.recursion_depth > 0]
                
                type_tokens = {"input": 0, "output": 0, "total": 0}
                type_duration = 0.0
                type_cost = 0.0
                successful_calls = 0
                
                for record in type_records:
                    for key, value in record.tokens_used.items():
                        if key in type_tokens:
                            type_tokens[key] += value
                    type_duration += record.duration_ms
                    type_cost += record.cost_usd
                    if record.success:
                        successful_calls += 1
                
                summary[llm_type.value] = {
                    'total_calls': len(type_records),
                    'root_calls': len(root_calls),
                    'recursive_calls': len(recursive_calls),
                    'successful_calls': successful_calls,
                    'success_rate': successful_calls / len(type_records),
                    'total_tokens': type_tokens,
                    'total_duration_ms': type_duration,
                    'avg_duration_ms': type_duration / len(type_records),
                    'total_cost_usd': type_cost,
                    'avg_cost_usd': type_cost / len(type_records),
                    'recursion_breakdown': {
                        'max_depth': max([r.recursion_depth for r in type_records], default=0),
                        'recursive_cost': sum([r.cost_usd for r in recursive_calls]),
                        'recursive_duration': sum([r.duration_ms for r in recursive_calls])
                    }
                }
        
        return summary
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with enhanced recursion analysis"""
        recursion_analysis = self.analyze_recursion()
        
        return {
            'session_id': self.session_id,
            'query': self.query,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'total_duration_ms': self.total_duration_ms,
            'total_records': len(self.records),
            'total_tokens': self.total_tokens,
            'total_cost_usd': self.total_cost,
            'success_rate': self.success_rate,
            'recursion_analysis': recursion_analysis,
            'summary_by_type': self.get_recursion_summary_by_type(),
            'records': [record.to_dict() for record in self.records]
        }
    
    @property
    def total_tokens(self) -> Dict[str, int]:
        """Calculate total tokens across all records"""
        totals = {"input": 0, "output": 0, "total": 0}
        for record in self.records:
            for key, value in record.tokens_used.items():
                if key in totals:
                    totals[key] += value
        return totals
    
    @property
    def total_cost(self) -> float:
        """Calculate total cost across all records"""
        return sum(record.cost_usd for record in self.records)
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate of LLM calls"""
        if not self.records:
            return 0.0
        successful = sum(1 for record in self.records if record.success)
        return successful / len(self.records)

class EnhancedLLMUsageTracker:
    """Enhanced tracker with recursion tracing"""
    
    def __init__(self):
        self.current_session: Optional[LLMUsageSummary] = None
        self.sessions: List[LLMUsageSummary] = []
        self.call_stack: List[str] = []  # Stack of current call IDs for recursion tracking
        self.metric_path: List[str] = []  # Stack of metric names for recursion path
    
    def start_session(self, query: str, session_id: Optional[str] = None) -> str:
        """Start a new tracking session"""
        if session_id is None:
            session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        
        self.current_session = LLMUsageSummary(
            session_id=session_id,
            query=query,
            start_time=datetime.now()
        )
        
        # Reset call stack for new session
        self.call_stack.clear()
        self.metric_path.clear()
        
        return session_id
    
    def push_recursion_context(self, metric_name: str) -> str:
        """Push a new recursion context and return call ID"""
        call_id = str(uuid.uuid4())[:8]
        self.call_stack.append(call_id)
        self.metric_path.append(metric_name)
        return call_id
    
    def pop_recursion_context(self):
        """Pop recursion context when exiting"""
        if self.call_stack:
            self.call_stack.pop()
        if self.metric_path:
            self.metric_path.pop()
    
    def record_llm_usage(self, 
                        llm_type: LLMType,
                        usage_data: Dict[str, Any],
                        duration_ms: float,
                        company_slug: Optional[str] = None,
                        metric_name: Optional[str] = None,
                        recursion_depth: int = 0,
                        model_name: Optional[str] = None,
                        success: bool = True,
                        error_message: Optional[str] = None,
                        additional_info: Optional[Dict[str, Any]] = None) -> str:
        """Enhanced record_llm_usage with recursion tracking"""
        
        if not self.current_session:
            raise ValueError("No active session. Call start_session first.")
        
        # Generate unique call ID
        call_id = str(uuid.uuid4())[:8]
        
        # Determine parent call ID
        parent_call_id = self.call_stack[-1] if self.call_stack else None
        
        # Build recursion path
        current_recursion_path = self.metric_path.copy()
        if metric_name and metric_name not in current_recursion_path:
            current_recursion_path.append(metric_name)
        
        # Parse tokens from usage_data
        tokens_used = {}
        if isinstance(usage_data, dict):
            if 'usage' in usage_data:
                usage = usage_data['usage']
                tokens_used = {
                    'input': usage.get('prompt_tokens', 0),
                    'output': usage.get('completion_tokens', 0),
                    'total': usage.get('total_tokens', 0)
                }
            elif 'input_tokens' in usage_data:
                tokens_used = {
                    'input': usage_data.get('input_tokens', 0),
                    'output': usage_data.get('output_tokens', 0),
                    'total': usage_data.get('total_tokens', 0)
                }
            else:
                tokens_used = {
                    'input': usage_data.get('input_tokens', 0),
                    'output': usage_data.get('output_tokens', 0),
                    'total': usage_data.get('total_tokens', 0)
                }
        
        # Calculate cost
        cost_usd = self._calculate_cost(tokens_used, model_name)
        
        # Enhanced additional info
        enhanced_additional_info = additional_info or {}
        enhanced_additional_info.update({
            'call_stack_depth': len(self.call_stack),
            'is_recursive_call': recursion_depth > 0,
            'recursion_trigger': parent_call_id is not None
        })
        
        record = LLMUsageRecord(
            call_id=call_id,
            parent_call_id=parent_call_id,
            llm_type=llm_type,
            company_slug=company_slug,
            metric_name=metric_name,
            recursion_depth=recursion_depth,
            recursion_path=current_recursion_path,
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_ms=duration_ms,
            tokens_used=tokens_used,
            cost_usd=cost_usd,
            model_name=model_name,
            success=success,
            error_message=error_message,
            additional_info=enhanced_additional_info
        )
        
        self.current_session.records.append(record)
        
        # Track call relationships
        if parent_call_id:
            if parent_call_id not in self.current_session.call_relationships:
                self.current_session.call_relationships[parent_call_id] = []
            self.current_session.call_relationships[parent_call_id].append(call_id)
        
        return call_id
    
    def end_session(self) -> Optional[LLMUsageSummary]:
        """End current session and return summary"""
        if not self.current_session:
            return None
        
        self.current_session.end_time = datetime.now()
        self.current_session.total_duration_ms = (
            self.current_session.end_time - self.current_session.start_time
        ).total_seconds() * 1000
        
        self.sessions.append(self.current_session)
        session = self.current_session
        self.current_session = None
        
        # Clear context
        self.call_stack.clear()
        self.metric_path.clear()
        
        return session
    
    def _calculate_cost(self, tokens_used: Dict[str, int], model_name: Optional[str] = None) -> float:
        """Calculate cost based on tokens and model"""
        pricing = {
            'gpt-4': {'input': 0.03 / 1000, 'output': 0.06 / 1000},
            'gpt-4.1': {'input': 0.03 / 1000, 'output': 0.06 / 1000},
            'gpt-3.5-turbo': {'input': 0.001 / 1000, 'output': 0.002 / 1000},
            'claude-3': {'input': 0.015 / 1000, 'output': 0.075 / 1000},
            'default': {'input': 0.01 / 1000, 'output': 0.03 / 1000}
        }
        
        model_pricing = pricing.get(model_name, pricing['default'])
        
        input_cost = tokens_used.get('input', 0) * model_pricing['input']
        output_cost = tokens_used.get('output', 0) * model_pricing['output']
        
        return input_cost + output_cost

def enhanced_log_usage_summary(summary: LLMUsageSummary, logger, custom_logger, store_logs_func):
    """Enhanced logging with recursion analysis"""
    
    recursion_analysis = summary.analyze_recursion()
    summary_dict = summary.to_dict()
    
    # Create formatted summary with recursion details
    summary_text = f"""
=== ENHANCED LLM USAGE SUMMARY ===
Session ID: {summary.session_id}
Query: {summary.query}
Total Duration: {summary.total_duration_ms:.2f}ms
Total Records: {len(summary.records)}
Success Rate: {summary.success_rate:.2%}

=== TOKEN USAGE ===
Total Input Tokens: {summary.total_tokens['input']:,}
Total Output Tokens: {summary.total_tokens['output']:,}
Total Tokens: {summary.total_tokens['total']:,}
Estimated Cost: ${summary.total_cost:.4f}

=== RECURSION ANALYSIS ===
Recursive Chains: {recursion_analysis['total_recursive_chains']}
Max Recursion Depth: {recursion_analysis['max_recursion_depth']}
Recursive Metrics: {', '.join(recursion_analysis['recursive_metrics'])}
Recursive Cost: ${recursion_analysis['recursive_costs']:.4f}
Depth Distribution: {recursion_analysis['depth_distribution']}

=== BREAKDOWN BY LLM TYPE ==="""
    
    for llm_type, stats in summary.get_recursion_summary_by_type().items():
        summary_text += f"""
{llm_type.upper()}:
  - Total Calls: {stats['total_calls']} (Root: {stats['root_calls']}, Recursive: {stats['recursive_calls']})
  - Success Rate: {stats['success_rate']:.2%}
  - Tokens: {stats['total_tokens']['total']:,} (Input: {stats['total_tokens']['input']:,}, Output: {stats['total_tokens']['output']:,})
  - Duration: {stats['total_duration_ms']:.2f}ms (Avg: {stats['avg_duration_ms']:.2f}ms)
  - Cost: ${stats['total_cost_usd']:.4f} (Avg: ${stats['avg_cost_usd']:.4f})
  - Recursion: Max Depth {stats['recursion_breakdown']['max_depth']}, Cost ${stats['recursion_breakdown']['recursive_cost']:.4f}"""
    
    # Log to all loggers
    logger.info(summary_text)
    custom_logger.info(summary_text)
    store_logs_func(summary_text)
    
    # Also log detailed JSON
    json_summary = json.dumps(summary_dict, indent=2)
    store_logs_func(f"DETAILED_RECURSION_ANALYSIS_JSON:\n{json_summary}")
    
    return summary_dict

# Replace the global tracker
llm_usage_tracker = EnhancedLLMUsageTracker()