def remove_irrelevant_auth_schemes(result, generator, request, public):
    """
    Post-processing hook to remove unwanted authentication schemes.
    """
    schema = result
    if "components" in schema and "securitySchemes" in schema["components"]:
        # Keep only the APIKeyAuth scheme
        schema["components"]["securitySchemes"] = {
            "apiKeyAuth": schema["components"]["securitySchemes"].get("apiKeyAuth"),
        }
    return schema
