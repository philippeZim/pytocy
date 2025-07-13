# full_integration_test.py
import numpy as np
from typing import Dict

class ParticleSimulator:
    """A simulator that uses NumPy for particle data and C++ for caching."""
    
    particles: np.ndarray  # A 2D array: [x, y, energy]
    energy_cache: Dict[int, float]

    def __init__(self, num_particles: int):
        self.particles = np.random.rand(num_particles, 3) * 100.0
        # The C++ map will be created in __cinit__

    def run_simulation_step(self, energy_threshold: float):
        """
        Updates particle energies. This should be a high-performance
        nogil function.
        """
        num_particles: int = len(self.particles)
        
        for i in range(num_particles):
            # Read from memoryview
            current_energy: float = self.particles[i, 2]

            if current_energy < energy_threshold:
                # Write to memoryview
                self.particles[i, 2] += 5.0 # Boost low-energy particles
            else:
                self.particles[i, 2] *= 0.9 # High-energy particles decay
    
    def get_average_energy(self) -> float:
        """Calculates the average energy of all particles."""
        total_energy: float = 0.0
        count: int = len(self.particles)
        
        if count == 0:
            return 0.0

        for i in range(count):
            total_energy += self.particles[i, 2]

        avg: float = total_energy / count
        # Update the C++ map cache
        self.energy_cache[0] = avg
        return avg