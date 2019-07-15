#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

"""Helper to symlink Terraform component modules.

Create symlinks to terraform files in m2a path by matching module names
to project in services.json.
"""

from __future__ import (absolute_import,
                        unicode_literals, print_function, division)

import argparse
import glob
import logging
import os
import os.path
import sys

from terraform_utils.modules_utils import (
    get_module_paths,
    get_module_source_terraform_paths,
)


logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s: %(message)s',
)
LOGGER = logging.getLogger()


class SymlinkError(Exception):
    """Base exception for all symlinking errors."""


def get_paths_to_symlink(modules, services):
    """Match required modules to service paths.

    :param modules: Modules to find service paths for.
    :type modules: Iterable[str]
    :param services: Mapping of modules to their paths.
    :type services: Mapping[str, str]

    :returns: Mapping of module names to service paths.
    :rtype: Dict[str, str]
    """
    paths = dict()
    for module in modules:
        if module in services:
            paths[module] = services[module]
        else:
            raise SymlinkError(
                'No path found for module \'{}\''.format(module))
    LOGGER.debug('paths to symlink: %s', paths)
    return paths


def create_symlinks(terraform_dir, paths):
    """Symlink modules into place.

    :param terraform_dir: Path to directory to create symlinks in.
    :type terraform_dir: str
    :param paths: Mapping of module names to service paths.
    :type: Mapping[str, str]
    """
    for module, source in paths.iteritems():
        target = "{}/{}".format(terraform_dir, module)
        if os.path.islink(target):
            os.unlink(target)
        LOGGER.info('Creating symlink %s -> %s', source, target)
        os.symlink(source, target)


def _main():
    """Helper utility entry-point."""
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog="\n".join(__doc__.splitlines()[1:]),
    )
    parser.add_argument(
        '-p',
        '--m2a_path',
        help='Path to directory the module checkouts',
        required=True,
    )
    parser.add_argument(
        '-e',
        '--env',
        help='Environment of the modules file',
        required=True,
    )
    args = parser.parse_args()
    env = args.env
    m2a_path = os.path.realpath(args.m2a_path)
    terraform_dir = os.path.join(os.getcwd(), 'terraform', env)
    LOGGER.info('M2A path: %s', m2a_path)
    LOGGER.info('Terraform path: %s', terraform_dir)
    module_glob = os.path.join(terraform_dir, 'modules*.tf')
    module_names = []
    for module_file in glob.iglob(module_glob):
        for module_name in get_module_paths(module_file):
            if module_name not in module_names:
                module_names.append(module_name)
                LOGGER.debug(
                    'Discovered \'%s\' from %s', module_name, module_file)
    module_paths = get_module_source_terraform_paths(module_names, m2a_path)
    try:
        create_symlinks(
            terraform_dir, get_paths_to_symlink(module_names, module_paths))
    except SymlinkError as error:
        LOGGER.error('Unable to create symlinks: %s;'
                     ' is the appropriate repository'
                     ' available on M2A path (%s)?', error, m2a_path)
        sys.exit(1)


if __name__ == '__main__':
    _main()
