import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from qc_station.config import load_environment


class EnvironmentTests(unittest.TestCase):
    def test_file_settings_preserve_literal_secret_and_ignore_unrelated_settings(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            path = Path(folder)/'.env'
            path.write_text('QC_API_KEY="literal-${HOME}-#value"\nQC_TWIN_URL=http://server:8000\nUNRELATED=value\n', encoding='utf-8-sig')
            load_environment(path)
            self.assertEqual(os.environ['QC_API_KEY'], 'literal-${HOME}-#value')
            self.assertEqual(os.environ['QC_TWIN_URL'], 'http://server:8000')
            self.assertNotIn('UNRELATED', os.environ)

    def test_exported_settings_win_and_missing_file_is_optional(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'QC_API_KEY':'exported'}, clear=True):
            path = Path(folder)/'.env'
            load_environment(path)
            path.write_text('QC_API_KEY=file-value\nQC_TWIN_URL=http://server:8000\n')
            load_environment(path)
            self.assertEqual(os.environ['QC_API_KEY'], 'exported')
            self.assertEqual(os.environ['QC_TWIN_URL'], 'http://server:8000')
