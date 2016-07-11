import sys
import os
from PyQt4 import QtGui
from sbs_gui_main import SbSGuiMainController


def main(match_path=None):
    sys.path.append(os.path.abspath("../../"))
    app = QtGui.QApplication(sys.argv)
    main_controller = SbSGuiMainController()
    if match_path is None:
        lhc_mode, match_path = main_controller.ask_for_initial_config()
        if match_path is None:
            return
    main_controller.set_match_path(match_path)
    main_controller.set_lhc_mode(lhc_mode)
    main_controller.show_view()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()