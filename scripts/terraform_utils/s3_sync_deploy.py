import os
import sys
import json
import io

from m2a_process_helper import run

'''
Sample terraform output:
{
    "crossaccount_bucket": {
        "sensitive": false,
        "type": "string",
        "value": "m2a-cucumber-crossaccount"
    },
    "crossaccount_bucket_user_keys_ak": {
        "sensitive": false,
        "type": "string",
        "value": "AKIAIORL5RTLQJRZ3VBA"
    },
[...]
'''

def sync_files(boto3_session, component_path, component_svc_info, resources_json, env):
    s3rsc = boto3_session.resource('s3')
    deployment_bucket = resources_json[component_svc_info['terraformBucket']]
    resources_key = component_svc_info.get('terraformResourcesKey')
    bucket = s3rsc.Bucket(deployment_bucket)
    if resources_key:
        print('Syncing resources.json to S3 key: {}'.format(resources_key))
        bucket.put_object(Key=resources_key,
                          Body=io.BytesIO((json.dumps(resources_json, indent=4, sort_keys=True))))

    real_component_path = os.path.realpath(component_path)
    print('Syncing {} to S3 bucket: {}'.format(real_component_path, deployment_bucket))
    run.cmd("aws --profile {} s3 sync {} s3://{}/".format(env, real_component_path, deployment_bucket),
            realtime_stdout_pipe=sys.stdout.write)
