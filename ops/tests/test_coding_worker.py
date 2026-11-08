"""Real product lane boundaries; no model calls or active source edits."""
import importlib.util
import json
import os
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

    def test_checker_rejects_false_success_and_baseline_but_accepts_real_priority(self):
        root = self.workspace()
        with self.assertRaisesRegex(self.m.Refusal, 'checker rejected'):
            self.m.check_candidate(root)
        good = self.base.replace(b"    elif value['state'] != 'reviewed':\n        action = 'independent_review_required'",
            b"    elif value['state'] != 'reviewed':\n"
            b"        if 'mode_binding_unverified' in review['refusal_codes']:\n"
            b"            action = 'verify_liquid_paper_binding'\n"
            b"        elif 'provider_parked' in review['refusal_codes']:\n"
            b"            action = 'inspect_parked_provider'\n"
            b"        elif 'runtime_unverified' in review['refusal_codes']:\n"
            b"            action = 'verify_runtime_acceptance'\n"
            b"        else:\n            action = 'independent_review_required'")
        target = root / 'ops/operations_receipt.py'
        target.write_bytes(good)
        checked = self.m.check_candidate(root)
        self.assertTrue(checked['accepted'])
        self.assertEqual(checked['checks'], 260)
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
        value = {'schema': 'floww-coding-live-admission.v1', 'task_id': 'receipt-next-action-v1',
                 'implementation_commit': head, 'registry': 'floww-coding-registry.v1',
                 'base_sha': self.m.BASE_SHA, 'checker_sha256': self.m.CHECKER_SHA256,
                 'max_generations': 3, 'approved': True}
        admission = self.root / 'admission.json'
        admission.touch(mode=0o600)
        with patch.object(self.m, '__file__', str(module_path)):
            for field, wrong in [('implementation_commit', '0' * 40), ('base_sha', '0' * 40),
                                 ('checker_sha256', '0' * 64), ('max_generations', 4), ('approved', 1)]:
                admission.write_text(json.dumps(dict(value, **{field: wrong})))
                with self.subTest(field=field), self.assertRaises(self.m.Refusal):
                    self.m._admit_live(admission)
                self.assertFalse(Path(str(admission) + '.consumed').exists())
            admission.write_text(json.dumps(value)[:-1] + ', "approved":true}')
            with self.assertRaisesRegex(self.m.Refusal, 'duplicate'):
                self.m._admit_live(admission)
            admission.write_text(json.dumps(value))
            self.m._admit_live(admission)
            self.assertEqual(Path(str(admission) + '.consumed').read_text(), head + '\n')
            with self.assertRaisesRegex(self.m.Refusal, 'consumed'):
                self.m._admit_live(admission)

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
