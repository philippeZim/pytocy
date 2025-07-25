# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: cdivision=True
# cython: nonecheck=False


from libcpp.map cimport map
from libcpp.memory cimport unique_ptr
from libcpp.vector cimport vector

cimport numpy as np
import numpy as np

cdef class DataProcessor:
    '''
    A processor that simulates a complex data analysis pipeline.
    It uses C++ containers for performance-critical logs and NumPy for numerical data.
    '''
    cdef unique_ptr[map[long, unique_ptr[vector[double]]]] event_log
    cdef np.float64_t[::1, ::1] result_matrix
    cdef long processed_count
    cdef long* last_error_code
    
    def __cinit__(self):
        self.event_log.reset(new map[long, unique_ptr[vector[double]]]())
    
    def  __init__(self, long num_rows, long num_cols):
        '''Initializes the data processor and allocates the NumPy result matrix.'''
        self.result_matrix = np.zeros((num_rows, num_cols), dtype=np.float64)
        self.processed_count = 0
        self.last_error_code = NULL
    
    cdef bint _is_valid_event(DataProcessor self, long event_id):
        '''A C-level helper function. Fast, but not accessible from Python.'''
        return event_id > 0 and event_id < 10000
    
    def  get_status_message(self) -> str:
        '''A pure Python method. This should remain a standard 'def' function.
        It accesses C-level attributes, which Cython will handle via properties.'''
        if self.last_error_code != NULL:
            return f'Error encountered with code: {self.last_error_code[0]}'
        return f'Successfully processed {self.processed_count} items.'
    
    cpdef void log_event(DataProcessor self, long event_id, double measurement):
        '''Logs a measurement for a given event ID. This function should be a 'cpdef'
        and contain a 'nogil' block for high-performance C++ operations.'''
        if not self._is_valid_event(event_id):
            self.last_error_code[0] = -1
            return
        if self.event_log.get().count(event_id) == 0:
            self.event_log.get()[event_id].reset(new double())
        self.event_log[event_id].append(measurement)
        self.processed_count += 1
        if self.last_error_code != NULL:
            self.last_error_code = NULL
    
    cpdef void process_data_stream(DataProcessor self, np.int32_t[::1] data_points):
        '''Processes a stream of data points, performing calculations and handling
        potential errors with try/except/finally.'''
        cdef long i = 0
        cdef long n = data_points.shape[0]
        while i < n:
            try:
                cdef object point = data_points[i]
                if point == 999:
                    raise ValueError('Encountered sentinel value')
                cdef object row = i % self.result_matrix.shape[0]
                cdef object col = i // self.result_matrix.shape[0] % self.result_matrix.shape[1]
                self.result_matrix[row, col] = point * 1.5
                self.log_event(100 + row, self.result_matrix[row, col])
            except ValueError as e:
                print(f'Caught a processing error: {e}')
                self.last_error_code[0] = 500
            finally:
                i += 1
        print('Stream processing finished.')
    
