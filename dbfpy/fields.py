"""DBF fields definitions.

TODO:
  - make memos work
  - use DBF encoding to encode
"""

__version__ = "$Revision: 1.15 $"[11:-2]
__date__ = "$Date: 2010/12/14 11:04:49 $"[7:-2]

__all__ = ["field_class_of", ]  # field classes added at the end of the module

import datetime
import struct
import locale

from .memo import MemoData
from . import utils


## abstract definitions

class DbfField(object):
    """Abstract field definition.

    Child classes must override ``type`` class attribute to provide datatype
    infromation of the field definition. For more info about types visit
    `http://www.clicketyclick.dk/databases/xbase/format/data_types.html`

    Also child classes must override ``defaultValue`` field to provide
    default value for the field value.

    If child class has fixed length ``length`` class attribute must be
    overriden and set to the valid value. None value means, that field
    isn't of fixed length.

    Note: ``name`` field must not be changed after instantiation.

    """

    __slots__ = (
        "name", "length", "decimal_count",
        "start", "end", "ignore_errors"
    )

    # length of the field, None in case of variable-length field,
    # or a number if this field is a fixed-length field
    default_length = None

    # field type. for more information about fields types visit
    # `http://www.clicketyclick.dk/databases/xbase/format/data_types.html`
    # must be overriden in child classes
    type_code = None

    # default value for the field. this field must be
    # overridden in child classes
    default_value = None

    # True if field data is kept in the Memo file
    @property
    def is_memo(self):
        return self.type_code in "GMP"

    def __init__(
            self, name, length=None, decimal_count=None,
            start=None, ignore_errors=False,
    ):
        """Initialize instance."""
        assert self.type_code is not None, "Type code must be overriden"
        assert self.default_value is not None, "Default value must be overriden"
        ## fix arguments
        if len(name) > 10:
            raise ValueError("Field name \"%s\" is too long" % name)
        name = str(name).upper()
        if self.default_length is None:
            if length is None:
                raise ValueError("[%s] Length isn't specified" % name)
            length = int(length)
            if length <= 0:
                raise ValueError("[%s] Length must be a positive integer"
                                 % name)
        else:
            length = self.default_length
        if decimal_count is None:
            decimal_count = 0
        ## set fields
        self.name = name
        # FIXME: validate length according to the specification at
        # http://www.clicketyclick.dk/databases/xbase/format/data_types.html
        self.length = length
        self.decimal_count = decimal_count
        self.ignore_errors = ignore_errors
        self.start = start

    def __hash__(self):
        return hash(self.name)

    @classmethod
    def from_bytes(cls, string, start, ignore_errors=False):
        """Decode dbf field definition from the string data.

        Arguments:
            string:
                a string, dbf definition is decoded from. length of
                the string must be 32 bytes.
            start:
                position in the database file.
            ignore_errors:
                initial error processing mode for the new field (boolean)

        """
        assert len(string) == 32
        return cls(
            # name
            utils.unzfill(string[:11]).decode(locale.getpreferredencoding()),
            length=string[16],
            decimal_count=string[17],
            start=start,
            ignore_errors=ignore_errors
        )

    def to_bytes(self):
        """Return encoded field definition.

        Return:
            Return value is a string object containing encoded
            definition of this field.

        """
        return struct.pack(
            '< 11s B L 2B 14s',
            self.name.encode(locale.getpreferredencoding()),
            ord(self.type_code),
            self.start,
            self.length,
            self.decimal_count,
            b'\x00' * 14,
        )

    def __str__(self):
        return "%-10s %1s %3d %3d" % self.field_info()

    def field_info(self):
        """Return field information.

        Return:
            Return value is a (name, type, length, decimals) tuple.

        """
        return self.name, self.type_code, self.length, self.decimal_count

    def raw_from_record(self, record):
        """Return a "raw" field value from the record string."""
        return record[self.start:self.start + self.length]

    def decode_from_record(self, record):
        """Return decoded field value from the record string."""
        try:
            return self.decode_value(self.raw_from_record(record))
        except:
            if self.ignore_errors:
                return utils.INVALID_VALUE
            else:
                raise

    def decode_value(self, value):
        """Return decoded value from string value.

        This method shouldn't be used publicly. It's called from the
        `decodeFromRecord` method.

        This is an abstract method and it must be overridden in child classes.
        """
        raise NotImplementedError

    def encode_value(self, value):
        """Return str object containing encoded field value.

        This is an abstract method and it must be overriden in child classes.
        """
        raise NotImplementedError


## real classes

class DbfCharacterField(DbfField):
    """Definition of the character field."""

    type_code = "C"
    default_value = ""

    def decode_value(self, value):
        """Return string object.

        Return value is a ``value`` argument with stripped right spaces.

        """
        return value.decode(locale.getpreferredencoding()).rstrip(" ")

    def encode_value(self, value):
        """Return raw data string encoded from a ``value``."""
        value = str(value).encode(locale.getpreferredencoding())
        return value[:self.length].ljust(self.length)


class DbfNumericField(DbfField):
    """Definition of the numeric field."""

    type_code = "N"
    # XXX: now I'm not sure it was a good idea to make a class field
    # `defaultValue` instead of a generic method as it was implemented
    # previously -- it's ok with all types except number, cuz
    # if self.decimalCount is 0, we should return 0 and 0.0 otherwise.
    default_value = 0

    def decode_value(self, value):
        """Return a number decoded from ``value``.

        If decimals is zero, value will be decoded as an integer;
        or as a float otherwise.

        Return:
            Return value is a int (long) or float instance.

        """
        value = value.strip(b" \x00").decode(locale.getpreferredencoding())
        if "." in value:
            # a float (has decimal separator)
            return float(value)
        elif value:
            # must be an integer
            return int(value)
        else:
            return 0

    def encode_value(self, value):
        """Return string containing encoded ``value``."""
        _rv = ("%*.*f" % (self.length, self.decimal_count, value))
        if len(_rv) > self.length:
            _ppos = _rv.find(".")
            if not (0 <= _ppos <= self.length):
                raise ValueError("[%s] Numeric overflow: %s (field width: %i)"
                                 % (self.name, _rv, self.length))

            _rv = _rv[:self.length]
        return _rv.encode(locale.getpreferredencoding())


class DbfFloatField(DbfNumericField):
    """Definition of the float field - same as numeric."""

    type_code = "F"


class DbfIntegerField(DbfField):
    """Definition of the integer field."""

    type_code = "I"
    default_length = 4
    default_value = 0

    def decode_value(self, value):
        """Return an integer number decoded from ``value``."""
        return struct.unpack("<i", value)[0]

    def encode_value(self, value):
        """Return string containing encoded ``value``."""
        return struct.pack("<i", int(value))


class DbfCurrencyField(DbfField):
    """Definition of the currency field."""

    type_code = "Y"
    default_length = 8
    default_value = 0.0

    def decode_value(self, value):
        """Return float number decoded from ``value``."""
        return struct.unpack("<q", value)[0] / 10000.

    def encode_value(self, value):
        """Return string containing encoded ``value``."""
        return struct.pack("<q", round(value * 10000))


class DbfLogicalField(DbfField):
    """Definition of the logical field."""

    type_code = "L"
    default_value = -1
    default_length = 1

    def decode_value(self, value):
        """Return True, False or -1 decoded from ``value``."""
        # Note: value always is 1-char string
        if value == b"?":
            return -1
        if value in b"NnFf ":
            return False
        if value in b"YyTt":
            return True
        raise ValueError("[%s] Invalid logical value %r" % (self.name, value))

    def encode_value(self, value):
        """Return a character from the "TF?" set.

        Return:
            Return value is "T" if ``value`` is True
            "?" if value is -1 or False otherwise.

        """
        if value is True:
            return b"T"
        elif value == -1:
            return b"?"
        else:
            return b"F"


class DbfMemoField(DbfField):
    """Definition of the memo field."""

    type_code = "M"
    default_value = b"\x00" * 4
    default_length = 4
    # MemoFile instance.  Must be set before reading or writing to the field.
    file = None
    # MemoData type for strings written to the memo file
    memoType = MemoData.TYPE_MEMO

    def decode_value(self, value):
        """Return MemoData instance containing field data."""
        _block = struct.unpack("<L", value)[0]
        if _block:
            return self.file.read(_block)
        else:
            return MemoData("", self.memoType)

    def encode_value(self, value):
        """Return raw data string encoded from a ``value``.

        Note: this is an internal method.

        """
        if value:
            return struct.pack("<L", self.file.write(MemoData(value, self.memoType)))
        else:
            return self.default_value


class DbfGeneralField(DbfField):
    """Definition of the general (OLE object) field."""

    type_code = "G"
    memoType = MemoData.TYPE_OBJECT


class DbfDateField(DbfField):
    """Definition of the date field."""

    type_code = "D"

    @utils.classproperty
    def default_value(cls):
        return datetime.date.today()

    # "yyyymmdd" gives us 8 characters
    default_length = 8

    def decode_value(self, value):
        """Return a ``datetime.date`` instance decoded from ``value``."""
        if value.strip():
            return utils.get_gate(value)
        else:
            return None

    def encode_value(self, value):
        """Return a string-encoded value.

        ``value`` argument should be a value suitable for the
        `utils.getDate` call.

        Return:
            Return value is a string in format "yyyymmdd".

        """
        if value:
            return utils.get_gate(value).strftime("%Y%m%d").encode(locale.getpreferredencoding())
        else:
            return b" " * self.length


class DbfDateTimeField(DbfField):
    """Definition of the timestamp field."""

    # a difference between JDN (Julian Day Number)
    # and GDN (Gregorian Day Number). note, that GDN < JDN
    JDN_GDN_DIFF = 1721425
    type_code = "T"

    @utils.classproperty
    def default_value(cls):
        return datetime.datetime.now()

    # two 32-bits integers representing JDN and amount of
    # milliseconds respectively gives us 8 bytes.
    # note, that values must be encoded in LE byteorder.
    default_length = 8

    def decode_value(self, value):
        """Return a `datetime.datetime` instance."""
        assert len(value) == self.length
        # LE byteorder
        _jdn, _msecs = struct.unpack("<2I", value)
        if _jdn >= 1:
            _rv = datetime.datetime.fromordinal(_jdn - self.JDN_GDN_DIFF)
            _rv += datetime.timedelta(0, _msecs / 1000.0)
        else:
            # empty date
            _rv = None
        return _rv

    def encode_value(self, value):
        """Return a string-encoded ``value``."""
        if value:
            value = utils.get_date_time(value)
            # LE byteorder
            _rv = struct.pack("<2I", value.toordinal() + self.JDN_GDN_DIFF,
                              (value.hour * 3600 + value.minute * 60 + value.second) * 1000)
        else:
            _rv = b"\x00" * self.length

        _rv = _rv.encode(locale.getpreferredencoding())
        assert len(_rv) == self.length
        return _rv


_fieldsRegistry = {}


def register_field(field_class):
    """Register field definition class.

    ``field_class`` should be subclass of the `DbfField`.

    Use `lookupFor` to retrieve field definition class
    by the type code.

    """
    assert field_class.type_code is not None, "Type code isn't defined"
    _fieldsRegistry[field_class.type_code.upper()] = field_class


def field_class_of(type_code):
    """Return field definition class for the given type code.

    ``type_code`` must be a single character. That type should be
    previously registered.

    Use `registerField` to register new field class.

    Return:
        Return value is a subclass of the `DbfField`.

    """
    return _fieldsRegistry[type_code.upper()]

## register generic types

for (type_code, klass) in list(globals().items()):
    if (isinstance(klass, type) and
            issubclass(klass, DbfField) and klass is not DbfField):
        __all__.append(type_code)
        register_field(klass)
del type_code, klass

# vim: et sts=4 sw=4 :
