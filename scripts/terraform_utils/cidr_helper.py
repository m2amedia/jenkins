# Based on LIVE-185
import boto3
import netaddr

VPC_NETMASK_BITS = '11111111.11111111.11100000.00000000' # 19 bits
SUBNET_BITS = 23 # 4 bits for subnet, max 16 subnets
DEFAULT_FIRST_CIDR = netaddr.IPNetwork('10.10.0.0/19') # because third parties eg elemental might claim '10.0.0.0' networks entirely for itself..

def _get_peered_cidrs(aws_profile, aws_region):
    session = boto3.session.Session(profile_name=aws_profile)
    ec2_client = session.client('ec2', aws_region)
    peered_conns = ec2_client.describe_vpc_peering_connections()
    peered_cidrs = [netaddr.IPNetwork(peered_conn['RequesterVpcInfo']['CidrBlock']) \
                    for peered_conn in peered_conns['VpcPeeringConnections'] \
                    if 'CidrBlock' in peered_conn['RequesterVpcInfo']]
    return peered_cidrs

def suggest_next_vpc_cidr(aws_profile, aws_region):
    peered_cidrs = _get_peered_cidrs(aws_profile, aws_region)
    peered_cidrs_with_curr_vpc_mask = [peered_cidr for peered_cidr in peered_cidrs if peered_cidr.netmask.bits() == VPC_NETMASK_BITS]
    first_cidr = sorted(peered_cidrs_with_curr_vpc_mask)[0] if len(peered_cidrs_with_curr_vpc_mask) > 0 else DEFAULT_FIRST_CIDR
    next_cidr = first_cidr
    while next_cidr in peered_cidrs_with_curr_vpc_mask:
        next_cidr = next_cidr.next()

    return str(next_cidr)

def peered_cidrs_as_string_list(aws_profile, aws_region):
    peered_cidrs = sorted(_get_peered_cidrs(aws_profile, aws_region))
    return [str(peered_cidr) for peered_cidr in peered_cidrs]

def is_vpc_cidr_in_use(vpc_cidr, aws_profile, aws_region):
    return netaddr.IPNetwork(vpc_cidr) in _get_peered_cidrs(aws_profile, aws_region)

def generate_subnet_cidrs(vpc_cidr):
    vpc_cidr_ipn = netaddr.IPNetwork(vpc_cidr)

    if vpc_cidr_ipn.netmask.bits() != VPC_NETMASK_BITS:
        raise RuntimeError('VPC netmask is not valid. The only valid netmask is {}'.format(VPC_NETMASK_BITS))

    subnets_ipn = list(vpc_cidr_ipn.subnet(SUBNET_BITS))
    subnets_cidr = ['"{}"'.format(subnet_ipn) for subnet_ipn in subnets_ipn]

    return "[{}]".format(','.join(subnets_cidr))
