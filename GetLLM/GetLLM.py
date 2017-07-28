import GetLLM
r'''
.. module: GetLLM.GetLLM

Created on 11/09/09

:author: Glenn Vanbavinckhove  (gvanbavi@cern.ch)

:version: 3.00dev


GetLLM calculates a large collection of optics functions and parameters at the BPMs using the output from DRIVE.

The GetLLM output is distributed over different files according to the observable and the transverse plane:
 - getCO*; files containing the closed orbit at all BPMs, one file per plane.
 - getIP*; files containing beta and phase advance functions at the IPs.
 - getampbeta*; files containing the beta function as compputed from amplitude, one file per plane (in case of ACdipole free and driven data is also computed).
 - getbeta*; files containing the beta function as computed from phase advances between 3 BPMs. There is one file per plane (in case of AC-dipole free and driven data is computed).
 - getchi*; files containing the $\chi$ terms.
 - getcouple*; files containing the coupling resonances $f_{1001}$  and $f_{0101}$ (in case of AC-dipole free and driven data is computed).
 - getsex*; files containing the sextupolar resonance driving terms.
 - getphase*; files containing the phase advances between BPMs, one file per plane (in case of AC-dipole free and driven data is computed).
 - getphasetot*; files containing the total phase-advance using the first BPM as reference, one file per plane (in case of ACdipole free and driven data is computed).
 - getkick*; files containing the kick amplitudes and the linear invariants as derived from peak-to-peak values and spectral lines amplitudes.
 - getD*; files containing the dispersion, one per plane ( if off-momentum data is acquired).
 - getNDx*; files containing the normalized horizontal dispersion ( if off-momentum data is acquired).


Usage1::

    >pythonafs ../GetLLM.py -m ../../MODEL/SPS/twiss.dat -f ../../MODEL/SPS/SimulatedData/ALLBPMs.3 -o ./

Usage2::

    >pythonafs ../GetLLM.py -m ../../MODEL/SPS/twiss.dat -d mydictionary.py -f 37gev270amp2_12.sdds.new -o ./


Change history::

        git log GetLLM.py


        --- STRUCTURE ---

_parse_args()-function
    _parse_args
main()-function
    main
helper-functions
    _intial_setup       note the missing i in the name!
    _create_tfs_files   
    _analyse_src_files
    _check_bpm_compatibility
    _calculate_orbit
    _phase_and_beta_for_non_zero_dpp
    _calculate_getsextupoles
    _calculate_kick
    _get_calibrated_amplitudes
    _copy_calibration_files
helper-classes
    _GetllmData
        __init__
        set_outputpath
        set_bpmu_and_cut_for_closed_orbit
    _TwissData
        __init__
        has_zero_dpp_x
        has_non_zero_dpp_x
        has_zero_dpp_y
        has_non_zero_dpp_y
        has_no_input_files
    _TuneData
        __init__
        initialize_tunes
main invocation
    _start
    call _start()
'''
import os
import sys
import traceback
import math
import re
import argparse

import __init__  # @UnusedImport init will include paths
import Python_Classes4MAD.metaclass
import utils.tfs_file
import algorithms.helper
import algorithms.phase
import algorithms.beta
import algorithms.compensate_ac_effect
import algorithms.dispersion
import algorithms.coupling
import algorithms.resonant_driving_terms
import algorithms.interaction_point
import algorithms.chi_terms
import Utilities.iotools
from model import manager, creator
from model.accelerators.accelerator import AccExcitationMode
from Utilities import tfs_pandas
import pandas as pd
from time import time

import copy

from numpy import array


####
#######
#########
VERSION = 'V3.0.0 Dev'
#########
#######
####
DEBUG = sys.flags.debug  # True with python option -d! ("python -d GetLLM.py...") (vimaier)

# default arguments:

ACCEL       = "LHCB1"   #@IgnorePep8
DICT        = "0"       #@IgnorePep8
MODELTWISS  = "0"       #@IgnorePep8
FILES       = "0"       #@IgnorePep8
COCUT       = 4000      #@IgnorePep8
OUTPATH     = "./"      #@IgnorePep8
NBCPL       = 2         #@IgnorePep8
NONLINEAR   = False     #@IgnorePep8
TBTANA      = "SUSSIX"  #@IgnorePep8
BPMUNIT     = "um"      #@IgnorePep8
LHCPHASE    = "0"       #@IgnorePep8
BBTHRESH    = "0.15"    #@IgnorePep8
ERRTHRESH   = "0.15"    #@IgnorePep8
NUMBER_OF_BPMS  = 10    #@IgnorePep8
RANGE_OF_BPMS   = 11    #@IgnorePep8
AVERAGE_TUNE    = 0     #@IgnorePep8
CALIBRATION     = None  #@IgnorePep8
ERRORDEFS       = None  #@IgnorePep8
NPROCESSES      = 16    #@IgnorePep8
USE_ONLY_THREE_BPMS_FOR_BETA_FROM_PHASE   = 0    #@IgnorePep8



# DEBUGGING
def print_time(index, t):
    print "\33[38;2;255;220;50m---------------------------------------------{:.3f}\33[0m".format(t)
    
    f = open("/afs/cern.ch/work/a/awegsche/public/44_acc_cls_perf/stats_acc_cls.txt", "a")
    f.write("{} {:.7f}\n".format(index, t))
    f.close()



#===================================================================================================
# _parse_args()-function
#===================================================================================================
def _parse_args():
    ''' Parses command line arguments. '''
    
    accel_cls, rest_args = manager.get_accel_class_from_args(
        sys.argv[1:]
    )
    print("Using accelerator class: " + accel_cls.__name__)
    parser = argparse.ArgumentParser()
    parser.add_argument("-m", "--modeldir", metavar="PATH_TO_DIR", dest="model_dir",
                    help="Path to the model directory")
    parser.add_argument("-d", "--dictionary",
                    help="File with the BPM dictionary",
                    metavar="DICT", default=DICT, dest="dict")
    parser.add_argument("-f", "--files",
                    help="Files from analysis, separated by comma",
                    metavar="FILES", default=FILES, dest="files")
    parser.add_argument("-o", "--output",
                    help="Output Path",
                    metavar="OUT", default=OUTPATH, dest="output")
    parser.add_argument("-c", "--cocut",
                    help="Cut for closed orbit measurement [um]",
                    metavar="COCUT", default=COCUT, dest="COcut")
    parser.add_argument("-n", "--nbcpl",
                    help="Analysis option for coupling, 1 bpm or 2 bpms",
                    metavar="NBCPL", default=NBCPL, dest="NBcpl")
    parser.add_argument("-t", "--tbtana",
                    help="Turn-by-turn data analysis algorithm: SUSSIX, SVD or HA",
                    metavar="TBTANA", default=TBTANA, dest="TBTana")
    parser.add_argument("--nonlinear",
                    help="Run the RDT analysis",
                    metavar="NONLINEAR", default=NONLINEAR, dest="nonlinear")
    parser.add_argument("-b", "--bpmu",
                    help="BPMunit: um, mm, cm, m (default um)",
                    metavar="BPMUNIT", default=BPMUNIT, dest="BPMUNIT")
    parser.add_argument("-p", "--lhcphase",
                    help="Compensate phase shifts by tunes for the LHC experiment data, off=0(default)/on=1",
                    metavar="LHCPHASE", default=LHCPHASE, dest="lhcphase")
    parser.add_argument("-k", "--bbthreshold",
                    help="Set beta-beating threshold for action calculations, default = 0.15",
                    metavar="BBTHRESH", default=BBTHRESH, dest="bbthreshold")
    parser.add_argument("-e", "--errthreshold",
                    help="Set beta relative uncertainty threshold for action calculations, default = 0.1",
                    metavar="ERRTHRESH", default=ERRTHRESH, dest="errthreshold")
    parser.add_argument("-g", "--threebpm",
                    help="Forces to use the 3 BPM method, yes=1/no=0, default = 0",
                    metavar="USE_ONLY_THREE_BPMS_FOR_BETA_FROM_PHASE", type=int,
                    default=USE_ONLY_THREE_BPMS_FOR_BETA_FROM_PHASE, dest="use_only_three_bpms_for_beta_from_phase")
    parser.add_argument("-j", "--numbpm",
                    help="Number of different BPM combinations for beta-calculation, default = 10",
                    metavar="NUMBER_OF_BPMS", default=NUMBER_OF_BPMS, dest="number_of_bpms")
    parser.add_argument("-i", "--range",
                    help="Range of BPM for beta-calculation (>=3 and odd), default = 11",
                    metavar="RANGE_OF_BPMS", default=RANGE_OF_BPMS, dest="range_of_bpms")
    parser.add_argument("-r", "--average_tune",
                    help="Set to 1 to use average tune for all BPMs instead of specific for each one.",
                    metavar="AVERAGE_TUNE", type=int, default=AVERAGE_TUNE, dest="use_average")
    parser.add_argument("--calibration",
                    help="Path to the directory where the calibration files (calibration_x.out, calibration_y.out) are stored.",
                    metavar="CALIBRATION", default=CALIBRATION, dest="calibration_dir_path")
    parser.add_argument("--errordefs",
                      help="Gives path to the error definition file. If specified, the analytical formula will be used to calculate weighted beta and alpha. Default = None",
                      metavar="PATH_TO_FILE", default=ERRORDEFS, dest="errordefspath")
    parser.add_argument("--nprocesses", default=NPROCESSES, dest="nprocesses",
                      metavar="NPROCESSES", type=int,
                      help="Sets the number of processes used. -1: take the number of CPUs 0: run serially >1: take the specified number. default = {0:d}".format(NPROCESSES))

    # awegsche June 2016, option to include an errorfile
    # update August 2016, looking by default for this file, raising error if unable to find it
    options = parser.parse_args(args=rest_args)
    
    return options, accel_cls


#===================================================================================================
# main()-function
#===================================================================================================
def main(accelerator,
         model_dir,
         outputpath,
         files_to_analyse,
         dict_file=DICT,
         lhcphase=LHCPHASE,
         bpmu=BPMUNIT,
         cocut=COCUT,
         nbcpl=NBCPL,
         nonlinear=NONLINEAR,
         tbtana=TBTANA,
         bbthreshold=BBTHRESH,
         errthreshold=ERRTHRESH,
         use_only_three_bpms_for_beta_from_phase=USE_ONLY_THREE_BPMS_FOR_BETA_FROM_PHASE,
         number_of_bpms=NUMBER_OF_BPMS,
         range_of_bpms=RANGE_OF_BPMS,
         use_average=AVERAGE_TUNE,
         calibration_dir_path=CALIBRATION,
         errordefspath=ERRORDEFS,
         nprocesses=NPROCESSES):
    '''
    GetLLM main function.

    :param string outputpath: The output path to store results
    :param string files_to_analyse: List of files, comma separated string.
    :param string model_filename: Path and filename of model to be used
    :param string dict_file: Name of the script which will be executed. Should store dictionary with
                    mappings of BPM names.
    :param string accel: Type of accelerator. LHCB1, LHCB2, LHCB4, RHIC, SPS
    :param string lhcphase: "0" or "1" -- Compensate phase shifts by tunes for the LHC experiment data,
                             off=0(default)/on=1
    :param string BPMU: BPMunit: "um", "mm", "cm", "m" (default "um")
    :param int COcut: Cut for closed orbit measurement [um]
    :param int NBcpl: For selecting the coupling measurement method 1 bpm or 2 bpms
    :param string TBTana: Turn-by-turn data analysis algorithm: SUSSIX, SVD or HA
    :param string bbthreshold: Threshold for _calculate_kick for (beta_d-beta_m)/beta_m
    :param string errthreshold: Threshold for calculate_kick for sigma(beta_d)/beta_d
    :param int use_only_three_bpms_for_beta_from_phase:
    :param int number_of_bpms: Number of BPM-combos for beta from phase
    :param int range_of_bpms: Range of BPMs for beta from phase
    :param int use_average: Uses AVG_MUX and AVG_MUY in _analyse_src_files if 1
    :returns: int  -- 0 if the function run successfully otherwise !=0.

    '''
    return_code = 0
    
    print "Starting GetLLM ", VERSION
    
    use_average = (use_average == 1)
    use_only_three_bpms_for_beta_from_phase = (use_only_three_bpms_for_beta_from_phase == 1)

    # The following objects stores multiple variables for GetLLM to avoid having many local
    # variables. Identifiers supposed to be as short as possible.
    # --vimaier
    twiss_d = _TwissData()
    tune_d = _TuneData()
    getllm_d = _GetllmData()
    getllm_d.set_outputpath(outputpath)
    getllm_d.set_bpmu_and_cut_for_closed_orbit(cocut, bpmu)
    getllm_d.lhc_phase = lhcphase
    getllm_d.num_bpms_for_coupling = nbcpl
    getllm_d.number_of_bpms = number_of_bpms
    getllm_d.range_of_bpms = range_of_bpms
    getllm_d.use_only_three_bpms_for_beta_from_phase = use_only_three_bpms_for_beta_from_phase
    getllm_d.errordefspath = errordefspath
    getllm_d.accelerator = accelerator
    getllm_d.nprocesses = nprocesses
    # Setup
    
    bpm_dictionary= _intial_setup(getllm_d, dict_file, model_dir)

    if sys.flags.debug:
        print "INFO: DEBUG ON"

    # Creates the output files dictionary
    files_dict = _create_tfs_files(getllm_d, os.path.join(model_dir, "twiss.dat"), nonlinear)

    # Copy calibration files calibration_x/y.out from calibration_dir_path to outputpath
    calibration_twiss = _copy_calibration_files(outputpath, calibration_dir_path)
    print_time("BEFORE_ANALYSE_SRC", time() - __getllm_starttime)
    twiss_d, files_dict = _analyse_src_files(getllm_d, twiss_d, files_to_analyse, nonlinear, tbtana, files_dict, use_average, calibration_twiss, accelerator.get_model_tfs())

    # Construct pseudo-double plane BPMs
#    if (accelerator.__name__ == "SPS" or "RHIC" in accelerator.__name__) and twiss_d.has_zero_dpp_x() and twiss_d.has_zero_dpp_y():
#        [pseudo_list_x, pseudo_list_y] = algorithms.helper.pseudo_double_plane_monitors(accelerator.get_model_tfs(), twiss_d.zero_dpp_x, twiss_d.zero_dpp_y, bpm_dictionary)
#    else:
#        # Initialize variables otherwise calculate_coupling would raise an exception(vimaier)
#        pseudo_list_x = None
#        pseudo_list_y = None
    
    print_time("BEFORE_PHASE", time() - __getllm_starttime)

    print "start the actual work"
    try:
        #-------- START Phase for beta calculation with best knowledge model in ac phase compensation
        temp_dict = copy.deepcopy(files_dict)
       
        phase_d_bk, _ = algorithms.phase.calculate_phase(getllm_d, twiss_d, tune_d,
                                                         accelerator.get_best_knowledge_model_tfs(),
                                                         accelerator.get_driven_tfs(),
                                                         accelerator.get_elements_tfs(),
                                                         temp_dict)
        print_time("AFTER_PHASE_BK", time() - __getllm_starttime)
       
        #-------- START Phase
        phase_d, tune_d = algorithms.phase.calculate_phase(getllm_d, twiss_d, tune_d,
                                                           accelerator.get_model_tfs(),
                                                           accelerator.get_driven_tfs(),
                                                           accelerator.get_elements_tfs(),
                                                           files_dict)
        print_time("AFTER_PHASE", time() - __getllm_starttime)


        #-------- START Beta
        beta_d = algorithms.beta.calculate_beta_from_phase(getllm_d, twiss_d, tune_d,
                                                           phase_d_bk,
                                                           accelerator.get_model_tfs(),
                                                           accelerator.get_driven_tfs(),
                                                           accelerator.get_elements_tfs(),
                                                           accelerator.get_best_knowledge_model_tfs(),
                                                           files_dict)
        print_time("AFTER_BETA_FROM_PHASE", time() - __getllm_starttime)

        #------- START beta from amplitude
        beta_d = algorithms.beta.calculate_beta_from_amplitude(getllm_d, twiss_d, tune_d, phase_d, beta_d, mad_twiss, mad_ac, files_dict)

        #-------- START IP
        algorithms.interaction_point.calculate_ip(getllm_d, twiss_d, tune_d, phase_d, beta_d, mad_twiss, mad_ac, files_dict)

        #-------- START Orbit
        list_of_co_x, list_of_co_y, files_dict = _calculate_orbit(getllm_d, twiss_d, tune_d, mad_twiss, files_dict)

        #-------- START Dispersion
        algorithms.dispersion.calculate_dispersion(getllm_d, twiss_d, tune_d, mad_twiss, files_dict, beta_d.x_amp, list_of_co_x, list_of_co_y)
        
        #------ Start get Q,JX,delta
        files_dict, inv_x, inv_y = _calculate_kick(getllm_d, twiss_d, phase_d, beta_d, mad_twiss, mad_ac, files_dict, bbthreshold, errthreshold)

        #-------- START coupling.
        tune_d = algorithms.coupling.calculate_coupling(getllm_d, twiss_d, phase_d, tune_d, mad_twiss, mad_ac, files_dict, pseudo_list_x, pseudo_list_y)

        #-------- START RDTs
        if nonlinear:
            algorithms.resonant_driving_terms.calculate_RDTs(mad_twiss, getllm_d, twiss_d, phase_d, tune_d, files_dict, inv_x, inv_y)

        if tbtana == "SUSSIX":
            #------ Start getsextupoles @ Glenn Vanbavinckhove
            files_dict = _calculate_getsextupoles(twiss_d, phase_d, mad_twiss, files_dict, tune_d.q1f)

            #------ Start getchiterms @ Glenn Vanbavinckhove
            files_dict = algorithms.chi_terms.calculate_chiterms(getllm_d, twiss_d, mad_twiss, files_dict)

    except:
        traceback.print_exc()
        return_code = 1
    finally:
        # Write results to files in files_dict
        print "Writing files"
        for tfsfile in files_dict.itervalues():
            tfsfile.write_to_file(formatted=True)

    return return_code
# END main() ---------------------------------------------------------------------------------------


#===================================================================================================
# helper-functions
#===================================================================================================
def _intial_setup(getllm_d, dict_file, model_dir):

    if dict_file == "0":
        bpm_dictionary = {}
    else:
        execfile(dict_file)
        bpm_dictionary = dictionary  # temporarily since presently name is not bpm_dictionary

    # look for file with important BPM pairs
    pairsfilename = os.path.join(model_dir, "important_pairs")
    if os.path.exists(pairsfilename):
        getllm_d.important_pairs = {}
        pair_file = open(pairsfilename)
        for line in pair_file:
            key_value = line.split(":")
            key = key_value[0].strip()
            value = key_value[1].strip()
            if key in getllm_d.important_pairs:
                getllm_d.important_pairs[key].append(value)
            else:
                getllm_d.important_pairs[key] = [value]

    return bpm_dictionary



# END _intial_setup ---------------------------------------------------------------------------------
    
def _create_tfs_files(getllm_d, model_filename, nonlinear):
    '''
    Creates the most tfs files and stores it in an dictionary whereby the key represents the file
    and the value is the corresponding GetllmTfsFile.

    :Return: dict: string --> GetllmTfsFile
            A dictionary of created GetllmTfsFile objects. Keys are the filenames and values are the
            GetllmTfsFile objects.
    '''
    # Static variable of GetllmTfsFile to save the outputfile, GetLLM version and model filename
    utils.tfs_file.GetllmTfsFile.s_output_path = getllm_d.outputpath
    utils.tfs_file.GetllmTfsFile.s_getllm_version = VERSION
    utils.tfs_file.GetllmTfsFile.s_mad_filename = model_filename

    files_dict = {}
    files_dict['getphasex.out'] = utils.tfs_file.GetllmTfsFile('getphasex.out')
    files_dict['getphasey.out'] = utils.tfs_file.GetllmTfsFile('getphasey.out')
    files_dict['getphasetotx.out'] = utils.tfs_file.GetllmTfsFile('getphasetotx.out')
    files_dict['getphasetoty.out'] = utils.tfs_file.GetllmTfsFile('getphasetoty.out')
    files_dict['getphasex_free.out'] = utils.tfs_file.GetllmTfsFile('getphasex_free.out')
    files_dict['getphasey_free.out'] = utils.tfs_file.GetllmTfsFile('getphasey_free.out')
    files_dict['getphasex_free2.out'] = utils.tfs_file.GetllmTfsFile('getphasex_free2.out')
    files_dict['getphasey_free2.out'] = utils.tfs_file.GetllmTfsFile('getphasey_free2.out')
    files_dict['getphasetotx_free.out'] = utils.tfs_file.GetllmTfsFile('getphasetotx_free.out')
    files_dict['getphasetoty_free.out'] = utils.tfs_file.GetllmTfsFile('getphasetoty_free.out')
    files_dict['getphasetotx_free2.out'] = utils.tfs_file.GetllmTfsFile('getphasetotx_free2.out')
    files_dict['getphasetoty_free2.out'] = utils.tfs_file.GetllmTfsFile('getphasetoty_free2.out')
    files_dict['getbetax.out'] = utils.tfs_file.GetllmTfsFile('getbetax.out')
    files_dict['getbetay.out'] = utils.tfs_file.GetllmTfsFile('getbetay.out')
    files_dict['getbetax_free.out'] = utils.tfs_file.GetllmTfsFile('getbetax_free.out')
    files_dict['getbetay_free.out'] = utils.tfs_file.GetllmTfsFile('getbetay_free.out')
    files_dict['getbetax_free2.out'] = utils.tfs_file.GetllmTfsFile('getbetax_free2.out')
    files_dict['getbetay_free2.out'] = utils.tfs_file.GetllmTfsFile('getbetay_free2.out')
    files_dict['getampbetax.out'] = utils.tfs_file.GetllmTfsFile('getampbetax.out')
    files_dict['getampbetay.out'] = utils.tfs_file.GetllmTfsFile('getampbetay.out')
    files_dict['getampbetax_free.out'] = utils.tfs_file.GetllmTfsFile('getampbetax_free.out')
    files_dict['getampbetay_free.out'] = utils.tfs_file.GetllmTfsFile('getampbetay_free.out')
    files_dict['getampbetax_free2.out'] = utils.tfs_file.GetllmTfsFile('getampbetax_free2.out')
    files_dict['getampbetay_free2.out'] = utils.tfs_file.GetllmTfsFile('getampbetay_free2.out')
    files_dict['getCOx.out'] = utils.tfs_file.GetllmTfsFile('getCOx.out')
    files_dict['getCOy.out'] = utils.tfs_file.GetllmTfsFile('getCOy.out')
    files_dict['getNDx.out'] = utils.tfs_file.GetllmTfsFile('getNDx.out')
    files_dict['getDx.out'] = utils.tfs_file.GetllmTfsFile('getDx.out')
    files_dict['getDy.out'] = utils.tfs_file.GetllmTfsFile('getDy.out')
    files_dict['getcouple.out'] = utils.tfs_file.GetllmTfsFile('getcouple.out')
    if nonlinear:
        for rdt in algorithms.resonant_driving_terms.RDT_LIST:
            files_dict[rdt+'_line.out'] = utils.tfs_file.GetllmTfsFile(rdt+'_line.out')
            files_dict[rdt+'.out'] = utils.tfs_file.GetllmTfsFile(rdt+'.out')
    if getllm_d.accelerator.excitation != AccExcitationMode.FREE:
        files_dict['getcouple_free.out'] = utils.tfs_file.GetllmTfsFile('getcouple_free.out')
        files_dict['getcouple_free2.out'] = utils.tfs_file.GetllmTfsFile('getcouple_free2.out')
    files_dict['getcoupleterms.out'] = utils.tfs_file.GetllmTfsFile('getcoupleterms.out')
    #if "LHC" in getllm_d.accelerator.__name__:
    files_dict['getIP.out'] = utils.tfs_file.GetllmTfsFile('getIP.out')
    files_dict['getIPx.out'] = utils.tfs_file.GetllmTfsFile('getIPx.out')
    files_dict['getIPy.out'] = utils.tfs_file.GetllmTfsFile('getIPy.out')
    files_dict['getIPfromphase.out'] = utils.tfs_file.GetllmTfsFile('getIPfromphase.out')
    files_dict['getIPx_free.out'] = utils.tfs_file.GetllmTfsFile('getIPx_free.out')
    files_dict['getIPy_free.out'] = utils.tfs_file.GetllmTfsFile('getIPy_free.out')
    files_dict['getIPx_free2.out'] = utils.tfs_file.GetllmTfsFile('getIPx_free2.out')
    files_dict['getIPy_free2.out'] = utils.tfs_file.GetllmTfsFile('getIPy_free2.out')
    files_dict['getIPfromphase_free.out'] = utils.tfs_file.GetllmTfsFile('getIPfromphase_free.out')
    files_dict['getIPfromphase_free2.out'] = utils.tfs_file.GetllmTfsFile('getIPfromphase_free2.out')

    files_dict["getsex3000.out"] = utils.tfs_file.GetllmTfsFile("getsex3000.out")
    files_dict['getchi3000.out'] = utils.tfs_file.GetllmTfsFile('getchi3000.out')
    files_dict['getchi1010.out'] = utils.tfs_file.GetllmTfsFile('getchi1010.out')
    files_dict['getkick.out'] = utils.tfs_file.GetllmTfsFile('getkick.out')
    files_dict['getkickphase.out'] = utils.tfs_file.GetllmTfsFile('getkickphase.out')
    files_dict['getkickac.out'] = utils.tfs_file.GetllmTfsFile('getkickac.out')

    return files_dict
# END _create_tfs_files -----------------------------------------------------------------------------


def _analyse_src_files(getllm_d, twiss_d, files_to_analyse, nonlinear, turn_by_turn_algo, files_dict, use_average, calibration_twiss, model):

    if turn_by_turn_algo == "SUSSIX":
        suffix_x = '_linx'
        suffix_y = '_liny'
    elif turn_by_turn_algo == 'SVD':
        suffix_x = '_svdx'
        suffix_y = '_svdy'
    elif turn_by_turn_algo == 'HA':
        suffix_x = '_hax'
        suffix_y = '_hay'

    for file_in in files_to_analyse.split(','):
        # x file
        if file_in.endswith(".gz"):
            file_x = file_in.replace(".gz", suffix_x + ".gz")
        else:
            file_x = file_in + suffix_x

        twiss_file_x = None
        try:
            twiss_file_x = tfs_pandas.read_tfs(file_x)
#            if twiss_file_x.has_no_bpm_data():
#                print >> sys.stderr, "Ignoring empty file:", twiss_file_x.filename
#                twiss_file_x = None
        except IOError:
            print >> sys.stderr, "Cannot load file:", file_x
        except ValueError:
            pass  # Information printed by metaclass already

        if twiss_file_x is not None:
            if use_average:
                twiss_file_x = twiss_file_x.rename(columns={"AVG_MUX": "MUX"})
            if calibration_twiss is not None:
                twiss_file_x["AMPX"], twiss_file_x["ERRAMPX"] = _get_calibrated_amplitudes(twiss_file_x, calibration_twiss, "X")
            try:
                dppi = float(twiss_file_x.headers["DPP"])
            except AttributeError:
                dppi = 0.0
            if type(dppi) != float:
                print type(dppi)
                print >> sys.stderr, 'Warning: DPP may not be given as a number in ', file_x, '...trying to forcibly cast it as a number'
                try:
                    dppi = float(dppi)
                    print 'dppi= ', dppi
                except ValueError:
                    print >> sys.stderr, 'but failing. DPP in ', file_x, ' is something wrong. String? --- leaving GetLLM'
                    print >> sys.stderr, traceback.format_exc()
                    sys.exit(1)
            if dppi == 0.0:
                twiss_d.zero_dpp_x.append(twiss_file_x)
                files_dict['getphasex.out'].add_filename_to_getllm_header(file_x)
                files_dict['getphasetotx.out'].add_filename_to_getllm_header(file_x)
                files_dict['getbetax.out'].add_filename_to_getllm_header(file_x)
                files_dict['getampbetax.out'].add_filename_to_getllm_header(file_x)
                files_dict['getCOx.out'].add_filename_to_getllm_header(file_x)
                files_dict['getNDx.out'].add_filename_to_getllm_header(file_x)
                files_dict['getDx.out'].add_filename_to_getllm_header(file_x)
                files_dict['getcouple.out'].add_filename_to_getllm_header(file_in)
                if nonlinear:
                    for rdt in algorithms.resonant_driving_terms.RDT_LIST:
                        files_dict[rdt+'_line.out'].add_filename_to_getllm_header(file_in)
                        files_dict[rdt+'.out'].add_filename_to_getllm_header(file_in)
                files_dict['getIPx.out'].add_filename_to_getllm_header(file_in)
                files_dict['getIPy.out'].add_filename_to_getllm_header(file_in)
                files_dict['getIPfromphase.out'].add_filename_to_getllm_header(file_in)
                files_dict['getIPx_free.out'].add_filename_to_getllm_header(file_in)
                files_dict['getIPy_free.out'].add_filename_to_getllm_header(file_in)
                files_dict['getIPx_free2.out'].add_filename_to_getllm_header(file_in)
                files_dict['getIPy_free2.out'].add_filename_to_getllm_header(file_in)
                files_dict['getIPfromphase_free.out'].add_filename_to_getllm_header(file_in)
                files_dict['getIPfromphase_free2.out'].add_filename_to_getllm_header(file_in)
                files_dict['getphasex_free.out'].add_filename_to_getllm_header(file_x)
                files_dict['getphasex_free2.out'].add_filename_to_getllm_header(file_x)
                files_dict['getphasetotx_free.out'].add_filename_to_getllm_header(file_x)
                files_dict['getphasetotx_free2.out'].add_filename_to_getllm_header(file_x)
                files_dict['getbetax_free.out'].add_filename_to_getllm_header(file_x)
                files_dict['getbetax_free2.out'].add_filename_to_getllm_header(file_x)
                files_dict['getampbetax_free.out'].add_filename_to_getllm_header(file_x)
                files_dict['getampbetax_free2.out'].add_filename_to_getllm_header(file_x)
                files_dict['getcouple_free.out'].add_filename_to_getllm_header(file_in)
                files_dict['getcouple_free2.out'].add_filename_to_getllm_header(file_in)
            else:
                twiss_d.non_zero_dpp_x.append(twiss_file_x)
                files_dict['getNDx.out'].add_filename_to_getllm_header(file_x)
                files_dict['getDx.out'].add_filename_to_getllm_header(file_x)

        # y file
        if file_in.endswith(".gz"):
            file_y = file_in.replace(".gz", suffix_y + ".gz")
        else:
            file_y = file_in + suffix_y

        twiss_file_y = None
        try:
            twiss_file_y = tfs_pandas.read_tfs(file_y)
#            if twiss_file_y.has_no_bpm_data():
#                print >> sys.stderr, "Ignoring empty file:", twiss_file_y.filename
#                twiss_file_y = None
        except IOError:
            print 'Warning: There seems no ' + str(file_y) + ' file in the specified directory.'
        except ValueError:
            pass  # Information printed by metaclass already

        if twiss_file_y is not None:
            if use_average:
                twiss_file_y.MUY = twiss_file_y.AVG_MUY
            if calibration_twiss is not None:
                twiss_file_y.AMPY, twiss_file_y["ERRAMPY"] = _get_calibrated_amplitudes(twiss_file_y, calibration_twiss, "Y")
            try:
                dppi = float(twiss_file_y.headers["DPP"])
            except AttributeError:
                dppi = 0.0
            if type(dppi) != float:
                print >> sys.stderr, 'Warning: DPP may not be given as a number in ', file_y, '...trying to forcibly cast it as a number'
                try:
                    dppi = float(dppi)
                    print 'dppi= ', dppi
                except ValueError:
                    print >> sys.stderr, 'but failing. DPP in ', file_y, ' is something wrong. String? --- leaving GetLLM'
                    print >> sys.stderr, traceback.format_exc()
                    sys.exit(1)
            if dppi == 0.0:
                twiss_d.zero_dpp_y.append(twiss_file_y)
                files_dict['getphasey.out'].add_filename_to_getllm_header(file_y)
                files_dict['getphasetoty.out'].add_filename_to_getllm_header(file_y)
                files_dict['getbetay.out'].add_filename_to_getllm_header(file_y)
                files_dict['getampbetay.out'].add_filename_to_getllm_header(file_y)
                files_dict['getCOy.out'].add_filename_to_getllm_header(file_y)
                files_dict['getDy.out'].add_filename_to_getllm_header(file_y)
                files_dict['getphasey_free.out'].add_filename_to_getllm_header(file_y)
                files_dict['getphasey_free2.out'].add_filename_to_getllm_header(file_y)
                files_dict['getphasetoty_free.out'].add_filename_to_getllm_header(file_y)
                files_dict['getphasetoty_free2.out'].add_filename_to_getllm_header(file_y)
                files_dict['getbetay_free.out'].add_filename_to_getllm_header(file_y)
                files_dict['getbetay_free2.out'].add_filename_to_getllm_header(file_y)
                files_dict['getampbetay_free.out'].add_filename_to_getllm_header(file_y)
                files_dict['getampbetay_free2.out'].add_filename_to_getllm_header(file_y)
            else:
                twiss_d.non_zero_dpp_y.append(twiss_file_y)
                files_dict['getDy.out'].add_filename_to_getllm_header(file_y)

    if not twiss_d.has_zero_dpp_x():
        print 'Warning: you are running GetLLM without "linx of dp/p=0". Are you sure?'

        if twiss_d.has_non_zero_dpp_x():
            twiss_d.zero_dpp_x = twiss_d.non_zero_dpp_x
            twiss_d.zero_dpp_y = twiss_d.non_zero_dpp_y
            twiss_d.non_zero_dpp_x = []
            twiss_d.non_zero_dpp_y = []

            print "Previous warning suppressed, running in chromatic mode"
            files_dict['getphasex.out'].add_filename_to_getllm_header("chrommode")
            files_dict['getbetax.out'].add_filename_to_getllm_header("chrommode")
            files_dict['getampbetax.out'].add_filename_to_getllm_header("chrommode")
            files_dict['getCOx.out'].add_filename_to_getllm_header("chrommode")
            files_dict['getNDx.out'].add_filename_to_getllm_header("chrommode")
            files_dict['getDx.out'].add_filename_to_getllm_header("chrommode")
            files_dict['getcouple.out'].add_filename_to_getllm_header("chrommode")
            files_dict['getcouple_free.out'].add_filename_to_getllm_header("chrommode")
            files_dict['getcouple_free2.out'].add_filename_to_getllm_header("chrommode")
            files_dict['getphasey.out'].add_filename_to_getllm_header("chrommode")
            files_dict['getbetay_free.out'].add_filename_to_getllm_header("chrommode")
            files_dict['getampbetay.out'].add_filename_to_getllm_header("chrommode")
            files_dict['getCOx.out'].add_filename_to_getllm_header("chrommode")
            files_dict['getDy.out'].add_filename_to_getllm_header("chrommode")

    if twiss_d.has_no_input_files():
        print >> sys.stderr, "No parsed input files"
        sys.exit(1)
    
    twiss_d.zero_dpp_commonbpms_x = _get_commonbpms(twiss_d.zero_dpp_x, model)    
    twiss_d.zero_dpp_commonbpms_y = _get_commonbpms(twiss_d.zero_dpp_y, model)    
    

    return twiss_d, files_dict
# END _analyse_src_files ----------------------------------------------------------------------------


def _check_bpm_compatibility(twiss_d, mad_twiss):
    '''
    Checks the monitor compatibility between data and model. If a monitor will not be found in the
    model, a message will be print to sys.stderr.
    '''
    all_twiss_files = twiss_d.non_zero_dpp_x + twiss_d.zero_dpp_x + twiss_d.non_zero_dpp_y + twiss_d.zero_dpp_y
    for twiss_file in all_twiss_files:
        for bpm_name in twiss_file.NAME:
            try:
                mad_twiss.NAME[mad_twiss.indx[bpm_name]]
            except KeyError:
                try:
                    mad_twiss.NAME[mad_twiss.indx[str.upper(bpm_name)]]
                except KeyError:
                    print >> sys.stderr, 'Monitor ' + bpm_name + ' cannot be found in the model!'


def _calculate_orbit(getllm_d, twiss_d, tune_d, mad_twiss, files_dict):
    '''
    Calculates orbit and fills the following TfsFiles:
     - getCOx.out
     - getCOy.out
     - getCOx_dpp_' + str(k + 1) + '.out
     - getCOy_dpp_' + str(k + 1) + '.out

    :param _GetllmData getllm_d: accel is used(In-param, values will only be read)
    :param _TwissData twiss_d: Holds twiss instances of the src files. (In-param, values will only be read)
    :param _TuneData tune_d: Holds tunes and phase advances (In-param, values will only be read)

    :returns: (list, list, dict)
     - an list of dictionairies from horizontal computations
     - an list of dictionairies from vertical computations
     - the same dict as param files_dict to indicate that dict will be extended here.
    '''
    print 'Calculating orbit'
    list_of_co_x = []
    if twiss_d.has_zero_dpp_x():
        [cox, bpms] = algorithms.helper.calculate_orbit(mad_twiss, twiss_d.zero_dpp_x)
        # The output file can be directly used for orbit correction with MADX
        tfs_file = files_dict['getCOx.out']
        tfs_file.add_string_descriptor("TABLE", 'ORBIT')
        tfs_file.add_string_descriptor("TYPE", 'ORBIT')
        tfs_file.add_string_descriptor("SEQUENCE", getllm_d.accel)
        tfs_file.add_float_descriptor("Q1", tune_d.q1)
        tfs_file.add_float_descriptor("Q2", tune_d.q2)
        tfs_file.add_column_names(["NAME", "S", "COUNT", "X", "STDX", "XMDL", "MUXMDL"])
        tfs_file.add_column_datatypes(["%s", "%le", "%le", "%le", "%le", "%le", "%le"])
        for i in range(0, len(bpms)):
            bn1 = str.upper(bpms[i][1])
            bns1 = bpms[i][0]
            list_row_entries = ['"' + bn1 + '"', bns1, len(twiss_d.zero_dpp_x), cox[bn1][0], cox[bn1][1], mad_twiss.X[mad_twiss.indx[bn1]], mad_twiss.MUX[mad_twiss.indx[bn1]]]
            tfs_file.add_table_row(list_row_entries)

        list_of_co_x.append(cox)
    list_of_co_y = []
    if twiss_d.has_zero_dpp_y():
        [coy, bpms] = algorithms.helper.calculate_orbit(mad_twiss, twiss_d.zero_dpp_y)
        # The output file can be directly used for orbit correction with MADX
        tfs_file = files_dict['getCOy.out']
        tfs_file.add_string_descriptor("TABLE", 'ORBIT')
        tfs_file.add_string_descriptor("TYPE", 'ORBIT')
        tfs_file.add_string_descriptor("SEQUENCE", getllm_d.accel)
        tfs_file.add_float_descriptor("Q1", tune_d.q1)
        tfs_file.add_float_descriptor("Q2", tune_d.q2)
        tfs_file.add_column_names(["NAME", "S", "COUNT", "Y", "STDY", "YMDL", "MUYMDL"])
        tfs_file.add_column_datatypes(["%s", "%le", "%le", "%le", "%le", "%le", "%le"])
        for i in range(0, len(bpms)):
            bn1 = str.upper(bpms[i][1])
            bns1 = bpms[i][0]
            list_row_entries = ['"' + bn1 + '"', bns1, len(twiss_d.zero_dpp_y), coy[bn1][0], coy[bn1][1], mad_twiss.Y[mad_twiss.indx[bn1]], mad_twiss.MUY[mad_twiss.indx[bn1]]]
            tfs_file.add_table_row(list_row_entries)

        list_of_co_y.append(coy)
    #-------- Orbit for non-zero DPP
    if twiss_d.has_non_zero_dpp_x():
        k = 0
        for twiss_file in twiss_d.non_zero_dpp_x:
            list_with_single_twiss = []
            list_with_single_twiss.append(twiss_file)
            filename = 'getCOx_dpp_' + str(k + 1) + '.out'
            files_dict[filename] = utils.tfs_file.GetllmTfsFile(filename)
            tfs_file = files_dict[filename]
            tfs_file.add_filename_to_getllm_header(twiss_file.filename)
            tfs_file.add_float_descriptor("DPP", float(twiss_file.DPP))
            tfs_file.add_float_descriptor("Q1", tune_d.q1)
            tfs_file.add_float_descriptor("Q2", tune_d.q2)
            [codpp, bpms] = algorithms.helper.calculate_orbit(mad_twiss, list_with_single_twiss)
            tfs_file.add_column_names(["NAME", "S", "COUNT", "X", "STDX", "XMDL", "MUXMDL"])
            tfs_file.add_column_datatypes(["%s", "%le", "%le", "%le", "%le", "%le", "%le"])
            for i in range(0, len(bpms)):
                bn1 = str.upper(bpms[i][1])
                bns1 = bpms[i][0]
                list_row_entries = ['"' + bn1 + '"', bns1, len(twiss_d.zero_dpp_x), codpp[bn1][0], codpp[bn1][1], mad_twiss.X[mad_twiss.indx[bn1]], mad_twiss.MUX[mad_twiss.indx[bn1]]]
                tfs_file.add_table_row(list_row_entries)

            list_of_co_x.append(codpp)
            k += 1

    if twiss_d.has_non_zero_dpp_y():
        k = 0
        for twiss_file in twiss_d.non_zero_dpp_y:
            list_with_single_twiss = []
            list_with_single_twiss.append(twiss_file)
            filename = 'getCOy_dpp_' + str(k + 1) + '.out'
            files_dict[filename] = utils.tfs_file.GetllmTfsFile(filename)
            tfs_file = files_dict[filename]
            tfs_file.add_filename_to_getllm_header(twiss_file.filename)
            tfs_file.add_float_descriptor("DPP", float(twiss_file.DPP))
            tfs_file.add_float_descriptor("Q1", tune_d.q1)
            tfs_file.add_float_descriptor("Q2", tune_d.q2)
            [codpp, bpms] = algorithms.helper.calculate_orbit(mad_twiss, list_with_single_twiss)
            tfs_file.add_column_names(["NAME", "S", "COUNT", "Y", "STDY", "YMDL", "MUYMDL"])
            tfs_file.add_column_datatypes(["%s", "%le", "%le", "%le", "%le", "%le", "%le"])
            for i in range(0, len(bpms)):
                bn1 = str.upper(bpms[i][1])
                bns1 = bpms[i][0]
                #TODO: why twiss_d.zero_dpp_y.. above used twiss_d.non_zero_dpp_y(vimaier)
                list_row_entries = ['"' + bn1 + '"', bns1, len(twiss_d.zero_dpp_y), codpp[bn1][0], codpp[bn1][1], mad_twiss.Y[mad_twiss.indx[bn1]], mad_twiss.MUY[mad_twiss.indx[bn1]]]
                tfs_file.add_table_row(list_row_entries)

            list_of_co_y.append(codpp)
            k += 1

    return list_of_co_x, list_of_co_y, files_dict
# END _calculate_orbit ------------------------------------------------------------------------------


def _calculate_getsextupoles(twiss_d, phase_d, mad_twiss, files_dict, q1f):
    '''
    Fills the following TfsFiles:
     - getsex3000.out

    :returns: dict string --> GetllmTfsFile -- The same instace of files_dict to indicate that the dict was extended.
    '''
    print "Calculating getsextupoles"
    # For getsex1200.out andgetsex2100.out take a look at older revisions. (vimaier)

    htot, afactor, pfactor = algorithms.helper.Getsextupole(mad_twiss, twiss_d.zero_dpp_x, phase_d.ph_x, q1f, 3, 0)

    tfs_file = files_dict["getsex3000.out"]
    tfs_file.add_float_descriptor("f2h_factor", afactor)
    tfs_file.add_float_descriptor("p_f2h_factor", pfactor)
    tfs_file.add_column_names(["NAME", "S", "AMP_20", "AMP_20std", "PHASE_20", "PHASE_20std", "f3000", "f3000std", "phase_f_3000", "phase_f_3000std", "h3000", "h3000_std", "phase_h_3000", "phase_h_3000_std"])
    tfs_file.add_column_datatypes(["%s", "%le", "%le", "%le", "%le", "%le", "%le", "%le", "%le", "%le", "%le", "%le", "%le", "%le"])
    for bpm_key in htot:
        li = htot[bpm_key]
        list_row_entries = [li[0], li[1], li[2], li[3], li[4], li[5], li[6], li[7], li[8], li[9], li[10], li[11], li[12], li[13]]
        tfs_file.add_table_row(list_row_entries)

    return files_dict
# END _calculate_getsextupoles ----------------------------------------------------------------------


def _calculate_kick(getllm_d, twiss_d, phase_d, beta_d, mad_twiss, mad_ac, files_dict, bbthreshold, errthreshold):
    '''
    Fills the following TfsFiles:
     - getkick.out
     - getkickac.out

    :returns: dict string --> GetllmTfsFile -- The same instace of files_dict to indicate that the dict was extended
    '''
    print "Calculating kick"
    files = [twiss_d.zero_dpp_x + twiss_d.non_zero_dpp_x, twiss_d.zero_dpp_y + twiss_d.non_zero_dpp_y]

    meansqrt_2jx = {}
    meansqrt_2jy = {}
    bpmrejx = {}
    bpmrejy = {}

    try:
        [meansqrt_2jx, meansqrt_2jy, _, _, tunes, dpp, bpmrejx, bpmrejy] = algorithms.helper.getkick(files, mad_twiss, beta_d, bbthreshold, errthreshold)
    except IndexError:  # occurs if either no x or no y files exist
        return files_dict, [], []

    #mean_2j = mean{2J} and meansqrt_2j=mean{sqrt(2J)}

    tfs_file_model = files_dict['getkick.out']
    tfs_file_model.add_comment("Calculates the kick from the model beta function")
    column_names_list = ["DPP", "QX", "QXRMS", "QY", "QYRMS", "NATQX", "NATQXRMS", "NATQY", "NATQYRMS", "sqrt2JX", "sqrt2JXSTD", "sqrt2JY", "sqrt2JYSTD", "2JX", "2JXSTD", "2JY", "2JYSTD"]
    column_types_list = ["%le", "%le", "%le", "%le", "%le",     "%le",      "%le",    "%le",      "%le", "%le",      "%le",        "%le",       "%le",    "%le",   "%le",  "%le",    "%le"]
    tfs_file_model.add_column_names(column_names_list)
    tfs_file_model.add_column_datatypes(column_types_list)

    for i in range(0, len(dpp)):
        list_row_entries = [dpp[i], tunes[0][i], tunes[1][i], tunes[2][i], tunes[3][i], tunes[4][i], tunes[5][i], tunes[6][i], tunes[7][i], meansqrt_2jx['model'][i][0], meansqrt_2jx['model'][i][1], meansqrt_2jy['model'][i][0], meansqrt_2jy['model'][i][1], (meansqrt_2jx['model'][i][0]**2), (2*meansqrt_2jx['model'][i][0]*meansqrt_2jx['model'][i][1]), (meansqrt_2jy['model'][i][0]**2), (2*meansqrt_2jy['model'][i][0]*meansqrt_2jy['model'][i][1])]
        tfs_file_model.add_table_row(list_row_entries)
        actions_x, actions_y = meansqrt_2jx['phase'], meansqrt_2jy['phase']

    tfs_file_phase = files_dict['getkickphase.out']
    tfs_file_phase.add_float_descriptor("Threshold_for_abs(beta_d-beta_m)/beta_m", bbthreshold)
    tfs_file_phase.add_float_descriptor("Threshold_for_uncert(beta_d)/beta_d", errthreshold)
    tfs_file_phase.add_float_descriptor("X_BPMs_Rejected", bpmrejx['phase'][len(dpp) - 1])
    tfs_file_phase.add_float_descriptor("Y_BPMs_Rejected", bpmrejy['phase'][len(dpp) - 1])
    tfs_file_phase.add_column_names(column_names_list)
    tfs_file_phase.add_column_datatypes(column_types_list)
    for i in range(0, len(dpp)):
        list_row_entries = [dpp[i], tunes[0][i], tunes[1][i], tunes[2][i], tunes[3][i], tunes[4][i], tunes[5][i], tunes[6][i], tunes[7][i], meansqrt_2jx['phase'][i][0], meansqrt_2jx['phase'][i][1], meansqrt_2jy['phase'][i][0], meansqrt_2jy['phase'][i][1], (meansqrt_2jx['model'][i][0]**2), (2*meansqrt_2jx['model'][i][0]*meansqrt_2jx['model'][i][1]), (meansqrt_2jy['model'][i][0]**2), (2*meansqrt_2jy['model'][i][0]*meansqrt_2jy['model'][i][1])]
        tfs_file_phase.add_table_row(list_row_entries)

    if getllm_d.accelerator.excitation != AccExcitationMode.FREE:
        tfs_file = files_dict['getkickac.out']
        tfs_file.add_float_descriptor("RescalingFactor_for_X", beta_d.x_ratio_f)
        tfs_file.add_float_descriptor("RescalingFactor_for_Y", beta_d.y_ratio_f)
        tfs_file.add_column_names(column_names_list + ["sqrt2JXRES", "sqrt2JXSTDRES", "sqrt2JYRES", "sqrt2JYSTDRES", "2JXRES", "2JXSTDRES", "2JYRES", "2JYSTDRES"])
        tfs_file.add_column_datatypes(column_types_list + ["%le", "%le", "%le", "%le", "%le", "%le", "%le", "%le"])
        [inv_jx, inv_jy, tunes, dpp] = algorithms.compensate_ac_effect.getkickac(mad_ac, files, phase_d.acphasex_ac2bpmac, phase_d.acphasey_ac2bpmac, getllm_d.beam_direction, getllm_d.lhc_phase)
        for i in range(0, len(dpp)):
            #TODO: in table will be the ratio without f(beta_d.x_ratio) used but rescaling factor is f version(beta_d.x_ratio_f). Check it (vimaier)
            list_row_entries = [dpp[i], tunes[0][i], tunes[1][i], tunes[2][i], tunes[3][i], tunes[4][i], tunes[5][i], tunes[6][i], tunes[7][i], inv_jx[i][0], inv_jx[i][1], inv_jy[i][0], inv_jy[i][1], (inv_jx[i][0] ** 2), (2 * inv_jx[i][0] * inv_jx[i][1]), (inv_jy[i][0] ** 2), (2 * inv_jy[i][0] * inv_jy[i][1]), (inv_jx[i][0] / math.sqrt(beta_d.x_ratio)), (inv_jx[i][1] / math.sqrt(beta_d.x_ratio)), (inv_jy[i][0] / math.sqrt(beta_d.y_ratio)), (inv_jy[i][1] / math.sqrt(beta_d.y_ratio)), (inv_jx[i][0] ** 2 / beta_d.x_ratio), (2 * inv_jx[i][0] * inv_jx[i][1] / beta_d.x_ratio), (inv_jy[i][0] ** 2 / beta_d.y_ratio), (2 * inv_jy[i][0] * inv_jy[i][1] / beta_d.y_ratio)]
            tfs_file.add_table_row(list_row_entries)
            actions_x, actions_y = inv_jx, inv_jx

    return files_dict, actions_x, actions_y
# END _calculate_kick -------------------------------------------------------------------------------


def _get_calibrated_amplitudes(drive_file, calibration_twiss, plane):
    calibration_file = calibration_twiss[plane]
    cal_amplitudes = []
    err_cal_amplitudes = []
    for bpm_name in drive_file.NAME:
        drive_index = drive_file.indx[bpm_name]
        cal_amplitude = getattr(drive_file, "AMP" + plane)[drive_index]
        err_cal_amplitude = 0.
        if bpm_name in calibration_file.NAME:
            cal_index = calibration_file.indx[bpm_name]
            cal_amplitude = cal_amplitude * calibration_file.CALIBRATION[cal_index]
            err_cal_amplitude = calibration_file.ERROR_CALIBRATION[cal_index]
        cal_amplitudes.append(cal_amplitude)
        err_cal_amplitudes.append(err_cal_amplitude)
    return array(cal_amplitudes), array(err_cal_amplitudes)
# END _get_calibrated_amplitudes --------------------------------------------------------------------


def _copy_calibration_files(output_path, calibration_dir_path):
    calibration_twiss = {}
    if calibration_dir_path is not None:
        original_cal_file_path_x = os.path.join(calibration_dir_path, "calibration_x.out")
        original_cal_file_path_y = os.path.join(calibration_dir_path, "calibration_y.out")
        cal_file_path_x = os.path.join(output_path, "calibration_x.out")
        cal_file_path_y = os.path.join(output_path, "calibration_y.out")
        Utilities.iotools.copy_item(original_cal_file_path_x, cal_file_path_x)
        Utilities.iotools.copy_item(original_cal_file_path_y, cal_file_path_y)

        calibration_twiss["X"] = Python_Classes4MAD.metaclass.twiss(cal_file_path_x)
        calibration_twiss["Y"] = Python_Classes4MAD.metaclass.twiss(cal_file_path_y)
        return calibration_twiss
    else:
        return None
# END _copy_calibration_files --------------------------------------------------------------------


def _get_commonbpms(ListOfFiles, model):
    starttime = time()
    commonbpms = pd.merge(model[["S", "NAME"]], ListOfFiles[0][["NAME","SLABEL"]], on="NAME", how="inner")   
    for i in range(1, len(ListOfFiles)):
        commonbpms = pd.merge(commonbpms, ListOfFiles[i][["NAME","SLABEL"]], on="NAME", how="inner") 


#    common_names = set(model["NAME"]) & set(ListOfFiles[0]["NAME"])
#    model_tfs = model.set_index("NAME")
#    for i in range(1, len(ListOfFiles)):
#        common_names = common_names & set(ListOfFiles[i]["NAME"])
#    commonbpms = [[b, model_tfs.loc[b,"S"]] for b in common_names]
    print "intersectiing bpms took {:.3f} s".format(time() - starttime)
    return commonbpms[["S", "NAME"]]


#===================================================================================================
# helper classes for data structures
#===================================================================================================

        
class _GetllmData(object):
    ''' Holds some data from parameters of main function. '''

    def __init__(self):
        '''Constructor'''
        self.outputpath = ""
        self.list_of_input_files = []

        self.accelerator = None
        self.lhc_phase = ""
        self.bpm_unit = ""
        self.cut_for_closed_orbit = 0
        self.num_bpms_for_coupling = 0 
        self.use_only_three_bpms_for_beta_from_phase = True
        self.number_of_bpms = 0
        self.range_of_bpms = 0
        self.errordefspath = ""
        self.parallel = False
        self.nprocesses = 1
        self.important_pairs = {}

    def set_outputpath(self, outputpath):
        ''' Sets the outputpath and creates directories if they not exist.

        :param string outputpath: Path to output dir. If dir(s) to output do(es) not exist, it/they will be created.
        '''
        Utilities.iotools.create_dirs(outputpath)
        self.outputpath = outputpath

    def set_bpmu_and_cut_for_closed_orbit(self, cut_co, bpm_unit):
        ''' Calculates and sets the cut and bpm unit.
        :param int cut_co: Cut in um(micrometer).
        :param string bpm_unit: Indicates used unit. um, mm, cm or m
        '''
        self.bpm_unit = bpm_unit

        if bpm_unit == 'um':
            self.cut_for_closed_orbit = cut_co
        elif bpm_unit == 'mm':
            self.cut_for_closed_orbit = cut_co / 1.0e3
        elif bpm_unit == 'cm':
            self.cut_for_closed_orbit = cut_co / 1.0e4
        elif bpm_unit == 'm':
            self.cut_for_closed_orbit = cut_co / 1.0e6
        else:
            print >> sys.stderr, "Wrong BPM unit:", bpm_unit


class _TwissData(object):
    ''' Holds twiss instances of all src files. '''
    def __init__(self):
        '''Constructor'''
        self.zero_dpp_x = []  # List of src files which have dpp==0.0
        self.non_zero_dpp_x = []  # List of src files which have dpp!=0.0
        self.zero_dpp_y = []  # List of src files which have dpp==0.0
        self.non_zero_dpp_y = []  # List of src files which have dpp!=0.0    
        self.zero_dpp_commonbpms_x = []
        self.zero_dpp_commonbpms_y = []

    def has_zero_dpp_x(self):
        ''' Returns True if _linx file(s) exist(s) with dpp==0 '''
        return 0 != len(self.zero_dpp_x)

    def has_non_zero_dpp_x(self):
        ''' Returns True if _linx file(s) exist(s) with dpp!=0 '''
        return 0 != len(self.non_zero_dpp_x)

    def has_zero_dpp_y(self):
        ''' Returns True if _liny file(s) exist(s) with dpp==0 '''
        return 0 != len(self.zero_dpp_y)

    def has_non_zero_dpp_y(self):
        ''' Returns True if _liny file(s) exist(s) with dpp!=0 '''
        return 0 != len(self.non_zero_dpp_y)
    
    def has_no_input_files(self):
        return not self.has_zero_dpp_x() and not self.has_zero_dpp_y() and not self.has_non_zero_dpp_x() and not self.has_non_zero_dpp_y()

class _TuneData(object):
    ''' Used as data structure to hold tunes and phase advances. '''
    def __init__(self):
        '''Constructor'''
        self.q1 = 0.0  # Driven horizontal tune
        self.q2 = 0.0  # Driven vertical tune
        self.mux = 0.0  # Driven horizontal phase advance
        self.muy = 0.0  # Driven vertical phase advance

        # Free is from analytic equation
        self.q1f = 0.0  # Free horizontal tune
        self.q2f = 0.0  # Free vertical tune
        self.muxf = 0.0  # Free horizontal phase advance
        self.muyf = 0.0  # Free vertical phase advance

        # Free2 is using the effective model
        self.muxf2 = 0.0  # Free2 horizontal phase advance
        self.muyf2 = 0.0  # Free2 vertical phase advance

        self.delta1 = None  # Used later to calculate free Q1. Only if with ac calculation.
        self.delta2 = None  # Used later to calculate free Q2. Only if with ac calculation.

 #===================================================================================================
# main invocation
#===================================================================================================


def _start():
    '''
    Starter function to avoid polluting global namespace with variables options,args.
    Before the following code was after 'if __name__=="__main__":'
    '''
    global __getllm_starttime
    __getllm_starttime = time()
    f = open("/afs/cern.ch/work/a/awegsche/public/44_acc_cls_perf/stats_acc_cls.txt", "a")
    f.write("Start\n")
    f.close()
    
    options, acc_cls = _parse_args()
    
    accelerator = acc_cls.init_from_model_dir(options.model_dir)
    
    print accelerator
    
    main(accelerator,
         options.model_dir,
         outputpath=options.output,
         dict_file=options.dict,
         files_to_analyse=options.files,
         lhcphase=options.lhcphase,
         bpmu=options.BPMUNIT,
         cocut=float(options.COcut),
         nbcpl=int(options.NBcpl),
         nonlinear=options.nonlinear,
         tbtana=options.TBTana,
         bbthreshold=options.bbthreshold,
         errthreshold=options.errthreshold,
         use_only_three_bpms_for_beta_from_phase=options.use_only_three_bpms_for_beta_from_phase,
         number_of_bpms=options.number_of_bpms,
         range_of_bpms=options.range_of_bpms,
         use_average=options.use_average,
         calibration_dir_path=options.calibration_dir_path,
         errordefspath=options.errordefspath,
         nprocesses=options.nprocesses)
     
     
if __name__ == "__main__":
    _start()
