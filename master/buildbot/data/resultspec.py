# This file is part of Buildbot.  Buildbot is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation, version 2.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Copyright Buildbot Team Members
from future.utils import iteritems

from twisted.python import log

from buildbot.data import base


class FieldBase(object):

    """
    This class implements a basic behavior
    to wrap value into a `Field` instance

    """
    __slots__ = ['field', 'op', 'values']

    singular_operators = {
        'eq': lambda d, v: d == v[0],
        'ne': lambda d, v: d != v[0],
        'lt': lambda d, v: d < v[0],
        'le': lambda d, v: d <= v[0],
        'gt': lambda d, v: d > v[0],
        'ge': lambda d, v: d >= v[0],
        'contains': lambda d, v: v[0] in d,
    }

    plural_operators = {
        'eq': lambda d, v: d in v,
        'ne': lambda d, v: d not in v,
        'contains': lambda d, v: set(v) <= set(d),
    }

    def __init__(self, field, op, values):
        self.field = field
        self.op = op
        self.values = values

    def getOperator(self):
        v = self.values
        if len(v) == 1:
            ops = self.singular_operators
        else:
            ops = self.plural_operators
            v = set(v)
        return ops[self.op]

    def apply(self, data):
        fld = self.field
        v = self.values
        f = self.getOperator()
        return (d for d in data if f(d[fld], v))

    def __repr__(self):
        return "resultspec.{}('{}','{}',{})".format(self.__class__.__name__, self.field, self.op, self.values)

    def __eq__(self, b):
        for i in self.__slots__:
            if getattr(self, i) != getattr(b, i):
                return False
        return True

    def __ne__(self, b):
        return not (self == b)


class Property(FieldBase):

    """
    Wraps ``property`` type value(s)

    """


class Filter(FieldBase):

    """
    Wraps ``filter`` type value(s)

    """


def nonecmp(a, b):
    # Some fields are nullable, and could raise TypeException, when REST is requesting sorting
    # I order to fix that, we create a custom cmp function which treats None
    # as smaller than anything
    if a is None and b is None:
        return 0
    if a is None:
        return -1
    if b is None:
        return 1
    return cmp(a, b)


class ResultSpec(object):

    __slots__ = ['filters', 'fields', 'properties',
                 'order', 'limit', 'offset', 'fieldMapping']

    def __init__(self, filters=None, fields=None, properties=None, order=None,
                 limit=None, offset=None):
        self.filters = filters or []
        self.properties = properties or []
        self.fields = fields
        self.order = order
        self.limit = limit
        self.offset = offset
        self.fieldMapping = {}

    def __repr__(self):
        return "ResultSpec(**" + repr(dict(filters=self.filters, fields=self.fields,
                                           properties=self.properties,
                                           order=self.order, limit=self.limit, offset=self.offset)) + ")"

    def __eq__(self, b):
        for i in ['filters', 'fields', 'properties', 'order', 'limit', 'offset']:
            if getattr(self, i) != getattr(b, i):
                return False
        return True

    def __ne__(self, b):
        return not (self == b)

    def popProperties(self):
        values = []
        for p in self.properties:
            if p.field == 'property' and p.op == 'eq':
                self.properties.remove(p)
                values = p.values
                break
        return values

    def popFilter(self, field, op):
        for f in self.filters:
            if f.field == field and f.op == op:
                self.filters.remove(f)
                return f.values

    def popOneFilter(self, field, op):
        v = self.popFilter(field, op)
        return v[0] if v is not None else None

    def popBooleanFilter(self, field):
        eqVals = self.popFilter(field, 'eq')
        if eqVals and len(eqVals) == 1:
            return eqVals[0]
        neVals = self.popFilter(field, 'ne')
        if neVals and len(neVals) == 1:
            return not neVals[0]

    def popStringFilter(self, field):
        eqVals = self.popFilter(field, 'eq')
        if eqVals and len(eqVals) == 1:
            return eqVals[0]

    def popIntegerFilter(self, field):
        eqVals = self.popFilter(field, 'eq')
        if eqVals and len(eqVals) == 1:
            try:
                return int(eqVals[0])
            except ValueError:
                raise ValueError("Filter value for {} should be integer, but got: {}".format(
                    field, eqVals[0]))

    def removePagination(self):
        self.limit = self.offset = None

    def removeOrder(self):
        self.order = None

    def popField(self, field):
        try:
            i = self.fields.index(field)
        except ValueError:
            return False
        del self.fields[i]
        return True

    def findColumn(self, query, field):
        # will throw key error if field not in mapping
        mapped = self.fieldMapping[field]
        for col in query.inner_columns:
            if str(col) == mapped:
                return col
        raise KeyError("unable to find field {} in query".format(field))

    def applyFilterToSQLQuery(self, query, f):
        field = f.field
        col = self.findColumn(query, field)
        # as sqlalchemy is overriding python operators, we can just use the same
        # python code generated by the filter
        return query.where(f.getOperator()(col, f.values))

    def applyOrderToSQLQuery(self, query, o):
        reverse = False
        if o.startswith('-'):
            reverse = True
            o = o[1:]
        col = self.findColumn(query, o)
        if reverse:
            col = col.desc()
        return query.order_by(col)

    def applyToSQLQuery(self, query):
        filters = self.filters
        order = self.order
        unmatched_filters = []
        unmatched_order = []
        # apply the filters if the name of field is found in the model, and
        # db2data
        for f in filters:
            try:
                query = self.applyFilterToSQLQuery(query, f)
            except KeyError:
                # if filter is unmatched, we will do the filtering manually in
                # self.apply
                unmatched_filters.append(f)

        # apply order if necessary
        if order:
            for o in order:
                try:
                    query = self.applyOrderToSQLQuery(query, o)
                except KeyError:
                    # if order is unmatched, we will do the ordering manually
                    # in self.apply
                    unmatched_order.append(o)

        # we cannot limit in sql if there is missing filtering or ordering
        if unmatched_filters or unmatched_order:
            if self.offset is not None or self.limit is not None:
                log.msg("Warning: limited data api query is not backed by db because of following filters",
                        unmatched_filters, unmatched_order)
            self.filters = unmatched_filters
            self.order = unmatched_order
            return query, None

        count_query = query.alias('q').count()
        self.order = None
        self.filters = []
        # finally, slice out the limit/offset
        if self.offset is not None:
            query = query.offset(self.offset)
            self.offset = None

        if self.limit is not None:
            query = query.limit(self.limit)
            self.limit = None

        return query, count_query

    def thd_execute(self, conn, q, dictFromRow):
        offset, limit = self.offset, self.limit
        q, qc = self.applyToSQLQuery(q)
        res = conn.execute(q)
        rv = [dictFromRow(row) for row in res.fetchall()]

        if qc is not None and (offset or limit):
            total = conn.execute(qc).scalar()
            rv = base.ListResult(rv)
            rv.offset, rv.total, rv.limit = offset, total, limit
        return rv

    def apply(self, data):
        if data is None:
            return data

        if self.fields:
            fields = set(self.fields)

            def includeFields(d):
                return dict((k, v) for k, v in iteritems(d)
                            if k in fields)
            applyFields = includeFields
        else:
            fields = None

        if isinstance(data, dict):
            # item details
            if fields:
                data = applyFields(data)
            return data
        else:
            filters = self.filters
            order = self.order

            # item collection
            if isinstance(data, base.ListResult):
                # if pagination was applied, then fields, etc. must be empty
                assert not fields and not order and not filters, \
                    "endpoint must apply fields, order, and filters if it performs pagination"
                offset, total = data.offset, data.total
                limit = data.limit
            else:
                offset, total = None, None
                limit = None

            if fields:
                data = (applyFields(d) for d in data)

            # link the filters together and then flatten to list
            for f in self.filters:
                data = f.apply(data)
            data = list(data)

            if total is None:
                total = len(data)

            # precompute the ordering functions and sort
            if self.order:
                order = [(lambda a, b, k=k[1:]: nonecmp(b[k], a[k]))
                         if k[0] == '-' else
                         (lambda a, b, k=k: nonecmp(a[k], b[k]))
                         for k in self.order]

                def cmpFunc(a, b):
                    for f in order:
                        c = f(a, b)
                        if c:
                            return c
                    return 0
                data.sort(cmp=cmpFunc)

            # finally, slice out the limit/offset
            if self.offset is not None or self.limit is not None:
                if offset is not None or limit is not None:
                    raise AssertionError("endpoint must clear offset/limit")
                end = ((self.offset or 0) + self.limit
                       if self.limit is not None
                       else None)
                data = data[self.offset:end]
                offset = self.offset
                limit = self.limit

            rv = base.ListResult(data)
            rv.offset, rv.total = offset, total
            rv.limit = limit
            return rv