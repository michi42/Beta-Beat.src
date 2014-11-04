import __init__  # @UnusedImport
import os
import SegmentBySegment
import sbs_beta_writer
import numpy as np
import math

from Utilities import tfs_file_writer


def write_phase(element_name, measured_hor_phase, measured_ver_phase, measured_hor_beta, measured_ver_beta,
                   input_model, propagated_models, save_path):

    file_phase_x, file_phase_y = _get_phase_tfs_files(element_name, save_path)

    model_propagation = propagated_models.propagation
    model_back_propagation = propagated_models.back_propagation
    model_cor = propagated_models.corrected
    model_back_cor = propagated_models.corrected_back_propagation

    bpms_list = SegmentBySegment.intersect([model_propagation, model_cor, model_back_propagation, model_back_cor, measured_hor_phase, input_model])

    _write_phase_for_plane(file_phase_x, element_name, "X", bpms_list, measured_hor_phase, measured_hor_beta, input_model, model_propagation, model_cor, model_back_propagation, model_back_cor)

    _write_phase_for_plane(file_phase_y, element_name, "Y", bpms_list, measured_ver_phase, measured_ver_beta, input_model, model_propagation, model_cor, model_back_propagation, model_back_cor)


def _write_phase_for_plane(file_phase, element_name, plane, bpms_list, measured_phase, measured_beta, input_model, model_propagation, model_cor, model_back_propagation, model_back_cor):
    first_bpm = bpms_list[0][1]
    last_bpm = bpms_list[-1][1]
    (beta_start, err_beta_start, alfa_start, err_alfa_start,
     beta_end, err_beta_end, alfa_end, err_alfa_end) = sbs_beta_writer._get_start_end_betas(bpms_list, measured_beta, plane)

    for bpm in bpms_list:
        bpm_s = bpm[0]
        bpm_name = bpm[1]

        model_s = input_model.S[input_model.indx[bpm_name]]

        meas_phase = (getattr(measured_phase, "PHASE" + plane)[measured_phase.indx[bpm_name]] -
                      getattr(measured_phase, "PHASE" + plane)[measured_phase.indx[first_bpm]]) % 1

        std_err_phase = getattr(measured_phase, "STDPH" + plane)[measured_phase.indx[bpm_name]]

        model_prop_phase = (getattr(model_propagation, "MU" + plane)[model_propagation.indx[bpm_name]] -
                            getattr(model_propagation, "MU" + plane)[model_propagation.indx[first_bpm]]) % 1

        model_cor_phase = (getattr(model_cor, "MU" + plane)[model_cor.indx[bpm_name]] -
                           getattr(model_cor, "MU" + plane)[model_cor.indx[first_bpm]]) % 1

        meas_phase_back = (getattr(measured_phase, "PHASE" + plane)[measured_phase.indx[bpm_name]] -
                           getattr(measured_phase, "PHASE" + plane)[measured_phase.indx[last_bpm]]) % 1

        model_back_propagation_phase = (getattr(model_back_propagation, "MU" + plane)[model_back_propagation.indx[last_bpm]] -
                                        getattr(model_back_propagation, "MU" + plane)[model_back_propagation.indx[bpm_name]]) % 1

        model_back_cor_phase = (getattr(model_back_cor, "MU" + plane)[model_back_cor.indx[last_bpm]] -
                                getattr(model_back_cor, "MU" + plane)[model_back_cor.indx[bpm_name]]) % 1

        prop_phase_difference = (meas_phase - model_prop_phase) % 1
        if prop_phase_difference > 0.5:
            prop_phase_difference = prop_phase_difference - 1

        back_prop_phase_difference = (meas_phase_back - model_back_propagation_phase) % 1
        if back_prop_phase_difference > 0.5:
            back_prop_phase_difference = back_prop_phase_difference - 1

        prop_cor_phase = -getattr(model_propagation, "MU" + plane)[model_propagation.indx[bpm_name]] + getattr(model_cor, "MU" + plane)[model_cor.indx[bpm_name]]
        back_cor_phase = -getattr(model_back_propagation, "MU" + plane)[model_back_propagation.indx[bpm_name]] + getattr(model_back_cor, "MU" + plane)[model_back_cor.indx[bpm_name]]

        prop_phase_error = _propagate_error_phase(err_beta_start, err_alfa_start, model_prop_phase, beta_start, alfa_start)
        cor_phase_error = _propagate_error_phase(err_beta_start, err_alfa_start, model_cor_phase, beta_start, alfa_start)

        back_phase_error = _propagate_error_phase(err_beta_end, err_alfa_end, model_back_propagation_phase, beta_end, alfa_end)
        back_cor_phase_error = _propagate_error_phase(err_beta_end, err_alfa_end, model_back_cor_phase, beta_end, alfa_end)

        file_phase.add_table_row([bpm_name, bpm_s, meas_phase, std_err_phase, prop_phase_difference, prop_phase_error, prop_cor_phase, cor_phase_error, back_prop_phase_difference, back_phase_error, back_cor_phase, back_cor_phase_error, model_s])

    file_phase.write_to_file()


def _get_phase_tfs_files(element_name, save_path):
    file_phase_x = tfs_file_writer.TfsFileWriter.open(os.path.join(save_path, "sbsphasext_" + element_name + ".out"))
    file_phase_y = tfs_file_writer.TfsFileWriter.open(os.path.join(save_path, "sbsphaseyt_" + element_name + ".out"))

    file_phase_x.add_column_names(["NAME", "S", "MEASPHASEX", "STDERRPHASEX", "PROPPHASEX", "ERRPROPPHASEX", "CORPHASEX", "ERRCORPHASEX", "BACKPHASEX", "ERRBACKPHASEX", "BACKCORPHASEX", "ERRBACKCORPHASEX", "MODEL_S"])
    file_phase_x.add_column_datatypes(["%bpm_s", "%le", "%le", "%le", "%le", "%le", "%le", "%le", "%le", "%le", "%le", "%le", "%le"])

    file_phase_y.add_column_names(["NAME", "S", "MEASPHASEY", "STDERRPHASEY", "PROPPHASEY", "ERRPROPPHASEY", "CORPHASEY", "ERRCORPHASEY", "BACKPHASEY", "ERRBACKPHASEY", "BACKCORPHASEY", "ERRBACKCORPHASEY", "MODEL_S"])
    file_phase_y.add_column_datatypes(["%bpm_s", "%le", "%le", "%le", "%le", "%le", "%le", "%le", "%le", "%le", "%le", "%le", "%le"])

    return file_phase_x, file_phase_y


def _propagate_error_phase(errb0, erra0, dphi, bet0, alf0):
    return math.sqrt((((1/2.*np.cos(4*np.pi*dphi)*alf0/bet0)-(1/2.*np.sin(4*np.pi*dphi)/bet0)-(1/2.*alf0/bet0))*errb0)**2+((-(1/2.*np.cos(4*np.pi*dphi))+(1/2.))*erra0)**2)/(2*np.pi)  # @IgnorePep8