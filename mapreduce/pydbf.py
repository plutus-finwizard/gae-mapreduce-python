import struct
import datetime
import decimal
import itertools
import StringIO
import logging

from google.appengine.ext import blobstore

__all__ = ['DbfInfo', 'DbfReader']

class DbfInfo(object):

    # Maintaining properties same as `BlobInfo`
    _all_properties = frozenset(['content_type', 'creation', 'filename',
                               'size', 'md5_hash', 'gs_object_name'])

    def __init__(self, blob_key):
        f = blobstore.BlobReader(blob_key)
        self.size, header_len = struct.unpack('<xxxxLH22x', f.read(32))

    @classmethod
    def get(cls, blob_key):
        return cls(blob_key)

class DbfReader(object):
    def __init__(self, blob_key, start_position=0):
        f = blobstore.BlobReader(blob_key)

        self.start_position = start_position
        self.size, self.header_len = struct.unpack('<xxxxLH22x', f.read(32))
        self.number_of_fields = (self.header_len - 33) // 32

        self.fields = []
        for fieldno in xrange(self.number_of_fields):
            name, typ, size, deci = struct.unpack('<11sc4xBB14x', f.read(32))
            name = name.replace('\0', '')       # eliminate NULs from string
            self.fields.append((name, typ, size, deci))

        terminator = f.read(1)
        assert terminator == '\r'

        self.fields.insert(0, ('DeletionFlag', 'C', 1, 0))
        self.format = ''.join(['%ds' % fieldinfo[2] for fieldinfo in self.fields])
        self.format_size = struct.calcsize(self.format)

        if self.start_position != 0:
            f.seek(self.header_len + (self.start_position*self.format_size), 0)

        self.iter = self.__iter__(f)

    def __iter__(self, f):
        for self.start_position in xrange(self.start_position+1, self.size+1):
            record = struct.unpack(self.format, f.read(self.format_size))
            if record[0] != ' ':
                continue                        # deleted record

            result = {}
            for (name, typ, size, deci), value in itertools.izip(self.fields, record):
                if name == 'DeletionFlag':
                    continue

                value = value.replace('\0', '').strip()
                # if typ == "N":
                #     value = value.replace('\0', '').lstrip()
                #     if value == '':
                #         value = 0
                #     elif deci:
                #         value = decimal.Decimal(value)
                #     else:
                #         value = int(value)
                # if typ == 'D':
                #     y, m, d = int(value[:4]), int(value[4:6]), int(value[6:8])
                #     value = datetime.date(y, m, d)
                # # elif typ == 'L':
                #     value = (value in 'YyTt' and 'T') or (value in 'NnFf' and 'F') or '?'
                # elif typ == 'F':
                #     value = float(value)

                result[name] = value
            yield result

    def readline(self):
        return self.iter.next()

    def tell(self):
        return self.start_position
