cimport numpy as np
from libcpp.map cimport map
from libcpp.set cimport set
from libcpp.string cimport string
from libcpp.vector cimport vector
import numpy as np


cdef class Config:
    cdef set[string]* valid_ids

cdef class Processor:
    cdef map[string, vector[long]*]* event_log
    cdef object config
    cdef public double[:, ::1] status_codes
