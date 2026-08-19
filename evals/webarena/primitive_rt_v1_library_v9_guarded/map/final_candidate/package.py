"""Generated candidate package; not promoted."""

class MapPlaces:

    def __init__(self, page):
        self.page = page

    def search_places(self, query: str, limit: int=10) -> dict:
        import requests
        if not isinstance(query, str) or not query.strip():
            raise ValueError('query must be a non-empty string')
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError('limit must be a positive integer')
        response = requests.get('http://18.208.187.221:8085/search', params={'q': query.strip(), 'format': 'jsonv2', 'addressdetails': 1, 'limit': limit}, timeout=30)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError('unexpected search response shape')
        results = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            try:
                lat = float(row['lat'])
                lon = float(row['lon'])
            except (KeyError, TypeError, ValueError):
                continue
            display_name = str(row.get('display_name', ''))
            result = {'label': display_name, 'display_name': display_name, 'name': str(row.get('name')) if row.get('name') is not None else None, 'lat': lat, 'lon': lon, 'place_id': str(row['place_id']) if row.get('place_id') is not None else None, 'osm_type': str(row['osm_type']) if row.get('osm_type') is not None else None, 'osm_id': str(row['osm_id']) if row.get('osm_id') is not None else None, 'boundingbox': row.get('boundingbox') if isinstance(row.get('boundingbox'), list) else None, 'class_name': str(row.get('class')) if row.get('class') is not None else None, 'type_name': str(row.get('type')) if row.get('type') is not None else None, 'category': str(row.get('category')) if row.get('category') is not None else None, 'importance': float(row['importance']) if row.get('importance') is not None else None, 'address': row.get('address') if isinstance(row.get('address'), dict) else None}
            results.append(result)
        return {'results': results}

class MapRoutes:

    def __init__(self, page):
        self.page = page

    def get_route_summary(self, origin_query: str, destination_query: str=None, travel_mode: str='car', destination_fallback_queries: list | None=None) -> dict:
        import re
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        if not isinstance(origin_query, str) or not origin_query.strip():
            raise ValueError('origin_query must be a non-empty string')
        if travel_mode not in {'car', 'foot'}:
            raise ValueError('travel_mode must be one of: car, foot')
        candidates = []
        if destination_query is not None:
            if not isinstance(destination_query, str) or not destination_query.strip():
                raise ValueError('destination_query must be a non-empty string when provided')
            candidates.append(destination_query.strip())
        if destination_fallback_queries is not None:
            if not isinstance(destination_fallback_queries, list) or not destination_fallback_queries:
                raise ValueError('destination_fallback_queries must be a non-empty list when provided')
            for q in destination_fallback_queries:
                if not isinstance(q, str) or not q.strip():
                    raise ValueError('each destination fallback query must be a non-empty string')
                q = q.strip()
                if q not in candidates:
                    candidates.append(q)
        if not candidates:
            raise ValueError('destination_query or destination_fallback_queries must provide at least one destination')
        attempted = []
        mode_label = {'car': 'Car (OSRM)', 'foot': 'Foot (OSRM)'}[travel_mode]

        def _open_and_bind_controls():
            self.page.goto('/directions', wait_until='domcontentloaded')
            try:
                self.page.wait_for_load_state('networkidle', timeout=10000)
            except PlaywrightTimeoutError:
                pass
            from_box = self.page.get_by_role('textbox', name='From')
            to_box = self.page.get_by_role('textbox', name='To')
            if from_box.count() > 0 and to_box.count() > 0:
                from_target = from_box.first
                to_target = to_box.first
            else:
                route_from = self.page.locator('#route_from, input[name="route_from"]')
                route_to = self.page.locator('#route_to, input[name="route_to"]')
                if route_from.count() == 0 or route_to.count() == 0:
                    raise RuntimeError('Directions input boxes were not found')
                from_target = route_from.nth(1 if route_from.count() > 1 else 0)
                to_target = route_to.nth(1 if route_to.count() > 1 else 0)
            selected = False
            combobox = self.page.get_by_role('combobox')
            if combobox.count() > 0:
                try:
                    combobox.first.select_option(label=mode_label)
                    selected = True
                except Exception:
                    pass
            if not selected:
                selects = self.page.locator('select.routing_engines')
                if selects.count() > 0:
                    target = selects.nth(1 if selects.count() > 1 else 0)
                    try:
                        target.select_option(label=mode_label)
                        selected = True
                    except Exception:
                        pass
            if not selected:
                raise RuntimeError('Directions travel mode control could not be set')
            go_button = self.page.get_by_role('button', name='Go')
            if go_button.count() > 0:
                submit = go_button.first
            else:
                routing_go = self.page.locator('.routing_go, input.routing_go')
                if routing_go.count() == 0:
                    raise RuntimeError('Directions submit control was not found')
                submit = routing_go.nth(1 if routing_go.count() > 1 else 0)
            return (from_target, to_target, submit)
        for candidate in candidates:
            (from_target, to_target, submit) = _open_and_bind_controls()
            from_target.fill(origin_query.strip())
            to_target.fill(candidate)
            attempted.append(candidate)
            submit.click()
            try:
                self.page.wait_for_load_state('networkidle', timeout=15000)
            except PlaywrightTimeoutError:
                pass
            try:
                self.page.get_by_role('heading', name='Directions').wait_for(timeout=5000)
            except Exception:
                pass
            summary_text = None
            try:
                summary_text = self.page.locator('#sidebar_content').inner_text(timeout=5000)
            except Exception:
                try:
                    summary_text = self.page.locator('body').inner_text(timeout=5000)
                except Exception as e:
                    raise RuntimeError('Directions results text was not available') from e
            distance_match = re.search('Distance:\\s*([^\\.\\n]+)', summary_text)
            time_match = re.search('Time:\\s*([^\\.\\n]+)', summary_text)
            distance_text = distance_match.group(1).strip() if distance_match else None
            duration_text = time_match.group(1).strip() if time_match else None
            results_panel_present = bool(distance_text or duration_text or 'Directions' in summary_text)
            if not results_panel_present:
                continue
            try:
                resolved_origin = from_target.input_value(timeout=1000).strip()
            except Exception:
                resolved_origin = origin_query.strip()
            try:
                resolved_destination = to_target.input_value(timeout=1000).strip()
            except Exception:
                resolved_destination = candidate
            return {'origin_query': origin_query.strip(), 'destination_query': candidate, 'attempted_destination_queries': attempted, 'travel_mode': travel_mode, 'resolved_origin': resolved_origin, 'resolved_destination': resolved_destination, 'summary_text': summary_text, 'distance_text': distance_text, 'duration_text': duration_text, 'results_panel_present': results_panel_present, 'final_url': self.page.url}
        raise RuntimeError(f'Could not obtain route result after attempts: {attempted}')

    def get_route_summary_by_coordinates(self, origin: dict, destination: dict, travel_mode: str) -> dict:
        import re
        import requests

        def _parse_point(name: str, value: dict) -> tuple[float, float]:
            if not isinstance(value, dict):
                raise ValueError(f'{name} must be an object with lat and lon')
            if 'lat' in value and 'lon' in value:
                lat_raw = value['lat']
                lon_raw = value['lon']
            elif 'latitude' in value and 'longitude' in value:
                lat_raw = value['latitude']
                lon_raw = value['longitude']
            else:
                raise ValueError(f'{name} must include lat/lon or latitude/longitude')
            try:
                lat = float(lat_raw)
                lon = float(lon_raw)
            except (TypeError, ValueError):
                raise ValueError(f'{name} must include numeric coordinates')
            if lat < -90 or lat > 90:
                raise ValueError(f'{name}.lat must be between -90 and 90')
            if lon < -180 or lon > 180:
                raise ValueError(f'{name}.lon must be between -180 and 180')
            return (lat, lon)

        def _parse_distance_m(distance_text: str):
            if not distance_text:
                return None
            s = distance_text.strip().lower().replace(' ', '')
            try:
                if s.endswith('km'):
                    return float(s[:-2]) * 1000
                if s.endswith('m'):
                    return float(s[:-1])
            except ValueError:
                return None
            return None
        (origin_lat, origin_lon) = _parse_point('origin', origin)
        (dest_lat, dest_lon) = _parse_point('destination', destination)
        if travel_mode == 'car':
            response = requests.get(f'http://18.208.187.221:5000/route/v1/driving/{origin_lon},{origin_lat};{dest_lon},{dest_lat}', params={'overview': 'false', 'steps': 'true', 'geometries': 'polyline'}, timeout=30)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError('unexpected route response shape')
            routes = []
            raw_routes = payload.get('routes')
            if isinstance(raw_routes, list):
                for row in raw_routes:
                    if not isinstance(row, dict):
                        continue
                    try:
                        duration_sec = float(row.get('duration'))
                        distance_m = float(row.get('distance'))
                    except (TypeError, ValueError):
                        continue
                    routes.append({'duration_sec': duration_sec, 'distance_m': distance_m, 'duration_text': None, 'distance_text': None})
            waypoints = []
            raw_waypoints = payload.get('waypoints')
            if isinstance(raw_waypoints, list):
                for row in raw_waypoints:
                    if not isinstance(row, dict):
                        continue
                    waypoint = {'name': str(row.get('name', '')), 'lon': None, 'lat': None}
                    location = row.get('location')
                    if isinstance(location, list) and len(location) >= 2:
                        try:
                            waypoint['lon'] = float(location[0])
                            waypoint['lat'] = float(location[1])
                        except (TypeError, ValueError):
                            waypoint['lon'] = None
                            waypoint['lat'] = None
                    waypoints.append(waypoint)
            return {'travel_mode': travel_mode, 'origin': {'lat': origin_lat, 'lon': origin_lon}, 'destination': {'lat': dest_lat, 'lon': dest_lon}, 'routes': routes, 'waypoints': waypoints, 'route_url': None, 'page_summary_text': None}
        if travel_mode != 'foot':
            raise ValueError('travel_mode must be one of: car, foot')
        route_url = f'http://ec2-18-223-172-69.us-east-2.compute.amazonaws.com:3000/directions?engine=fossgis_osrm_foot&route={origin_lat},{origin_lon};{dest_lat},{dest_lon}'
        response = requests.get(route_url, timeout=30)
        response.raise_for_status()
        page_text = response.text
        distance_text = None
        duration_text = None
        summary_match = re.search('Distance:\\s*([^\\.\\n]+(?:m|km))\\.\\s*Time:\\s*([^\\n]+)', page_text)
        if summary_match:
            distance_text = summary_match.group(1).strip()
            duration_text = summary_match.group(2).strip().rstrip('.')
        else:
            for line in page_text.splitlines():
                line = line.strip()
                if line.startswith('Distance:'):
                    distance_part = line.split('Time:', 1)[0]
                    distance_text = distance_part.split('Distance:', 1)[1].strip().rstrip('.')
                    if 'Time:' in line:
                        duration_text = line.split('Time:', 1)[1].strip().rstrip('.')
                    break
        routes = []
        if distance_text is not None or duration_text is not None:
            routes.append({'duration_sec': None, 'distance_m': _parse_distance_m(distance_text) if distance_text else None, 'duration_text': duration_text, 'distance_text': distance_text})
        return {'travel_mode': travel_mode, 'origin': {'lat': origin_lat, 'lon': origin_lon}, 'destination': {'lat': dest_lat, 'lon': dest_lon}, 'routes': routes, 'waypoints': [], 'route_url': route_url, 'page_summary_text': page_text}

class MapSite:

    def __init__(self, page):
        self.places = MapPlaces(page)
        self.routes = MapRoutes(page)
