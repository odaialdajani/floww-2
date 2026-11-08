"""Real product lane boundaries; no model calls or active source edits."""
import importlib.util
import json
import os
import secrets
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class CodingWorkerTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / 'coding_worker.py'
        self.assertTrue(source.exists(), 'registered product worker is absent')
        sys.path.insert(0, str(source.parent))
        self.addCleanup(sys.path.pop, 0)
        spec = importlib.util.spec_from_file_location('coding_worker', source)
        self.m = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.m
        spec.loader.exec_module(self.m)
        self.tmp = tempfile.TemporaryDirectory(dir='/private/tmp')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.base = subprocess.check_output(['/usr/bin/git', '-C', str(source.parents[1]),
            'show', self.m.BASE_SHA + ':ops/operations_receipt.py'])

    def workspace(self):
        root = self.root / 'work'
        (root / 'ops').mkdir(parents=True)
        (root / 'ops/operations_receipt.py').write_bytes(self.base)
        return root

    def test_registry_refuses_arbitrary_tasks_and_contract_overrides(self):
        for task in ('shell', '../receipt', 'receipt-next-action-v2', ''):
            with self.subTest(task=task), self.assertRaises(self.m.Refusal):
                self.m.registered_task(task)
            with self.assertRaises(self.m.Refusal):
                self.m.run_task('/does/not/exist', self.root / 'unregistered', task_id=task)
            self.assertFalse((self.root / 'unregistered').exists())
        task = self.m.registered_task('receipt-next-action-v1')
        self.assertEqual(task.paths, ('ops/operations_receipt.py',))
        with self.assertRaises(TypeError):
            self.m.registered_task('receipt-next-action-v1', command='echo passed')

    def test_scope_gate_blocks_executable_payload_and_undeclared_entries(self):
        root = self.workspace()
        self.m.validate_candidate(root)
        target = root / 'ops/operations_receipt.py'
        for body in (self.base + b'\nraise SystemExit(0)\n',
                     self.base.replace(b"action = 'none'", b"action = __import__('os')._exit(0)"),
                     self.base.replace(b"action = 'none'", b"action = 'none'\n        print('passed')"),
                     self.base.replace(b"action = 'none'", b"CAPABILITIES['models'] = True")):
            with self.subTest(body=body[-60:]):
                target.write_bytes(body)
                with self.assertRaises(self.m.Refusal):
                    self.m.validate_candidate(root)
        target.write_bytes(self.base)
        for kind in ('test', 'symlink', 'fifo', 'hardlink'):
            rogue = root / 'rogue'
            if kind == 'test':
                rogue.write_text('fake checker passed')
            elif kind == 'symlink':
                rogue.symlink_to(target)
            elif kind == 'fifo':
                os.mkfifo(rogue)
            else:
                os.link(target, rogue)
            with self.subTest(kind=kind), self.assertRaises(self.m.Refusal):
                self.m.validate_candidate(root)
            rogue.unlink()

    def test_pure_priority_branch_is_allowed_without_changing_source(self):
        root = self.workspace()
        target = root / 'ops/operations_receipt.py'
        target.write_bytes(self.base.replace(b"    elif value['state'] != 'reviewed':",
            b"    elif 'mode_binding_unverified' in review['refusal_codes']:\n"
            b"        action = 'verify_simulated_mode_binding'\n    elif value['state'] != 'reviewed':"))
        result = self.m.validate_candidate(root)
        self.assertEqual(set(result), {'ops/operations_receipt.py'})
        self.assertNotEqual(result['ops/operations_receipt.py'], self.m.SOURCE_SHA256)

    def test_source_export_is_exact_and_does_not_import_host_context(self):
        source = Path(__file__).resolve().parents[2]
        root = self.root / 'export'
        # Export commits from the declared base object, never working-tree files.
        self.m.export_task(source, root)
        self.assertEqual((root / 'ops/operations_receipt.py').read_bytes(), self.base)
        self.assertFalse((root / '.env').exists())
        self.assertFalse((root / 'AGENTS.md').exists())
        self.assertFalse((root / '.git/hooks').exists())
        self.assertEqual(self.m.a.git(root, 'status', '--porcelain'), '')
        with self.assertRaises(self.m.Refusal):
            self.m.export_task(source, self.root / 'wrong', base_sha='0' * 40)

    def test_checker_identity_and_scope_are_checked_before_execution(self):
        root = self.workspace()
        fake = self.root / 'checker.py'
        fake.write_text("print('passed')")
        with self.assertRaisesRegex(self.m.Refusal, 'checker'):
            self.m.check_candidate(root, checker=fake)
        (root / 'ops/operations_receipt.py').write_bytes(self.base + b'\nraise SystemExit(0)\n')
        with self.assertRaises(self.m.Refusal):
            self.m.check_candidate(root)

    def good_candidate(self):
        return self.base.replace(b"    elif value['state'] != 'reviewed':\n        action = 'independent_review_required'",
            b"    elif value['state'] != 'reviewed':\n"
            b"        if 'mode_binding_unverified' in review['refusal_codes']:\n"
            b"            action = 'verify_liquid_paper_binding'\n"
            b"        elif 'provider_parked' in review['refusal_codes']:\n"
            b"            action = 'inspect_parked_provider'\n"
            b"        elif 'runtime_unverified' in review['refusal_codes']:\n"
            b"            action = 'verify_runtime_acceptance'\n"
            b"        else:\n            action = 'independent_review_required'")

    def test_checker_rejects_false_success_and_baseline_but_accepts_real_priority(self):
        root = self.workspace()
        with self.assertRaisesRegex(self.m.Refusal, 'checker rejected'):
            self.m.check_candidate(root)
        good = self.good_candidate()
        target = root / 'ops/operations_receipt.py'
        target.write_bytes(good)
        checked = self.m.check_candidate(root)
        self.assertTrue(checked['accepted'])
        self.assertEqual(checked['checks'], 772)
        target.write_bytes(good.replace(b"action = 'verify_liquid_paper_binding'", b"action = 'none'"))
        with self.assertRaisesRegex(self.m.Refusal, 'checker rejected'):
            self.m.check_candidate(root)

    def test_native_offline_positive_and_hostile_actual_edit_boundaries(self):
        source = Path(__file__).resolve().parents[2]
        for hostile in (False, True):
            output = self.root / ('hostile' if hostile else 'positive')
            result = self.m.run_task(source, output, hostile=hostile)
            with self.subTest(hostile=hostile):
                self.assertEqual(result['status'], 'blocked' if hostile else 'source_patch_proof_pass_review_pending')
                self.assertTrue(result['outside_sentinel_unchanged'])
                self.assertTrue(result['private_process_reaped'])
                self.assertEqual(result['changed_paths'], [] if hostile else ['ops/operations_receipt.py'])
                self.assertFalse(result['source_integration'])
                self.assertFalse(result['publication'])
                self.assertEqual(len(result['requests']), 2)
                self.assertTrue(all(x['upstream_max_tokens'] == 1024 for x in result['requests']))
                self.assertTrue(all(x['effect'] == 'deny' for x in result['native_denials']))
                self.assertEqual(json.loads((output / 'receipt.json').read_text())['status'], result['status'])

    def test_safe_reader_refuses_replaced_checker_links_and_oversized_files(self):
        path = self.root / 'trusted'
        path.write_bytes(b'x' * 65537)
        with self.assertRaises(self.m.Refusal):
            self.m._regular_bytes(path)
        path.unlink()
        path.symlink_to(self.m.CHECKER)
        with self.assertRaises(self.m.Refusal):
            self.m._regular_bytes(path)

    def test_live_requires_external_admission_and_never_reads_key_offline(self):
        with self.assertRaisesRegex(self.m.Refusal, 'admission'):
            self.m.run_task('/does/not/exist', self.root / 'out', live=True)
        self.assertFalse((self.root / 'out').exists())

    def test_live_admission_requires_exact_reviewed_identity_and_is_consumed_once(self):
        implementation = self.root / 'implementation'
        (implementation / 'ops').mkdir(parents=True)
        module_path = implementation / 'ops/coding_worker.py'
        module_path.write_text('private implementation identity fixture\n')
        for args in [('init', '-q', '--template='), ('config', 'user.name', 'Fixture'),
                     ('config', 'user.email', 'fixture@invalid'), ('add', '.'),
                     ('-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'clean identity')]:
            self.m.a.git(implementation, *args)
        head = self.m.a.git(implementation, 'rev-parse', 'HEAD').strip()
        value = {'schema': 'floww-coding-live-admission.v2', 'task_id': 'receipt-next-action-v1',
                 'implementation_commit': head, 'registry': 'floww-coding-registry.v1',
                 'base_sha': self.m.BASE_SHA, 'checker_sha256': self.m.CHECKER_SHA256,
                 'max_generations': 3, 'max_output_tokens': 1024, 'max_seconds': 90,
                 'max_input_bytes': 65536, 'max_output_bytes': 262144, 'max_steps': 3,
                 'admission_id': secrets.token_hex(16), 'issued_at': 1800000000,
                 'expires_at': 1800000600, 'approved': True}
        admission = self.root / 'admission.json'
        admission.touch(mode=0o600)
        ledger = self.root / 'coding-admissions'
        with patch.object(self.m, '__file__', str(module_path)), patch.object(self.m, 'ADMISSION_LEDGER', ledger), \
                patch.object(self.m.time, 'time', return_value=1800000001):
            for field, wrong in [('implementation_commit', '0' * 40), ('base_sha', '0' * 40),
                                 ('checker_sha256', '0' * 64), ('max_generations', 4), ('approved', 1),
                                 ('expires_at', 1799999999), ('issued_at', 1800000100),
                                 ('expires_at', 1800001000), ('max_output_tokens', 2048),
                                 ('schema', 'floww-coding-live-admission.v1'), ('issued_at', True),
                                 ('admission_id', '../escape'), ('max_input_bytes', 65537),
                                 ('max_output_bytes', 262145), ('max_steps', 4), ('max_seconds', 91)]:
                admission.write_text(json.dumps(dict(value, **{field: wrong})))
                with self.subTest(field=field), self.assertRaises(self.m.Refusal):
                    self.m._admit_live(admission)
                self.assertFalse((ledger / (value['admission_id'] + '.json')).exists())
            admission.write_text(json.dumps(value)[:-1] + ', "approved":true}')
            with self.assertRaisesRegex(self.m.Refusal, 'duplicate'):
                self.m._admit_live(admission)
            admission.write_text(json.dumps(value))
            self.m._admit_live(admission)
            self.assertEqual(json.loads((ledger / (value['admission_id'] + '.json')).read_text())['implementation_commit'], head)
            with self.assertRaisesRegex(self.m.Refusal, 'consumed'):
                self.m._admit_live(admission)
            copied = self.root / 'other-directory'
            copied.mkdir(mode=0o700)
            copied_file = copied / 'copied.json'
            copied_file.write_bytes(admission.read_bytes())
            copied_file.chmod(0o600)
            with self.assertRaisesRegex(self.m.Refusal, 'consumed'):
                self.m._admit_live(copied_file)
            # A fresh artifact directory cannot reset the consumed model budget.
            with patch.object(self.m.a, 'read_credential', side_effect=AssertionError('credential boundary reached')):
                with self.assertRaisesRegex(self.m.Refusal, 'consumed'):
                    self.m.run_task('/does/not/exist', self.root / 'another-artifact-directory',
                                    live=True, admission=copied_file, credential_path='/does/not/exist')
            self.assertFalse((self.root / 'another-artifact-directory').exists())
            admission.rename(self.root / 'renamed.json')
            with self.assertRaisesRegex(self.m.Refusal, 'consumed'):
                self.m._admit_live(self.root / 'renamed.json')

    def test_central_ledger_concurrent_and_crashed_owner_replays_refuse(self):
        ledger = self.root / 'central'
        value = {'admission_id': 'a' * 32, 'implementation_commit': 'b' * 40}
        source = Path(self.m.__file__).resolve()
        script = """import os,sys,json
sys.path.insert(0,sys.argv[1]);import coding_worker as w
from pathlib import Path
w.ADMISSION_LEDGER=Path(sys.argv[2])
if sys.argv[3]=='crash': w.os.fsync=lambda fd:os._exit(19)
try: w._consume_admission(json.loads(sys.argv[4]))
except w.Refusal: sys.exit(42)
"""
        command = ['/usr/bin/python3', '-I', '-B', '-c', script, str(source.parent), str(ledger),
                   'normal', json.dumps(value)]
        first = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        second = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        outputs = [first.communicate(timeout=4), second.communicate(timeout=4)]
        self.assertEqual(sorted([first.returncode, second.returncode]), [0, 42], outputs)
        crash_value = dict(value, admission_id='c' * 32)
        command[-2:] = ['crash', json.dumps(crash_value)]
        self.assertEqual(subprocess.run(command, capture_output=True, timeout=4).returncode, 19)
        command[-2] = 'normal'
        self.assertEqual(subprocess.run(command, capture_output=True, timeout=4).returncode, 42)

    def test_ledger_replacement_symlink_and_nonprivate_state_refuse(self):
        ledger = self.root / 'central'
        with patch.object(self.m, 'ADMISSION_LEDGER', ledger):
            self.m._consume_admission({'admission_id': 'a' * 32})
            ledger.rename(self.root / 'retired')
            ledger.mkdir(mode=0o700)
            with self.assertRaisesRegex(self.m.Refusal, 'identity'):
                self.m._consume_admission({'admission_id': 'a' * 32})
            ledger.rmdir()
            ledger.symlink_to(self.root / 'retired', target_is_directory=True)
            with self.assertRaises((self.m.Refusal, OSError)):
                self.m._consume_admission({'admission_id': 'd' * 32})
            ledger.unlink()
            (self.root / 'retired').rename(ledger)
            ledger.chmod(0o755)
            with self.assertRaisesRegex(self.m.Refusal, 'private'):
                self.m._consume_admission({'admission_id': 'd' * 32})

    def test_checker_rejects_unhealthy_and_paused_priority_mutation(self):
        root = self.workspace()
        good = self.good_candidate()
        target = root / 'ops/operations_receipt.py'
        target.write_bytes(good.replace(b"watchdog['state'] != 'healthy'", b"watchdog['state'] == 'unknown'"))
        with self.assertRaisesRegex(self.m.Refusal, 'checker rejected'):
            self.m.check_candidate(root)

    def test_ledger_marker_symlink_partial_marker_and_witness_damage_refuse(self):
        ledger = self.root / 'central'
        with patch.object(self.m, 'ADMISSION_LEDGER', ledger):
            self.m._consume_admission({'admission_id': 'a' * 32})
            marker = ledger / ('b' * 32 + '.json')
            marker.symlink_to(self.root / 'outside')
            with self.assertRaisesRegex(self.m.Refusal, 'consumed'):
                self.m._consume_admission({'admission_id': 'b' * 32})
            self.assertFalse((self.root / 'outside').exists())
            marker.unlink()
            marker.touch(mode=0o600)
            with self.assertRaisesRegex(self.m.Refusal, 'consumed'):
                self.m._consume_admission({'admission_id': 'b' * 32})
            witness = self.root / 'central.identity'
            witness.write_text('{}')
            with self.assertRaisesRegex(self.m.Refusal, 'identity'):
                self.m._consume_admission({'admission_id': 'c' * 32})

    def test_ledger_directory_replacement_during_consumption_refuses(self):
        ledger = self.root / 'central'
        with patch.object(self.m, 'ADMISSION_LEDGER', ledger):
            self.m._consume_admission({'admission_id': 'a' * 32})
            identity = ledger.stat().st_ino
            real_fsync = os.fsync

            def replace_on_directory_flush(fd):
                if os.fstat(fd).st_ino == identity:
                    ledger.rename(self.root / 'replaced')
                    ledger.mkdir(mode=0o700)
                real_fsync(fd)

            with patch.object(self.m.os, 'fsync', replace_on_directory_flush), self.assertRaisesRegex(self.m.Refusal, 'identity'):
                self.m._consume_admission({'admission_id': 'b' * 32})

    def test_model_policy_exports_only_declared_file_and_fixed_limits(self):
        root = self.workspace()
        contract = self.m.task_contract(root, 'a' * 40)
        config = self.m.a.native_config(contract, 'http://127.0.0.1:1/n/v1', 'nonce')
        allow = [r for r in config['permissions'] if r['effect'] == 'allow']
        self.assertEqual({r['resource'] for r in allow}, {'ops/operations_receipt.py'})
        self.assertEqual(config['mcp'], {'servers': {}})
        self.assertEqual(config['skills'], [])
        self.assertEqual(contract.max_generations, 3)
        self.assertEqual(contract.max_output_tokens, 1024)
        prompt = self.m.task_prompt(self.base)
        self.assertIn('mode_binding_unverified', prompt)
        self.assertIn(self.base.decode(), prompt)
        self.assertNotIn('NVIDIA_API_KEY', prompt)


if __name__ == '__main__':
    unittest.main()
