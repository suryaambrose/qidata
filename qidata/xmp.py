# -*- coding: utf-8 -*-

# Standard Library
import collections
from compiler.misc import mangle
from itertools import islice
import os.path
import re
import weakref
# XMP
import libxmp

ALDEBARAN_NS_V1=u"http://aldebaran.com/xmp/1"
ALDEBARAN_NS = ALDEBARAN_NS_V1
SUGGESTED_ALDEBARAN_NS_PREFIX=u"aldebaran"
libxmp.exempi.register_namespace(ALDEBARAN_NS, SUGGESTED_ALDEBARAN_NS_PREFIX)

# ─────────────────────
# Formatting parameters

INDENT_SIZE = 5
INDENT = ' ' * INDENT_SIZE
TREE_INDENT = u'─'*(INDENT_SIZE-2) + " "
TREE_MID_INDENT  = u"├" + TREE_INDENT
TREE_LAST_INDENT = u"└" + TREE_INDENT

# ───────────────
# General XMP API

def isQualified(name):
	return name.find(':') != -1

def qualify(name, prefix):
	return "{prefix}:{name}".format(name=name, prefix=prefix)

class XMPFile(object):
	"""
	Handle to a file path to manipulate as a container to an XMP packet.

	Attributes:
		rw: Whether the file is considered writable.
		file_path: Path to the file to manipulate.
		metadata: The metadata manipulator for the file.
	"""

	def __init__(self, file_path, rw = False):
		self.__rw             = rw
		self.file_path        = os.path.abspath(file_path)
		self.libxmp_file      = None
		self._libxmp_metadata = None
		self.metadata         = None

	# ──────────
	# Properties

	@property
	def libxmp_metadata(self):
		return self._libxmp_metadata

	@libxmp_metadata.setter
	def libxmp_metadata(self, new_metadata):
		if new_metadata is not None:
			self._libxmp_metadata = new_metadata
		else:
			self._libxmp_metadata = libxmp.XMPMeta()
		self.metadata = XMPMetadata(self._libxmp_metadata)

		# Record to warn the user when they modify their metadata in read-only mode
		self.__original_repr = repr(self._libxmp_metadata)

	@property
	def rw(self):
	    return self.__rw

	@property
	def is_open(self):
	    return self.libxmp_file      is not None \
	       and self._libxmp_metadata is not None \
	       and self.metadata         is not None

	@property
	def has_changed(self):
	    return repr(self._libxmp_metadata) != self.__original_repr

	@property
	def read_only(self):
	    return not self.rw

	# ──────────
	# Public API

	def open(self):
		if self.is_open:
			raise RuntimeError("File {} is already open".format(self.file_path))
		if libxmp.exempi.files_check_file_format(self.file_path) == libxmp.consts.XMP_FT_UNKNOWN:
			raise RuntimeError("Unknown XMP file type")

		self.libxmp_file = libxmp.XMPFiles(file_path = self.file_path,
		                                open_onlyxmp = True,
		                              open_forupdate = self.rw)
		self.libxmp_metadata = self.libxmp_file.get_xmp()

	def close(self):
		try:
			if self.read_only and self.has_changed:
				message =  "Modified a read-only XMP file; won't be saved"
				raise RuntimeWarning(message)

			if self.rw:
				try:
					if self.libxmp_file.can_put_xmp(self.libxmp_metadata):
						self.libxmp_file.put_xmp(self.libxmp_metadata)
					else:
						raise
				except:
					raise RuntimeError("Can't serialize XMP to file " + self.file_path)

		finally:
			self.libxmp_file.close_file()
			self._reset()

	# ───────────────
	# Context Manager

	def __enter__(self):
		self.open()
		return self

	def __exit__(self, type, value, traceback):
		self.close()

	# ───────
	# Helpers

	def _reset(self):
		self.libxmp_file      = None
		self._libxmp_metadata = None
		self.metadata         = None
		self.__original_repr  = None

	# ──────────────
	# Textualization

	def __str__(self):
		return "XMP file {}:\n{}".format(self.file_path, str(self.metadata))

class XMPMetadata(collections.Mapping):
	"""
	XMP metadata packet.

	This may be a purely in-memory packet, or a packet read from a file by an
	XMPFile object managing it and which may automatically write it when closed.
	"""

	def __init__(self, libxmp_metadata = libxmp.XMPMeta()):
		self.libxmp_metadata = libxmp_metadata
		self._namespaces = {}

		# Group all elements by namespace and parse them in LibXMPElements
		elements_by_namespace = {}
		for libxmp_tuple in self.libxmp_metadata:
			libxmp_element = LibXMPElement(libxmp_tuple)
			if libxmp_element.is_namespace: continue
			try:
				elements_by_namespace[libxmp_element.namespace].append(libxmp_element)
			except KeyError:
				elements_by_namespace[libxmp_element.namespace] = [libxmp_element]

		# Construct namespaces; each one is the root object of an XMP object tree
		for ns_uid, ns_libxmp_descendents in elements_by_namespace.iteritems():
			namespace = XMPNamespace(self, ns_uid)
			libxmp_members = namespace.childrenIn(ns_libxmp_descendents)
			members = [XMPElement.fromLibXMP(m, ns_libxmp_descendents, namespace)
			           for m in libxmp_members]
			namespace.children = members
			self._namespaces[ns_uid] = namespace

	# ──────────
	# Properties

	@property
	def namespaces(self):
		return [n for n in self._namespaces.itervalues()]

	# ───────────
	# Mapping API

	def __len__(self):
		return len(self._namespaces)

	def __iter__(self):
		return iter(self._namespaces)

	def __getitem__(self, key):
		try:
			return self._namespaces[key]
		except KeyError:
			return XMPNamespace(self, key)

	# ──────────────
	# Textualization

	def __str__(self):
		return unicode(self).encode("utf-8")

	def __unicode__(self):
		return "\n".join([unicode(n) for n in self.namespaces])

	def pretty_str(self):
		import libxmp.utils
		raw_pretty_string = XMP.textualizeXMPDict(libxmp.utils.object_to_dict(self.libxmp_metadata))
		return raw_pretty_string.encode("utf-8")

	def xml(self):
		raw_xml = self.libxmp_metadata.serialize_and_format().encode("utf-8")
		return raw_xml

	# ───────
	# Helpers

	@staticmethod
	def textualizeXMPDict(x, indent = ""):
		rep = ""
		if isinstance(x, dict):
			textualized_items = [str(k)+": " + XMP.textualizeXMPDict(v, indent+' '*(2+len(str(k))))
			                     for k,v in x.iteritems()]
			rep += ("\n"+indent).join(items)
		elif isinstance(x, list):
			rep += ("\n"+indent).join([u"⁃ " + XMP.textualizeXMPDict(e, indent+' '*2) for e in x])
		elif isinstance(x, tuple) and len(x) == 3:
			node_name  = x[0]
			node_value = x[1]
			rep += node_name + " = " + node_value
		else:
			return str(x)
		return rep

class TreePredicatesMixin:
	"""
	Defines tree operations for any element that has a namespace and address.
	"""

	ARRAY_ELEMENT_REGEX = re.compile(r"(.*)\[(\d+)\]$")
	INDEX_REGEX = re.compile(r"^\[\d+\]$")
	STRUCT_CHILD_REGEX = re.compile(r"^/[^/]+$")

	# ──────────
	# Properties

	@property
	def name(self):
		return self.address.split("/")[-1]

	@property
	def namespace_uid(self):
		if isinstance(self, LibXMPElement):
			return self.namespace
		elif isinstance(self, XMPElement):
			return self.namespace.uid

	@property
	def is_top_level(self):
		return "/" not in self.address \
		   and not TreePredicatesMixin.ARRAY_ELEMENT_REGEX.match(self.address)

	@property
	def is_array_element(self):
		return TreePredicatesMixin.ARRAY_ELEMENT_REGEX.match(self.address) is not None

	@property
	def parent_address(self):
		if self.is_top_level:
			return None

		if self.is_array_element:
			return TreePredicatesMixin.ARRAY_ELEMENT_REGEX.match(self.address).group(1)
		else:
			return "/".join(self.address.split("/")[:-1])

	# ────────────────────
	# Address manipulation

	def absoluteAddress(self, relative_address):
		if not self.address:
			# Relative to a namespace: absolute is relative
			return relative_address
		elif TreePredicatesMixin.INDEX_REGEX.match(relative_address):
			return self.address + relative_address
		else:
			return "{base_address}/{relative_address}".format(base_address = self.address,
			                                              relative_address = relative_address)

	# ──────────
	# Predicates

	def inSameNamespace(self, other):
		return self.namespace_uid == other.namespace_uid

	def isDescendantOf(self, other):
		return self.address.startswith(other.address) \
		   and self.inSameNamespace(other) \
		   and self.address != other.address

	def isAncestorOf(self, other):
		return other.isDescendantOf(self)

	def isChildrenOf(self, other):

		if not self.inSameNamespace(other) \
		or not self.address.startswith(other.address):
			return False

		address_delta = self.address[len(other.address):]
		struct_depth_delta = address_delta.count("/")
		is_array_element = TreePredicatesMixin.ARRAY_ELEMENT_REGEX.match(address_delta) is not None
		other_is_namespace = not other.address

		if other_is_namespace and not is_array_element:
			# If other is a namespace, its address is the empty string and
			# children don't have a / in their address
			return struct_depth_delta == 0
		elif is_array_element:
			return bool(TreePredicatesMixin.INDEX_REGEX.match(address_delta))
		else:
			return bool(TreePredicatesMixin.STRUCT_CHILD_REGEX.match(address_delta))

	def isParentOf(self, other):
		return other.isChildrenOf(self)

	# ─────────────────────────────────
	# Filters in containers of elements

	def descendentsIn(self, elements):
		return [e for e in elements if e.isDescendantOf(self)]

	def ancestorsIn(self, elements):
		return [e for e in elements if e.isAncestorOf(self)]

	def childrenIn(self, elements):
		return [e for e in elements if e.isChildrenOf(self)]

	def parentsIn(self, elements):
		return [e for e in elements if e.isParentOf(self)]

	# ──────────────────
	# Equality operators

	def __eq__(self, other):
		return isinstance(other, self.__class__) \
		   and self.namespace == other.namespace \
		   and self.address   == other.address

	def __neq__(self, other):
		return not self.__eq__(other)

class TreeManipulationMixin(TreePredicatesMixin):
	@property
	def parent(self):
		parent_address = self.parent_address
		if parent_address is not None:
			return self.namespace[parent_address]
		elif isinstance(self, XMPNamespace):
			return None
		else:
			return self.namespace

class LibXMPElement(object, TreePredicatesMixin):
	""" Wrapper around a libXMP iterator element. """

	# ───────────
	# Constructor

	def __init__(self, tuple):
		self.namespace  = unicode(tuple[0])
		self.address    = unicode(tuple[1])
		self.value      = unicode(tuple[2])
		self.descriptor = tuple[3]

	# ──────────
	# Properties

	@property
	def tuple(self):
		return (self.namespace, self.address, self.value, self.descriptor)

	@property
	def is_container(self):
	    return self.descriptor["VALUE_IS_STRUCT"] or self.descriptor["VALUE_IS_ARRAY"]

	@property
	def is_value(self):
	    return not self.is_container

	@property
	def is_namespace(self):
	    return self.descriptor["IS_SCHEMA"]

	@property
	def is_struct(self):
	    return self.descriptor["VALUE_IS_STRUCT"]

	@property
	def is_array(self):
	    return self.descriptor["VALUE_IS_ARRAY"] and self.descriptor["ARRAY_IS_ORDERED"]

	@property
	def is_set(self):
	    return self.descriptor["VALUE_IS_ARRAY"] and not self.descriptor["ARRAY_IS_ORDERED"]

	# ──────────────
	# Textualization

	def __repr__(self):
		return repr(self.tuple)

	def __str__(self):
		return unicode(self).encode("utf-8")

	def __unicode__(self):
		rep = self.address
		if self.value: rep += " = " + self.value
		return rep

class FreezeMixin:
	@staticmethod
	def marker(classname):
		return "_{classname}___frozen".format(classname = classname)

	@property
	def frozen(self):
		try:
			# Don't use getattr, as the class probably overrides it and tests
			# this function to check whether it should return something special,
			# which would cause an infinite recursion.
			return self.__dict__[FreezeMixin.marker(self.__class__.__name__)]
		except KeyError:
			return False

	def freeze(self, class_or_classname, value = True):
		if isinstance(class_or_classname, str):
			classname = class_or_classname
		elif isinstance(class_or_classname, type):
			classname = class_or_classname.__name__
		else:
			raise ValueError("Freezing is done for a class or class-name")
		# Bypass the objet's setattr, which may have additional semantics
		object.__setattr__(self, FreezeMixin.marker(classname), value)

class ContainerMixin:
	# ──────────
	# Properties

	@property
	def children(self):
		""" Iterator over children with mutable semantics; must be overriden. """
		raise NotImplementedError("Must be overriden")

	# ────────────────────
	# XMPElement overrides

	@property
	def is_container(self):
		return True

class XMPElement(object, TreeManipulationMixin, FreezeMixin):
	"""
	Manipulator for an element in an XMP packet.

	Abstracts a fully-qualified, absolute address in a namespace of an XMP metadata
	packet. Contrary to :class:`XMPVirtualElement`, the manipulated element already
	exists in the XMP tree.
	"""

	# ────────────
	# Constructors

	def __init__(self, namespace, address):
		"""
		Constructs a manipulator for an XMP element in an XMP packet.

		Arguments:
		    namespace: The namespace to which the element belongs to, or None if the
		               element is a namespace itself. No "strong" reference of it will
		               be kept, only a weakref.
		    address: The fully-qualified, absolute address of the element in its namespace.
		"""

		if namespace is not None and not isinstance(namespace, weakref.ReferenceType):
			self._namespace = weakref.ref(namespace)
		else:
			self._namespace = namespace
		self.address = address
		self.freeze(XMPElement)

	@staticmethod
	def fromLibXMP(libxmp_element, potential_descendents, namespace):
		if libxmp_element.is_value:
			return XMPValue(namespace, libxmp_element.address)
		else:
			# Container type elements
			libxmp_descendents = libxmp_element.descendentsIn(potential_descendents)
			libxmp_children    = libxmp_element.childrenIn(libxmp_descendents)

			# Recursively build children
			children_elements = [XMPElement.fromLibXMP(libxmp_child,
			                                           libxmp_descendents,
			                                           namespace) for libxmp_child \
			                                                       in libxmp_children]

			# Return the assembled tree
			if libxmp_element.is_struct:
				return XMPStructure(namespace, libxmp_element.address, children_elements)
			elif libxmp_element.is_array:
				return XMPArray(namespace, libxmp_element.address, children_elements)
			elif libxmp_element.is_set:
				return XMPSet(namespace, libxmp_element.address, children_elements)

	# ───────────────────
	# Descriptor protocol

	def __set__(self, owner_object, value):
		raise NotImplementedError("Must be overriden")

	def __delete__(self, obj):
		self.libxmp_metadata.delete_property(schema_ns=self.namespace.uid, prop_name=self.address)

	# ──────────
	# Properties

	@property
	def is_leaf(self):
		return not self.is_container

	@property
	def is_container(self):
		raise NotImplementedError("Must be overriden")

	@property
	def namespace(self):
		return self._namespace()

	@property
	def libxmp_metadata(self):
		return self.namespace.libxmp_metadata

	@property
	def value(self):
		raise NotImplementedError("Must be overriden")

	@property
	def desynchronized(self):
		return self.libxmp_metadata.does_property_exist(schema_ns = self.namespace.uid,
		                                                prop_name = self.address)

	# ──────────────
	# Textualization

	def __str__(self):
		return unicode(self).encode("utf-8")

	def __unicode__(self):
		return "{namespace}@{address}".format(namespace = unicode(self.namespace.uid),
		                                        address = self.address)

class XMPVirtualElement(object, TreeManipulationMixin):
	"""
	Element in an XMP packet.

	Abstracts a fully-qualified, absolute address in a namespace of an XMP metadata
	packet. Virtual elements represent an address the corresponding element of which
	may not exist.
	"""

	# ────────────
	# Constructors

	def __init__(self, namespace, address):
		"""
		Constructs a virtual XMP element.

		Arguments:
			namespace: The namespace to which the element belongs to, or None if the
			           element is a namespace itself. No strong reference of it will be
			           kept, only a weakref.
			address: The fully-qualified, absolute address of the element in its namespace.
		"""

		if namespace is not None and not isinstance(namespace, weakref.ReferenceType):
			self._namespace = weakref.ref(namespace)
		else:
			self._namespace = namespace
		self.address = address

	# ──────────
	# Properties

	@property
	def namespace(self):
		return self._namespace()

	@property
	def parent(self):
		try:
			return super(XMPVirtualElement, self).parent
		except KeyError:
			return XMPVirtualElement(self.namespace, self.parent_address)

	# ─────────────
	# Attribute API

	def has(self, field_name):
		return False

	def __getattr__(self, name):
		"""
		Creates a child virtual element if normal attribute lookup fails.

		Warning:
		    This may cause confusion if the user wants to actually access a sub-field
		    called namespace or address, which they legitimately may want.
		    Notwithstanding the confusion, the user would have to use __getitem__ in
		    this case.
		"""

		# A subfield of a virtual element is also virtual
		qualified_field_name = self.namespace.qualify(name)
		return XMPVirtualElement(self.namespace,
		                         self.absoluteAddress(qualified_field_name))

	# ──────────────────
	# ???

	def __getitem__(self, key):
		if isinstance(key, (int, long)):
			return XMPVirtualElement(self.namespace,
			                         self.absoluteAddress("[%s]"%key))
		elif isinstance(key, basestring):
			qualified_field_name = self.namespace.qualify(key)
			return XMPVirtualElement(self.namespace,
				                     self.absoluteAddress(qualified_field_name))
		else:
			raise TypeError("Wrong index type "+str(type(key)))

	# ───────────────────
	# Descriptor protocol

	def __set__(self, owner_object, value):
		"""
		Sets the property in the associated libxmp metadata and adds an XMP element to
		the object tree rooted in the virtual element's namespace.

		Attributes:
			owner_object: object the
		"""

		parent = self.parent

		if type(parent) is XMPVirtualElement:
			# Set was called on chained virtual elements; go up the chain, recursing to the
			# base case where the parent exists.

			# There are only 2 ways to get a child virtual element from a parent virtual
			# element:
			# - with the . attribute operator or [] field-name lookup operator, in which
			#   case the parent (virtual) element will be a struct;
			# - with the [] integer-indexing operator, in which case the parent (virtual)
			#   element is an array.

			# TODO

			if parent.is_array_element:
				parent.__set__(owner_object, {self.name : value})
			else:
				# Parent is a struct of which this virtual element is a named child
				parent.__set__(owner_object, {self.name : value})

			raise NotImplementedError("Virtual element assignment [Not implemented YET]")
		else:
			# The parent already exists ; we'll do out part by creating the element, and
			# recursing downwards to let children create themselves if needed.

			if isinstance(value, collections.Mapping):
				# We're going to create a new XMPStructure ex-nihilo
				new_element = XMPStructure(self.namespace, self.address, [])
			elif isinstance(value, collections.Sequence):
				# We're going to create a new XMPArray ex-nihilo
				new_element = XMPArray(self.namespace, self.address, [])
			elif isinstance(value, collections.Set):
				# we're going to create a new XMPSet ex-nihilo
				new_element = XMPSet(self.namespace, self.address, [])
			else:
				# We're going to create a new XMPValue ex-nihilo
				new_element = XMPValue(self.namespace, self.address)
				new_element.__set__(owner_object, value)

			# Record the new element in its parent's children list

			parent.append(new_element)

	# ──────────────
	# Textualization

	def __str__(self):
		return unicode(self).encode("utf-8")

	def __unicode__(self):
		return "{namespace}@{address} [virtual]".format(namespace = self.namespace.uid,
		                                                  address = self.address)

class XMPStructure(XMPElement, ContainerMixin, collections.MutableSequence, collections.Mapping):
	""" Convenience wrapper around libXMP to manipulate an XMP struct. """

	# ────────────
	# Constructors

	def __init__(self, namespace, address, children):
		XMPElement.__init__(self, namespace, address)
		self.children = children
		self.freeze(XMPStructure)

	# ──────────
	# Properties

	@property
	def attributes(self):
		return self._children.iterkeys()

	@property
	def fields(self):
		return self.attributes

	@property
	def keys(self):
		return self.attributes

	@property
	def children(self):
		return self._children.itervalues()

	@children.setter
	def children(self, new_children):
		if isinstance(new_children, collections.MutableMapping):
			self._children = new_children
		else:
			self._children = collections.OrderedDict((c.name, c) for c in new_children)

	@property
	def value(self):
		return collections.OrderedDict((c.name, c.value) for c in children)

	@property
	def desynchronized(self):
		if not self.libxmp_metadata.does_property_exist(schema_ns = self.namespace.uid,
		                                                prop_name = self.address):
			return True

		# Check that all children exist in the xmp packet
		return any(children.desynchronized for c in self.children)

		# TODO Check that no element in the xmp packet exist that do not exist among children
		#      (false-negatives)

	# ─────────────
	# Attribute API

	def has(self, field_name):
		qualified_field_name = self.namespace.qualify(field_name)
		return any(qualified_field_name == c.name for c in self.children)

	def __raw_getattr__(self, name):
		# Search in the object, then in all parent classes if not found
		for o in [self] + self.__class__.mro():
			try:
				return o.__dict__[name]
			except KeyError:
				continue
		raise AttributeError

	def __raw_hasattr__(self, name):
		try:
			self.__raw_getattr__(name)
			return True
		except AttributeError:
			return False

	def __getattr__(self, name):
		"""
		Standard __getattr__ implementing custom field access when __getattribute__'s search fails.

		See:
		    https://docs.python.org/2/reference/datamodel.html#object.__getattr__
		"""

		# self.frozen is safe to call as it will tap into __getattribute__ first, which
		# should find the attribute without coming back here in an infinite recursion
		if not self.frozen:
			raise
		field = self.get(name, default=None)
		if field is not None:
			return field
		else:
			qualified_field_name = self.namespace.qualify(name)
			return XMPVirtualElement(self.namespace,
			                         self.absoluteAddress(qualified_field_name))

	def __setattr__(self, name, value):
		"""
		Standard __setattr__ with virtual-element attribute fallback for all non-frozen attributes.

		See:
		    https://docs.python.org/2/reference/datamodel.html#object.__setattr__
		"""

		if self.frozen and not self.__raw_hasattr__(name):
			child = self.__getattr__(name)
			assert(hasattr(child, "__set__") and callable(child.__set__))
			child.__set__(self, value)
		else:
			object.__setattr__(self, name, value)

	def __delattr__(self, name):
		try:
			object.__delattr__(self, name)
		except AttributeError as attribute_error:
			if attribute_error.args[0] != name:
				raise
			child = self.__getattr__(name)
			assert(hasattr(child, "__set__") and callable(child.__set__))
			child.__delete__(self)
			raise

	# ────────────────────────────────────
	# Mutable{Sequence,Mapping} common API

	def __getitem__(self, key_or_index):
		if isinstance(key_or_index, (int,long)):
			return self.children[key_or_index]
		elif not isinstance(key_or_index, basestring):
			raise TypeError("Wrong index type "+str(type(key_or_index)))

		key_components = key_or_index.split("/")
		qualified_field_name = self.namespace.qualify(key_components[0])
		nested_components = key_components[1:]
		try:
			child = self._children[qualified_field_name]
		except KeyError:
			raise KeyError(qualified_field_name)

		if nested_components:
			return child["/".join(nested_components)]
		else:
			return child

	def __setitem__(self, key_or_index, value):
		if isinstance(key_or_index, (int,long)):
			pass
		elif not isinstance(key_or_index, basestring):
			raise TypeError("Wrong index type "+str(type(key_or_index)))
		raise NotImplementedError # TODO

	def __delitem__(self, key_or_index):
		if isinstance(key_or_index, (int,long)):
			pass
		elif not isinstance(key_or_index, basestring):
			raise TypeError("Wrong index type "+str(type(key_or_index)))
		raise NotImplementedError # TODO

	def __len__(self):
		return sum(1 for _ in self.children)

	def __contains__(self, key):
		if not isinstance(key, basestring):
			raise TypeError("Wrong index type "+str(type(key)))

		key_components = key.split("/")
		qualified_field_name = self.namespace.qualify(key_components[0])
		nested_components = key_components[1:]
		if not nested_components:
			return qualified_field_name in self._children
		else:
			try:
				return "/".join(nested_components) in self[qualified_field_name]
			except KeyError:
				return False

	def __iter__(self):
		return self.children

	def pop(self, key_or_index, mapping_default):
		if isinstance(key_or_index, (int,long)):
			pass
		elif not isinstance(key_or_index, basestring):
			raise TypeError("Wrong index type "+str(type(key_or_index)))
		raise NotImplementedError # TODO

	# ───────────────────
	# MutableSequence API

	def insert(self, i, element):
		raise NotImplementedError # TODO

	# Note: the following methods are automatically implemented as mixin methods
	#       using the Sequence ABC:
	#       • __reversed__
	#       • index
	#       • count
	#       • append
	#       • reverse
	#       • extend
	#       • remove
	#       • __iadd__
	# For more information: https://docs.python.org/2/library/collections.html

	# Note: the following methods are automatically implemented as mixin methods
	#       using the Mapping ABC:
	#       • keys
	#       • items
	#       • values
	#       • get
	#       • popitem
	#       • clear
	#       • update
	#       • setdefault
	# For more information: https://docs.python.org/2/library/collections.html

	# ──────────────
	# Textualization

	def __str__(self):
		children = "\n".join([str(c) for c in self.children])
		return self.name + "\n\t" + children.replace("\n", "\n\t")

	def __unicode__(self):
		if self.children:
			mid_children = [TREE_MID_INDENT+unicode(c) for c in self.children[:-1]]
			last_child = TREE_LAST_INDENT+unicode(self.children[-1])
			children = mid_children + [last_child]
		else:
			children = []
		return self.name + "\n" + "\n".join([c.replace("\n","\n"+INDENT)for c in children])

class XMPArray(XMPElement, ContainerMixin, collections.Sequence):
	""" Convenience wrapper around libXMP to manipulate an XMP array (rdf:Seq). """

	# ────────────
	# Constructors

	def __init__(self, namespace, address, children):
		XMPElement.__init__(self, namespace, address)
		self._children = children
		self.freeze(XMPArray)

	# ──────────
	# Properties

	@property
	def value(self):
		return [c.value for c in self.children]

	@property
	def desynchronized(self):
		if not self.libxmp_metadata.does_property_exist(schema_ns = self.namespace.uid,
		                                                prop_name = self.address):
			return True

		any_child_desynchronized = any(children.desynchronized for c in self.children)
		real_length = self.libxmp_metadata.count_array_items(schema_ns = self.namespace.uid,
		                                                     prop_name = self.address)
		missing_elements = real_length != len(self)

		return any_child_desynchronized or missing_elements

	# ────────────────────────
	# ContainerMixin overrides

	@property
	def children(self):
		return self._children

	# ────────────
	# Sequence API

	def __getitem__(self, index):
		return self.children[index]

	def __setitem__(self, key, value):
		# TODO Implement sequence set
		raise NotImplementedError # TODO

	def __len__(self):
		return len(self.children)

	# ──────────────
	# Textualization

	def __str__(self):
		children_strings = "\n".join(["- "+str(c).replace("\n", "\n  ")
		                              for c in self.children])
		return self.name + " [\n    " + children_strings.replace("\n", "\n    ") + "\n]"

	def __unicode__(self):
		children_strings = "\n".join([u"⁃ "+unicode(c).replace("\n", "\n  ")
		                              for c in self.children])
		return self.name + " [\n    " + children_strings.replace("\n", "\n    ") + "\n]"

class XMPSet(XMPElement, ContainerMixin):
	""" Convenience wrapper around libXMP to manipulate an XMP set (rdf:Bag). """

	# ────────────
	# Constructors

	def __init__(self, namespace, address, children):
		super(XMPSet, self).__init__(namespace, address)
		self._children = set(children)
		self.freeze(XMPSet)

	# ──────────
	# Properties

	@property
	def value(self):
		return set(c.value for c in self.children)

	@property
	def desynchronized(self):
		if not self.libxmp_metadata.does_property_exist(schema_ns = self.namespace.uid,
		                                                prop_name = self.address):
			return True

		any_child_desynchronized = any(children.desynchronized for c in self.children)
		real_length = self.libxmp_metadata.count_array_items(schema_ns = self.namespace.uid,
		                                                     prop_name = self.address)
		missing_elements = real_length != len(self)

		return any_child_desynchronized or missing_elements

	# ────────────────────────
	# ContainerMixin overrides

	@property
	def children(self):
		return self._children

	# ────────────
	# Sequence API

	def __getitem__(self, index):
		return self.children[index]

	def __setitem__(self, key, value):
		# TODO Implement set-element set
		raise NotImplementedError # TODO

	def __len__(self):
		return len(self.children)

	# ──────────────
	# Textualization

	def __str__(self):
		children_strings = "\n".join(["* "+str(c).replace("\n", "\n  ")
		                              for c in self.children])
		return self.name + " {\n    " + children_strings.replace("\n", "\n    ") + "\n}"

	def __unicode__(self):
		children_strings = "\n".join([u"• "+unicode(c).replace("\n", "\n  ")
		                              for c in self.children])
		return self.name + " {\n    " + children_strings.replace("\n", "\n    ") + "\n}"

class XMPValue(XMPElement):
	""" Convenience wrapper around libXMP to manipulate an XMP value. """

	# ────────────
	# Constructors

	def __init__(self, *args, **kwargs):
		super(XMPValue, self).__init__(*args, **kwargs)
		self.freeze(XMPValue)

	# ──────────
	# Properties

	@property
	def value(self):
		return self.libxmp_metadata.get_property(schema_ns = self.namespace.uid,
		                                         prop_name = self.address)

	@property
	def desynchronized(self):
		raise self.libxmp_metadata.does_property_exist(schema_ns = self.namespace.uid,
		                                               prop_name = self.address)
		raise NotImplementedError # TODO

	# ────────────────────
	# XMPElement overrides

	@property
	def is_container(self):
		return False

	# ───────────────────
	# Descriptor protocol

	def __set__(self, owner_object, value):
		if not isinstance(value, basestring):
			value = unicode(value)

		self.libxmp_metadata.set_property(schema_ns = self.namespace.uid,
		                                  prop_name = self.address,
		                                 prop_value = value)

	# ──────────────
	# Textualization

	def __str__(self):
		return self.name + " = " + str(self.value)

	def __unicode__(self):
		return self.name + " = " + unicode(self.value)

class XMPNamespace(XMPStructure):
	""" Convenience wrapper around libXMP to manipulate a namespace. """

	# ──────────
	# Properties

	def __init__(self, xmp, uid):
		XMPStructure.__init__(self, None, "", [])
		if not isinstance(xmp, weakref.ReferenceType):
			self._xmp = weakref.ref(xmp)
		else:
			self._xmp = xmp
		self.uid = uid
		self.freeze(XMPNamespace)

	# ──────────
	# Properties

	@property
	def xmp(self):
		return self._xmp()

	@property
	def namespace(self):
		return self

	@property
	def libxmp_metadata(self):
		return self.xmp.libxmp_metadata

	@property
	def prefix(self):
		return self.libxmp_metadata.get_prefix_for_namespace(self.uid)[:-1]

	# ──────────────
	# Comparison API

	def __eq__(self, other):
		return isinstance(other, self.__class__) \
		   and self.xmp is other.xmp \
		   and self.uid == other.uid

	# ───────────
	# Utility API

	def qualify(self, name):
		if isQualified(name): return name
		return qualify(name, self.prefix)

	# ──────────────
	# Textualization

	def __str__(self):
		return unicode(self).encode("utf-8")

	def __unicode__(self):
		if self.children:
			unicode_children = (unicode(e) for e in self.children)
			return u"{}\n{}".format(self.uid, "\n".join(unicode_children)).replace("\n","\n\t")
		else:
			return self.uid
