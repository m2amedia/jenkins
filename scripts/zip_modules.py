#!/usr/bin/env python
import argparse
import subprocess
import multiprocessing
from terraform_utils.modules_utils import *


def zip_modules(m2a_local_path, env, zip_dir="{}/terraform/lambda_files".format(os.getcwd())):
    working_dir = "{}/terraform/".format(os.getcwd())
    module_file = '{}/{}/modules.tf'.format(working_dir, env)
    if not os.path.exists(module_file):
        print('No modules.tf file - skipping zip')
        return

    if not os.path.isdir(zip_dir):
        os.mkdir(zip_dir)

    # for each module call zip-components with output going to terraform/lambda_files
    modules = get_module_paths(module_file)
    module_source_paths = get_module_source_paths(modules, m2a_local_path)

    zip_procs = [["zip-components.py", "-c", module_source_path, "-z", zip_dir] for module_source_path in module_source_paths.values()]

    pool = multiprocessing.Pool()
    pool.map(subprocess.check_output, zip_procs)
    pool.close()
    pool.join()

    print("Done")


def main():
    parser = argparse.ArgumentParser(
        description='Zips components within modules and copies them in terraform/lambda_files')
    parser.add_argument('m2a_path', help='Path to directory the module checkouts')
    parser.add_argument('env', help='Environment of the modules file')
    args = parser.parse_args()
    m2a_path = args.m2a_path
    env = args.env

    zip_modules(m2a_path, env)


if __name__ == "__main__":
    main()
