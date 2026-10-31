from datetime import datetime, timedelta
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from nspa.reference_data import ReferenceError, ReferenceRequest
from nspa.reference_data.models import ObservationPlan
from nspa.reference_data.formats import parse_ephemeris, write_gaia
from nspa.reference_data.providers import gaia, imcce
from nspa.reference_data.validation import validate_gaia_file
from reference_fixtures import gaia_response, imcce_response, imcce_fetch


class ProviderTests(unittest.TestCase):
    def form(self):
        return {'satellite':'7001','plnvar':'0','observatory':'286','initmom':'2020 11 13 12 00 00',
                'timestep':str(1/60),'ntimes':'3'}

    def test_official_ids_are_not_built_by_simple_addition(self):
        for code, expected in (('J14','5006'),('S32','6044'),('U24','7022'),('N3','8008')):
            self.assertEqual(imcce.TARGETS[code]['satellite'], expected)
        self.assertEqual(len(imcce.TARGETS), 185)

    def test_actual_model_is_checked_even_if_static_label_disagrees(self):
        raw, charset = imcce_response(self.form())
        rows, metadata = imcce.parse_response(raw, charset, 'U1', '286', pattern=r'Lainey.*2015')
        self.assertEqual(len(rows), 3)
        self.assertIn('Lainey', metadata['model'])
        raw, charset = imcce_response({**self.form(),'plnvar':'2'})
        with self.assertRaisesRegex(ReferenceError, 'GUST86'):
            imcce.parse_response(raw, charset, 'U1', '286', pattern=r'Lainey.*2015')

    def test_wrong_station_planet_model_and_target_are_rejected(self):
        for options, target in (({'station':'500'},'U1'), ({'planet':'DE431'},'U1'), ({},'U2')):
            raw, charset = imcce_response(self.form(), **options)
            with self.subTest(options=options,target=target), self.assertRaises(ReferenceError):
                imcce.parse_response(raw, charset, target, '286')

    def test_gaia_overflow_error_and_wrong_units_are_rejected(self):
        for options in ({'overflow':True}, {'bad_units':True}):
            with self.subTest(options=options), self.assertRaises(ReferenceError):
                gaia.parse_response(gaia_response(**options))
        with self.assertRaises(ReferenceError):gaia.parse_response(b'<html>Service error</html>')

    def test_nulls_are_counted_and_never_replaced_by_zero(self):
        stars, meta = gaia.parse_response(gaia_response())
        self.assertEqual(meta['total_rows'], 3)
        self.assertEqual(meta['usable_rows'], 2)
        self.assertEqual(meta['missing_required_fields'], 1)
        self.assertEqual([sid for sid, values in stars], [101,102])
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'gaia.DAT';write_gaia(path,stars)
            self.assertEqual(validate_gaia_file(path,stars),2)
            self.assertEqual(len(path.read_text().splitlines()[:60]),60)

    def test_nonfinite_and_out_of_order_ephemeris_rows_are_rejected(self):
        for text in ('2020 11 13 12 0 0 nan 13',
                     '2020 11 13 12 1 0 2 13\n2020 11 13 12 0 0 2 13'):
            with self.subTest(text=text), self.assertRaises(ReferenceError):parse_ephemeris(text)

    def test_large_time_grid_is_chunked_without_losing_boundary_points(self):
        start=datetime(2020,11,1)
        stop=start+timedelta(minutes=5000)
        plan=ObservationPlan((start,stop),start,stop,'202011',2)
        with tempfile.TemporaryDirectory() as tmp:
            request=ReferenceRequest((),Path(tmp),observatory='286')
            with patch('nspa.reference_data.providers.imcce.fetch',side_effect=imcce_fetch) as network:
                name,metadata=imcce.build(Path(tmp),'U1',plan,request,lambda _s:None)
            self.assertEqual(network.call_count,3)
            self.assertEqual(len(parse_ephemeris((Path(tmp)/name).read_text())),5001)
            self.assertFalse(metadata['visibility_filter'])

    def test_pinned_neptune_model_is_verified_instead_of_using_default(self):
        start=datetime(2020,11,1)
        plan=ObservationPlan((start,),start,start+timedelta(minutes=5),'202011',1)
        with tempfile.TemporaryDirectory() as tmp:
            request=ReferenceRequest((),Path(tmp),observatory='286')
            with patch('nspa.reference_data.providers.imcce.fetch',side_effect=imcce_fetch):
                _name,metadata=imcce.build(Path(tmp),'N1',plan,request,lambda _s:None,expected_model='Jacobson (2009)')
            self.assertEqual(metadata['model'],'Jacobson (2009)')
            self.assertEqual(len(metadata['failed_model_probes']),2)


if __name__ == '__main__': unittest.main()
