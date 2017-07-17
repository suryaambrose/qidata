# -*- coding: utf-8 -*-

# Standard Library
import unittest
# Qidata
from qidata import qidatafile
from qidata._mixin import XMPHandlerMixin
import utilities

class FileTools(unittest.TestCase):
	def test_support(self):
		assert(qidatafile.isSupported("./toto.png"))
		assert(not qidatafile.isSupported(""))

class File(unittest.TestCase):
	def setUp(self):
		self.jpg_path = utilities.sandboxed(utilities.JPG_PHOTO)

	def test_contextmanager_noop(self):
		with qidatafile.open(self.jpg_path):
			pass

	def test_raw_data_attribute(self):
		with qidatafile.open(self.jpg_path) as datafile:
			datafile.raw_data

	def test_metadata_attribute(self):
		with qidatafile.open(self.jpg_path) as datafile:
			datafile.metadata

	def test_type_attribute(self):
		with qidatafile.open(self.jpg_path) as datafile:
			datafile.type

	def test_closed_attribute(self):
		with qidatafile.open(self.jpg_path) as datafile:
			assert(datafile.closed==False)

	def test_mode_attribute(self):
		with qidatafile.open(self.jpg_path) as datafile:
			assert(datafile.mode == "r")
			assert(datafile.read_only)

		with qidatafile.open(self.jpg_path, "w") as datafile:
			assert(datafile.mode == "w")
			assert(not datafile.read_only)

	def test_path_attribute(self):
		with qidatafile.open(self.jpg_path) as datafile:
			assert(datafile.path == self.jpg_path)

	def test_annotators_attribute(self):
		with qidatafile.open(self.jpg_path) as datafile:
			datafile.annotators

	def test_file_display(self):
		with qidatafile.open(self.jpg_path) as datafile:
			unicode(datafile)

	def test_unsupported_file(self):
		with self.assertRaises(TypeError):
			qidatafile.open("file.unknown_extension", mode="r")

class MetadataReading(unittest.TestCase):
	def setUp(self):
		self.jpg_data_path = utilities.sandboxed(utilities.QIDATA_TEST_FILE)
		self.jpg_data_item = qidatafile.open(self.jpg_data_path)

	def tearDown(self):
		self.jpg_data_item.close()

	def test_annotations(self):
		utilities.verifyAnnotations(self.jpg_data_item, "sambrose")

	def test_annotators(self):
		annotators = self.jpg_data_item.annotators
		assert(annotators == ["sambrose"])

	def test_modification_readonly(self):
		from qidata.metadata_objects import Person
		annotations = self.jpg_data_item.metadata
		test_person = [Person("name"), [[1.0, 2.0],[20.0, 25.0]]]
		annotations["jdoe"]=dict()
		annotations["jdoe"]["Person"]=[test_person]
		self.jpg_data_item.metadata = annotations
		self.jpg_data_item.close()
		self.jpg_data_item = qidatafile.open(self.jpg_data_path)

		utilities.verifyAnnotations(self.jpg_data_item, "sambrose")

class MetadataWriting(unittest.TestCase):
	def setUp(self):
		self.jpg_data_path = utilities.sandboxed(utilities.QIDATA_TEST_FILE)
		self.jpg_data_item = qidatafile.open(self.jpg_data_path, "w")

	def test_modification(self):
		from qidata.metadata_objects import Person
		annotations = self.jpg_data_item.metadata
		test_person = [Person("name"), [[1.0, 2.0],[20.0, 25.0]]]
		annotations["jdoe"]=dict()
		annotations["jdoe"]["Person"]=[test_person]
		self.jpg_data_item.metadata = annotations
		self.jpg_data_item.close()
		self.jpg_data_item = qidatafile.open(self.jpg_data_path)

		annotations = self.jpg_data_item.metadata
		assert(annotations.has_key("jdoe"))
		assert(annotations["jdoe"].has_key("Person"))
		assert(len(annotations["jdoe"]["Person"][0])==2)
		assert(isinstance(annotations["jdoe"]["Person"][0][0], Person))
		person = annotations["jdoe"]["Person"][0][0]
		location = annotations["jdoe"]["Person"][0][1]
		assert(person.name == "name")
		assert(location == [[1.0, 2.0],[20.0, 25.0]])

	def test_modification_with_two_annot_types(self):
		from qidata.metadata_objects import Person, Face
		annotations = self.jpg_data_item.metadata
		test_person = [Person("name"), [[1.0, 2.0],[20.0, 25.0]]]
		test_face = [Face("name"), [[1.0, 2.0],[20.0, 25.0]]]
		annotations["jdoe"]=dict()
		annotations["jdoe"]["Person"]=[test_person]
		annotations["jdoe"]["Face"]=[test_face]
		self.jpg_data_item.metadata = annotations
		self.jpg_data_item.close()
		self.jpg_data_item = qidatafile.open(self.jpg_data_path)

		annotations = self.jpg_data_item.metadata
		assert(annotations.has_key("jdoe"))
		assert(annotations["jdoe"].has_key("Person"))
		assert(annotations["jdoe"].has_key("Face"))
		assert(len(annotations["jdoe"]["Person"][0])==2)
		assert(len(annotations["jdoe"]["Face"][0])==2)
		assert(isinstance(annotations["jdoe"]["Person"][0][0], Person))
		assert(isinstance(annotations["jdoe"]["Face"][0][0], Face))
		person = annotations["jdoe"]["Person"][0][0]
		location = annotations["jdoe"]["Person"][0][1]
		assert(person.name == "name")
		assert(location == [[1.0, 2.0],[20.0, 25.0]])
		face = annotations["jdoe"]["Face"][0][0]
		location = annotations["jdoe"]["Face"][0][1]
		assert(face.name == "name")
		assert(location == [[1.0, 2.0],[20.0, 25.0]])

	def test_bad_modification(self):
		from qidata.metadata_objects import Person

		with self.assertRaises(AttributeError) as e:
			self.jpg_data_item.metadata = list()
		assert(str(e.exception) == "Metadata must be a mapping")

		self.jpg_data_item.metadata = dict() # OK

		with self.assertRaises(AttributeError) as e:
			self.jpg_data_item.metadata = dict(jdoe=list())
		assert(str(e.exception) == "Metadata from annotator jdoe must be a dict, not list")

		with self.assertRaises(AttributeError) as e:
			self.jpg_data_item.metadata = dict(jdoe=dict(Toto=dict()))
		assert(str(e.exception) == "Type Toto in jdoe's metadata does not exist")

		with self.assertRaises(AttributeError) as e:
			self.jpg_data_item.metadata = dict(jdoe=dict(Person=dict()))
		assert(str(e.exception) == "List of Person metadata from annotator jdoe must be a list")

		self.jpg_data_item.metadata = dict(jdoe=dict(Person=list())) # OK

		with self.assertRaises(AttributeError) as e:
			self.jpg_data_item.metadata = dict(
			                                   jdoe=dict(
			                                             Person=[
			                                                 Person("name")
			                                             ]
			                                    )
			                              )
		assert(str(e.exception) == "Metadata stored in Person's metadata list must be a list or tuple, not Person")

		with self.assertRaises(AttributeError) as e:
			self.jpg_data_item.metadata = dict(
			                                   jdoe=dict(
			                                             Person=[
			                                                 [Person("name")]
			                                             ]
			                                    )
			                              )
		assert(str(e.exception) == "Metadata of type Person in Person's metadata from jdoe must be of size 2")

		with self.assertRaises(AttributeError) as e:
			self.jpg_data_item.metadata = dict(
			                                   jdoe=dict(
			                                             Face=[
			                                                 [Person("name"), None]
			                                             ]
			                                    )
			                              )
		assert(str(e.exception) == "Person metadata received instead of Face in jdoe's metadata")

		with self.assertRaises(AttributeError) as e:
			self.jpg_data_item.metadata = dict(
			                                   jdoe=dict(
			                                             Person=[
			                                                 [Person("name"),
			                                                 0]
			                                             ]
			                                    )
			                              )
		assert(str(e.exception) == "Location of metadata of type Person in Person's metadata from jdoe is incorrect. Must be list or None")

		self.jpg_data_item.metadata = dict(
		                                   jdoe=dict(
		                                             Person=[
		                                                 [Person("name"),
		                                                 None]
		                                             ]
		                                    )
		                              ) # OK


	def test_deletion(self):
		annotations = self.jpg_data_item.metadata
		for annotator in annotations.keys():
			annotations.pop(annotator)
		self.jpg_data_item.metadata = annotations
		self.jpg_data_item.close()
		self.jpg_data_item = qidatafile.open(self.jpg_data_path)

		annotations = self.jpg_data_item.metadata
		assert(not annotations.has_key("sambrose"))

	def test_reload(self):
		from qidata.metadata_objects import Person
		annotations = self.jpg_data_item.metadata
		test_person = [Person("name"), [[1.0, 2.0],[20.0, 25.0]]]
		annotations["jdoe"]=dict()
		annotations["jdoe"]["Person"]=[test_person]
		self.jpg_data_item.metadata = annotations
		assert(self.jpg_data_item.metadata.has_key("jdoe"))
		self.jpg_data_item.reloadMetadata()
		assert(not self.jpg_data_item.metadata.has_key("jdoe"))

class MetadataTestCases(unittest.TestCase):
	def setUp(self):
		self.jpg_data_path = utilities.sandboxed(utilities.QIDATA_TEST_FILE)
		self.jpg_data_item = qidatafile.open(self.jpg_data_path, "w")

	def test_general_annotation(self):
		"""
		This test checks if it is possible to add an annotation without
		specific location (annotation to the whole file)
		"""
		from qidata.metadata_objects import Person
		annotations = self.jpg_data_item.metadata
		test_person = [Person("name"), None]
		annotations["jdoe"]=dict()
		annotations["jdoe"]["Person"]=[test_person]
		self.jpg_data_item.metadata = annotations
		self.jpg_data_item.close()
		self.jpg_data_item = qidatafile.open(self.jpg_data_path)

		annotations = self.jpg_data_item.metadata
		assert(annotations.has_key("jdoe"))
		assert(annotations["jdoe"].has_key("Person"))
		assert(len(annotations["jdoe"]["Person"][0])==2)
		assert(isinstance(annotations["jdoe"]["Person"][0][0], Person))
		person = annotations["jdoe"]["Person"][0][0]
		location = annotations["jdoe"]["Person"][0][1]
		assert(person.name == "name")
		assert(location == None)

	def test_file_display(self):
		str(self.jpg_data_item)

class XMPMixin(unittest.TestCase):
	# A lot is already tested with the files
	# Here we just add a few test for error handling just
	# to make sure it will work, even if it is not supposed
	# to happen
	def test_unicode_conversion(self):

		with self.assertRaises(TypeError):
			XMPHandlerMixin._unicodeListToBuiltInList(())

		data = ["1"]
		XMPHandlerMixin._unicodeListToBuiltInList(data)
		assert(data == [1])

		data = ["1.0", "1"]
		XMPHandlerMixin._unicodeListToBuiltInList(data)
		assert(data == [1.0, 1])

		data = ["a",["1","2.0"]]
		XMPHandlerMixin._unicodeListToBuiltInList(data)
		assert(data == ["a", [1, 2.0]])

		with self.assertRaises(TypeError):
			XMPHandlerMixin._unicodeToBuiltInType([])