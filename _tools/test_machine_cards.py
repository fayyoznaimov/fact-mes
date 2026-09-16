"""Текущая смена и показатели карточки без обращений к FACT."""
import logging
from pathlib import Path
import sys
import unittest
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '_app'))
import logs
with patch.object(logs, 'get', lambda name: logging.getLogger(name)):
    import dashboard


class CardsTest(unittest.TestCase):
    def test_current_night_shift_metrics_and_ticket_filter(self):
        row = dict.fromkeys(('operator','cause_ru','ticket','reason','reason_from','state_min',
                             'rpm_now','design','article','style_fact'), None)
        row.update(loom='D1',state='stop',panels=2)
        stat = dict(loom='D1',run_min=2,stop_min=1,picks=1000,pieces=3,stops_total=4,
                    weft_ct=2,warp_ct=1,top_ct=1,weft_stop_min=.5,warp_stop_min=.3,top_stop_min=.2)
        db = MagicMock()
        db.__enter__.return_value.execute.return_value.fetchall.return_value = [stat]
        board = dict(looms=[dict(loom='D1',cause='Manual',running=False,state_sec=120)],
                     andon={'warn_min':2},source='fact',stale=False,snapshot_age_sec=5)
        with patch.object(dashboard,'fact',return_value=db), \
             patch.object(dashboard,'rows',return_value={'rows':[row],'totals':{}}) as rows, \
             patch.object(dashboard,'loom_details',return_value={}), \
             patch.object(dashboard,'_picks_by_shift',return_value={}), \
             patch.object(dashboard.people,'fact_operators',return_value={}), \
             patch.object(dashboard.tickets,'current_shift',return_value='2026.09.15.C'), \
             patch.object(dashboard.tickets,'board',return_value=board):
            result = dashboard.cards()
            rows.assert_called_with('2026.09.15','C')
            card = result['rows'][0]
            self.assertEqual(card['rpm_avg'],500)
            self.assertEqual(card['towels_per_hour'],120)
            self.assertEqual(card['efficiency_pct'],66.7)
            self.assertEqual(card['stops_total'],4)
            self.assertEqual(card['weft_ct'],2)
            self.assertTrue(card['awaiting_ticket'])
            for values in ({'state_sec':119},{'ticket_category':'electrical'},
                           {'running':True},{'cause':'Warp'},{'cause':'Power_off'}):
                original=board['looms'][0].copy()
                board['looms'][0].update(values)
                self.assertFalse(dashboard.cards()['rows'][0]['awaiting_ticket'])
                board['looms'][0]=original
            board['stale']=True
            self.assertFalse(dashboard.cards()['rows'][0]['awaiting_ticket'])


if __name__=='__main__': unittest.main()
