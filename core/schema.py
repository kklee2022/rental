def filter_legacy_api_paths(endpoints, **kwargs):
    """Expose only the versioned API in generated OpenAPI documents."""

    return [
        endpoint
        for endpoint in endpoints
        if endpoint[0].startswith("/api/v1/") or endpoint[0].startswith("/api/schema")
    ]
