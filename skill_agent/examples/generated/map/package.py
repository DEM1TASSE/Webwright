"""Generated candidate package; not promoted."""

class MapRoute:

    def __init__(self, page):
        self.page = page

    def get_osrm_route(self, osrm_base_url, coordinates):
        from urllib.parse import urlencode
        from urllib.request import urlopen
        import json
        if len(coordinates) < 2:
            raise ValueError('coordinates must contain at least two points')
        coord_path = ';'.join((f"{point['lon']},{point['lat']}" for point in coordinates))
        params = {'overview': 'false', 'steps': 'true'}
        base = osrm_base_url.rstrip('/')
        url = f'{base}/{coord_path}?{urlencode(params)}'
        with urlopen(url, timeout=60) as resp:
            payload = json.load(resp)
        route = payload['routes'][0]
        legs = []
        for leg in route.get('legs', []):
            legs.append({'duration_seconds': leg.get('duration'), 'distance_meters': leg.get('distance')})
        return {'code': payload.get('code'), 'duration_seconds': route.get('duration'), 'distance_meters': route.get('distance'), 'legs': legs}

class MapSearch:

    def __init__(self, page):
        self.page = page

    def geocode_search_query(self, base_url, query, limit):
        from urllib.parse import urlencode, urljoin
        from urllib.request import urlopen
        import json
        params = {'q': query, 'format': 'jsonv2', 'limit': int(limit)}
        base = base_url if base_url.endswith('/') else base_url + '/'
        url = urljoin(base, 'search') + '?' + urlencode(params)
        with urlopen(url, timeout=60) as resp:
            payload = json.load(resp)
        results = []
        for item in payload:
            results.append({'display_name': item.get('display_name'), 'lat': float(item['lat']) if item.get('lat') is not None else None, 'lon': float(item['lon']) if item.get('lon') is not None else None, 'place_id': item.get('place_id'), 'osm_type': item.get('osm_type'), 'osm_id': item.get('osm_id'), 'class': item.get('class'), 'type': item.get('type'), 'importance': item.get('importance'), 'address_type': item.get('addresstype'), 'name': item.get('name')})
        return {'results': results}

class MapSite:

    def __init__(self, page):
        self.route = MapRoute(page)
        self.search = MapSearch(page)
