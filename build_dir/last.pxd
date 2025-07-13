# V4 Generated .pxd file by py2cy (FINAL)
cimport numpy as np
from libcpp.map cimport map
from libcpp.memory cimport unique_ptr
from libcpp.vector cimport vector


cdef class DataProcessor:
    cdef readonly np.float64_t[:, ::1] result_matrix
    cdef readonly long processed_count
    cdef readonly long* last_error_code
    
    cdef bint _is_valid_event(long event_id)
    cpdef void log_event(long event_id, double measurement)
    cpdef void process_data_stream(np.int32_t[::1] data_points)


