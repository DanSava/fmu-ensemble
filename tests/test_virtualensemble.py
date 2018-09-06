# -*- coding: utf-8 -*-
"""Testing fmu-ensemble."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
import pandas as pd
import pytest

from fmu import config
from fmu.ensemble import ScratchEnsemble

fmux = config.etc.Interaction()
logger = fmux.basiclogger(__name__)

if not fmux.testsetup():
    raise SystemExit()


def test_virtualensemble():

    if '__file__' in globals():
        # Easen up copying test code into interactive sessions
        testdir = os.path.dirname(os.path.abspath(__file__))
    else:
        testdir = os.path.abspath('.')

    reekensemble = ScratchEnsemble('reektest',
                                   testdir +
                                   '/data/testensemble-reek001/' +
                                   'realization-*/iter-0')
    reekensemble.from_smry(time_index='yearly', column_keys=['F*'])
    vens = reekensemble.to_virtual()

    # Check that we have data for 5 realizations
    assert len(vens['unsmry-yearly']['REAL'].unique()) == 5
    assert len(vens['parameters.txt']) == 5


    # Eclipse summary vector statistics for a given ensemble
    df_stats = reekensemble.get_smry_stats(column_keys=['FOPR', 'FGPR'],
                                           time_index='yearly')
    assert isinstance(df_stats, dict)
    assert len(df_stats.keys()) == 2
    assert isinstance(df_stats['FOPR'], pd.DataFrame)
    assert len(df_stats['FOPR'].index) == 4

    # Check webviz requirements for dataframe
    assert 'min' in df_stats['FOPR'].columns
    assert 'max' in df_stats['FOPR'].columns
    assert 'name' in df_stats['FOPR'].columns
    assert df_stats['FOPR']['name'].unique() == 'FOPR'
    assert 'index' in df_stats['FOPR'].columns  # This is DATE (!)
    assert 'mean' in df_stats['FOPR'].columns
    assert 'p10' in df_stats['FOPR'].columns
    assert 'p90' in df_stats['FOPR'].columns
    assert df_stats['FOPR']['min'].iloc[-1] < \
        df_stats['FOPR']['max'].iloc[-1]

    # Test virtrealization retrieval:
    vreal = vens.get_realization(2)
    assert vreal.keys() == vens.keys()

    # Test realization removal:
    vens.remove_realizations(3)
    assert len(vens.parameters['REAL'].unique()) == 4
    vens.remove_realizations(3)  # This will give warning
    assert len(vens.parameters['REAL'].unique()) == 4
    assert len(vens['unsmry-yearly']['REAL'].unique()) == 4

    # Test data removal:
    vens.remove_data('parameters.txt')
    assert 'parameters.txt' not in vens.keys()
    vens.remove_data('bogus')  # This should only give warning

    # Test data addition. It should(?) work also for earlier nonexisting
    vens.append('betterdata', pd.DataFrame({'REAL': [0, 1, 2, 3, 4, 5, 6, 80],
                                            'NPV': [1000, 2000, 1500,
                                                    2300, 6000, 3000,
                                                    800, 9]}))
    assert 'betterdata' in vens.keys()
    assert vens.get_realization(3)['betterdata']['NPV'] == 2300
    assert vens.get_realization(0)['betterdata']['NPV'] == 1000
    assert vens.get_realization(1)['betterdata']['NPV'] == 2000
    assert vens.get_realization(2)['betterdata']['NPV'] == 1500
    assert vens.get_realization(80)['betterdata']['NPV'] == 9

    with pytest.raises(ValueError):
        vens.get_realization(9999)
