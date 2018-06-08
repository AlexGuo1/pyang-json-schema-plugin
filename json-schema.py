"""JSON Schema output plugin
"""

# pylint: disable=C0111

from __future__ import print_function

import optparse
import logging

import json

from pyang import plugin
from pyang import statements
from pyang import grammar
from pyang import types
from pyang import error

json_stmts = [

    # (<keyword>, <occurance when used>,
    #  (<argument type name | None>, <substmts>),
    #  <list of keywords where <keyword> can occur>)

    ('key', '*',
     ('string', None),
     ['list']),
]
json_module_name = 'json-module'

def pyang_plugin_init():
    plugin.register_plugin(JSONSchemaPlugin())

class JSONSchemaPlugin(plugin.PyangPlugin):
    # Register that we handle extensions from the YANG module
    # 'ietf-yang-metadata'
    #grammar.register_extension_module(json_module_name)

    '''
    # Register the special grammar
    for (stmt, occurance, (arg, rules), add_to_stmts) in json_stmts:
        grammar.add_stmt((json_module_name, stmt), (arg, rules))
        grammar.add_to_stmts_rules(add_to_stmts,
        [((json_module_name, stmt), occurance)])
    '''

    def add_output_format(self, fmts):
        self.multiple_modules = True
        fmts['json-schema'] = self

    def add_opts(self, optparser):
        optlist = [
            optparse.make_option('--json-schema-debug',
                                 dest='schema_debug',
                                 action="store_true",
                                 help='JSON Schema debug'),
            optparse.make_option('--json-schema-path',
                                 dest='schema_path',
                                 help='JSON Schema path'),
            optparse.make_option('--json-schema-title',
                                 dest='schema_title',
                                 help='JSON Schema title'),
            ]

        group = optparser.add_option_group("JSON Schema-specific options")
        group.add_options(optlist)

    def setup_ctx(self, ctx):
        ctx.opts.stmts = None

    def setup_fmt(self, ctx):
        ctx.implicit_errors = False

    def emit(self, ctx, modules, fd):
        root_stmt = modules[0]
        #logging.warning('emit:root:%s',root_stmt.arg)
        #logging.basicConfig(level=logging.DEBUG)
        if ctx.opts.schema_debug:
            logging.basicConfig(level=logging.DEBUG)
            print("")
        if ctx.opts.schema_path is not None:
            logging.debug("schema_path: %s", ctx.opts.schema_path)
            path = ctx.opts.schema_path
            root_stmt = find_stmt_by_path(modules[0], path)
        else:
            path = None

        if ctx.opts.schema_title is not None:
            schema_title = ctx.opts.schema_title
        else:
            schema_title = root_stmt.arg

        description_str = "Generated by pyang from module %s" % modules[0].arg
        result = {"title": schema_title,
                  "$schema": "http://json-schema.org/draft-04/schema#",
                  "description": description_str,
                  "type": "object",
                  "properties": {}}

        schema = produce_schema(root_stmt)
        result["properties"].update(schema)

        fd.write(json.dumps(result, indent=2))

def find_stmt_by_path(module, path):
    logging.debug("in find_stmt_by_path with: %s %s path: %s", module.keyword, module.arg, path)
	
    if path is not None:
        spath = path.split("/")
        if spath[0] == '':
            spath = spath[1:]

    children = [child for child in module.i_children
                if child.keyword in statements.data_definition_keywords]

    while spath is not None and len(spath) > 0:
        match = [child for child in children if child.arg == spath[0]
                 and child.keyword in statements.data_definition_keywords]
        if len(match) > 0:
            logging.debug("Match on: %s, path: %s", match[0].arg, spath)
            spath = spath[1:]
            children = match[0].i_children
            logging.debug("Path is now: %s", spath)
        else:
            logging.debug("Miss at %s, path: %s", children, spath)
            raise error.EmitError("Path '%s' does not exist in module" % path)

    logging.debug("Ended up with %s %s", match[0].keyword, match[0].arg)
    return match[0]


def produce_schema(root_stmt):
    logging.debug("in produce_schema: %s %s", root_stmt.keyword, root_stmt.arg)
    result = {}
    enums_dict = {}
    for enum, info in root_stmt.i_typedefs.iteritems():
        enum_list = []
        for tmp in info.substmts:
            for val in tmp.substmts:
                enum_list.append((val.arg, val.i_value))
        enums_dict[enum] = enum_list
        
    for child in root_stmt.i_children:
        #logging.warning('produce_schema:child.keyword:%s',child.keyword)
        if child.keyword in statements.data_definition_keywords:
            if child.keyword in producers:
                logging.debug("keyword hit on: %s %s", child.keyword, child.arg)
                add = producers[child.keyword](child)
                result.update(add)
            else:
                logging.debug("keyword miss on: %s %s", child.keyword, child.arg)
        else:
            logging.debug("keyword not in data_definition_keywords: %s %s", child.keyword,
                          child.arg)
    result['enums'] = enums_dict
    return result

def produce_type(type_stmt):
    logging.debug("In produce_type with: %s %s", type_stmt.keyword, type_stmt.arg,)
    type_id = type_stmt.arg

    if types.is_base_type(type_id):
        logging.debug("In produce_type base type: %s %s", type_stmt.keyword, type_stmt.arg)
        if type_id in _numeric_type_trans_tbl:
            type_str = numeric_type_trans(type_id)
        elif type_id in _other_type_trans_tbl:
            type_str = other_type_trans(type_id, type_stmt)
            logging.debug("else case, type_str:%s",type_str)
        else:
            logging.debug("Missing mapping of base type: %s %s",
                          type_stmt.keyword, type_stmt.arg)
            type_str = {"type": "string"}
    elif hasattr(type_stmt, "i_typedef") and type_stmt.i_typedef is not None:
        logging.debug("In produce_type  Found typedef type in: %s %s (typedef) %s",
                      type_stmt.keyword, type_stmt.arg, type_stmt.i_typedef)
        #typedef_type_stmt = type_stmt.i_typedef.search_one('type')
        #typedef_type = produce_type(typedef_type_stmt)
        #type_str = typedef_type
        type_str = {"type": type_stmt.arg}
    else:
        logging.debug("Missing mapping of: %s %s",
                      type_stmt.keyword, type_stmt.arg, type_stmt.i_typede)
        type_str = {"type": "string"}
    return type_str


def produce_leaf(stmt):
    logging.debug("in produce_leaf: %s %s", stmt.keyword, stmt.arg)
    arg = qualify_name(stmt)
    type_stmt = stmt.search_one('type')
    description = stmt.search_one('description').arg
    type_str = produce_type(type_stmt)
    if stmt.search_one(('ne-types', 'required')) is None:
        required = 'false'
    else:
        required = stmt.search_one(('ne-types', 'required')).arg

    if stmt.search_one(('ne-types', 'nonUpdatable')) is None:
        nonUpdatable = 'false'
    else:
        nonUpdatable = stmt.search_one(('ne-types', 'nonUpdatable')).arg
    return {arg: {'type': type_str['type'] , 'description':description, 'required' : required, 'nonUpdatable': nonUpdatable}}

def produce_list(stmt):
    logging.debug("in produce_list: %s %s,len(substmt)=%s,ichildren=%s", stmt.keyword, stmt.arg,len(stmt.substmts),stmt.i_children[0].keyword,)
    arg = qualify_name(stmt)
    if stmt.search_one('key') is None:
        logging.warning('produce_list: potentially invalid list with no key element')
        key = ''
    else:
        key = stmt.search_one('key').arg
    if stmt.search_one(('ne-types', 'ttlBased')) is None:
	    ttlBased = False
    else:
	    ttlBased = stmt.search_one(('ne-types', 'ttlBased')).arg

    if stmt.search_one(('ne-types', 'metaData')) is None:
	    metaData = "none"
    else:
	    metaData = stmt.search_one(('ne-types', 'metaData')).arg

    if stmt.search_one(('ne-types', 'clusterKey')) is None:
        clusterKey = "none"
    else:
        clusterKey = stmt.search_one(('ne-types', 'clusterKey')).arg
    if stmt.parent.keyword != "list":
        result = {arg: {"key":key,"type": "array", "items": [],'isTTLBased':ttlBased,'clusterKey':clusterKey,'metaData':metaData}}
        logging.debug( 'result when parent keyword is not list, result:%s',result,)
    else:
        result = {"type": "object", "properties": {arg: {"type": "array", "items": [],"key":key,'isTTLBased':ttlBased,'clusterKey':clusterKey,'metaData':metaData}}}
        logging.debug( 'result when parent keyword is list, result:%s',result,)

    if hasattr(stmt, 'i_children'):
        for child in stmt.i_children:
            if child.keyword in producers:
                logging.debug("keyword hit on: %s %s", child.keyword, child.arg)
                if stmt.parent.keyword != "list":
                    result[arg]["items"].append(producers[child.keyword](child))
                else:
                    result["properties"][arg]["items"].append(producers[child.keyword](child))
            else:
                logging.debug("keyword miss on: %s %s", child.keyword, child.arg)
    logging.debug("In produce_list for %s, returning %s", stmt.arg, result)
    return result

def produce_leaf_list(stmt):
    logging.debug("in produce_leaf_list: %s %s", stmt.keyword, stmt.arg)
    arg = qualify_name(stmt)
    type_stmt = stmt.search_one('type')
    type_id = type_stmt.arg

    if types.is_base_type(type_id) or type_id in _other_type_trans_tbl:
        type_str = produce_type(type_stmt)
        result = {arg: {"type": "array", "items": type_str}}
    else:
        logging.debug("Missing mapping of base type: %s %s, type: %s",
                      stmt.keyword, stmt.arg, type_id)
        result = {arg: {"type": "array", "items": [{"type": "string"}]}}
    return result

def produce_container(stmt):
    logging.debug("in produce_container: %s %s", stmt.keyword, stmt.arg)
    arg = qualify_name(stmt)
    config =True
    if stmt.search_one('config') is None:
        config = False
    else:
        logging.debug( "produce_container:%s", stmt.search_one('config').arg)
        config = stmt.search_one('config').arg
    if stmt.search_one('description') is None:
        description = ''
    else:
        description = stmt.search_one('description').arg
    if stmt.search_one(('ne-types', 'enterpriseDependent')) is None:
	    enterpriseDependent = False
    else:
	    enterpriseDependent = stmt.search_one(('ne-types', 'enterpriseDependent')).arg

    if stmt.parent.keyword != "list":
        result = {arg: {"type": "object", "properties": {"isConfig":config, 'isEnterpriseDependent':enterpriseDependent, 'description': description}}}
    else:
        result = {"type": "object", "properties": {arg:{"type": "object", 'description': description, "properties": {}},"isConfig":config, 'isEnterpriseDependent':enterpriseDependent}}

    if hasattr(stmt, 'i_children'):
        for child in stmt.i_children:
            if child.keyword in producers:
                logging.debug("keyword hit on: %s %s", child.keyword, child.arg)
                if stmt.parent.keyword != "list":
                    result[arg]["properties"].update(producers[child.keyword](child))
                else:
                    result["properties"][arg]["properties"].update(producers[child.keyword](child))
            else:
                logging.debug("keyword miss on: %s %s", child.keyword, child.arg)
    logging.debug("In produce_container, returning %s", result)
    return result

def produce_choice(stmt):
    logging.debug("in produce_choice: %s %s", stmt.keyword, stmt.arg)

    result = {}

    # https://tools.ietf.org/html/rfc6020#section-7.9.2
    for case in stmt.search("case"):
        if hasattr(case, 'i_children'):
            for child in case.i_children:
                if child.keyword in producers:
                    logging.debug("keyword hit on (long version): %s %s", child.keyword, child.arg)
                    result.update(producers[child.keyword](child))
                else:
                    logging.debug("keyword miss on: %s %s", child.keyword, child.arg)

    # Short ("case-less") version
    #  https://tools.ietf.org/html/rfc6020#section-7.9.2
    for child in stmt.substmts:
        logging.debug("checking on keywords with: %s %s", child.keyword, child.arg)
        if child.keyword in ["container", "leaf", "list", "leaf-list"]:
            logging.debug("keyword hit on (short version): %s %s", child.keyword, child.arg)
            result.update(producers[child.keyword](child))

    logging.debug("In produce_choice, returning %s", result)
    return result

producers = {
    # "module":     produce_module,
    "container":    produce_container,
    "list":         produce_list,
    "leaf-list":    produce_leaf_list,
    "leaf":         produce_leaf,
    "choice":       produce_choice,
}

_numeric_type_trans_tbl = {
    # https://tools.ietf.org/html/draft-ietf-netmod-yang-json-02#section-6
    "int": ("int", None),
    "int8": ("int8", None),
    "int16": ("int16", None),
    "int32": ("int32", "int32"),
    "int64": ("int64", "int64"),
    "uint8": ("number", None),
    "uint16": ("uint16", None),
    "uint32": ("uint32", "uint32"),
    "uint64": ("uint64", "uint64")
    }

def numeric_type_trans(dtype):
    trans_type = _numeric_type_trans_tbl[dtype][0]
    # Should include format string in return value
    # tformat = _numeric_type_trans_tbl[dtype][1]
    return {"type": trans_type}

def string_trans(stmt):
    logging.debug("in string_trans with stmt %s %s", stmt.keyword, stmt.arg)
    result = {"type": "string"}
    return result

def enumeration_trans(stmt):
    logging.debug("in enumeration_trans with stmt %s %s", stmt.keyword, stmt.arg)
    result = {"properties": {"type": {"enum": []}}}
    for enum in stmt.search("enum"):
        result["properties"]["type"]["enum"].append(enum.arg)
    logging.debug("In enumeration_trans for %s, returning %s", stmt.arg, result)
    return result

def bits_trans(stmt):
    logging.debug("in bits_trans with stmt %s %s", stmt.keyword, stmt.arg)
    result = {"type": "string"}
    return result

def boolean_trans(stmt):
    logging.debug("in boolean_trans with stmt %s %s", stmt.keyword, stmt.arg)
    result = {"type": "boolean"}
    return result

def empty_trans(stmt):
    logging.debug("in empty_trans with stmt %s %s", stmt.keyword, stmt.arg)
    result = {"type": "array", "items": [{"type": "null"}]}
    # Likely needs more/other work per:
    #  https://tools.ietf.org/html/draft-ietf-netmod-yang-json-10#section-6.9
    return result

def union_trans(stmt):
    logging.debug("in union_trans with stmt %s %s", stmt.keyword, stmt.arg)
    result = {"oneOf": []}
    for member in stmt.search("type"):
        member_type = produce_type(member)
        result["oneOf"].append(member_type)
    return result

def instance_identifier_trans(stmt):
    logging.debug("in instance_identifier_trans with stmt %s %s", stmt.keyword, stmt.arg)
    result = {"type": "string"}
    return result

def decimal_trans(stmt):
    logging.debug("in instance_identifier_trans with stmt %s %s", stmt.keyword, stmt.arg)
    result = {"type": "float64"}
    return result

def leafref_trans(stmt):
    logging.debug("in leafref_trans with stmt %s %s", stmt.keyword, stmt.arg)
    # TODO: Need to resolve i_leafref_ptr here 
    result = {"type": "string"}
    return result

_other_type_trans_tbl = {
    # https://tools.ietf.org/html/draft-ietf-netmod-yang-json-02#section-6
    "string":                   string_trans,
    "enumeration":              enumeration_trans,
    "bits":                     bits_trans,
    "boolean":                  boolean_trans,
    "empty":                    empty_trans,
    "union":                    union_trans,
    "instance-identifier":      instance_identifier_trans,
    "leafref":                  leafref_trans,
    "decimal64":                decimal_trans
}

def other_type_trans(dtype, stmt):
    return _other_type_trans_tbl[dtype](stmt)

def qualify_name(stmt):
    # From: draft-ietf-netmod-yang-json
    # A namespace-qualified member name MUST be used for all members of a
    # top-level JSON object, and then also whenever the namespaces of the
    # data node and its parent node are different.  In all other cases, the
    # simple form of the member name MUST be used.
    if stmt.parent.parent is None: # We're on top
        pfx = stmt.i_module.arg
        logging.debug("In qualify_name with: %s %s on top", stmt.keyword, stmt.arg)
        return pfx + ":" + stmt.arg
    if stmt.top.arg != stmt.parent.top.arg: # Parent node is different
        pfx = stmt.top.arg
        logging.debug("In qualify_name with: %s %s and parent is different", stmt.keyword, stmt.arg)
        return pfx + ":" + stmt.arg
    return stmt.arg
