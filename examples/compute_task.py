def process_data(factor: float, iterations: int):
    """A sample function with typed arguments."""
    total = 0.0  # Will be inferred as a double
    i = 0        # Will be inferred as a long
    
    for i in range(iterations):
        # A simple calculation
        total = total + (i * factor)
        
    some_text = "Calculation finished." # Will be an object
    print(some_text)
    
    return total

def main_entrypoint():
    print("Starting computation...")
    result = process_data(2.5, 10000000)
    print(f"Final result: {result}")