"""Small synthetic FITS and official-response shapes; no observation downloads."""
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import numpy as np
from astropy.io import fits

from nspa.reference_data.formats import write_gaia
from nspa.reference_data.providers.imcce import TARGETS


def dataset(root):
    root = Path(root)
    inputs = root / 'disk with spaces/inputs'
    raw = inputs / 'images/U/2020/20201113/fits'
    raw.mkdir(parents=True)
    for index, date in enumerate(('2020-11-13T12:00:00', '2020-11-13T12:03:00')):
        header = fits.Header({'DATE-OBS': date, 'EXPTIME': 30})
        fits.writeto(raw / f'20201113-{index}.fit', np.zeros((2, 2)), header)
    catalogs = inputs / 'catalogs/U/2020'
    catalogs.mkdir(parents=True)
    ephemerides = []
    for target in ('U1', 'U2'):
        path = catalogs / f'EPH_{target}_202011.DAT'
        header = ['v5.test Planet: Uranus  (DE441)',
                  f'Satellite: {TARGETS[target]["name"]}  ( Lainey et al. (2015))',
                  'ephemerides valid', 'Observatory N: 286 - Yunnan Observatory',
                  'Timescale: UTC', 'Mean equator and equinox of J2000. ICRF.',
                  'Coordinates astrometric', 'Year M D H M S alpha (h) delta (deg)']
        lines = [f'2020 11 13 11 {minute} 0.00 2.3774750518 13.684154636' for minute in range(55, 60)]
        lines += [f'2020 11 13 12 {minute} 0.00 2.3774750518 13.684154636' for minute in range(12)]
        path.write_text('\n'.join(header + lines) + '\n')
        ephemerides.append(path)
    gaia = catalogs / 'GAIA3_US_202011.DAT'
    write_gaia(gaia, [(101, ('35.6', '13.6', '1.23', '-2.34', '12.345678')),
                      (102, ('35.7', '13.7', '2.34', '3.45', '13.456789'))])
    configs = inputs / 'configs'
    configs.mkdir()
    (configs / 'local.cfg').write_text('; locally edited configuration\n1superflag=1\n')
    return inputs, raw, tuple(ephemerides), gaia


def imcce_response(form, *, model=None, planet='DE441', station=None, truncate=False):
    target = next(code for code, value in TARGETS.items() if value['satellite'] == form['satellite'])
    if model is None and TARGETS[target]['system'] == 'N':
        model = {'0':'Emelyanov et al. (2015)', '1':'Jacobson (2009)', '2':'Zhang et al. (2014)'}.get(form.get('plnvar'),'unavailable')
    model = model or ('Lainey et al. (2015)' if form.get('plnvar') == '0' else 'GUST86')
    start = datetime.strptime(form['initmom'], '%Y %m %d %H %M %S')
    count = int(form['ntimes']) - int(truncate)
    parent = {'U':'Uranus','S':'Saturn','J':'Jupiter','N':'Neptune','M':'Mars','P':'Pluto'}[TARGETS[target]['system']]
    lines = [f'v5.test Planet: {parent}  ({planet})', f'Satellite: {TARGETS[target]["name"]}  ( {model})',
             'ephemerides valid', f'Observatory N: {station or form["observatory"]} - Yunnan Observatory',
             'Timescale: UTC', 'Mean equator and equinox of J2000. ICRF.',
             'Coordinates astrometric', 'Year M D H M S alpha (h) delta (deg)']
    for index in range(count):
        t = start + timedelta(hours=float(form['timestep']) * index)
        lines.append(f'{t:%Y %m %d %H %M} {t.second:.2f} 2.3774750518 13.684154636')
    return ('<html><pre>\n' + '\n'.join(lines) + '\n</pre></html>').encode(), 'utf-8'


def imcce_fetch(url, data=None, **kwargs):
    form = {key: value[0] for key, value in parse_qs(data.decode()).items()}
    return imcce_response(form)


def gaia_response(*, overflow=False, bad_units=False, nulls=True):
    units = ('', 'rad' if bad_units else 'deg', 'deg', 'mas.yr**-1', 'mas.yr**-1', 'mag')
    names = ('source_id', 'ra', 'dec', 'pmra', 'pmdec', 'phot_g_mean_mag')
    fields = ''.join(f'<FIELD name="{name}" datatype="double" unit="{unit}"/>' for name, unit in zip(names, units))
    rows = '<TR><TD>101</TD><TD>35.6</TD><TD>13.6</TD><TD>1.23</TD><TD>-2.34</TD><TD>12.345678</TD></TR>'
    rows += '<TR><TD>102</TD><TD>35.7</TD><TD>13.7</TD><TD>2.34</TD><TD>3.45</TD><TD>13.456789</TD></TR>'
    if nulls:
        rows += '<TR><TD>103</TD><TD>35.5</TD><TD>13.5</TD><TD></TD><TD></TD><TD>14</TD></TR>'
    status = '<INFO name="QUERY_STATUS" value="OVERFLOW"/>' if overflow else ''
    return (f'<VOTABLE><RESOURCE><INFO name="QUERY_STATUS" value="OK"/><TABLE>{fields}<DATA>'
            f'<TABLEDATA>{rows}</TABLEDATA></DATA></TABLE>{status}</RESOURCE></VOTABLE>').encode()


def gaia_fetch(url, data=None, **kwargs):
    query = parse_qs(urlsplit(url).query)
    assert query['FORMAT'] == ['votable_plain']
    assert 'gaiadr3.gaia_source' in query['QUERY'][0]
    return gaia_response(), 'utf-8'
