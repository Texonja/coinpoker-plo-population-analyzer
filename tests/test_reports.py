from html.parser import HTMLParser
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from poker_population_analytics import fourbet, report_ui


class ReportParser(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.rows = []
        self.tags = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        values = dict(attrs)
        if tag == 'tr' and 'data-detail' in values:
            self.rows.append(json.loads(values['data-detail']))


class ReportTests(unittest.TestCase):
    def test_review_text_survives_as_text_in_table_and_detail(self):
        name = '<img src=x onerror="alert(1)"> & "quoted"'
        row = dict(spot_name=name, stake_label='PL50', pot_type='srp',
                   benchmark_metric='fold_pct', fold_pct=44.6,
                   benchmark_flag='audit_required', leak_note=name)
        html = report_ui.html_table([row], ['spot_id', 'stake_label', 'benchmark_flag'], selectable=True)
        parsed = ReportParser(html)
        self.assertNotIn('img', parsed.tags)
        self.assertEqual(parsed.rows[0]['name'], name)
        self.assertEqual(parsed.rows[0]['note'], name)
        self.assertEqual(parsed.rows[0]['status'], 'Audit required')
        self.assertEqual(parsed.rows[0]['context'], 'PL50 · SRP')

    def test_fourbet_coverage_does_not_double_count_position_subtotals(self):
        rows = [
            dict(stake_label='PL50', fourbettor_position='CO', known_cards=True, is_aaxx=True),
            dict(stake_label='PL50', fourbettor_position='BTN', known_cards=False, is_aaxx=False),
            dict(stake_label='PL25', fourbettor_position='SB', known_cards=True, is_aaxx=False),
        ]
        with TemporaryDirectory() as directory:
            out = Path(directory)
            report_ui.fourbet_report(out, fourbet.summarize(rows), [], [], 60, '')
            html = (out / 'fourbet_dashboard.html').read_text(encoding='utf-8')
        self.assertIn('2 of 3 qualifying four-bets have known cards', html)
        self.assertIn('<strong>50.0%</strong>', html)
        self.assertIn('<style>', html)
        self.assertIn('<script>', html)


if __name__ == '__main__':
    unittest.main()
