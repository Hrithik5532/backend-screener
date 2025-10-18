"""
Error handling and tracking for financial analysis system
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any


class AnalysisErrorType(Enum):
    """Enumeration of all possible error types in the analysis system"""
    TABLE_FILTERING_ERROR = "table_filtering_error"
    DATA_RETRIEVAL_ERROR = "data_retrieval_error"
    FORMULA_GENERATION_ERROR = "formula_generation_error"
    RECURSION_LIMIT_ERROR = "recursion_limit_error"
    DATABASE_ERROR = "database_error"
    GENERAL_ERROR = "general_error"
    PARALLEL_PROCESSING_ERROR = "parallel_processing_error"
    EXTERNAL_API_ERROR = "external_api_error"


@dataclass
class AnalysisError:
    """
    Standardized error structure for analysis operations
    """
    error_type: AnalysisErrorType
    message: str
    metric_name: str
    company_slug: str
    original_exception: Optional[Exception] = None
    recursion_depth: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert AnalysisError to dictionary for serialization"""
        return {
            'error_type': self.error_type.value,
            'message': self.message,
            'metric_name': self.metric_name,
            'company_slug': self.company_slug,
            'exception_str': str(self.original_exception) if self.original_exception else None,
            'recursion_depth': self.recursion_depth,
        }


class RecursionTracker:
    """
    Track recursion depth for individual metrics/queries to prevent infinite loops
    """
    
    def __init__(self, max_depth: int = 3):
        self.max_depth = max_depth
        self.depth_tracker = {}  # key: metric_name, value: current_depth
    
    def get_depth(self, metric_key: str) -> int:
        """Get current recursion depth for a metric"""
        return self.depth_tracker.get(metric_key, 0)
    
    def increment(self, metric_key: str) -> bool:
        """Increment depth and return True if within limits"""
        current_depth = self.depth_tracker.get(metric_key, 0)
        new_depth = current_depth + 1
        
        if new_depth > self.max_depth:
            return False
        
        self.depth_tracker[metric_key] = new_depth
        return True
    
    def decrement(self, metric_key: str):
        """Decrement depth when exiting recursion"""
        if metric_key in self.depth_tracker:
            self.depth_tracker[metric_key] = max(0, self.depth_tracker[metric_key] - 1)
    
    def reset_metric(self, metric_key: str):
        """Reset recursion depth for a specific metric"""
        self.depth_tracker.pop(metric_key, None)
    
    def clear_all(self):
        """Clear all recursion tracking"""
        self.depth_tracker.clear()


def deep_serialize_for_crew(data: Any) -> Any:
    """
    Recursively convert any custom objects to serializable dictionaries for CrewAI
    This ensures no custom objects are passed to CrewAI
    """
    if isinstance(data, AnalysisError):
        return data.to_dict()
    elif isinstance(data, Exception):
        return {
            'error_type': 'exception',
            'message': str(data),
            'exception_type': type(data).__name__,
        }
    elif isinstance(data, dict):
        return {key: deep_serialize_for_crew(value) for key, value in data.items()}
    elif isinstance(data, (list, tuple)):
        return [deep_serialize_for_crew(item) for item in data]
    elif isinstance(data, (str, int, float, bool)) or data is None:
        return data
    else:
        # Convert any other object to string representation
        return {
            'error_type': 'unknown_object',
            'message': str(data),
            'object_type': type(data).__name__
        }


def validate_crew_input(data: Any, path: str = "root") -> list[str]:
    """
    Validate that data contains only CrewAI-compatible types
    Returns list of paths where invalid objects are found
    """
    invalid_paths = []
    
    if isinstance(data, (str, int, float, bool)) or data is None:
        return invalid_paths
    elif isinstance(data, dict):
        for key, value in data.items():
            invalid_paths.extend(validate_crew_input(value, f"{path}.{key}"))
    elif isinstance(data, (list, tuple)):
        for i, item in enumerate(data):
            invalid_paths.extend(validate_crew_input(item, f"{path}[{i}]"))
    else:
        # Found non-serializable object
        invalid_paths.append(f"{path}: {type(data).__name__}")
    
    return invalid_paths




import json
import re
import logging
from typing import List, Dict, Any

def extract_and_parse_json(output_text: str, input_structure: List) -> List[Dict]:
    """
    Robust JSON extraction and parsing with multiple fallback strategies
    """
    
    def try_parse_json(text: str) -> tuple[bool, Any]:
        """Try to parse JSON and return (success, data)"""
        try:
            data = json.loads(text)
            return True, data
        except json.JSONDecodeError:
            return False, None
    
    def clean_json_text(text: str) -> str:
        """Clean common JSON formatting issues"""
        # Remove markdown code blocks
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        
        # Strip whitespace
        text = text.strip()
        
        # Remove any text before the first { or [
        first_brace = text.find('{')
        first_bracket = text.find('[')
        
        if first_brace == -1 and first_bracket == -1:
            return text
        
        start_pos = first_brace if first_brace != -1 else float('inf')
        if first_bracket != -1:
            start_pos = min(start_pos, first_bracket)
        
        if start_pos != float('inf'):
            text = text[int(start_pos):]
        
        # Remove any text after the last } or ]
        last_brace = text.rfind('}')
        last_bracket = text.rfind(']')
        
        end_pos = max(last_brace, last_bracket)
        if end_pos != -1:
            text = text[:end_pos + 1]
        
        return text
    
    def fix_common_json_issues(text: str) -> str:
        """Fix common JSON formatting issues"""
        # Fix trailing commas
        text = re.sub(r',(\s*[}\]])', r'\1', text)
        
        # Fix single quotes to double quotes (but be careful with apostrophes)
        text = re.sub(r"'([^']*)':", r'"\1":', text)  # Keys
        text = re.sub(r":\s*'([^']*)'", r': "\1"', text)  # String values
        
        # Fix unquoted keys
        text = re.sub(r'(\w+):', r'"\1":', text)
        
        return text
    
    def extract_json_with_regex(text: str) -> List[str]:
        """Extract potential JSON objects using regex"""
        # Look for JSON objects
        json_objects = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
        
        # Look for JSON arrays
        json_arrays = re.findall(r'\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\]', text, re.DOTALL)
        
        return json_objects + json_arrays
    
    def create_fallback_response(input_structure: List, error_msg: str) -> List[Dict]:
        """Create fallback response when all parsing fails"""
        fallback_response = []
        
        for item in input_structure:
            if isinstance(item, str):
                metric_name = item
            elif isinstance(item, dict):
                metric_name = item.get('metric_name', 'unknown')
            else:
                metric_name = 'unknown'
            
            fallback_response.append({
                "metric_name": metric_name,
                "table_name": "None",
                "reasoning": f"JSON parsing failed: {error_msg}",
                "confidence_score": "0.0"
            })
        
        return fallback_response
    
    # Strategy 1: Try parsing the original text
    success, data = try_parse_json(output_text)
    if success:
        return data if isinstance(data, list) else [data]
    
    # Strategy 2: Clean the text and try again
    cleaned_text = clean_json_text(output_text)
    success, data = try_parse_json(cleaned_text)
    if success:
        return data if isinstance(data, list) else [data]
    
    # Strategy 3: Fix common JSON issues and try again
    fixed_text = fix_common_json_issues(cleaned_text)
    success, data = try_parse_json(fixed_text)
    if success:
        return data if isinstance(data, list) else [data]
    
    # Strategy 4: Extract JSON using regex and try parsing each match
    potential_jsons = extract_json_with_regex(output_text)
    for potential_json in potential_jsons:
        cleaned_potential = clean_json_text(potential_json)
        fixed_potential = fix_common_json_issues(cleaned_potential)
        
        success, data = try_parse_json(fixed_potential)
        if success:
            return data if isinstance(data, list) else [data]
    
    # Strategy 5: Try to extract key information manually if JSON parsing completely fails
    logging.warning(f"All JSON parsing strategies failed. Original text: {output_text}")
    
    # Last resort: create fallback response
    return create_fallback_response(input_structure, "All parsing strategies failed")
