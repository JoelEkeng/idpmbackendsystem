from fastapi.routing import APIRoute

from main import app


PAGINATED_PATHS = {
    "/api/v1/attendance/me",
    "/api/v1/attendance/user/{user_id}",
    "/api/v1/attendance/profile/{profile_id}",
    "/api/v1/attendance/group/{group_id}",
    "/api/v1/attendance/service/{service_id}",
}


def test_attendance_history_routes_enforce_pagination_bounds():
    routes = {
        route.path: route
        for route in app.routes
        if isinstance(route, APIRoute) and route.path in PAGINATED_PATHS
    }

    assert routes.keys() == PAGINATED_PATHS

    for route in routes.values():
        query_params = {field.name: field for field in route.dependant.query_params}
        assert query_params["limit"].default == 100
        assert query_params["limit"].field_info.metadata[0].ge == 1
        assert query_params["limit"].field_info.metadata[1].le == 500
        assert query_params["offset"].default == 0
        assert query_params["offset"].field_info.metadata[0].ge == 0
