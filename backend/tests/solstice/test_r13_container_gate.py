"""Container acceptance must exercise the candidate, without deployment rights."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github/workflows/ci.yml"


def _job():
    return yaml.safe_load(WORKFLOW.read_text())["jobs"]["docker-build"]


def test_container_gate_admits_main_and_same_repository_prs_only():
    assert _job()["if"] == (
        "github.ref == 'refs/heads/main' || "
        "(github.event_name == 'pull_request' && "
        "github.event.pull_request.head.repo.full_name == github.repository)"
    )
    assert "pull_request_target:" not in WORKFLOW.read_text()


def test_container_checkout_and_receipt_are_bound_to_candidate_head():
    job = _job()
    checkout = next(step for step in job["steps"] if step.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["ref"] == (
        "${{ github.event_name == 'pull_request' && github.event.pull_request.head.sha || github.sha }}"
    )
    receipt = next(step for step in job["steps"] if step.get("name") == "Verify container source")
    assert receipt["env"]["EXPECTED_SHA"] == checkout["with"]["ref"]
    assert 'test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"' in receipt["run"]
    assert "git rev-parse HEAD" in receipt["run"]


def test_container_job_is_read_only_and_cannot_mask_a_failed_gate():
    job = _job()
    assert job["permissions"] == {"contents": "read"}
    assert job["needs"] == ["backend-tests", "frontend-build"]
    assert not job.get("continue-on-error", False)
    for step in job["steps"]:
        assert not step.get("continue-on-error", False)
    text = yaml.safe_dump(job)
    for forbidden in ("secrets.", "docker push", "docker login", "azure/", "deploy@", "|| true"):
        assert forbidden not in text


def test_image_identity_and_network_isolated_runtime_smoke_are_required():
    job = _job()
    builds = [step for step in job["steps"] if step.get("name", "").startswith("Build ")]
    assert len(builds) == 2
    for step in builds:
        assert '--label "org.opencontainers.image.revision=$SOURCE_SHA"' in step["run"]
    smoke = next(step for step in job["steps"] if step.get("name") == "Test Docker images")
    assert smoke["run"].count("docker run --rm --network none") == 2
    assert "import server" in smoke["run"]
    assert "build/index.html" in smoke["run"]
    identity = next(step for step in job["steps"] if step.get("name") == "Record image identity")
    assert "docker image inspect" in identity["run"]
    assert ".Id" in identity["run"]
    assert "org.opencontainers.image.revision" in identity["run"]
