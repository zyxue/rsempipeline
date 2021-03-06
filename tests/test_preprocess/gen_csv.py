import os
import shutil
import unittest
import tempfile

import mock
from testfixtures import log_capture
# https://pythonhosted.org/testfixtures/logging.html
# LogCapture and log_capture are used in different ways to achieve the same
# results
from bs4 import BeautifulSoup

from rsempipeline.preprocess import rp_prep, gen_csv
from rsempipeline.conf.settings import (HTML_OUTDIR_BASENAME,
                                        SPECIES_CSV_BASENAME,
                                        NO_SPECIES_CSV_BASENAME)


class GenCsvTestCase(unittest.TestCase):
    def setUp(self):
        """setUp and tearDown are run for teach test"""
        self.input_csv = os.path.join(os.path.dirname(__file__), '___valid_input.csv')
        with open(self.input_csv, 'wb') as opf1:
            opf1.write(
"""
GSE59813,GSM1446812;
GSE61491,GSM1506106; GSM1506107;
""")
        parser = rp_prep.get_parser()
        self.temp_outdir = tempfile.mkdtemp() # mkdtemp returns abspath
        self.options1 = parser.parse_args(['gen-csv', '-f', self.input_csv])
        self.options2 = parser.parse_args(['gen-csv', '-f', self.input_csv,
                                           '--outdir', self.temp_outdir])
        self.gse = 'GSE38003'
        self.gsm = 'GSM931711'
        
    def tearDown(self):
        os.remove(self.input_csv)
        shutil.rmtree(self.temp_outdir)

    def test_gen_outdir_as_dirname_of_input_csv(self):
        self.assertEqual(os.path.dirname(__file__),
                         # since __file__ contains absolute path
                         os.path.abspath(gen_csv.gen_outdir(self.options1)))

    def test_gen_outdir_as_temp_outdir(self):
        self.assertEqual(self.temp_outdir,
                         os.path.abspath(gen_csv.gen_outdir(self.options2)))

    @mock.patch('rsempipeline.preprocess.gen_csv.mkdir')
    def test_gen_outdir_without_specified_outdir(self, mock_mkdir):
        p = rp_prep.get_parser()
        options = p.parse_args(['gen-csv', '-f', 'any_dir/input.csv'])
        self.assertEqual('any_dir', gen_csv.gen_outdir(options))
        self.assertFalse(mock_mkdir.called, "mkdir shouldn't have been called with -f is specified")

    @mock.patch('rsempipeline.preprocess.gen_csv.mkdir')
    def test_gen_outdir_with_specified_outdir(self, mock_mkdir):
        p = rp_prep.get_parser()
        options = p.parse_args(['gen-csv', '-f', 'any_dir/input.csv', '--outdir', 'specified_outdir'])
        self.assertEqual('specified_outdir', gen_csv.gen_outdir(options))        
        mock_mkdir.called_once_with('specified_outdir')


    def test_gen_html_outdir(self):
        d = os.path.join(self.temp_outdir, HTML_OUTDIR_BASENAME)
        self.assertEqual(d, gen_csv.gen_html_outdir(self.temp_outdir))
        self.assertTrue(os.path.exists(d))

    def test_gen_gse_dir(self):
        html_dir = gen_csv.gen_html_outdir(self.temp_outdir)
        d = os.path.join(html_dir, self.gse)
        self.assertEqual(d, gen_csv.gen_gse_dir(self.temp_outdir, self.gse))
        self.assertTrue(os.path.exists(d))

    @log_capture()
    def test_gen_gsm_html(self, L):
        html = gen_csv.gen_gsm_html(self.temp_outdir, self.gse, self.gsm)
        self.assertTrue(os.path.exists(html))
        with open(html) as inf:
            self.assertIn(self.gse, inf.read())
        L.check(('rsempipeline.preprocess.gen_csv', 'INFO',
                 'downloading {0}'.format(html)))

    @log_capture()
    def test_gen_gsm_html_with_already_existed_html(self, L):
        gse_dir = gen_csv.gen_gse_dir(self.temp_outdir, self.gse)
        gsm_html = os.path.join(gse_dir, '{0}.html'.format(self.gsm))
        with open(gsm_html, 'wb') as opf:
            opf.write('')
        gen_csv.gen_gsm_html(self.temp_outdir, self.gse, self.gsm)
        L.check(('rsempipeline.preprocess.gen_csv', 'INFO',
                 '{0} already downloaded'.format(gsm_html)))

    def test_gen_gsm_html_with_invalid_gsm(self):
        html = gen_csv.gen_gsm_html(self.temp_outdir, self.gse, 'invalid_GSM12345')
        self.assertTrue(os.path.exists(html))
        with open(html) as inf:
            content = inf.read()
            self.assertIn('Type in the a valid GEO accession number in the text box above', content)
            self.assertNotIn(self.gse, content)

    def test_download_html(self):
        out_html = os.path.join(self.temp_outdir, 'tmp.html')
        self.assertFalse(os.path.exists(out_html))
        gen_csv.download_html(self.gsm, out_html)
        self.assertTrue(os.path.exists(out_html))

    def test_gen_soup(self):
        self.assertIsInstance(gen_csv.gen_soup(self.gse, self.gsm, self.temp_outdir),
                              BeautifulSoup)

    def test_find_species_homo_sapiens(self):
        self.assertEqual(gen_csv.find_species(self.gse, self.gsm, self.temp_outdir),
                         'Homo sapiens')

    def test_find_species_mus_musculus(self):
        self.assertEqual(gen_csv.find_species('GSE49366', 'GSM119816', self.temp_outdir),
                         'Mus musculus')

    # def test_find_species_no_species_info(self):
    #     # write one after such a GSM is found
    #     pass

    def test_generate_csv(self):
        gen_csv.generate_csv(self.input_csv, self.temp_outdir, num_threads=2)
        out_csv = os.path.join(self.temp_outdir, SPECIES_CSV_BASENAME)
        self.assertTrue(os.path.exists(out_csv))
        with open(out_csv) as inf:
            self.assertEqual(
"""GSE59813,Mus musculus,GSM1446812
GSE61491,Homo sapiens,GSM1506106
GSE61491,Homo sapiens,GSM1506107
""",
                inf.read())

    # def test_generate_csv_no_species_info(self):
    #     pass
        

if __name__ == "__main__":
    unittest.main()
