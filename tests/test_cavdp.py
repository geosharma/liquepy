import liquepy.motion.measures
from liquepy.settlement import methods

import numpy as np
from tests.conftest import TEST_DATA_DIR
import eqsig


def test_cavdp():

    fpath = TEST_DATA_DIR + "input_acc.his"
    acc_file = np.loadtxt(fpath, skiprows=4)
    acc = acc_file[:, 1]
    acc = acc
    time = acc_file[:, 0]
    dt = time[1] - time[0]
    asig = eqsig.AccSignal(acc, dt)

    cav_dp = liquepy.motion.measures.calc_cav_dp_series(asig)[-1]

    # 1.4598176 from liquepy 0.1.0  tested with several motion
    assert np.isclose(cav_dp, 1.4598176, rtol=0.001), cav_dp
    cav_dp = liquepy.motion.measures.calculate_cav_dp(asig.values, dt)
    assert np.isclose(cav_dp, 1.4598176, rtol=0.001), cav_dp


if __name__ == '__main__':
    test_cavdp()
