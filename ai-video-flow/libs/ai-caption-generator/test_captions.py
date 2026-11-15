import tempfile
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import generate_captions as captions


def word(text, start, end):
    return dict(text=text, start=start, end=end)


class CaptionTests(unittest.TestCase):
    def group(self, words, **settings):
        return captions.group_captions(words, captions.validate_settings(settings))

    def test_word_and_character_limits(self):
        words = [word(text, i * .3, (i + 1) * .3) for i, text in enumerate(
            ['one', 'two', 'three', 'four', 'five', 'six'])]
        result = self.group(words, max_words=2, max_chars=8)
        self.assertEqual(' '.join(c['text'] for c in result), 'one two three four five six')
        self.assertTrue(all(len(c['text']) <= 8 for c in result))
        self.assertTrue(all(len(c['text'].split()) <= 2 for c in result))

    def test_pause_sentence_and_punctuation_removal(self):
        words = [word('Hello.', 0, .2), word('Next', .3, .5), word('scene', 1.5, 2)]
        result = self.group(words, remove_punctuation=True, uppercase=True)
        self.assertEqual([c['text'] for c in result], ['HELLO', 'NEXT', 'SCENE'])
        self.assertLessEqual(result[0]['end'], result[1]['start'])

    def test_long_word_and_slow_speech_prioritize_timing(self):
        result = self.group([word('extraordinarily', 0, 4), word('slow', 4.1, 4.3)],
                            max_chars=3, max_duration=1, min_duration=2)
        self.assertEqual(result[0]['text'], 'extraordinarily')
        self.assertEqual(result[0]['end'], 4000)
        self.assertEqual(result[1]['start'], 4100)

    def test_duration_and_single_words(self):
        words = [word('A', 0, .8), word('B', .9, 1.8), word('C', 1.9, 2.8)]
        self.assertEqual(len(self.group(words, max_words=1)), 3)
        self.assertEqual(len(self.group(words, max_duration=1)), 3)

    def test_minimum_does_not_overlap_and_offset_clamps(self):
        result = self.group([word('a', 0, .1), word('b', .15, .2), word('c', .3, .4)],
                            max_words=1, offset=-200)
        self.assertTrue(all(c['start'] >= 0 and c['end'] > c['start'] for c in result))
        self.assertTrue(all(a['end'] <= b['start'] for a, b in zip(result, result[1:])))

    def test_multiline_and_unicode(self):
        result = self.group([word('සුබ', 0, .2), word('උදෑසනක්!', .2, .4)],
                            max_lines=2, remove_punctuation=True)
        self.assertIn('සුබ', result[0]['text'])
        self.assertNotIn('!', result[0]['text'])
        self.assertLessEqual(len(result[0]['text'].splitlines()), 2)

    def test_timestamp_rounding_and_srt(self):
        self.assertEqual(captions.timestamp(3599999), '00:59:59,999')
        self.assertEqual(captions.timestamp(3600000), '01:00:00,000')
        self.assertEqual(captions.timestamp(-20), '00:00:00,000')
        text = captions.srt_text([dict(start=0, end=1234, text='Hello\nworld')])
        self.assertEqual(text, '1\n00:00:00,000 --> 00:00:01,234\nHello\nworld\n\n')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'captions.srt'
            path.write_text(text, encoding='utf-8')
            self.assertEqual(path.read_text(encoding='utf-8'), text)

    def test_cli_writes_utf8_srt_and_preserves_source(self):
        result = {'segments': [{'text': 'Hello world.', 'words': [
            dict(word='Hello', start=.2, end=.5), dict(word='world.', start=.5, end=1)]}]}
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'audio.wav'
            source.write_bytes(b'source must remain unchanged')
            output = Path(folder) / 'captions.srt'
            with patch.object(sys, 'argv', ['generate_captions.py', str(source),
                    '--output', str(output), '--uppercase', '--remove-punctuation']), \
                    patch.object(captions, 'get_transcription', return_value=result):
                captions.main()
            self.assertIn('HELLO WORLD', output.read_text(encoding='utf-8'))
            self.assertEqual(source.read_bytes(), b'source must remain unchanged')

    def test_overlap_normalization_and_missing_words(self):
        result = {'segments': [{'words': [dict(word='a', start=0, end=1),
                                           dict(word='b', start=.8, end=1.2)]}]}
        words = captions.timed_words(result)
        self.assertEqual(words[1]['start'], 1)
        with self.assertRaises(ValueError):
            captions.timed_words({'segments': [{'text': 'hello'}]})

    def test_cache_reuses_caption_changes_and_invalidates_input_model_language(self):
        result = {'segments': [{'text': 'hello', 'words': [dict(word='hello', start=0, end=1)]}]}
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'audio.wav'
            source.write_bytes(b'original')
            config = captions.validate_settings({})
            with patch.object(captions, 'transcribe', return_value=result) as transcribe:
                captions.get_transcription(source, config, cache_dir=Path(folder))
                captions.get_transcription(source, {**config, 'max_words': 1}, cache_dir=Path(folder))
                self.assertEqual(transcribe.call_count, 1)
                captions.get_transcription(source, config, force=True, cache_dir=Path(folder))
                source.write_bytes(b'changed')
                captions.get_transcription(source, config, cache_dir=Path(folder))
                captions.get_transcription(source, {**config, 'model': 'another-model'}, cache_dir=Path(folder))
                captions.get_transcription(source, {**config, 'language': 'si'}, cache_dir=Path(folder))
                self.assertEqual(transcribe.call_count, 5)

    def test_invalid_settings(self):
        for settings in ({'max_words': 0}, {'pause': -1}, {'max_lines': True},
                         {'offset': float('nan')}, {'uppercase': 'true'}, {'unknown': 2}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                captions.validate_settings(settings)


if __name__ == '__main__':
    unittest.main()
