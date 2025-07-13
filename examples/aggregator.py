# aggregator.py
from typing import List, Dict

def aggregate_values(values: List[float]) -> Dict[str, float]:
    """
    A function that takes a list of floats and returns an aggregated dictionary.
    This is a perfect use case for V2 optimization.
    """
    output_dict: Dict[str, float] = {} # Annotated assignment
    
    total: float = 0.0
    count: int = 0
    
    for v in values:
        total += v
    
    count = len(values)
    
    if count > 0:
        output_dict['mean'] = total / count
    
    output_dict['sum'] = total
    output_dict['count'] = count
    
    return output_dict