#!/usr/bin/python
# -*- coding: utf-8 -*-
import sys
import os
import subprocess
from optparse import OptionParser

def tab(indent):
    return '    ' * indent

class Int64Property:
    def gen_result(self, out, indent, stmt, k, idx):
        print >>out, tab(indent) + "%s %s = sqlite3_column_int64(%s, %d);" % (self.sqlite3_type(), k, stmt, idx)

    def gen_bind(self, out, indent, stmt, k, idx):
        print >>out, tab(indent) + "sqlite3_bind_int64(%s, %d, %s);" % (stmt, idx, k)

    def sqlite3_type(self):
        return "int64_t"

    def sql_type(self):
        return "BIGINT"

class IntegerProperty:
    def gen_result(self, out, indent, stmt, k, idx):
        print >>out, tab(indent) + "%s %s = sqlite3_column_int(%s, %d);" % (self.sqlite3_type(), k, stmt, idx)

    def gen_bind(self, out, indent, stmt, k, idx):
        print >>out, tab(indent) + "sqlite3_bind_int(%s, %d, %s);" % (stmt, idx, k)

    def sqlite3_type(self):
        return "int"

    def sql_type(self):
        return "INT"

class TextProperty:
    def gen_result(self, out, indent, stmt, k, idx):
        print >>out, tab(indent) + "%s %s = reinterpret_cast<%s>(sqlite3_column_text(%s, %d));" % (self.sqlite3_type(), k, self.sqlite3_type(), stmt, idx)

    def gen_bind(self, out, indent, stmt, k, idx):
        print >>out, tab(indent) + "sqlite3_bind_text(%s, %d, %s, -1, NULL);" % (stmt, idx, k)

    def sqlite3_type(self):
        return "const char *"

    def sql_type(self):
        return "TEXT"

class Query:
    def __init__(self, **columns):
        self.cols = columns


    def gen_result(self, out, indent, stmt, idx = 0):
        for k, v in self.cols.iteritems():
            v.gen_result(out, indent, stmt, k, idx)
            idx += 1
        return idx

    def gen_bind(self, out, indent, stmt, binds, idx = 0):
        for k, v in binds.iteritems():
            v.gen_bind(out, indent, stmt, k, idx)
            idx += 1
        return idx

class CreateTable(Query):
    def table(self, name):
        self.table_name = name
        return self

    def gen_func(self, out, indent, name, decl, prefix):
        print >>out, tab(indent) + prefix + "int %s(sqlite3 *db, char **errmsg)" % (name) + (";" if decl else "")
        if decl:
            return self

        lines = [ "CREATE TABLE %s (" % self.table_name ]
        first = True
        for k, v in self.cols.iteritems():
            lines.append('%s   %s %s' % ((" " if first else ","), k, v.sql_type()))
            first = False
        lines.append(')')

        print >>out, tab(indent) + "{"
        print >>out, tab(indent) + '    const char *sql = ""'
        for line in lines:
            print >>out, tab(indent) + '        "%s\\n"' % line
        print >>out, tab(indent) + '        ;'
        print >>out
        print >>out, tab(indent) + "    int r = sqlite3_exec(db, sql, NULL, NULL, errmsg);"
        print >>out, tab(indent) + "    return r;"
        print >>out, tab(indent) + "}"
        print >>out
        return self

class Insert(Query):
    def table(self, name):
        self.table_name = name
        return self

    def prepare(self, out, indent, stmt):
        sql_query = 'INSERT INTO %s(%s) VALUES (%s)' % (
            self.table_name,
            ", ".join(self.cols.iterkeys()),
            ", ".join([ ":" + k for k in self.cols.iterkeys() ]),
        )
        print >>out, tab(indent) + 'sqlite3_prepare_v2(db, "%s", %d, &%s, NULL);' % (
            sql_query,
            len(sql_query),
            stmt
        )
        return self

    def gen_func(self, out, indent, name, decl, prefix):
        stmt = "stmt"
        params = [ "sqlite3 *db" ]
        for k, v in self.cols.iteritems():
            params.append(v.sqlite3_type() + " " + k)

        print >>out, tab(indent) + prefix + "int %s(%s)" % (name, ", ".join(params)) + (";" if decl else "")
        if decl:
            return self

        print >>out, tab(indent) + "{"
        print >>out, tab(indent) + "    sqlite3_stmt *stmt = NULL;"
        print >>out, tab(indent) + "    scoped_exit ensure_finalize(&stmt); // sqlite3_finalize(stmt)"
        print >>out
        self.prepare(out, indent + 1, stmt)
        print >>out
        self.gen_bind(out, indent + 1, stmt, self.cols)
        print >>out
        print >>out, tab(indent) + "    int r = sqlite3_step(%s);" % stmt
        print >>out, tab(indent) + "    return r;"
        print >>out, tab(indent) + "}"
        print >>out

        print >>out, tab(indent) + "template <typename Model>"
        print >>out, tab(indent) + prefix + "int %s_with_model(sqlite3 *db, Model const& m)" % name
        print >>out, tab(indent) + "{"
        print >>out, tab(indent) + "    return %s(db, %s);" % (name, ", ".join(["m." + k for k in self.cols.iterkeys()]))
        print >>out, tab(indent) + "}"
        print >>out

        return self

class Update(Query):
    def __init__(self, **columns):
        Query.__init__(self, **columns)
        self.sql_query = ''
        self.binds = {}

    def table(self, name):
        self.table_name = name
        return self

    def sql(self, sql_query, **bind):
        self.sql_query = sql_query
        self.binds = bind
        return self

    def prepare(self, out, indent, stmt):
        sql_query = 'UPDATE %s SET %s %s' % (
            self.table_name,
            ", ".join([ k + "=:" + k for k in self.cols.iterkeys() ]),
            self.sql_query,
        )
        print >>out, tab(indent) + 'sqlite3_prepare_v2(db, "%s", %d, &%s, NULL);' % (
            sql_query,
            len(sql_query),
            stmt
        )
        return self

    def gen_func(self, out, indent, name, decl, prefix):
        union_args = self.cols.copy()
        union_args.update(self.binds)

        stmt = "stmt"
        params = [ "sqlite3 *db" ]
        for k, v in union_args.iteritems():
            params.append(v.sqlite3_type() + " " + k)

        print >>out, tab(indent) + prefix + "int %s(%s)" % (name, ", ".join(params)) + (";" if decl else "")
        if decl:
            return self

        print >>out, tab(indent) + "{"
        print >>out, tab(indent) + "    sqlite3_stmt *stmt = NULL;"
        print >>out, tab(indent) + "    scoped_exit ensure_finalize(&stmt); // sqlite3_finalize(stmt)"
        print >>out
        self.prepare(out, indent + 1, stmt)
        print >>out
        idx = self.gen_bind(out, indent + 1, stmt, self.cols)
        print >>out
        self.gen_bind(out, indent + 1, stmt, self.binds, idx)
        print >>out
        print >>out, tab(indent) + "    int r = sqlite3_step(%s);" % stmt
        print >>out, tab(indent) + "    return r;"
        print >>out, tab(indent) + "}"
        print >>out

        print >>out, tab(indent) + "template <typename Model>"
        print >>out, tab(indent) + prefix + "int %s_with_model(sqlite3 *db, Model const& m)" % name
        print >>out, tab(indent) + "{"
        print >>out, tab(indent) + "    return %s(db, %s);" % (name, ", ".join(["m." + k for k in self.cols.iterkeys()]))
        print >>out, tab(indent) + "}"
        print >>out
        return self

class Delete(Query):
    def __init__(self, **columns):
        Query.__init__(self, **columns)
        self.sql_query = ''
        self.binds = {}

    def table(self, name):
        self.table_name = name
        return self

    def sql(self, sql_query, **bind):
        self.sql_query = sql_query
        self.binds = bind
        return self

    def prepare(self, out, indent, stmt):
        sql_query = 'DELETE FROM %s %s' % (
            self.table_name,
            self.sql_query,
        )
        print >>out, tab(indent) + 'sqlite3_prepare_v2(db, "%s", %d, &%s, NULL);' % (
            sql_query,
            len(sql_query),
            stmt
        )
        return self

    def gen_func(self, out, indent, name, decl, prefix):
        union_args = self.cols.copy()
        union_args.update(self.binds)

        stmt = "stmt"
        params = [ "sqlite3 *db" ]
        for k, v in union_args.iteritems():
            params.append(v.sqlite3_type() + " " + k)

        print >>out, tab(indent) + prefix + "int %s(%s)" % (name, ", ".join(params)) + (";" if decl else "")
        if decl:
            return self

        print >>out, tab(indent) + "{"
        print >>out, tab(indent) + "    sqlite3_stmt *stmt = NULL;"
        print >>out, tab(indent) + "    scoped_exit ensure_finalize(&stmt); // sqlite3_finalize(stmt)"
        print >>out
        self.prepare(out, indent + 1, stmt)
        print >>out
        self.gen_bind(out, indent + 1, stmt, self.binds)
        print >>out
        print >>out, tab(indent) + "    int r = sqlite3_step(%s);" % stmt
        print >>out, tab(indent) + "    return r;"
        print >>out, tab(indent) + "}"
        print >>out
        return self

class SelectRows(Query):
    def sql(self, sql_query, **bind):
        self.sql_query = sql_query
        self.binds = bind
        return self

    def prepare(self, out, indent, stmt):
        print >>out, tab(indent) + 'sqlite3_prepare_v2(db, "SELECT %s %s", %d, &%s, NULL);' % (
            ", ".join(self.cols.keys()), self.sql_query, len(self.sql_query), stmt)
        return self

    def gen_func(self, out, indent, name, decl, prefix):
        stmt = "stmt"
        params = [ "sqlite3 *db" ]
        for k, v in self.binds.iteritems():
            params.append(v.sqlite3_type() + " " + k)
        params.append("Handler handler")

        print >>out, tab(indent) + "template <typename Handler>"
        print >>out, tab(indent) + "void %s(%s)" % (name, ", ".join(params)) + (";" if decl else "")
        if decl:
            return self

        print >>out, tab(indent) + "{"
        print >>out, tab(indent) + "    sqlite3_stmt *stmt = NULL;"
        print >>out, tab(indent) + "    scoped_exit ensure_finalize(&stmt); // sqlite3_finalize(stmt)"
        print >>out
        self.prepare(out, indent + 1, stmt)
        print >>out
        self.gen_bind(out, indent + 1, stmt, self.binds)
        print >>out, tab(indent) + "    while (1) {"
        print >>out, tab(indent) + "        int r = sqlite3_step(%s);" % stmt
        print >>out, tab(indent) + "        if (r == SQLITE_ROW) {"
        self.gen_result(out, indent + 3, stmt)
        print >>out, tab(indent) + "            if (! handler(r, %s))" % (", ".join(self.cols.keys()))
        print >>out, tab(indent) + "                break;"
        print >>out, tab(indent) + "        } else {"
        print >>out, tab(indent) + "            handler(r);"
        print >>out, tab(indent) + "            break;"
        print >>out, tab(indent) + "        }"
        print >>out, tab(indent) + "    }"
        print >>out, tab(indent) + "}"
        print >>out
        return self.gen_func_model(out, indent, name, decl, prefix)

    def gen_func_model(self, out, indent, name, decl, prefix):
        stmt = "stmt"
        params = [ "sqlite3 *db", "Model& m" ]
        for k, v in self.binds.iteritems():
            params.append(v.sqlite3_type() + " " + k)
        params.append("Handler handler")

        print >>out, tab(indent) + "template <typename Model, typename Handler>"
        print >>out, tab(indent) + "void %s(%s)" % (name, ", ".join(params)) + (";" if decl else "")
        if decl:
            return self

        print >>out, tab(indent) + "{"
        print >>out, tab(indent) + "    sqlite3_stmt *stmt = NULL;"
        print >>out, tab(indent) + "    scoped_exit ensure_finalize(&stmt); // sqlite3_finalize(stmt)"
        print >>out
        self.prepare(out, indent + 1, stmt)
        print >>out
        self.gen_bind(out, indent + 1, stmt, self.binds)
        print >>out, tab(indent) + "    while (1) {"
        print >>out, tab(indent) + "        int r = sqlite3_step(%s);" % stmt
        print >>out, tab(indent) + "        if (r == SQLITE_ROW) {"
        self.gen_result(out, indent + 3, stmt)
        for k in self.cols.iterkeys():
            print >>out, tab(indent) + "            m.%s = %s;" % (k, k)
        print >>out, tab(indent) + "            if (! handler(r, &m))"
        print >>out, tab(indent) + "                break;"
        print >>out, tab(indent) + "        } else {"
        print >>out, tab(indent) + "            handler(r);"
        print >>out, tab(indent) + "            break;"
        print >>out, tab(indent) + "        }"
        print >>out, tab(indent) + "    }"
        print >>out, tab(indent) + "}"
        print >>out
        return self

queries = {
    "query_something" : SelectRows(
            id=IntegerProperty(),
            name=TextProperty(),
        ).sql("FROM users WHERE id=:id", id=IntegerProperty()),

    "query_something2" : SelectRows(
            id=IntegerProperty(),
            name=TextProperty(),
        ).sql("FROM users2 WHERE id=:id", id=IntegerProperty()),

    "insert_something" : Insert(
            id=IntegerProperty(),
            name=TextProperty(),
        ).table("XXX"),

    "update_something" : Update(
            id=IntegerProperty(),
            name=TextProperty(),
        ).table("XXX").sql("WHERE id=:id AND type=:type", id=IntegerProperty(), type=IntegerProperty()),

    "delete_something" : Delete(
        ).table("XXX").sql("WHERE id=:id AND type=:type", id=IntegerProperty(), type=IntegerProperty()),

    "create_table_something" : CreateTable(
            id=IntegerProperty(),
            name=TextProperty(),
        ).table("XXX"),
}

def generate_core(out, decl):
    indent = options.indent
    for name, query in queries.iteritems():
        query.gen_func(out, indent, name, decl, "inline ")

#
# Invoker
#

parser = OptionParser()
parser.add_option("-d", "--dir", action="store", type="string", dest="dir")
parser.add_option("-f", "--file", action="store", type="string", dest="file")
parser.add_option("-p", "--indent", action="store", type="int", dest="indent", default=0)
parser.add_option("-t", "--template", action="store", type="string", dest="template")
parser.add_option("--decl", action="store_true", dest="decl")
(options, args) = parser.parse_args()

if not options.file:
    parser.error("--file オプションがありません")

if len(args) == 0:
    parser.error("sub-commandがありません (core, android, ios)")

filename = []
if options.dir:
    subprocess.check_call(["mkdir", "-p", options.dir])
    filename.append(options.dir)

filename.append(options.file)

if args[0] == "core":
    with open("/".join(filename), 'wb') as out:
        if options.template:
            with open(options.template, 'rb') as tmpl:
                for line in tmpl:
                    if line == "%%\n":
                        break
                    print >>out, line,

                generate_core(out, options.decl)

                for line in tmpl:
                    print >>out, line,
        else:
            generate_core(out, options.decl)

