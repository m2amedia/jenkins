import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
from multiprocessing.dummy import Pool
from terraform_utils.bcolors import *

from m2a_process_helper import run

# default command for terraform - can be set like this: utils_terraform.TERRAFORM_CMD = "/usr/bin/terraform_0.8.8"
TERRAFORM_CMD = "terraform"


def delete_local_state(local_state_folder_path):
    '''deprecated'''
    if os.path.exists(local_state_folder_path):
        print(('{}Deleting local Terraform state file'.format(bcolors.OKBLUE)))
        shutil.rmtree(local_state_folder_path)


def get_project_name():
    '''deprecated'''
    service_info = json.load(open("{}/services-info.json".format(os.getcwd())))
    if "project" in service_info and "name" in service_info["project"]:
        return service_info["project"]["name"]
    else:
        raise ValueError("{}Could not find project name in service-info.json".format(bcolors.FAIL))


def zip_files(zip_files_location="{}/terraform/lambda_files".format(os.getcwd())):
    if not os.path.isdir(zip_files_location):
        print(("{}Creating zip files as directory {} does not exist".format(bcolors.OKBLUE, zip_files_location)))
        subprocess.call(['zip-components.py'], shell=True)
        return

    zip_files_exists = True if os.listdir(zip_files_location) else False
    if not zip_files_exists:
        print(("{}Creating zip files for as files do not exist".format(bcolors.OKBLUE)))
        subprocess.call(['zip-components.py'], shell=True)


def get_file_sha256base64(file_path):
    blocksize = 65536
    m = hashlib.sha256()
    with open(file_path, 'rb') as f:
        buf = f.read(blocksize)
        while len(buf) > 0:
            m.update(buf)
            buf = f.read(blocksize)
    return base64.b64encode(m.digest())


def get_component_by_sha256base64(hash_str):
    zip_files_location = "{}/terraform/lambda_files".format(os.getcwd())
    for filename in os.listdir(zip_files_location):
        abs_file_path = os.path.join(zip_files_location, filename)
        if os.path.isfile(abs_file_path):
            if hash_str == get_file_sha256base64(abs_file_path):
                return os.path.splitext(os.path.basename(filename))[0]


def terraform_action(action, tf_env, tf_env_vars, extra_args=None, return_output=False):
    '''deprecated'''
    tf_dir = "terraform/{}".format(tf_env) if tf_env else ''
    command = action.split(' ')
    command.insert(0, TERRAFORM_CMD)

    if extra_args:
        if isinstance(extra_args, str):
            command.append(extra_args)
        else:
            command.extend(extra_args)

    if tf_dir is not "":
        command.append(tf_dir)
    print(("Executing command: `{}`".format(' '.join(command))))

    if return_output:
        process = subprocess.Popen(command,
                                   shell=False,
                                   stderr=subprocess.PIPE,
                                   stdout=subprocess.PIPE,
                                   env=tf_env_vars)
        (output, stderr) = process.communicate()
        return_code = process.wait()
    else:
        return_code = subprocess.call(command, shell=False, env=tf_env_vars)

    if return_code != 0:
        raise ValueError("Error executing command {}".format(command))

    return output if return_output else return_code


def terraform_get_output(output_name, tf_env_vars):
    return terraform_action("output", output_name, tf_env_vars, "")


def terraform_list_resources(tf_env_vars):
    return terraform_action("state list", '', tf_env_vars, return_output=True)


def terraform_outputs(modules, terraform_src_dir):
    all_outputs = dict()
    pool = Pool()
    def get_tf_output(module):
        (stdout, _) = run.cmd('terraform output -json -module={}'.format(module), cwd=terraform_src_dir)
        outputs = json.loads(stdout)
        return outputs

    all_outputs = dict()
    for output in pool.map(get_tf_output, modules):
        all_outputs.update(output)

    pool.close()
    return all_outputs


def terraform_taint_resource(module_resource, tf_env_vars):
    return terraform_action("taint -module={} {}".format(module_resource.split('.')[1], '.'.join(module_resource.split('.')[2:])),
                            '', tf_env_vars)


def query_yes_no(question, default="no"):
    valid = {"yes": True, "y": True, "ye": True,
             "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("Invalid answer: {}".format(default))

    while True:
        sys.stdout.write(question + prompt)
        choice = input().lower()
        if default is not None and choice == '':
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write("{}Valid answers 'yes' or 'no' or 'y' or 'n'.\n".format(bcolors.WARNING))


def query_answer(question):
    while True:
        sys.stdout.write(question)
        return input().lower()


def get_full_service_name(env, service):
    service_parts = service.split("-")
    deploy_name = service_parts[:1]
    deploy_name.append(env)
    deploy_name.extend(service_parts[1:])
    return "-".join(deploy_name)


def enable_remote_terraform_state(bucket_name, package_name, session):
    '''deprecated'''
    key = "{}/terraform-remote/terraform.tfstate".format(package_name)
    command = [('{} remote config '
                '-backend=s3 '
                '-backend-config="region={}" '
                '-backend-config="bucket={}" '
                '-backend-config="key={}" '
                '-backend-config="profile={}"').format(TERRAFORM_CMD, session.region_name, bucket_name, key, session.profile_name)]
    print(("Executing command: {}".format(command)))
    return subprocess.call(command, shell=True)
