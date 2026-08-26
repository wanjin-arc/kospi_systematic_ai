import unittest
from datetime import date

import pandas as pd

from tools.collect_krx_kospi200_index import index_params, parse_index


class Kospi200IndexCollectorTests(unittest.TestCase):
    def test_index_params_use_1028(self):
        self.assertEqual(index_params(date(2004, 1, 2), date(2023, 12, 31)), {
            "strtDd": "20040102", "endDd": "20231231", "indIdx": "1", "indIdx2": "028"
        })

    def test_parse_english_export(self):
        raw = b"TRD_DD,OPNPRC_IDX,HGPRC_IDX,LWPRC_IDX,CLSPRC_IDX,ACC_TRDVOL,ACC_TRDVAL\n20230103,2200,2210,2190,2205,100,200000\n"
        result = parse_index(raw)
        self.assertEqual(result.loc[0, "index_code"], "1028")
        self.assertEqual(float(result.loc[0, "close"]), 2205.0)

    def test_parse_positional_export(self):
        raw = "가,나,다,라,마,바\n20230103,2200,2210,2190,2205,100\n".encode("utf-8")
        result = parse_index(raw)
        self.assertEqual(pd.Timestamp(result.loc[0, "date"]), pd.Timestamp("2023-01-03"))
        self.assertEqual(float(result.loc[0, "open"]), 2200.0)

