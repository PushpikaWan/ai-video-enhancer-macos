import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import flow


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.config = {'cuts': [{'id': 'cut01', 'start': 0, 'duration': 4, 'text': 'Hello.'}]}

    def test_existing_example_is_valid(self):
        sample = flow.VOICE_GENERATOR.parent / 'scripts/narration.json'
        flow.validate_script(flow.read_json(sample))

    def test_workflow_scripts_exist_in_libs(self):
        self.assertTrue(flow.VOICE_GENERATOR.is_file())
        self.assertTrue(flow.VIDEO_ENHANCER.is_file())

    def test_rejects_invalid_scripts_before_generation(self):
        invalid = [[], {}, {'cuts': []}]
        for key, value in [('id', '../escape'), ('text', ''), ('start', True),
                           ('start', -1), ('start', float('nan')),
                           ('duration', 0), ('duration', float('inf'))]:
            config = copy.deepcopy(self.config)
            config['cuts'][0][key] = value
            invalid.append(config)
        invalid.append({**self.config, 'speed': False})
        invalid.append({**self.config, 'voice': []})
        invalid.append({'cuts': self.config['cuts'] * 2})
        invalid.append({'cuts': self.config['cuts'] + [
            {'id': 'cut02', 'start': 2, 'duration': 4, 'text': 'Overlap'}]})
        for config in invalid:
            with self.subTest(config=config), self.assertRaises(ValueError):
                flow.validate_script(config)

    def test_projects_persist_and_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            with patch.object(flow, 'STATE', parent / 'state/projects.json'), \
                    patch.object(flow, 'browse', return_value=parent), \
                    patch('builtins.input', return_value='My Video'):
                project = flow.new_project()
                self.assertTrue((project / 'frames').is_dir())
                self.assertEqual(json.loads(flow.STATE.read_text()), [str(project)])
                with patch('builtins.input', return_value='1'):
                    self.assertEqual(flow.existing_project(), project)
                with self.assertRaises(FileExistsError):
                    flow.new_project()

    def test_last_frame_command_handles_spaces(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / 'frames').mkdir()
            video = project / 'scene one.mp4'
            output = project / 'frames/scene one_lastframe.png'
            def run(command, **kwargs):
                self.assertEqual(command, ['ffmpeg', '-sseof', '-0.5', '-i', str(video),
                                          '-update', '1', '-y', str(output)])
                output.write_bytes(b'frame')
            with patch.object(flow, 'browse', return_value=video), \
                    patch.object(flow.subprocess, 'run', side_effect=run):
                flow.last_frame(project)

    def test_invalid_json_does_not_invoke_generator(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / 'bad.json'
            script.write_text('{"cuts": []}')
            with patch('builtins.input', side_effect=['{"cuts": []}', 'END']), \
                    patch.object(flow.subprocess, 'run') as run:
                with self.assertRaises(ValueError):
                    flow.paste_script(script)
                run.assert_not_called()
                self.assertEqual(script.read_text(), '{"cuts": []}')

    def test_paste_then_generate_saved_script(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / 'audio').mkdir()
            with patch('builtins.input', side_effect=[
                    *json.dumps(self.config, indent=2).splitlines(), 'END', '1']), \
                    patch.object(flow.subprocess, 'run') as run:
                flow.generate_audio(project)
                saved = project / 'scripts/narration.json'
                self.assertEqual(flow.read_json(saved), self.config)
                self.assertIn(str(saved), run.call_args.args[0])
                self.assertEqual(run.call_args.args[0][2], str(flow.VOICE_GENERATOR))

    def test_enhance_uses_relocated_script(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / 'enhanced').mkdir()
            video = project / 'video.mp4'
            with patch.object(flow, 'browse', return_value=video), \
                    patch.object(flow.subprocess, 'run') as run:
                flow.enhance(project)
                self.assertEqual(run.call_args.args[0], [
                    'bash', str(flow.VIDEO_ENHANCER), str(video),
                    str(project / 'enhanced/video-AI-2x.mp4')])

    def test_edit_existing_then_generate(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / 'audio').mkdir()
            saved = project / 'scripts/narration.json'
            flow.write_json(saved, self.config)
            edited = copy.deepcopy(self.config)
            edited['cuts'][0]['text'] = 'Updated narration.'
            with patch('builtins.input', side_effect=[
                    '1', '2', 'y', json.dumps(edited), 'END', '1']), \
                    patch.object(flow.subprocess, 'run') as run:
                flow.generate_audio(project)
                self.assertEqual(flow.read_json(saved), edited)
                run.assert_called_once()

    def test_cancel_paste_preserves_existing_script(self):
        with tempfile.TemporaryDirectory() as directory:
            saved = Path(directory) / 'narration.json'
            flow.write_json(saved, self.config)
            with patch('builtins.input', side_effect=['{', 'CANCEL']):
                self.assertFalse(flow.paste_script(saved))
            self.assertEqual(flow.read_json(saved), self.config)


if __name__ == '__main__':
    unittest.main()
