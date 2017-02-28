from __future__ import print_function
import sys
import os
import numpy as np
sys.path.append(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../")
))
from madx import madx_wrapper
from drive import drive_runner
from GetLLM import GetLLM
from Python_Classes4MAD import metaclass
import tempfile
import iotools
import ADDbpmerror
from Utilities.contexts import silence


HOR, VER = 0, 1
PLANE_SUFFIX = {HOR: "x", VER: "y"}

MADX_SCRIPT = """
title, "Tracking test for GetLLM";

!@require lhc_runII_2016
!@require tracking

option, -echo;
exec, full_lhc_def("%(MODIFIERS)s", %(BEAM)i);
call, file="/afs/cern.ch/eng/lhc/optics/runII/2015/toolkit/slice.madx";
use, sequence=LHCB%(BEAM)i;
option, echo;

beam, sequence=LHCB1, particle=proton, energy=6500,
    kbunch=1, npart=1.15E11, bv=1;
beam, sequence=LHCB2, particle=proton, energy=6500,
    kbunch=1, npart=1.15E11, bv=-1;

exec, match_tunes(64.%(IQX)s, 59.%(IQY)s, %(BEAM)i);

exec, do_twiss_monitors(
    LHCB%(BEAM)i,
    "%(TWISS)s",
    0.0
);
exec, do_twiss_elements(
    LHCB%(BEAM)i,
    "%(TWISS_ELEMENTS)s",
    0.0
);

if(%(DO_ACD)s == 1){
    exec, twiss_ac_dipole(
        %(QX)s, %(QY)s,
        %(DQX)s, %(DQY)s,
        %(BEAM)i, "%(TWISS_AC)s", 0.0
    );

    ! Uninstall AC-dipole matrix...
    seqedit, sequence=LHCB%(BEAM)i;
        remove, element=hacmap;
        remove, element=vacmap;
    endedit;

    ! ...and install as element for tracking
    exec, install_acd_as_element(
        %(QX)s, %(QY)s,
        %(DQX)s, %(DQY)s,
        %(BEAM)i,
        %(RAMP1)s, %(RAMP2)s, %(RAMP3)s, %(RAMP4)s
    );
}

exec, do_madx_track_single_particle(
    %(KICK_X)s, %(KICK_Y)s, 0.0, 0.0,
    %(NUM_TURNS)s, "%(TRACK_PATH)s"
);
"""

OPTICS = "40cm"

MODIFIERS = {
    "injection": "call file=\"runII_2016/opt_inj.madx\";",
    "40cm": "call file=\"runII_2016/opt_400_10000_400_3000.madx\";",
}

ERR_DEF_FILES = {
    "injection": "0450GeV",
    "40cm": "6500GeV",
}
ERR_DEF_PATH = os.path.join(
    "/afs", "cern.ch", "work", "o", "omc",
    "Error_definition_files", ERR_DEF_FILES[OPTICS]
)

BEAM = 1
QX = 0.28
QY = 0.31
DQX = 0.27
DQY = 0.32
TUNE_WINDOW = 0.001

DO_ACD = 1
KICK_X = 0.0
KICK_Y = 0.0

RAMP1 = 50  # Ramp up start turn
RAMP2 = 2050  # Ramp up end start turn
RAMP3 = 4250  # Ramp down start turn
RAMP4 = 6250  # Ramp down start turn

NUM_TURNS = RAMP3


def print_getllm_precision():
    output_dir = tempfile.mkdtemp()
    try:
        _run_tracking_model(output_dir)
        _do_analysis(output_dir)
        _comprare_results(output_dir)
    finally:
        _clean_up_files(output_dir)


def _run_tracking_model(directory):
    print("Creating model and tracking...")
    madx_script = _get_madx_script(BEAM, directory)
    with silence():
        madx_wrapper.resolve_and_run_string(madx_script)
    track_path = _get_track_path(directory, one=True)
    tbt_path = _get_tbt_path(directory)
    with silence():
        ADDbpmerror.convert_files(infile=track_path, outfile=tbt_path)


def _get_madx_script(beam, directory):
    modifiers_file_path = _get_modifiers_file(OPTICS, directory)
    twiss_path = _get_twiss_path(directory)
    twiss_elem_path = _get_twiss_elem_path(directory)
    twiss_ac_path = _get_twiss_ac_path(directory)
    track_path = _get_track_path(directory)
    madx_script = MADX_SCRIPT % {
        "MODIFIERS": modifiers_file_path,
        "BEAM": beam,
        "IQX": str(QX).replace("0.", ""),
        "IQY": str(QY).replace("0.", ""),
        "QX": QX,
        "QY": QY,
        "DQX": DQX,
        "DQY": DQY,
        "TWISS": twiss_path,
        "TWISS_ELEMENTS": twiss_elem_path,
        "TWISS_AC": twiss_ac_path,
        "NUM_TURNS": NUM_TURNS,
        "TRACK_PATH": track_path,
        "DO_ACD": DO_ACD,
        "KICK_X": KICK_X,
        "KICK_Y": KICK_Y,
        "RAMP1": RAMP1,
        "RAMP2": RAMP2,
        "RAMP3": RAMP3,
        "RAMP4": RAMP4,
    }
    return madx_script


def _get_twiss_path(directory):
    return os.path.join(directory, "twiss.dat")


def _get_twiss_elem_path(directory):
    return os.path.join(directory, "twiss_elements.dat")


# TODO: This into madx template
def _get_twiss_centre_path(directory):
    return os.path.join(directory, "twiss_elements_centre.dat")


def _get_twiss_ac_path(directory):
    return os.path.join(directory, "twiss_ac.dat")


def _get_track_path(directory, one=False):
    if not one:
        return os.path.join(directory, "track")
    return os.path.join(directory, "trackone")


def _get_tbt_path(directory):
    return os.path.join(directory, "ALLBPMs")


def _get_harmonic_path(directory, plane):
    return os.path.join(directory, "ALLBPMs_lin" + PLANE_SUFFIX[plane])


def _do_analysis(directory):
    print("Performing analysis...")
    tbt_path = _get_tbt_path(directory)
    print("    -> Running drive...")
    with silence():
        drive_runner.run_drive(tbt_path, RAMP2, RAMP3,
                               DQX, DQY, QX, QY,
                               stdout=open(os.devnull, "w"),
                               tune_window=TUNE_WINDOW)
    twiss_path = os.path.join(directory, "twiss.dat")
    # TODO: What should we do with error definition files?
    # err_def_path = _copy_error_def_file(directory)
    print("    -> Running GetLLM...")
    with silence():
        GetLLM.main(directory, tbt_path, twiss_path, bpmu="mm",)
    # errordefspath=err_def_path)


def _copy_error_def_file(directory):
    new_err_def_path = os.path.join(directory, "error_deff.txt")
    iotools.copy_item(ERR_DEF_PATH, new_err_def_path)
    return new_err_def_path


def _get_modifiers_file(optics, directory):
    modifiers_file_path = os.path.join(directory, "modifiers.madx")
    with open(modifiers_file_path, "w") as modifiers_file:
        modifiers_file.write(MODIFIERS[optics])
    return modifiers_file_path


def _comprare_results(directory):
    _print_results(directory)
    if os.path.isfile(_get_twiss_ac_path(directory)):
        _print_results(directory, free=False)


def _print_results(directory, free=True):
    if free:
        print("+++++++ Results for free files +++++++\n")
    else:
        print("+++++++ Results for AC dipole files +++++++\n")
    meas_tunex = _get_tune_data(directory, HOR, free=free)
    meas_tuney = _get_tune_data(directory, VER, free=free)
    model_qx, model_qy = QX, QY
    if not free:
        model_qx, model_qy = DQX, DQY
    _compare_tunes(meas_tunex, meas_tuney, model_qx, model_qy)
    betax_data = _get_beta_data(directory, HOR, free=free)
    betay_data = _get_beta_data(directory, VER, free=free)
    _compare_betas(betax_data, betay_data)
    phasex_data = _get_phase_data(directory, HOR, free=free)
    phasey_data = _get_phase_data(directory, VER, free=free)
    _compare_phases(phasex_data, phasey_data)
    print("++++++++++++++++++++++++++++++++++++++\n")


def _get_tune_data(directory, plane, free=True):
    har_data = metaclass.twiss(_get_harmonic_path(directory, plane))
    plane_index = {HOR: "1", VER: "2"}
    if not free:
        return (getattr(har_data, "Q" + plane_index[plane]),
                getattr(har_data, "Q" + plane_index[plane] + "RMS"))
    return (getattr(har_data, "NATQ" + plane_index[plane]),
            getattr(har_data, "NATQ" + plane_index[plane] + "RMS"))


def _get_beta_data(directory, plane, free=True):
    suffix = PLANE_SUFFIX[plane]
    getbeta = os.path.join(directory, "getbeta" + suffix + ".out")
    getbetafree = os.path.join(directory, "getbeta" + suffix + "_free.out")
    if not free:
        return metaclass.twiss(getbeta)
    return _get_twiss_for_one_of(getbetafree, getbeta)


def _get_phase_data(directory, plane, free=True):
    suffix = PLANE_SUFFIX[plane]
    getphase = os.path.join(directory,
                            "getphasetot" + suffix + ".out")
    getphasefree = os.path.join(directory,
                                "getphasetot" + suffix + "_free.out")
    if not free:
        return metaclass.twiss(getphase)
    return _get_twiss_for_one_of(getphasefree, getphase)


def _get_twiss_for_one_of(*paths):
    for path in paths:
        if os.path.isfile(path):
            return metaclass.twiss(path)
    raise IOError("None of the files exist:\n\t" + "\n\t".join(path))


def _compare_tunes(meas_tunex, meas_tuney, model_qx, model_qy):
    print("-> Tunes:")
    value_tune_x, rms_tune_x = meas_tunex
    value_tune_y, rms_tune_y = meas_tuney
    print("    Horizontal:")
    print("    -Measured tune:", value_tune_x, "+-", rms_tune_x)
    print("    -Design tune:", model_qx)
    print("    Vertical:")
    print("    -Measured tune:", value_tune_y, "+-", rms_tune_y)
    print("    -Design tune:", model_qy)
    print("")


def _compare_betas(betax, betay):
    print("-> Beta-beating:")
    x_beta_beat = ((betax.BETX - betax.BETXMDL) /
                   betax.BETXMDL)
    y_beta_beat = ((betay.BETY - betay.BETYMDL) /
                   betay.BETYMDL)
    print("    Horizontal:")
    print("    -RMS beating:", np.std(x_beta_beat))
    print("    -Peak beating:", x_beta_beat[np.argmax(np.abs(x_beta_beat))])
    print("    Vertical:")
    print("    -RMS beating:", np.std(y_beta_beat))
    print("    -Peak beating:", y_beta_beat[np.argmax(np.abs(y_beta_beat))])
    print("")


def _compare_phases(phasex, phasey):
    print("-> Phase:")
    x_phase_err = phasex.PHASEX - phasex.PHXMDL
    y_phase_err = phasey.PHASEY - phasey.PHYMDL
    print("    Horizontal:")
    print("    -RMS error:", np.std(x_phase_err))
    print("    -Peak error:", x_phase_err[np.argmax(np.abs(x_phase_err))])
    print("    Vertical:")
    print("    -RMS error:", np.std(y_phase_err))
    print("    -Peak error:", y_phase_err[np.argmax(np.abs(y_phase_err))])
    print("")


def _clean_up_files(ouput_dir):
    iotools.delete_item(ouput_dir)


if __name__ == "__main__":
    print_getllm_precision()