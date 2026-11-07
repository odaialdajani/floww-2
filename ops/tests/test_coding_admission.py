"""Boundary tests: admission, exclusive ownership, changed paths and request caps."""
import copy
import hashlib
import importlib.util
import json
import os
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch


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
        with self.m.WorkspaceLease(c, self.root / "lease") as lease:
            with self.assertRaisesRegex(self.m.Refusal, "owned"):
                with self.m.WorkspaceLease(c, self.root / "lease"):
                    self.fail("second owner admitted")
        with self.m.WorkspaceLease(c, self.root / "restart") as restarted:
            self.assertEqual(restarted.path, lease.path)

    def test_canonical_workspace_ownership_ignores_proposed_lock_path_across_processes(self):
        with self.m.WorkspaceLease(self.contract(), self.root / "lease-a"):
            script = """import importlib.util,json,sys
s=importlib.util.spec_from_file_location('coding_admission',sys.argv[1]);m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)
c=m.TaskContract(**json.loads(sys.argv[2]))
try:
    with m.WorkspaceLease(c,sys.argv[3]): pass
except m.Refusal:
    sys.exit(42)
"""
            result = subprocess.run(["/usr/bin/python3", "-I", "-B", "-c", script,
                str(Path(self.m.__file__)), json.dumps(self.m.asdict(self.contract())), str(self.root / "lease-b")],
                capture_output=True, timeout=3)
            self.assertEqual(result.returncode, 42, result.stderr.decode())

    def test_stale_or_replaced_lease_is_not_reclaimed_or_deleted(self):
        lease = self.m.WorkspaceLease(self.contract(), self.root / "lease-a")
        lease.path.write_text("stale owner")
        with self.assertRaises(self.m.Refusal):
            with self.m.WorkspaceLease(self.contract(), self.root / "lease-b"):
                self.fail("stale lease admitted")
        lease.path.unlink()
        with lease:
            lease.path.unlink()
            lease.path.write_text("replacement owner")
        self.assertEqual(lease.path.read_text(), "replacement owner")
        with self.assertRaises(self.m.Refusal):
            with self.m.WorkspaceLease(self.contract(), self.root / "lease-c"):
                self.fail("replacement ownership admitted")

    def test_crashed_owner_stays_blocked_after_process_exit(self):
        script = """import importlib.util,json,os,sys
s=importlib.util.spec_from_file_location('coding_admission',sys.argv[1]);m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)
lease=m.WorkspaceLease(m.TaskContract(**json.loads(sys.argv[2])),sys.argv[3]);lease.__enter__();os._exit(0)
"""
        result = subprocess.run(["/usr/bin/python3", "-I", "-B", "-c", script,
            str(Path(self.m.__file__)), json.dumps(self.m.asdict(self.contract())), str(self.root / "different")],
            capture_output=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        with self.assertRaisesRegex(self.m.Refusal, "owned or stale"):
            with self.m.WorkspaceLease(self.contract(), self.root / "new-path"):
                self.fail("crashed owner reclaimed")

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

    def test_nonregular_and_ignored_untracked_entries_are_refused_at_both_gates(self):
        before = self.m.snapshot(self.repo)
        for kind in ("fifo", "socket", "hardlink", "ignored-file"):
            path = self.repo / "rogue"
            with self.subTest(kind=kind):
                sock = None
                if kind == "fifo":
                    os.mkfifo(path, 0o600)
                elif kind == "socket":
                    sock = socket.socket(socket.AF_UNIX)
                    sock.bind(str(path))
                elif kind == "hardlink":
                    os.link(self.repo / "README.md", path)
                else:
                    (self.repo / ".git/info/exclude").write_text("rogue\n")
                    path.write_text("ignored by Git, still outside task")
                try:
                    for check in (lambda: self.m.validate_workspace(self.contract()),
                                  lambda: self.m.changed_paths(self.repo, before, self.contract())):
                        with self.assertRaises(self.m.Refusal):
                            check()
                finally:
                    if sock:
                        sock.close()
                    path.unlink()

    def test_new_empty_directory_is_outside_declared_fixture(self):
        before = self.m.snapshot(self.repo)
        (self.repo / "undeclared").mkdir()
        with self.assertRaises(self.m.Refusal):
            self.m.validate_workspace(self.contract())
        with self.assertRaises(self.m.Refusal):
            self.m.changed_paths(self.repo, before, self.contract())

    def test_file_symlink_swap_before_open_never_reads_outside(self):
        target = self.repo / "README.md"
        outside = self.root / "outside"
        outside.write_bytes(b"synthetic outside bytes")
        real_open = os.open
        swapped = False
        def swapping_open(path, flags, *args, **kwargs):
            nonlocal swapped
            if not swapped and Path(path).name == "README.md":
                target.unlink()
                target.symlink_to(outside)
                swapped = True
            return real_open(path, flags, *args, **kwargs)
        with patch.object(os, "open", swapping_open), self.assertRaises(self.m.Refusal):
            self.m.snapshot(self.repo)
        self.assertTrue(swapped)

    def test_parent_directory_swap_before_open_is_refused(self):
        nested = self.repo / "nested"
        nested.mkdir()
        (nested / "inside.txt").write_text("inside")
        outside = self.root / "outside-dir"
        outside.mkdir()
        (outside / "inside.txt").write_text("outside")
        real_open = os.open
        swapped = False
        def swapping_open(path, flags, *args, **kwargs):
            nonlocal swapped
            if not swapped and Path(path).name == "nested":
                nested.rename(self.root / "held-original")
                nested.symlink_to(outside, target_is_directory=True)
                swapped = True
            return real_open(path, flags, *args, **kwargs)
        with patch.object(os, "open", swapping_open), self.assertRaises(self.m.Refusal):
            self.m.snapshot(self.repo)
        self.assertTrue(swapped)

    def test_open_file_size_change_during_read_refuses(self):
        target = self.repo / "README.md"
        target_identity = target.stat().st_ino
        real_read = os.read
        changed = False
        def changing_read(fd, size):
            nonlocal changed
            if not changed and os.fstat(fd).st_ino == target_identity:
                target.write_text("changed while reading, different length")
                changed = True
            return real_read(fd, size)
        with patch.object(os, "read", changing_read), self.assertRaises(self.m.Refusal):
            self.m.snapshot(self.repo)
        self.assertTrue(changed)

    def test_file_replacement_link_or_same_size_mutation_during_read_refuses(self):
        target = self.repo / "README.md"
        real_read = os.read
        for change in ("replacement", "hardlink", "same-size"):
            with self.subTest(change=change):
                target.write_bytes(b"Fixture\n")
                before = target.stat()
                changed = False
                link = self.root / "outside-link"
                def changing_read(fd, size, change=change, before=before, link=link):
                    nonlocal changed
                    if not changed and os.fstat(fd).st_ino == before.st_ino:
                        changed = True
                        if change == "replacement":
                            target.unlink()
                            target.write_bytes(b"NEWFILE\n")
                        elif change == "hardlink":
                            os.link(target, link)
                        else:
                            target.write_bytes(b"NEWFILE\n")
                            os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))
                    return real_read(fd, size)
                try:
                    with patch.object(os, "read", changing_read), self.assertRaises(self.m.Refusal):
                        self.m.snapshot(self.repo)
                    self.assertTrue(changed)
                finally:
                    if link.exists():
                        link.unlink()

    def test_parent_replacement_after_open_refuses(self):
        real_read = os.read
        nested = self.repo / "nested"
        nested.mkdir()
        file = nested / "inside.txt"
        file.write_text("inside")
        identity = file.stat().st_ino
        outside = self.root / "outside-dir"
        outside.mkdir()
        (outside / "inside.txt").write_text("outside")
        changed = False
        def changing_parent(fd, size):
            nonlocal changed
            if not changed and os.fstat(fd).st_ino == identity:
                nested.rename(self.root / "held-original")
                nested.symlink_to(outside, target_is_directory=True)
                changed = True
            return real_read(fd, size)
        with patch.object(os, "read", changing_parent), self.assertRaises(self.m.Refusal):
            self.m.snapshot(self.repo)
        self.assertTrue(changed)

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
        example = Path(self.m.__file__).parent / "templates/coding-task.example.json"
        tools = json.loads(example.read_text())["native_envelope"]["tool_catalog"]
        body = dict(model="minimaxai/minimax-m3.1-flash", messages=[{"role": "user", "content": "fixture"}],
                    max_tokens=1024, stream=True, tools=tools)
        body.update(changes)
        return body

    def test_actual_request_cap_injected_and_only_file_tools_admitted(self):
        gate = self.m.RequestGate(self.contract())
        body = gate.admit(self.envelope(max_tokens=99999))
        self.assertEqual(body["max_tokens"], 1024)
        self.assertEqual(gate.receipts[0]["tools"], ["edit", "read", "write"])
        self.assertEqual(gate.receipts[0]["native_max_tokens"], 99999)
        self.assertEqual(gate.receipts[0]["upstream_max_tokens"], 1024)
        for name in ("execute", "shell", "webfetch", "mcp_x", "subagent", "broker_order"):
            with self.subTest(name=name), self.assertRaises(self.m.Refusal):
                self.m.RequestGate(self.contract()).admit(self.envelope(
                    tools=[{"type": "function", "function": {"name": name}}]))

    def test_complete_catalog_and_every_schema_field_are_pinned(self):
        catalog = self.envelope()["tools"]
        digest = hashlib.sha256(json.dumps(catalog, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(digest, "67e1bb437fde5c8fc87349ab0e9862442bd66849de8f8a5c33c7404843fc32d2")
        mutants = [[], catalog[:1], catalog + [catalog[0]], list(reversed(catalog))]
        for field, value in (("required", ["path"]), ("additionalProperties", True),
                             ("properties", {"command": {"type": "string"}}), ("type", "string")):
            altered = copy.deepcopy(catalog)
            altered[0]["function"]["parameters"][field] = value
            mutants.append(altered)
        altered = copy.deepcopy(catalog)
        altered[0]["function"]["parameters"]["properties"]["path"]["type"] = "integer"
        mutants.append(altered)
        altered = copy.deepcopy(catalog)
        altered[0]["function"]["extra"] = "unexpected"
        mutants.append(altered)
        for tools in mutants:
            with self.subTest(tools=tools), self.assertRaises(self.m.Refusal):
                self.m.RequestGate(self.contract()).admit(self.envelope(tools=tools))
        missing = self.envelope()
        del missing["tools"]
        with self.assertRaises(self.m.Refusal):
            self.m.RequestGate(self.contract()).admit(missing)

    def test_command_shaped_permitted_tool_never_reaches_transport(self):
        calls = []
        def transport(*args):
            calls.append(args)
            return 200, "application/json", b'{}'
        tools = self.envelope()["tools"]
        tools[0]["function"]["parameters"]["properties"] = {"command": {"type": "string"}}
        with self.m.Gateway(self.m.RequestGate(self.contract()), None, transport) as gateway:
            req = urllib.request.Request(gateway.base_url + "/chat/completions",
                data=json.dumps(self.envelope(tools=tools)).encode(),
                headers={"Authorization": "Bearer " + gateway.nonce, "Content-Type": "application/json"})
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(req, timeout=2)
        self.assertEqual(calls, [])

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

    def test_duplicate_security_headers_in_either_order_never_reach_transport(self):
        for header in ("Host", "Origin", "Authorization"):
            for reverse in (False, True):
                for identical in (False, True):
                    with self.subTest(header=header, reverse=reverse, identical=identical):
                        calls = []
                        def transport(*args, calls=calls):
                            calls.append(args)
                            return 200, "application/json", b'{}'
                        with self.m.Gateway(self.m.RequestGate(self.contract()), None, transport) as gateway:
                            values = {"Host": "127.0.0.1:" + str(gateway.server.server_port),
                                      "Origin": gateway.origin, "Authorization": "Bearer " + gateway.nonce}
                            pair = [values[header], values[header] if identical else "evil.invalid"]
                            if reverse:
                                pair.reverse()
                            lines = ["POST /" + gateway.nonce + "/v1/chat/completions HTTP/1.1"]
                            for name, value in values.items():
                                lines.extend(name + ": " + v for v in (pair if name == header else [value]))
                            data = json.dumps(self.envelope()).encode()
                            lines += ["Content-Length: " + str(len(data)), "Connection: close", "", ""]
                            with socket.create_connection(("127.0.0.1", gateway.server.server_port), timeout=2) as conn:
                                conn.sendall("\r\n".join(lines).encode() + data)
                                status = conn.recv(4096).split(b"\r\n", 1)[0]
                            self.assertIn(b"400", status)
                        self.assertEqual(calls, [])

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
