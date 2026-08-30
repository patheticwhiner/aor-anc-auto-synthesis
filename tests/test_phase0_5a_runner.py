from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from aor_anc.phase0_5a import run_phase0_5a


REPOSITORY = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPOSITORY / "configs" / "experiment.yaml"


def _external_sources_present() -> bool:
    with CONFIG_PATH.open("r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    historical = config["models"]["existing_imc_fxlms_baseline"]
    fair = config["models"]["fair_imc_fxlms_baseline"]
    return all(
        Path(path).is_file()
        for path in (
            historical["source_path"],
            historical["scenario_data_path"],
            fair["scenario_data_path"],
            config["models"]["nominal_secondary_path"]["source_path"],
            config["models"]["alternative_secondary_path"]["source_path"],
        )
    )


@pytest.mark.skipif(not _external_sources_present(), reason="external source artifact absent")
def test_phase0_5a_runner_preserves_history_and_emits_fair_metadata() -> None:
    summary = run_phase0_5a(CONFIG_PATH)
    assert summary["historical_source_reproduction"]["unchanged"]
    assert summary["historical_source_reproduction"]["golden_reproduction_passed"]
    assert len(summary["fair_results"]) == 4
    for result in summary["fair_results"]:
        assert result["implementation_mode"] == "corrected_information_fair"
        assert result["true_secondary_path_model_id"]
        assert result["internal_secondary_path_model_id"]
        assert result["plant_information_budget"]["id"]
        assert result["plant_information_budget_id"] == result[
            "plant_information_budget"
        ]["id"]
        assert result["evaluation_window"]["start_sample"] >= result[
            "adaptation_start_sample"
        ]
        assert result["evaluation_start_sample"] == result["evaluation_window"][
            "start_sample"
        ]
        assert result["sustain_duration_samples"] > 0
        assert result["prestart_residual_max_abs_error"] == 0.0
        assert result["reconstruction_identity_max_abs_error"] == 0.0
        assert result["time_to_10db_status"] in {"reached", "not_reached"}
        if result["time_to_10db_status"] == "not_reached":
            assert result["time_to_10db_seconds"] is None
