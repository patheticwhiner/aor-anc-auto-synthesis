from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from aor_anc.phase0 import run_phase0


REPOSITORY = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPOSITORY / "configs" / "experiment.yaml"


def _external_sources_present() -> bool:
    with CONFIG_PATH.open("r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    baseline = config["models"]["existing_imc_fxlms_baseline"]
    return Path(baseline["source_path"]).is_file() and Path(
        baseline["scenario_data_path"]
    ).is_file()


@pytest.mark.skipif(not _external_sources_present(), reason="external source artifact absent")
def test_source_baseline_matches_matlab_golden_metrics() -> None:
    summary = run_phase0(CONFIG_PATH)
    for result in summary["baseline_results"]:
        assert result["source_reproduction_passed"]
        assert result["golden_max_relative_error"] < 1e-10


@pytest.mark.skipif(not _external_sources_present(), reason="external source artifact absent")
def test_nonphysical_startup_cannot_be_reported_as_valid_convergence() -> None:
    summary = run_phase0(CONFIG_PATH)
    assert summary["convergence_metric_status"].startswith("invalid")
    assert all(
        not result["convergence_metric_valid"]
        for result in summary["baseline_results"]
    )
