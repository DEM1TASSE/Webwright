"""Generated candidate package; not promoted."""

class MapGeocoding:

    def __init__(self, page):
        self.page = page

    def search_local_geocoder_results(self, query: str, minlon: float, minlat: float, maxlon: float, maxlat: float, zoom: int):
        import html
        import re
        from urllib.parse import urlsplit
        if not isinstance(query, str) or not query.strip():
            raise ValueError('query is required')
        current_url = self.page.url or ''
        if current_url:
            parts = urlsplit(current_url)
            base_url = f'{parts.scheme}://{parts.netloc}'
        else:
            base_url = 'http://ec2-18-223-172-69.us-east-2.compute.amazonaws.com:3000'
        self.page.goto(base_url + '/search')
        search_html = self.page.content()
        csrf_param_match = re.search('<meta name="csrf-param" content="([^"]+)"', search_html)
        csrf_token_match = re.search('<meta name="csrf-token" content="([^"]+)"', search_html)
        if not csrf_param_match or not csrf_token_match:
            raise RuntimeError('CSRF metadata not found on search page')
        csrf_param = csrf_param_match.group(1)
        csrf_token = csrf_token_match.group(1)
        response = self.page.request.post(base_url + '/geocoder/search_osm_nominatim', form={'query': query, 'zoom': str(zoom), 'minlon': str(minlon), 'minlat': str(minlat), 'maxlon': str(maxlon), 'maxlat': str(maxlat), csrf_param: csrf_token}, headers={'X-Requested-With': 'XMLHttpRequest', 'Referer': self.page.url})
        snippet = response.text()
        records = []
        pattern = re.compile('<a class="set_position"[^>]*data-lat="([^"]+)"[^>]*data-lon="([^"]+)"[^>]*data-prefix="([^"]*)"[^>]*data-name="([^"]+)"')
        for match in pattern.finditer(snippet):
            records.append({'name': html.unescape(match.group(4)), 'category': html.unescape(match.group(3)) or None, 'latitude': float(match.group(1)), 'longitude': float(match.group(2))})
        return {'query': query, 'viewport': {'minlon': minlon, 'minlat': minlat, 'maxlon': maxlon, 'maxlat': maxlat, 'zoom': zoom}, 'records': records, 'result_count': len(records), 'is_complete': False}

    def search_places(self, query: str, limit: int=10, response_format: str='jsonv2'):
        import json
        import urllib.parse
        import urllib.request
        if not isinstance(query, str) or not query.strip():
            raise ValueError('query is required')
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError('limit must be a positive integer')
        if not isinstance(response_format, str) or not response_format.strip():
            raise ValueError('response_format is required')
        base_url = 'http://18.208.187.221:8085/search'
        params = {'q': query, 'format': response_format, 'limit': limit}
        url = base_url + '?' + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=30) as response:
            payload = json.loads(response.read().decode('utf-8'))
        candidates = []
        for item in payload:
            lat_value = item.get('lat')
            lon_value = item.get('lon')
            candidates.append({'place_id': item.get('place_id'), 'osm_type': item.get('osm_type'), 'osm_id': item.get('osm_id'), 'display_name': item.get('display_name'), 'latitude': float(lat_value) if lat_value is not None else None, 'longitude': float(lon_value) if lon_value is not None else None, 'category': item.get('category') or item.get('class'), 'type': item.get('type'), 'importance': item.get('importance'), 'boundingbox': item.get('boundingbox')})
        return {'query': query, 'limit_requested': limit, 'response_format': response_format, 'candidates': candidates, 'result_count': len(candidates), 'is_complete': False}

class MapRouting:

    def __init__(self, page):
        self.page = page

    def get_route(self, waypoints: list, profile: str='driving', base_url: str='http://18.208.187.221:5000', overview=False, steps: bool=True, annotations: bool=False, geometries: str='polyline', alternatives: bool=False):
        import json
        import urllib.parse
        import urllib.request
        if not isinstance(profile, str) or not profile.strip():
            raise ValueError('profile is required')
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError('base_url is required')
        if not isinstance(waypoints, list) or len(waypoints) < 2:
            raise ValueError('at least two waypoints are required')
        encoded_points = []
        for waypoint in waypoints:
            if 'longitude' not in waypoint or 'latitude' not in waypoint:
                raise ValueError('each waypoint must include latitude and longitude')
            encoded_points.append(f"{waypoint['longitude']},{waypoint['latitude']}")
        coords = ';'.join(encoded_points)
        normalized_base = base_url.rstrip('/')
        request_base = f'{normalized_base}/route/v1/{profile}/{coords}'
        params = {'overview': str(overview).lower() if isinstance(overview, bool) else overview, 'steps': str(steps).lower(), 'annotations': str(annotations).lower(), 'geometries': geometries, 'alternatives': str(alternatives).lower()}
        request_url = request_base + '?' + urllib.parse.urlencode(params)
        request = urllib.request.Request(request_url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode('utf-8'))
        routes = []
        for route in payload.get('routes', []):
            routes.append({'duration_seconds': route.get('duration'), 'distance_meters': route.get('distance'), 'weight': route.get('weight'), 'weight_name': route.get('weight_name'), 'geometry': route.get('geometry'), 'legs': route.get('legs')})
        returned_waypoints = []
        for waypoint in payload.get('waypoints', []):
            location = waypoint.get('location') or [None, None]
            returned_waypoints.append({'name': waypoint.get('name'), 'longitude': location[0], 'latitude': location[1], 'distance_meters': waypoint.get('distance')})
        return {'profile': profile, 'base_url': normalized_base, 'code': payload.get('code'), 'routes': routes, 'waypoints': returned_waypoints, 'route_count': len(routes), 'request_waypoint_count': len(waypoints), 'request_url': request_url}

class MapSite:

    def __init__(self, page):
        self.geocoding = MapGeocoding(page)
        self.routing = MapRouting(page)
