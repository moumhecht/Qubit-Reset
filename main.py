'''
Main Initialization File and Configuration File

'''

#%% Importing Libraries
from scipy.signal.windows import gaussian
from waveform_tools import *

## Quantum Machines Imports
from qm.qua import *
from qm import LoopbackInterface
from qm import QuantumMachinesManager
from qm import SimulationConfig
from qualang_tools.loops import from_array
from qualang_tools.analysis.discriminator import two_state_discriminator
from qm.logger import logger
## Functional Imports
import plot_functions as pf
from datetime import datetime, date
import csv
import h5py
import pandas as pd
import glob
import time
import os
import numpy as np
from Utilities import *
from pathlib import Path
import json
import Labber
import warnings
import matplotlib.pyplot as plt
from get_results import *
from scipy.signal import savgol_filter
from res_fittools.res_fit import resonator
from Utilities import clk
from calibrations import *




#%% OPX and Device Definitions


host = '10.71.0.57'
port = '9510'
logger.setLevel(level='WARNING')

device_name = 'DISS10v1'
today = date.today()
sdate = today.strftime("%y%m%d")

class device():

#%% Initialization

    #%%% Default Parameters:
    default_pars = {"LO": {
                        "rr": 6.0e9, 
                        "A": 3.6e9,
                        "B": 3.7e9,
                        "C": 4.0e9,
                        "FFL_cavity":3.0e9,
                        "FFL_qubit_reset": 10.03e9
                            },
                    "A_freq": {
                        "ge": 3.695e9,
                        "ef": 3.695e9,
                        "gf": 3.695e9
                        } ,
                    # "B_freq": {
                    #     "ge": 3.695e9,
                    #     "ef": 3.695e9,
                    #     "gf": 3.695e9
                    #     },
                    # "C_freq": {
                    #     "ge": 3.895e9,
                    #     "ef": 3.895e9,
                    #     "gf": 3.895e9
                    #     },
                    "FFL_cavity_freq": 3.0e9,
                    "FFL_qubit_reset_freq": 10.03e9,
                    "rr_freq": 6.03e9,
                    "pi": {
                        "amp": 0.4,
                        "len": 48, 
                        },
                    "pi_half": {
                        "amp": 0.2,
                        "len": 48,
                        },
                    "amp_r" : 0.4,
                    "gauss_amp": 0.4,
                    "gauss_len": 48,
                    "rr_atten": 20,
                    "tof": 280, 
                    "rr_pulse_len": 2000, # Readout Integration Time in Clock cycles
                    "IQ_rotation": 0,
                    "analog_input_offsets": [0,0],
                    "qubit_reset_time": 100e3, 
                    "rr_resettime": 20e3,
                    "pi_A": {
                        "ge": {"amp": 0.4, "len": 48, "alpha": 0, "anharm": -200e6, "det": 0 },
                        "ef": {"amp": 0.4, "len": 48, "alpha": 0, "anharm": -200e6, "det": 0 },
                        "gf": {"amp": 0.4, "len": 48, "alpha": 0, "anharm": -200e6, "det": 0 },
                            },
                    "pi_half_A": {
                        "ge": { "amp": 0.2, "len": 48, "alpha": 0, "anharm": -200e6, "det": 0 },
                        "ef": { "amp": 0.2, "len": 48, "alpha": 0, "anharm": -200e6, "det": 0 },
                        "gf": { "amp": 0.2, "len": 48, "alpha": 0, "anharm": -200e6, "det": 0 },
                            },
                    "mixer_offsets": {
                        "rr" : [0,0],
                        "A" : [0,0],
                        "ffl" : [0,0]
                        },
                    "mixer_imbalance" : {
                        "rr" : [0,0],
                        "A_ge" : [0,0], 
                        "A_ef" : [0,0],
                        "A_gf" : [0,0],
                        "ffl" : [0,0]
                        },  
                    }


    #%%% __init__ function
    def __init__(self, qb):
        self.name = qb
        self.host=  host
        self.port = port

        saveDir = f"D:\OPX\qubit_reset_measurements\\{qb}\\{sdate}"
        self.saveDir = saveDir

        try:
            print("Loading Parameters from JSON File")
            with open(f'{self.saveDir}\{qb}_parameters.json', 'r') as f:
                self.pars  = json.load(f)
                
                ## Check pars
                default_keys = set(self.default_pars.keys())
                keys = set(self.pars.keys())

                for k in (default_keys - keys):
                    print(f"Key {k} is missing from the loaded parameters. Adding default value.")
                    self.pars[k] = self.default_pars[k]

                for k in (keys - default_keys):
                    self.remove_key(k)
        except FileNotFoundError:
            print("No JSON file found. Initializing with default parameters.")
            self.pars = self.default_pars
            
        
        self.write_pars()
        self.init_instruments()
        self.make_config(self.pars)

#%%% Time of Flight Calibration

def tof_cal(self, element):
    n_avg = 1000
    reset_time = 40 * clk(self.pars['rr_resettime'])

    with program() as raw_trace_prog:
        n = declare(int)
        adc_st = declare_stream(adc_trace = True)
        update_frequency(element,5e6)

        with for_(n, 0, n < n_avg, n + 1): 
            reset_phase(element)
            measure("readout", element, adc_st)
            wait(reset_time,element)

    with stream_processing():
        ## Saving the Average
        adc_st.input1().average.save("adc1")
        adc_st.input2().average.save("adc2")
        ## Save the Last Trace
        adc_st.input1().save("adc1_single_run")
        adc_st.input2().save("adc2_single_run")

    qmm = QuantumMachinesManager(host = host, port = port)
    qm = qmm.open_qm(self.config)
    job = qm.execute(raw_trace_prog)
    res_handles = job.result_handles
    res_handles.wait_for_all_values()
    adc1 = u.raw2volts(res_handles.get("adc1").fetch_all())
    adc2 = u.raw2volts(res_handles.get("adc2").fetch_all())
    adc1_single = u.raw2volts(res_handles.get("adc1_single_run").fetch_all())
    adc2_single = u.raw2volts(res_handles.get("adc2_single_run").fetch_all())

    adc1_mean = np.mean(adc1)
    adc2_mean = np.mean(adc2)

    adc1_unbiased = adc1_single - adc1_mean
    adc2_unbiased = adc2_single - adc2_mean

    signal = savgol_filter(np.abs(adc1_unbiased + 1j*adc2_unbiased), 11, 3)
    th = np.mean(signal[:100]) + 0.5*(np.max(signal)- np.mean(signal[:50]))