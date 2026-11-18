import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('lesson', Path(__file__).with_name('lesson.py'))
lesson = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lesson)


def fixture():
    return {'expressions': [dict(category=cat, expression='test ' + cat, meaning='含义', register='语气',
        collocations='搭配', context='场合', comparison='辨析',
        examples=[dict(en='Original example one.', zh='原创例句一'), dict(en='Original example two.', zh='原创例句二')],
        source=dict(url='https://example.com/' + cat, title='Fixture only', quote='Short quote', locator='Paragraph 1', verification='Test fixture, not real research'),
        image=None, missing_image_reason='测试缺图说明') for cat in lesson.CATEGORIES]}


class LessonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent.parent / 'logs')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'templates').mkdir()
        source = Path(__file__).resolve().parent.parent / 'templates/lesson.html'
        (self.root / 'templates/lesson.html').write_bytes(source.read_bytes())

    def test_render_offline_and_escape(self):
        payload = fixture()
        payload['expressions'][0]['meaning'] = '<script>alert(1)</script>'
        doc = lesson.render(self.root, payload, [], 7, '2026-11-16')
        self.assertEqual(doc.count('<section class="expression">'), 3)
        self.assertEqual(doc.count('<li>'), 6)
        self.assertNotIn('<script>', doc)
        self.assertNotIn('$sections', doc)
        self.assertEqual(doc.count('缺图说明：'), 3)
        self.assertNotIn('常见误用', doc)
        payload['expressions'][0]['misuse'] = '旧版本误用字段'
        self.assertNotIn('旧版本误用字段', lesson.render(self.root, payload, [], 7, '2026-11-16'))

    def test_reject_duplicate_and_missing_category(self):
        with self.assertRaises(ValueError):
            lesson.validate(fixture(), ['TEST spoken'])
        payload = fixture()
        payload['expressions'][1]['category'] = 'spoken'
        with self.assertRaises(ValueError):
            lesson.validate(payload, [])

    def test_reject_incomplete_evidence_and_examples(self):
        payload = fixture()
        payload['expressions'][0]['source']['locator'] = ''
        with self.assertRaises(ValueError):
            lesson.validate(payload, [])
        payload = fixture()
        payload['expressions'][0]['examples'].pop()
        with self.assertRaises(ValueError):
            lesson.validate(payload, [])

    def test_real_image_embed_and_download_failure(self):
        payload = fixture()
        payload['expressions'][0]['image'] = dict(url='https://example.com/image.png', source_url='https://example.com/spoken', caption='Test image')
        data_uri = 'data:image/png;base64,iVBORw0KGgo='
        doc = lesson.render(self.root, payload, [], 7, '2026-11-16', fetch=lambda _: data_uri)
        self.assertIn('src="' + data_uri + '"', doc)
        self.assertNotIn('src="https://', doc)
        def fail(_):
            raise OSError('Test failure')
        doc = lesson.render(self.root, payload, [], 7, '2026-11-16', fetch=fail)
        self.assertIn('下载或格式校验失败', doc)
        self.assertNotIn('<img', doc)

    def test_legacy_index_and_idempotent_index_refresh(self):
        p = self.root / 'Day 002 · 2026-11-12 .html'
        p.write_text('<h2>fair enough</h2><h2>with respect to</h2><h2>at the expense of</h2>', encoding='utf-8')
        index = lesson.refresh_index(self.root)
        self.assertEqual(index['files'][0]['number'], 2)
        self.assertEqual(len(index['files'][0]['expressions']), 3)
        before = (self.root / 'data/expressions.json').stat().st_mtime_ns
        lesson.refresh_index(self.root)
        self.assertEqual((self.root / 'data/expressions.json').stat().st_mtime_ns, before)
        lesson.run(self.root, index_only=True)
        self.assertEqual(json.loads((self.root / 'data/state.json').read_text())['push']['status'], 'not_checked')

    def test_same_day_skips_model_and_records_push_failure(self):
        today = lesson.datetime.now(lesson.timezone(lesson.timedelta(hours=8))).date().isoformat()
        p = self.root / f'Day006_{today}.html'
        p.write_text('<h2>one</h2><h2>two</h2><h2>three</h2>', encoding='utf-8')
        original = p.read_bytes()
        with patch.object(lesson.subprocess, 'run', side_effect=OSError('push failed')) as invoke:
            with self.assertRaises(OSError):
                lesson.run(self.root)
            self.assertEqual(invoke.call_count, 1)
            self.assertEqual(invoke.call_args.args[0][0], 'powershell.exe')
        state = json.loads((self.root / 'data/state.json').read_text())
        self.assertEqual(state['generation'], 'complete')
        self.assertEqual(state['push']['status'], 'failed')
        self.assertEqual(original, p.read_bytes())
        with patch.object(lesson.subprocess, 'run') as invoke:
            lesson.run(self.root)
            self.assertEqual(invoke.call_count, 1)
        self.assertEqual(json.loads((self.root / 'data/state.json').read_text())['push']['status'], 'success')

    def test_generate_with_stub_model_and_atomic_publish(self):
        (self.root / 'automation').mkdir()
        (self.root / 'automation/prompt.txt').write_text('Fixture prompt')
        def invoke(command, **kwargs):
            if command[0] == 'fixture-codex.cmd':
                (self.root / 'logs/lesson-response.json.partial').write_text(json.dumps(fixture()), encoding='utf-8')
        with patch.object(lesson.shutil, 'which', return_value='fixture-codex.cmd'), patch.object(lesson.subprocess, 'run', side_effect=invoke) as calls:
            lesson.run(self.root)
            self.assertEqual(calls.call_count, 2)
        outputs = list(self.root.glob('Day*.html'))
        self.assertEqual(len(outputs), 1)
        self.assertTrue(outputs[0].name.startswith('Day001_'))
        self.assertEqual(outputs[0].read_text(encoding='utf-8').count('<section class="expression">'), 3)
        self.assertEqual(json.loads((self.root / 'data/state.json').read_text())['push']['status'], 'success')

    def test_duplicate_format_variants_and_same_lesson(self):
        for expression in ['PAVE THE WAY FOR', '“pave the way for”',
                           'pave-the-way-for', 'pave the way for（为……铺路）']:
            payload = fixture()
            payload['expressions'][0]['expression'] = expression
            with self.assertRaises(lesson.DuplicateExpressionError):
                lesson.validate(payload, ['pave the way for'])
        payload = fixture()
        payload['expressions'][0]['expression'] = "for what it’s worth"
        with self.assertRaises(lesson.DuplicateExpressionError):
            lesson.validate(payload, ["for what it's worth"])
        payload = fixture()
        payload['expressions'][1]['expression'] = 'TEST-spoken'
        with self.assertRaises(lesson.DuplicateExpressionError):
            lesson.validate(payload, [])

    def test_history_survives_removed_course(self):
        course = self.root / 'Day007_2026-11-17.html'
        course.write_text('<h2>pave the way for</h2><h2>two</h2><h2>three</h2>')
        lesson.refresh_index(self.root)
        course.unlink()
        lesson.refresh_index(self.root)
        history = lesson.load_json(self.root / 'data/used-expressions.json', [])
        self.assertIn('pave the way for', history)

    def test_duplicate_retry_and_exhaustion(self):
        (self.root / 'automation').mkdir()
        (self.root / 'automation/prompt.txt').write_text('Fixture prompt')
        for succeeds in [True, False]:
            attempts = []
            def invoke(command, **kwargs):
                attempts.append(kwargs['input'])
                payload = fixture()
                if not succeeds or len(attempts) == 1:
                    payload['expressions'][1]['expression'] = 'TEST-spoken'
                (self.root / 'logs/lesson-response.json.partial').write_text(json.dumps(payload))
            with patch.object(lesson.shutil, 'which', return_value='fixture-codex.cmd'), patch.object(lesson.subprocess, 'run', side_effect=invoke):
                if succeeds:
                    lesson.run(self.root, preview=True)
                    self.assertTrue((self.root / 'Preview.html').exists())
                    (self.root / 'Preview.html').unlink()
                    self.assertEqual(len(attempts), 2)
                    self.assertIn('retry_reason', attempts[1])
                else:
                    with self.assertRaises(lesson.DuplicateExpressionError):
                        lesson.run(self.root, preview=True)
                    self.assertEqual(len(attempts), 3)
                    self.assertFalse((self.root / 'Preview.html').exists())

    def test_backend_failure_preserves_reason_and_does_not_publish(self):
        (self.root / 'automation').mkdir()
        (self.root / 'automation/prompt.txt').write_text('Fixture prompt')
        def fail(command, **kwargs):
            kwargs['stdout'].write('HTTP 403: Unable to load site\nworkspace routing discovery failed')
            kwargs['stdout'].flush()
            raise lesson.subprocess.CalledProcessError(1, command)
        with patch.object(lesson.shutil, 'which', return_value='fixture-codex.cmd'), patch.object(lesson.subprocess, 'run', side_effect=fail) as calls:
            with self.assertRaises(lesson.GenerationFailed):
                lesson.run(self.root)
            self.assertEqual(calls.call_count, 1)
        state = json.loads((self.root / 'data/state.json').read_text())
        self.assertEqual(state['error_code'], 'backend_access_denied')
        self.assertEqual(state['push']['status'], 'not_started')
        self.assertTrue(Path(state['error_log']).exists())
        self.assertFalse(list(self.root.glob('Day*.html')))

    def test_reject_private_url_and_oversized_quote(self):
        for url in ['http://example.com/a', 'https://localhost/a', 'https://127.0.0.1/a']:
            with self.assertRaises(ValueError):
                lesson.https_url(url)
        payload = fixture()
        payload['expressions'][0]['source']['quote'] = 'word ' * 26
        with self.assertRaises(ValueError):
            lesson.validate(payload, [])


if __name__ == '__main__':
    unittest.main()
