#!/usr/bin/env python
import argparse
import hcl
import sys
import logging
from terraform_utils.modules_utils import *

parser = argparse.ArgumentParser(description='Change module source git url to point to given ref')
parser.add_argument('--ref', help='Git ref (e.g commit SHA or branch)')
parser.add_argument('-D', '--debug', help='Enables debug mode for extra information', action="store_true")

args = parser.parse_args()
ref = args.ref
debug = args.debug
log_level = logging.INFO

if debug:
    log_level = logging.DEBUG

logging.basicConfig(stream=sys.stderr, level=log_level)


def replace_all(file_path, search_exp, replace_exp):
    with open(file_path, 'r') as f:
        contents = f.read()

    contents = contents.replace(search_exp, replace_exp)
    with open(file_path, 'w') as f:
        f.write(contents)


def update_source_version(tf_modules_file, git_ref):
    source_path = None
    with open(tf_modules_file, "r+") as fp:
        modules_tf = hcl.load(fp)
        for source in modules_tf["module"].values():
            source_path = source["source"]

    new_source_path = '{}?ref={}'.format(source_path.split('?', 1)[0], git_ref)
    logging.info("Replacing module source from {} to {}".format(source_path, new_source_path))
    replace_all(tf_modules_file, source_path, new_source_path)

    return True


working_dir = os.getcwd()

module_file = get_module_file(working_dir)

updated = update_source_version(module_file, ref)
logging.info("Successfully updated module source") if updated else logging.info("Failed to update")
