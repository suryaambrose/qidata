# -*- coding: utf-8 -*-

# Standard Library
import unittest

from qidata.qidataobject import QiDataObject
from qidata.files import qidatafile
import fixtures

class QidataObjectTest(unittest.TestCase):
    def test_attributes(self):
        qidata_object = QiDataObject()
        with self.assertRaises(NotImplementedError):
            qidata_object.raw_data
        with self.assertRaises(NotImplementedError):
            qidata_object.metadata
        with self.assertRaises(NotImplementedError):
            qidata_object.type

class QiDataObjectImplem:
    def test_attributes(self):
        self.qidata_object.raw_data
        self.qidata_object.metadata
        self.qidata_object.type

class QiDataFileAsObject(unittest.TestCase, QiDataObjectImplem):

    def setUp(self):
        self.jpg_path = fixtures.sandboxed(fixtures.JPG_PHOTO)
        self.qidata_object = qidatafile.open(self.jpg_path)

    def tearDown(self):
        self.qidata_object.close()
