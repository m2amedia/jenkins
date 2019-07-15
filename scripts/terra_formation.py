#!/usr/bin/env python
import argparse
import hashlib
import io
import pprint
import json
import traceback
import boto3
import os
import re
import sys
import datetime
import logging
import tempfile
from string import Template
from multiprocessing.dummy import Pool

import update_apigateway_stages
import zip_modules
from terraform_utils import api_gateway_helper, environment_verifier, ssh_key_create, utils_terraform
from terraform_utils import environment_report
from terraform_utils.bcolors import bcolors
from terraform_utils.modules_utils import get_terraform_modules, get_module_paths, get_module_source_paths
from terraform_utils import s3_sync_deploy
from terraform_utils import cidr_helper

from m2a_process_helper import run
import pkg_resources
print(('<Assumption> m2a_process_helper v{} is >=0.3.x'.format(pkg_resources.get_distribution("m2a_process_helper").version)))

CURR_WORK_DIR = os.getcwd()

parser = argparse.ArgumentParser(description='Deployment of AWS resources using Terraform')
parser.add_argument('--env', '-e', help='Set environment you want your resources deployed in: int, test, live', required=True)
parser.add_argument('--module-name', '-m', help='Module to deploy', required=False)
# below is for bkw-compat, but this is the best: parser.add_argument('--non-interactive', '-n', help='Non interactive mode', action='store_true', required=False)
parser.add_argument('--non-interactive', '-n', action='store_true', help='Non interactive mode', required=False)
parser.add_argument('--m2a-path', '-p', help='M2a workspace path, if specified all modules are zipped', required=False, nargs=1)
parser.add_argument('--upload-resources', '-r',
                    action='store_true',
                    default=False,
                    help='Resources will be created and uploaded to s3, Requires m2a-path to be set',
                    required=False)
parser.add_argument('--region', '-rg', help='Set region you want your resources deployed in', required=False)
parser.add_argument('--destroy', '-d', help='Terraform Destroy', action='store_true', default=False)
parser.add_argument('--plan', help='Run terraform plan only', action='store_true', default=False)
parser.add_argument('--tf-env-vars-source', help='Relative Terraform TF_VAR source file', default='./env-vars/{environment}.json')
parser.add_argument('--zip-cache', help='Zipped files', default="{}/terraform/lambda_files".format(CURR_WORK_DIR))
parser.add_argument('--show-resources-only', help='Only view currently deployed resources.json', action='store_true', default=False)
parser.add_argument('--create-usage-plan', help='Create usage plan', default="true")

args = parser.parse_args()
environment = args.env
module_name = args.module_name
m2a_path = args.m2a_path[0]
upload_resources = args.upload_resources
destroy = args.destroy
plan = args.plan
non_interactive = args.non_interactive
tf_env_vars_path = os.path.realpath(args.tf_env_vars_source.format(environment=environment))
tf_env_vars = json.load(open(tf_env_vars_path))
zip_cache = args.zip_cache
create_usage = False if args.create_usage_plan.lower() == "false" else True

PPRINT = pprint.PrettyPrinter().pprint

TERRAFORM_SRC_DIR = '{}/terraform/{}'.format(CURR_WORK_DIR, environment)

logging.basicConfig(format='%(asctime)s %(name)s:%(lineno)s %(levelname).1s %(message)s', level=logging.INFO)
logging.getLogger('boto3.resources.action').setLevel(logging.CRITICAL)
logging.getLogger('botocore.vendored.requests.packages.urllib3.connectionpool').setLevel(logging.CRITICAL)

def setup_tf_env_vars():
    print(('Using env vars with MD5 = {}'.format(hashlib.md5(open(tf_env_vars_path, 'rb').read()).hexdigest())))

    for k, v in tf_env_vars.items():
        os.environ[k] = v
    terraform_dir = "{}/terraform".format(CURR_WORK_DIR)
    var_file = '{}/{}/common_variables.tf'.format(terraform_dir, environment)
    environment_verifier.verify_vars_exists(var_file, non_interactive)
    tf_profile = os.getenv("TF_VAR_aws_profile")
    tf_region = args.region or os.getenv("TF_VAR_region")
    if not tf_region:
        raise RuntimeError('Define a region')
    tf_env = os.getenv("TF_VAR_environment")
    if os.getenv("TERRAFORM_CMD") is not None:
        utils_terraform.TERRAFORM_CMD = os.getenv("TERRAFORM_CMD")

    # VPC-related - see LIVE-185
    vpc_cidr = os.getenv("TF_VAR_vpc_cidr")
    if vpc_cidr: # then generate subnet cidrs
        root_acc_profile = 'root' # ASSUMPTION
        # FIXME must exclude obviously the case in which the current env is the owner of this vpc cidr..
        # if cidr_helper.is_vpc_cidr_in_use(vpc_cidr, root_acc_profile, tf_region):
            # raise RuntimeError('VPC cidr is already peered in root account for region {}: {}'.format(tf_region, vpc_cidr))
        subnet_cidrs = cidr_helper.generate_subnet_cidrs(vpc_cidr)
        os.environ["TF_VAR_subnet_cidrs"] = subnet_cidrs
        print('Proposed subnet CIDRs for VPC CIDR {}:\n{}'.format(vpc_cidr, subnet_cidrs))

    return tf_profile, tf_region, tf_env


def init_remote_state():
    run.cmd('terraform init', cwd=TERRAFORM_SRC_DIR, realtime_stdout_pipe=sys.stdout.write)

    current_modules_dir = '{}/.terraform/modules'.format(CURR_WORK_DIR)

    if os.path.exists(current_modules_dir):
        print("Deleting existing modules...\nCalling " \
              "command: {}".format('rm -rf {}'.format(current_modules_dir)))

        run.cmd('rm -rf {}'.format(current_modules_dir))

    if os.path.exists('{}/.terraform/terraform.tfstate'.format(CURR_WORK_DIR)):
        print("Deleting existing terraform state file...\nCalling " \
              "command: {}".format('rm {}/.terraform/terraform.tfstate'.format(CURR_WORK_DIR)))

        run.cmd('rm {}/.terraform/terraform.tfstate'.format(CURR_WORK_DIR))

    print("Copying modules and terraform state file from" \
          " {}/terraform/{}/.terraform/ to {}/.terraform/'".format(CURR_WORK_DIR, environment, CURR_WORK_DIR))

    run.cmd('cp -R {}/terraform/{}/.terraform {}/'.format(CURR_WORK_DIR, environment, CURR_WORK_DIR))


def deploy_s3_sync_modules(boto3_session, terraform_module_paths, resources_json):
    '''upload resources and sync s3'''
    for tf_module in terraform_module_paths:
        service_info_path = '{}/terraform/{}/{}/../services-info.json'.format(CURR_WORK_DIR, environment, tf_module)
        if not os.path.isfile(service_info_path):
            print("service-info.json not found in {}".format(service_info_path))
            continue

        service_info = json.load(open(service_info_path))
        components = service_info.get('components', {})
        for component in components.keys():
            component_svc_info = components[component]
            if "s3_sync" not in component_svc_info.get('deployment', ''):
                continue

            component_path = '{}/terraform/{}/{}/../{}'.format(CURR_WORK_DIR, environment, tf_module, component)
            s3_sync_deploy.sync_files(boto3_session, component_path, component_svc_info, resources_json, environment)


def create_resources_per_module(boto3_session, terraform_module_paths, resources_json):
    awslogs_config_template = """
[general]
state_file = /var/awslogs/state/agent-state

[service]
file = /home/m2a/m2a-service/logs/service.log
log_group_name = /m2a/${environment}-${component}
log_stream_name = {ip_address}__{instance_id}
time_zone = UTC
"""

    # Resources to component-independent location
    for k, v in resources_json.items():
        if 'ResourcesBucketName' in k:
            print('Uploading terraform_outputs.json to {}'.format(v))
            bucket = boto3_session.resource('s3').Bucket(v)
            resources_json_buffer = io.BytesIO(json.dumps(resources_json, indent=4, sort_keys=True))
            bucket.put_object(Key='terraform_outputs.json', Body=resources_json_buffer)

    # Component-specific resourcesjson and awslogs config
    s3rsc = boto3_session.resource('s3')
    module_source_paths = get_module_source_paths(terraform_module_paths, m2a_path)

    thread_pool = Pool()
    buckets = dict()
    payloads = []
    def partial_put_object(payload):
        buckets[payload['bucket_name']].put_object(Key=payload['key'], Body=payload['body'])

    for module_name, module_source_path in module_source_paths.items():
        print("Creating resources for module {}".format(module_source_path))

        service_info = json.load(open("{}/services-info.json".format(module_source_path)))
        if "components" in service_info:
            for component in service_info["components"]:
                bucket_name = "m2a-{}-{}-resources".format(component.split("-")[1], environment)
                buckets[bucket_name] = s3rsc.Bucket(bucket_name)

                resources_key = "configuration/{}/resources.json".format(component)
                print("Uploading resources file to s3://{}/{}".format(bucket_name, resources_key))
                payloads.append(dict(bucket_name=bucket_name, key=resources_key,
                                     body=io.BytesIO((json.dumps(resources_json, indent=4, sort_keys=True)))))

                config_file = "{}/{}/src/resources/config.{}.json".format(module_source_path, component, environment)
                if os.path.exists(config_file):
                    config_key = "configuration/{}/config.json".format(component)
                    print("Uploading config file to s3://{}/{}".format(bucket_name, config_key))
                    payloads.append(dict(bucket_name=bucket_name, key=config_key,
                                         body=io.FileIO(config_file)))

                awslogs_config = Template(awslogs_config_template).substitute(environment=os.environ['TF_VAR_environment'],
                                                                              component=component)
                awslogs_config_key = "configuration/{}/awslogs".format(component)
                print("Uploading awslogs config file to s3://{}/{}".format(bucket_name, awslogs_config_key))
                payloads.append(dict(bucket_name=bucket_name, key=awslogs_config_key,
                                     body=io.BytesIO(str(awslogs_config))))

    thread_pool.map(partial_put_object, payloads)
    thread_pool.close()
    thread_pool.join()


def prepare_resources_json_from_terraform_outs():
    # Add all module resources to root module resources json
    def terraform_json_to_m2a_resources_json(terraform_json):
        return {output_key: terraform_json[output_key]['value'] for output_key in list(terraform_json.keys())}

    (root_module_resources_json, _) = run.cmd('terraform output -json',
                                              cwd=TERRAFORM_SRC_DIR, env_vars=os.environ, realtime_stdout_pipe=sys.stdout.write)

    root_module_resources = terraform_json_to_m2a_resources_json(json.loads(root_module_resources_json))
    module_file = '{}/terraform/{}/modules.tf'.format(CURR_WORK_DIR, environment)
    terraform_module_paths = get_module_paths(module_file)
    terraform_modules = get_terraform_modules(module_file)
    print('{}Retrieving terraform outputs for modules {}'.format(bcolors.OKBLUE, terraform_modules))
    terraform_module_resources = utils_terraform.terraform_outputs(terraform_modules, TERRAFORM_SRC_DIR)
    module_resources = terraform_json_to_m2a_resources_json(terraform_module_resources)
    root_module_resources.update(module_resources)
    resources_json = root_module_resources
    print('{}resources.json of all modules:\n{}'.format(bcolors.OKGREEN, json.dumps(resources_json, indent=2)))

    return (terraform_module_paths, resources_json)


def main():
    tflog_file = None
    try:
        profile, region, tf_environment = setup_tf_env_vars()
        boto3_session = boto3.session.Session(profile_name=profile, region_name=region)

        init_remote_state()

        if args.show_resources_only:
            prepare_resources_json_from_terraform_outs()
            return 0

        ssh_key_create.create_ssh_key(tf_environment, boto3_session)
        os.environ["TF_VAR_dev_api_key"] = api_gateway_helper.create_api_key(tf_environment, boto3_session)

        # Did not work: "Active stages pointing to this deployment must be moved or deleted"
        # print '{}Tainting API GW deployments - so it can be redeployed'.format(bcolors.OKBLUE)
        # terraform_state_resources = utils_terraform.terraform_list_resources(os.environ)
        # api_gw_deployments = [rsc for rsc in terraform_state_resources.split('\n') if 'aws_api_gateway_deployment' in rsc]
        # for api_gw_deployment in api_gw_deployments:
        #     utils_terraform.terraform_taint_resource(api_gw_deployment, os.environ)

        # if m2a_path provided recursively zip all modules to single dir (terraform/lambda_files)
        if m2a_path:
            zip_modules.zip_modules(m2a_path, environment, zip_dir=zip_cache)
        else:
            utils_terraform.zip_files(zip_files_location=zip_cache)

        terraform_src_path = "terraform/{}".format(environment)
        module_param = ''
        if module_name:
            print('{}Deploying module {}'.format(bcolors.OKBLUE, module_name))
            module_param = "-target=module.{}".format(module_name)

        # Always log to a file at WARN level, and output after plan/apply operations as it might contain essential info for resolving issues:
        tflog_file = tempfile.NamedTemporaryFile(prefix='terraform-tflog-')
        os.environ['TF_LOG'] = 'WARN'
        os.environ['TF_LOG_PATH'] = tflog_file.name

        if destroy:
            print('{}Destroying terraform deployment!'.format(bcolors.WARNING))
            run.cmd('terraform destroy {} {}'.format(module_param, terraform_src_path), env_vars=os.environ, realtime_stdout_pipe=sys.stdout.write)
        elif plan:
            print('{}Running plan only, will not deploy'.format(bcolors.WARNING))
            run.cmd('terraform plan {} {}'.format(module_param, terraform_src_path), env_vars=os.environ, realtime_stdout_pipe=sys.stdout.write)
        else:
            plan_file = tempfile.NamedTemporaryFile(prefix='terraform-plan-')
            print('{}Planning'.format(bcolors.OKBLUE))
            run.cmd('terraform plan -parallelism=20 {} -out {} {}'.format(module_param, plan_file.name, terraform_src_path),
                    env_vars=os.environ, realtime_stdout_pipe=sys.stdout.write)
            print('{}Creating/Updating resources in AWS'.format(bcolors.OKBLUE))
            run.cmd('terraform apply {} -parallelism=20 {} {}'.format('-auto-approve' if non_interactive else '', module_param, plan_file.name),
                    env_vars=os.environ, realtime_stdout_pipe=sys.stdout.write)
            print('{}Successfully applied changes'.format(bcolors.OKBLUE))
            plan_file.close()

            (terraform_module_paths, resources_json) = prepare_resources_json_from_terraform_outs()
            deploy_s3_sync_modules(boto3_session, terraform_module_paths, resources_json)

            print('{}Updating API GW Stages...'.format(bcolors.ENDC))
            update_apigateway_stages.update_stages(boto3_session, environment)

            print('{}Generating report...'.format(bcolors.ENDC))
            environment_report.generate_and_sync_env_report_file(environment, region)

            if m2a_path and upload_resources:
                print('{}Creating usage plan...'.format(bcolors.ENDC))
                api_gateway_helper.create_usage_plan(environment, boto3_session, create_usage)
                print('{}Creating modules resources...'.format(bcolors.ENDC))
                create_resources_per_module(boto3_session, terraform_module_paths, resources_json)

                ### WIP: api gw automatic deployment
                # print '{}Retrieving API GW deployments for redeployment'.format(bcolors.OKBLUE)
                # terraform_outputs = utils_terraform.terraform_outputs(modules, os.environ)
            else:
                print('{}NOT creating/updating changes in AWS'.format(bcolors.WARNING))

        print('{}Complete.'.format(bcolors.OKGREEN))
        return 0

    except BaseException as ex:
        print(bcolors.FAIL)
        traceback.print_exc()
        if tflog_file:
            tflog = open(tflog_file.name).read()
            print('===TFLOG===\n')
            PPRINT(re.findall('\[WARN.*', tflog))
            PPRINT(re.findall('\[ERROR.*', tflog))

        return 1

    finally:
        if tflog_file:
            tflog_file.close()



ret_code = main()
print(bcolors.ENDC)
exit(ret_code)
