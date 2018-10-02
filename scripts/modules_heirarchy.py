#!/usr/bin/env python
import argparse
import os.path
import hcl
import json

from collections import deque

parser = argparse.ArgumentParser(description="Create a release file")
parser.add_argument('--ci', help="Set to true if a ci environment to set common modules as external",
                    action='store_true')
parser.add_argument('--target', help="Path to modules.json file")
args = parser.parse_args()
ci = args.ci
target = args.target

data = {}
if ci:
    data['external_dependencies'] = ['networking']

modules = {}
for dir_path, _, filenames in os.walk('.'):
    for filename in [f for f in filenames if f == 'remote_states.tf']:
        with open(os.path.join(dir_path, filename), "r") as my_file:
            outputs = hcl.load(my_file)
            for output in outputs["data"].values():
                module_name = os.path.basename(dir_path)
                pipeline = dir_path.replace("./", '').replace("/", "-")
                modules[module_name] = []
                for key in output.keys():
                    if key not in data['external_dependencies']:
                        modules[module_name].append(key)


def sort_modules(modules_to_sort):
    reverse_order = deque()
    enter = set(modules)
    state = {}

    def depth_first_search(node):
        state[node] = False
        for dependency in modules_to_sort.get(node, ()):
            key_state = state.get(dependency, None)
            print("key_state", key_state)
            if key_state is False:
                raise ValueError("cycle")
            if key_state is True:
                continue
            enter.discard(dependency)
            depth_first_search(dependency)
        reverse_order.appendleft(node)
        state[node] = True

    while enter:
        depth_first_search(enter.pop())

    reverse_order.reverse()
    return reverse_order


data['order'] = list(sort_modules(modules))

with open(target, "w") as new_file:
    json.dump(data, new_file, indent=4)
