#!/usr/bin/env python
import os

from botocore.exceptions import ClientError


def create_ssh_key(env, aws_session):
    ec2_client = aws_session.client('ec2')
    key_name = 'm2a-{}-key'.format(env)

    exists = does_key_exist(ec2_client, key_name)
    if not exists:
        print("{}SSH Key {} doesn't exist, creating ~/{}.pem...".format('\033[93m', key_name, key_name))
        create_key(ec2_client, key_name)


def does_key_exist(ec2_client, key_name):
    try:
        ec2_client.describe_key_pairs(KeyNames=[key_name])
    except ClientError as e:
        if e.response["Error"]["Code"] == "InvalidKeyPair.NotFound":
            return False
        raise e

    print("SSH Key {} exists not creating".format(key_name))
    return True


def create_key(ec2_client, key_name):
    response = ec2_client.create_key_pair(KeyName=key_name)
    private_key = response['KeyMaterial']

    key_path = os.path.expanduser("~/{}.pem".format(key_name))
    ssh_file = open(key_path, "wb")
    ssh_file.write(private_key)
    ssh_file.close()
    print("SSH Key created at {}".format(key_path))
