import argparse
import boto3

from botocore.exceptions import ClientError

def update_stages(session, stage):

    client = session.client('apigateway')

    apis_list = client.get_rest_apis()

    print("\nEnabling metrics and setting logging level for the following APIs:\n")
    for api in apis_list['items']:
        print("{}, id: {}, Name: {}".format(api.get('description', None), api.get('id', None), api.get('name', None)))
        try:
            response = client.update_stage(
                restApiId=api['id'],
                stageName=stage,
                patchOperations=[
                    {
                        "op" : "replace",
                        "path" : "/*/*/metrics/enabled",
                        "value" : "true"
                    },
                    {
                        "op" : "replace",
                        "path" : "/*/*/logging/loglevel",
                        "value" : "INFO"
                    },
                    {
                        "op" : "replace",
                        "path" : "/*/*/logging/dataTrace",
                        "value" : "true"
                    }
                ]
            )
        except ClientError as ex:
            print("\n^ {}\n".format(ex))

def main():

    parser = argparse.ArgumentParser(description='Update APIGateway Stages')
    parser.add_argument('--stageName', '-s', help='Stage name ', required=True)

    args = parser.parse_args()
    stage = args.stageName

    session = boto3.session.Session(profile_name=stage, region_name='eu-west-1')
    update_stages(session, stage)

if __name__ == "__main__":
    main()
