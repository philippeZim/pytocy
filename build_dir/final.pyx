# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: cdivision=True
# cython: nonecheck=False


from cython.operator cimport dereference as deref
from libcpp.map cimport map
from libcpp.set cimport set
from libcpp.string cimport string
from libcpp.vector cimport vector

cimport numpy as np
import numpy as np

'\nA stress test designed to probe for edge cases in the py2cy transpiler.\nIt focuses on nested C++ containers, multi-class interactions, and mixed\nGIL/nogil code blocks.\n'
cdef class Config:
    '''A simple configuration class. Tests multi-class handling.'''
    cdef set[string]* valid_ids
    
    def __cinit__(self):
        self.valid_ids = new set[string]()
    
    def __dealloc__(self):
        del self.valid_ids
    
    cpdef void __init__(self):
        pass
    
    cpdef void setup_ids(Config self):
        '''Tests C++ method translation for set.add -> set.insert.'''
        deref(self.valid_ids).insert('ID-001')
        deref(self.valid_ids).insert('ID-007')
    
    cpdef bint is_valid(Config self, object an_id):
        '''Tests C++ set.count() for checking existence.'''
        return self.valid_ids.count(an_id) > 0
    
cdef class Processor:
    '''
    A more complex class that uses nested C++ types and interacts
    with another transpiled class.
    '''
    cdef map[string, vector[long]*]* event_log
    cdef object config
    cdef double[:, ::1] status_codes
    
    def __cinit__(self):
        self.event_log = new map[string, vector[long]*]()
    
    def __dealloc__(self):
        del self.event_log
    
    cpdef void __init__(self, object config_obj):
        '''Initializes with another class instance.'''
        self.event_log = {}
        self.config = config_obj
        self.status_codes = np.array([0, 0, 0], dtype=np.int32)
    
    cpdef void register_event(Processor self, object event_id, long event_code):
        '''Tests appending to a vector that is a value in a map. This is
        a complex dereferencing scenario.'''
        if event_id not in self.event_log:
            deref(self.event_log)[event_id] = new vector[long]()
        deref(deref(self.event_log)[event_id]).push_back(event_code)
    
    cpdef void process_events(Processor self):
        '''A mixed-mode method. The outer loop can be nogil, but the inner
        print statement requires the GIL. This tests context handling.'''
        cdef long num_events = deref(self.event_log).size()
        print(f'Processing {num_events} unique event IDs.')
        for key in self.event_log:
            if self.config.is_valid(key):
                print(f'  Processing valid key: {key}')
                self.status_codes[0] += 1
            else:
                print(f'  Skipping invalid key: {key}')
                self.status_codes[1] += 1
    
    cpdef vector[long]* get_events_for_id(Processor self, object event_id):
        '''Tests returning a C++ container, which Cython should auto-convert
        to a Python list for the caller.'''
        if event_id in self.event_log:
            return deref(self.event_log)[event_id]
        return []
    
if __name__ == '__main__':
    print('--- Starting Edge Case Stress Test ---')
    cdef object conf = Config()
    conf.setup_ids()
    cdef object proc = Processor(conf)
    proc.register_event('ID-001', 100)
    proc.register_event('ID-001', 101)
    proc.register_event('ID-007', 200)
    proc.register_event('ID-INVALID', 999)
    print('\n[State] Initial Processor State:')
    print(f'  Event Log: {proc.event_log}')
    print('\n[Action] Processing events...')
    proc.process_events()
    print('\n[State] Status codes after processing [valid, invalid, other]:')
    print(f'  {proc.status_codes}')
    assert proc.status_codes[0] == 2
    assert proc.status_codes[1] == 1
    cdef object events = proc.get_events_for_id('ID-001')
    print(f'\n[State] Events retrieved for ID-001: {events}')
    assert isinstance(events, list)
    assert events == [100, 101]
    print('\n--- Edge Case Stress Test Completed Successfully ---')
