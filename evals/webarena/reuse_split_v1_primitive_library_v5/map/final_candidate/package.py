"""Generated candidate package; not promoted."""

class MapGeocoding:

    def __init__(self, page):
        self.page = page

    def search_local_geocoder_places(self, query: str, map_bounds: dict, zoom: int) -> dict:
        import html
        import re
        from urllib.parse import urlencode
        if not isinstance(query, str) or not query.strip():
            raise ValueError('query must be a non-empty string')
        if not isinstance(map_bounds, dict):
            raise ValueError('map_bounds must be an object')
        for key in ('minlon', 'minlat', 'maxlon', 'maxlat'):
            if key not in map_bounds:
                raise ValueError(f'map_bounds must include {key}')
        if not isinstance(zoom, int):
            raise ValueError('zoom must be an integer')
        base_url = 'http://ec2-18-223-172-69.us-east-2.compute.amazonaws.com:3000'
        search_url = base_url + '/search?' + urlencode({'query': query})
        search_response = self.page.request.get(search_url, timeout=30000)
        if not search_response.ok:
            raise RuntimeError(f'failed to load search page: {search_response.status}')
        search_html = search_response.text()
        csrf_param_match = re.search('<meta name="csrf-param" content="([^"]+)"', search_html)
        csrf_token_match = re.search('<meta name="csrf-token" content="([^"]+)"', search_html)
        if not csrf_param_match or not csrf_token_match:
            raise RuntimeError('failed to extract CSRF metadata from search page')
        csrf_param = csrf_param_match.group(1)
        csrf_token = csrf_token_match.group(1)
        form_data = {'query': query, 'zoom': str(zoom), 'minlon': str(map_bounds['minlon']), 'minlat': str(map_bounds['minlat']), 'maxlon': str(map_bounds['maxlon']), 'maxlat': str(map_bounds['maxlat']), csrf_param: csrf_token}
        response = self.page.request.post(base_url + '/geocoder/search_osm_nominatim', form=form_data, headers={'Referer': search_url, 'X-Requested-With': 'XMLHttpRequest'}, timeout=30000)
        if not response.ok:
            raise RuntimeError(f'local geocoder request failed: {response.status}')
        response_html = response.text()
        pattern = re.compile('<a class="set_position"[^>]*data-lat="([^"]+)"[^>]*data-lon="([^"]+)"[^>]*data-prefix="([^"]*)"[^>]*data-name="([^"]+)"')
        results = []
        for match in pattern.finditer(response_html):
            results.append({'prefix': html.unescape(match.group(3)), 'display_name': html.unescape(match.group(4)), 'latitude': float(match.group(1)), 'longitude': float(match.group(2))})
        return {'query': query, 'results': results, 'result_count': len(results), 'search_scope': {'map_bounds': {'minlon': float(map_bounds['minlon']), 'minlat': float(map_bounds['minlat']), 'maxlon': float(map_bounds['maxlon']), 'maxlat': float(map_bounds['maxlat'])}, 'zoom': zoom}}

    def search_places(self, query: str, result_limit: int=5) -> dict:
        import json
        import urllib.parse
        import urllib.request
        if not isinstance(query, str) or not query.strip():
            raise ValueError('query must be a non-empty string')
        if not isinstance(result_limit, int) or result_limit <= 0:
            raise ValueError('result_limit must be a positive integer')
        base_url = 'http://18.208.187.221:8085/search'
        params = {'q': query, 'format': 'jsonv2', 'limit': str(result_limit)}
        url = base_url + '?' + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=30) as response:
            payload = json.loads(response.read().decode('utf-8'))
        results = []
        for item in payload:
            lat_raw = item.get('lat')
            lon_raw = item.get('lon')
            results.append({'place_id': item.get('place_id'), 'osm_type': item.get('osm_type'), 'osm_id': item.get('osm_id'), 'display_name': item.get('display_name'), 'latitude': float(lat_raw) if lat_raw is not None else None, 'longitude': float(lon_raw) if lon_raw is not None else None, 'category': item.get('category'), 'place_type': item.get('type'), 'importance': item.get('importance')})
        return {'query': query, 'result_limit': result_limit, 'results': results, 'result_count': len(results)}

class MapRouting:

    def __init__(self, page):
        self.page = page

    def get_route(self, waypoints: list, transportation_method: str='driving') -> dict:
        import json
        import urllib.parse
        import urllib.request
        if not isinstance(waypoints, list) or len(waypoints) < 2:
            raise ValueError('waypoints must be a list of at least two coordinate objects')
        if transportation_method not in {'driving', 'walking', 'biking'}:
            raise ValueError('transportation_method must be one of: driving, walking, biking')
        mode_config = {'driving': {'port': 5000, 'profile': 'driving'}, 'biking': {'port': 5001, 'profile': 'driving'}, 'walking': {'port': 5002, 'profile': 'driving'}}
        config = mode_config[transportation_method]
        normalized_waypoints = []
        encoded_points = []
        for waypoint in waypoints:
            if not isinstance(waypoint, dict):
                raise ValueError('each waypoint must be an object with latitude and longitude')
            latitude = waypoint.get('latitude')
            longitude = waypoint.get('longitude')
            if latitude is None or longitude is None:
                raise ValueError('each waypoint must include latitude and longitude')
            latitude = float(latitude)
            longitude = float(longitude)
            normalized_waypoints.append({'latitude': latitude, 'longitude': longitude})
            encoded_points.append(f'{longitude},{latitude}')
        url = f"http://18.208.187.221:{config['port']}/route/v1/{config['profile']}/" + ';'.join(encoded_points) + '?' + urllib.parse.urlencode({'overview': 'false', 'steps': 'true', 'alternatives': 'false', 'annotations': 'false', 'geometries': 'polyline'})
        request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode('utf-8'))
        output_waypoints = []
        for waypoint in payload.get('waypoints', []):
            location = waypoint.get('location') or []
            longitude = location[0] if len(location) > 0 else None
            latitude = location[1] if len(location) > 1 else None
            output_waypoints.append({'name': waypoint.get('name'), 'latitude': float(latitude) if latitude is not None else None, 'longitude': float(longitude) if longitude is not None else None})
        routes = []
        for route in payload.get('routes', []):
            legs_out = []
            for leg in route.get('legs', []):
                steps_out = []
                for step in leg.get('steps', []):
                    steps_out.append({'mode': step.get('mode'), 'distance_meters': step.get('distance'), 'duration_seconds': step.get('duration'), 'name': step.get('name'), 'maneuver': step.get('maneuver')})
                legs_out.append({'steps': steps_out})
            routes.append({'duration_seconds': route.get('duration'), 'distance_meters': route.get('distance'), 'legs': legs_out})
        return {'transportation_method': transportation_method, 'code': payload.get('code'), 'input_waypoints': normalized_waypoints, 'waypoints': output_waypoints, 'routes': routes, 'route_count': len(routes)}

class MapSite:

    def __init__(self, page):
        self.geocoding = MapGeocoding(page)
        self.routing = MapRouting(page)
