from botocore.client import ClientError

import api_gateway_cache_helper


def create_api_key(env, session):
    api_gateway = session.client('apigateway')
    api_key_name = "m2a-{}-dev-key".format(env)
    api_key_value = get_api_key_value(api_key_name, api_gateway)

    if not api_key_value:
        print("Api key {} does not exist creating".format(api_key_name))
        response = api_gateway.create_api_key(name=api_key_name, enabled=True)
        api_key_value = response["value"]
        return api_key_value

    print("Api key {} exists not creating".format(api_key_name))
    return api_key_value


def create_usage_plan(env, session, create_usage):
    if create_usage:
        api_gateway = session.client('apigateway')
        api_usage_plan_name = "m2a-{}-dev-usage-plan".format(env)
        print('Checking if usage plan {} exists'.format(api_usage_plan_name))

        api_ids = _get_api_ids(api_gateway)

        usage_plan_id = _get_usage_plan_id(api_usage_plan_name, api_gateway)
        if not usage_plan_id:
            print("Creating new Usage plan {}".format(api_usage_plan_name))
            api_stages = _get_api_stages_and_add_cache_key_params(api_gateway)
            usage_response = api_gateway.create_usage_plan(name=api_usage_plan_name, apiStages=api_stages)
            api_gateway.create_usage_plan_key(
                usagePlanId=usage_response["id"],
                keyId=_get_api_key_id("m2a-{}-dev-key".format(env), api_gateway),
                keyType='API_KEY'
            )
        else:
            print('Usage plan {} found, linking api deployed stages to usage plan'.format(api_usage_plan_name))
            linked_api_stages = _get_linked_api_stages(usage_plan_id, api_gateway)
            update_usage_plan(api_ids, linked_api_stages, env, usage_plan_id, api_usage_plan_name, api_gateway)


def update_usage_plan(api_ids, linked_api_stages, stage_name, usage_plan_id, api_usage_plan_name,
                      api_gateway_client):
    for api_id in api_ids:
        if not any(d['apiId'] == api_id for d in linked_api_stages):
            print('Adding apiId:{} stage:{} to usage plan {}'.format(api_id, stage_name, api_usage_plan_name))
            stage = '{}:{}'.format(api_id, stage_name)
            try:
                api_gateway_client.update_usage_plan(
                    usagePlanId=usage_plan_id,
                    patchOperations=[
                        {
                            'op': 'add',
                            'path': '/apiStages',
                            'value': stage
                        }
                    ]
                )
            except Exception:
                print((
                    'could not find apiId:{} stage:{} to usage plan {}'.format(api_id, stage_name, api_usage_plan_name)))


def _get_api_stages_and_add_cache_key_params(api_gateway_client):
    api_stages = []
    apis = api_gateway_client.get_rest_apis()["items"]
    for api in apis:
        rest_api_id = api["id"]
        stages = api_gateway_client.get_stages(restApiId=rest_api_id)["item"]
        for stage in stages:
            api_stages.append(dict(apiId=rest_api_id, stage=stage["stageName"]))
    return api_stages


def _get_api_ids(api_gateway_client):
    api_stages_ids = []
    apis = api_gateway_client.get_rest_apis()["items"]
    for api in apis:
        rest_api_id = api["id"]
        api_gateway_cache_helper.update_caching_parameters(api_gateway_client, api)
        api_stages_ids.append(rest_api_id)
    return api_stages_ids


def _get_usage_plan_id(usage_plan_name, api_gateway_client):
    usage_plans = api_gateway_client.get_usage_plans()["items"]
    for usage_plan in usage_plans:
        if usage_plan["name"] == usage_plan_name:
            return usage_plan['id']
        else:
            print("Usage plan: {} doesn't exist".format(usage_plan_name))
            return False


def _get_linked_api_stages(usage_plan_id, api_gateway_client):
    try:
        usage_plan = api_gateway_client.get_usage_plan(usagePlanId=usage_plan_id)
        linked_api_stages = usage_plan["apiStages"]
        return linked_api_stages
    except ClientError:
        print("Usage plan: {} doesn't exist".format(usage_plan_id))


def get_api_key_value(api_key_name, api_gateway_client):
    api_key = _get_api_key(api_key_name, api_gateway_client)
    return api_key["value"] if api_key else None


def _get_api_key_id(api_key_name, api_gateway_client):
    api_key = _get_api_key(api_key_name, api_gateway_client)
    return api_key["id"] if api_key else None


def _get_api_key(api_key_name, api_gateway_client):
    response = api_gateway_client.get_api_keys(nameQuery=api_key_name, includeValues=True)

    items = response["items"]
    for item in items:
        if item["name"] == api_key_name:
            return item
