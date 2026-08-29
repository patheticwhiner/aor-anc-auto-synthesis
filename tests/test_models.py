from __future__ import annotations

import numpy as np
import pytest

from aor_anc.models import DiscreteTransferModel


def test_explicit_delay_is_preserved_in_impulse_response() -> None:
    model = DiscreteTransferModel(
        model_id="delay-test",
        numerator=np.asarray([0.0, 0.5, -0.2]),
        denominator=np.asarray([1.0]),
        sample_rate_hz=2000.0,
        input_delay_samples=1,
    )
    model.validate()
    np.testing.assert_allclose(model.impulse_response(5), [0.0, 0.5, -0.2, 0.0, 0.0])


def test_delay_mismatch_is_rejected() -> None:
    model = DiscreteTransferModel(
        model_id="bad-delay",
        numerator=np.asarray([0.0, 0.5]),
        denominator=np.asarray([1.0]),
        sample_rate_hz=2000.0,
        input_delay_samples=0,
    )
    with pytest.raises(ValueError, match="declared input delay"):
        model.validate()


def test_fir_poles_include_delay_states() -> None:
    model = DiscreteTransferModel(
        model_id="fir-test",
        numerator=np.asarray([0.0, 0.5, -0.2]),
        denominator=np.asarray([1.0]),
        sample_rate_hz=2000.0,
        input_delay_samples=1,
    )
    poles, zeros = model.poles_and_zeros()
    np.testing.assert_allclose(poles, [0.0, 0.0])
    np.testing.assert_allclose(zeros, [0.4])
