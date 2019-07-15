import os

import hcl

from terraform_utils.bcolors import *
from terraform_utils.utils_terraform import query_answer


def verify_vars_exists(var_file, non_interactive=False):
    missing_vars = []
    with open(var_file, 'r') as variables:
        tf_vars = hcl.load(variables)
        for variable in tf_vars["variable"]:
            expected = "TF_VAR_{}".format(variable)
            if not os.environ.get(expected) and not expected == "TF_VAR_environment" and not "default" in tf_vars["variable"][variable]:
                missing_vars.append(expected)

    if missing_vars:
        exceptions = set(['TF_VAR_dev_api_key', 'TF_VAR_subnet_cidrs'])
        # EXCEPTION: because this is created after the first-run non-interactively
        if exceptions.intersection(missing_vars):
            print('[SKIP missing var] allowing {} to be empty'.format(exceptions))
        elif non_interactive:
            exit("{}Terraform needs ENVIRONMENT VARIABLES to be set {}".format(bcolors.FAIL, missing_vars))
        else:
            for missing in missing_vars:
                os.environ[missing] = query_answer("Enter value for {}: ".format(missing))
