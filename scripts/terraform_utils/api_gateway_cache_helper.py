def get_method_request_param_and_cache_key_params(method, rest_api_id, resource_id, api_gateway):
    method = api_gateway.get_method(restApiId=rest_api_id, resourceId=resource_id, httpMethod=method)
    method_integration = method.get("methodIntegration", {})
    request_parameters = None

    if "requestParameters" in method:
        request_parameters = method["requestParameters"]

    return request_parameters, method_integration.get("cacheKeyParameters", None)


def update_cache_key_params_for_verb(verb, resource, rest_api_id, api_gateway):
    resource_methods = resource["resourceMethods"]
    resource_id = resource["id"]
    if verb in resource_methods:
        request_parameters, cache_key_parameters = get_method_request_param_and_cache_key_params(verb,
                                                                                                 rest_api_id,
                                                                                                 resource_id,
                                                                                                 api_gateway)

        if request_parameters:
            for request_parameter in request_parameters:
                if isinstance(cache_key_parameters, list) and request_parameter not in cache_key_parameters:
                    print("Updating key cache parameters for {}".format(request_parameter))
                    api_gateway.update_integration(
                        restApiId=rest_api_id,
                        resourceId=resource_id,
                        httpMethod=verb,
                        patchOperations=[
                            {
                                'op': 'add',
                                'path': "/cacheKeyParameters/{}".format(request_parameter)
                            },
                        ]
                    )


def update_caching_parameters(client, rest_api):
    rest_api_id = rest_api["id"]
    resources = client.get_resources(restApiId=rest_api_id)["items"]

    for resource in resources:
        if "resourceMethods" in resource:
            update_cache_key_params_for_verb("GET", resource, rest_api_id, client)
            update_cache_key_params_for_verb("OPTIONS", resource, rest_api_id, client)
            update_cache_key_params_for_verb("HEAD", resource, rest_api_id, client)
