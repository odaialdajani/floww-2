"""Boundary tests: admission, exclusive ownership, changed paths and request caps."""
import importlib.util
import json
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path


class CodingAdmissionTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / "coding_admission.py"
        if not source.exists():
            self.fail("coding admission implementation is absent")
        spec = importlib.util.spec_from_file_location("coding_admission", source)
        import sys
        self.m = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.m
        spec.loader.exec_module(self.m)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@invalid")
        (self.repo / "arithmetic.py").write_text("def add(a, b):\n    return a - b\n")
        (self.repo / "README.md").write_text("Fixture\n")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture baseline")
        self.sha = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return subprocess.check_output(["/usr/bin/git", "-C", str(self.repo), *args], text=True)

    def contract(self, **changes):
        data = dict(task_id="fixture-1", base_sha=self.sha, workspace=str(self.repo),
                    allowed_paths=("arithmetic.py", "README.md"),
                    acceptance="pure-add-v1", max_generations=3, max_output_tokens=1024,
                    max_seconds=90, max_input_bytes=65536, max_output_bytes=262144,
                    max_steps=3, corrections=0)
        data.update(changes)
        return self.m.TaskContract(**data)

    def test_clean_exact_head_admitted_and_lease_blocks_second_owner(self):
        c = self.contract()
        with self.m.WorkspaceLease(c, self.root / "lease"):
            with self.assertRaisesRegex(self.m.Refusal, "owned"):
                with self.m.WorkspaceLease(c, self.root / "lease"):
                    self.fail("second owner admitted")
        self.assertFalse((self.root / "lease").exists())

    def test_dirty_workspace_refused(self):
        (self.repo / "README.md").write_text("dirty")
        with self.assertRaisesRegex(self.m.Refusal, "dirty"):
            self.m.validate_workspace(self.contract())

    def test_wrong_head_refused(self):
        with self.assertRaisesRegex(self.m.Refusal, "head"):
            self.m.validate_workspace(self.contract(base_sha="0" * 40))

    def test_unbounded_or_wrong_contract_refused(self):
        for changes in ({"max_generations": 4}, {"max_seconds": 91},
                        {"max_output_tokens": 1025}, {"max_steps": 4},
                        {"max_generations": True}, {"corrections": 4},
                        {"base_sha": "HEAD"}, {"acceptance": "shell command"}):
            with self.subTest(changes=changes), self.assertRaises(self.m.Refusal):
                self.contract(**changes).validate()

    def test_unsafe_paths_and_symlinks_refused(self):
        for path in ("../escape", "/tmp/escape", ".git/config", ".env", "a/*", "a/../b"):
            with self.subTest(path=path), self.assertRaises(self.m.Refusal):
                self.contract(allowed_paths=(path,)).validate()
        (self.repo / "README.md").unlink()
        (self.repo / "README.md").symlink_to(self.root / "outside")
        with self.assertRaises(self.m.Refusal):
            self.m.snapshot(self.repo)

    def test_changed_path_gate_includes_untracked_and_deleted(self):
        before = self.m.snapshot(self.repo)
        (self.repo / "arithmetic.py").write_text("changed")
        self.assertEqual(self.m.changed_paths(self.repo, before, self.contract()), ["arithmetic.py"])
        (self.repo / "unexpected").write_text("outside scope")
        with self.assertRaisesRegex(self.m.Refusal, "scope"):
            self.m.changed_paths(self.repo, before, self.contract())

    def test_pure_checker_rejects_wrong_function_and_executable_payload(self):
        with self.assertRaises(self.m.Refusal):
            self.m.check_pure_add(self.repo)
        (self.repo / "arithmetic.py").write_text("def add(a, b):\n    return a + b\n")
        self.assertEqual(self.m.check_pure_add(self.repo)["cases"], 6)
        (self.repo / "arithmetic.py").write_text("import os\ndef add(a, b):\n    return a + b\n")
        with self.assertRaises(self.m.Refusal):
            self.m.check_pure_add(self.repo)
        (self.repo / "arithmetic.py").write_text("def add(a, b) -> dangerous():\n    return a + b\n")
        with self.assertRaises(self.m.Refusal):
            self.m.check_pure_add(self.repo)

    def envelope(self, **changes):
        body = dict(model="minimaxai/minimax-m3.1-flash", messages=[{"role": "user", "content": "fixture"}],
                    max_tokens=1024, stream=True,
                    tools=[{"type": "function", "function": {"name": "edit", "parameters": {"type": "object"}}}])
        body.update(changes)
        return body

    def test_actual_request_cap_injected_and_only_file_tools_admitted(self):
        gate = self.m.RequestGate(self.contract())
        body = gate.admit(self.envelope(max_tokens=99999))
        self.assertEqual(body["max_tokens"], 1024)
        self.assertEqual(gate.receipts[0]["tools"], ["edit"])
        self.assertEqual(gate.receipts[0]["native_max_tokens"], 99999)
        self.assertEqual(gate.receipts[0]["upstream_max_tokens"], 1024)
        for name in ("execute", "shell", "webfetch", "mcp_x", "subagent", "broker_order"):
            with self.subTest(name=name), self.assertRaises(self.m.Refusal):
                self.m.RequestGate(self.contract()).admit(self.envelope(
                    tools=[{"type": "function", "function": {"name": name}}]))

    def test_wrong_model_redirect_body_and_unknown_fields_refused(self):
        for changes in ({"model": "paid/fallback"}, {"url": "https://evil.invalid"},
                        {"messages": []}, {"messages": "wrong"}, {"n": 2}):
            with self.subTest(changes=changes), self.assertRaises(self.m.Refusal):
                self.m.RequestGate(self.contract()).admit(self.envelope(**changes))

    def test_duplicate_generation_and_after_failure_are_refused(self):
        gate = self.m.RequestGate(self.contract())
        gate.admit(self.envelope())
        with self.assertRaisesRegex(self.m.Refusal, "duplicate"):
            gate.admit(self.envelope())
        gate = self.m.RequestGate(self.contract())
        gate.stop("upstream_failure")
        with self.assertRaisesRegex(self.m.Refusal, "stopped"):
            gate.admit(self.envelope())

    def test_total_generation_deadline_and_bytes_are_enforced(self):
        gate = self.m.RequestGate(self.contract(), clock=lambda: 0)
        for i in range(3):
            gate.admit(self.envelope(messages=[{"role": "user", "content": str(i)}]))
        with self.assertRaisesRegex(self.m.Refusal, "generation"):
            gate.admit(self.envelope(messages=[{"role": "user", "content": "four"}]))
        gate = self.m.RequestGate(self.contract(), clock=lambda: 100)
        gate.deadline = 99
        with self.assertRaisesRegex(self.m.Refusal, "deadline"):
            gate.admit(self.envelope())
        gate = self.m.RequestGate(self.contract())
        with self.assertRaisesRegex(self.m.Refusal, "input"):
            gate.admit(self.envelope(messages=[{"role": "user", "content": "x" * 70000}]))
        with self.assertRaisesRegex(self.m.Refusal, "output"):
            gate.record_output(262145)

    def test_private_config_has_exact_permissions_and_no_shell(self):
        config = self.m.native_config(self.contract(), "http://127.0.0.1:4567/nonce/v1", "nonce")
        self.assertEqual(config["mcp"], {"servers": {}})
        self.assertEqual(config["plugins"], ["-opencode.tools"])
        self.assertEqual(config["agents"]["floww_coding"]["steps"], 3)
        allows = [r for r in config["permissions"] if r["effect"] == "allow"]
        self.assertEqual({r["action"] for r in allows}, {"read", "edit"})
        self.assertTrue(all(r["resource"] in ("arithmetic.py", "README.md")
                            for r in allows))

    def test_gateway_enforces_nonce_origin_path_and_uses_fixed_transport(self):
        calls = []
        def transport(body, credential, timeout):
            calls.append((body, credential, timeout))
            return 200, "application/json", b'{}'
        gate = self.m.RequestGate(self.contract())
        with self.m.Gateway(gate, "synthetic-key", transport) as gateway:
            req = urllib.request.Request(gateway.base_url + "/chat/completions",
                data=json.dumps(self.envelope()).encode(), headers={"Authorization": "Bearer " + gateway.nonce,
                                                                  "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=2) as response:
                self.assertEqual(response.status, 200)
            self.assertEqual(calls[0][0]["max_tokens"], 1024)
            self.assertEqual(calls[0][1], "synthetic-key")
            req = urllib.request.Request(gateway.origin + "/arbitrary", data=b'{}')
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(req, timeout=2)
            self.assertEqual(len(calls), 1)
            self.assertTrue(gate.stopped)

    def test_supervisor_kills_group_on_deadline_and_output_cap(self):
        process = subprocess.Popen(["/usr/bin/python3", "-c", "import time;time.sleep(5)"],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        supervisor = self.m.ProcessSupervisor(process, time.monotonic() + .15, 1024)
        self.addCleanup(supervisor.close)
        supervisor.start()
        supervisor.thread.join(timeout=3)
        self.assertIsNotNone(process.poll())
        self.assertEqual(supervisor.reason, "deadline")
        supervisor.close()
        process = subprocess.Popen(["/usr/bin/python3", "-c", "print('x'*4096,flush=True);import time;time.sleep(5)"],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        supervisor = self.m.ProcessSupervisor(process, time.monotonic() + 4, 1024)
        self.addCleanup(supervisor.close)
        supervisor.start()
        supervisor.thread.join(timeout=3)
        self.assertIsNotNone(process.poll())
        self.assertEqual(supervisor.reason, "process_output_cap")
        supervisor.close()


if __name__ == "__main__":
    unittest.main()
