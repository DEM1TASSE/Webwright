"""Generated candidate package; not promoted."""

class MapPlaces:

    def __init__(self, page):
        self.page = page

    async def search_places(self, query: str, limit: int=10) -> dict:
        import re
        from urllib.parse import quote, urljoin, urlsplit
        if not isinstance(query, str) or not query.strip():
            raise ValueError('query must be a non-empty string')
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError('limit must be a positive integer')
        if not (self.page.url or '').startswith(('http://', 'https://')):
            raise RuntimeError('self.page.url must already be on the site so the deployment origin can be derived')
        parts = urlsplit(self.page.url)
        origin = f'{parts.scheme}://{parts.netloc}'
        home_url = urljoin(origin + '/', '')
        await self.page.goto(home_url, wait_until='domcontentloaded')
        script_urls = await self.page.locator('script[src]').evaluate_all("els => els.map(e => e.getAttribute('src')).filter(Boolean)")
        search_base_url = None
        for src in script_urls:
            asset_url = urljoin(origin + '/', str(src).lstrip('/'))
            try:
                asset_response = await self.page.request.get(asset_url)
            except Exception:
                continue
            if not asset_response.ok:
                continue
            try:
                text = await asset_response.text()
            except Exception:
                continue
            match = re.search('NOMINATIM_URL\\s*[:=]\\s*["\\\']([^"\\\']+)["\\\']', text)
            if match:
                search_base_url = match.group(1)
                break
        if not search_base_url:
            raise RuntimeError('Could not discover the deployment search backend from site assets')
        request_url = f'{search_base_url.rstrip('/')}/search?format=jsonv2&limit={limit}&q={quote(query.strip())}'
        api_response = await self.page.request.get(request_url)
        if not api_response.ok:
            raise RuntimeError(f'Search backend request failed with status {api_response.status}')
        payload = await api_response.json()
        if not isinstance(payload, list):
            raise RuntimeError('Expected search backend to return a JSON array')
        ui_by_coords = {}
        try:
            primary_input = self.page.locator('input[name="query"]:visible').first
            alt_input = self.page.locator('input[placeholder="Search"]:visible').first
            used_ui = False
            if await primary_input.count() > 0:
                await primary_input.wait_for(state='visible', timeout=5000)
                await primary_input.fill('')
                await primary_input.fill(query.strip())
                submit_button = self.page.locator('input[name="commit"]:visible').first
                if await submit_button.count() > 0:
                    await submit_button.click()
                    used_ui = True
            elif await alt_input.count() > 0:
                await alt_input.wait_for(state='visible', timeout=5000)
                await alt_input.fill('')
                await alt_input.fill(query.strip())
                await alt_input.press('Enter')
                used_ui = True
            if used_ui:
                await self.page.wait_for_timeout(1500)
                anchors = self.page.locator('a.set_position')
                count = await anchors.count()
                for i in range(count):
                    a = anchors.nth(i)
                    lat_text = await a.get_attribute('data-lat')
                    lon_text = await a.get_attribute('data-lon')
                    if lat_text is None or lon_text is None:
                        continue
                    href = await a.get_attribute('href')
                    ui_by_coords[str(lat_text).strip(), str(lon_text).strip()] = {'name': (await a.get_attribute('data-name') or await a.inner_text() or '').strip(), 'latitude_text': str(lat_text), 'longitude_text': str(lon_text), 'href': href, 'url': urljoin(self.page.url, href) if href else None}
        except Exception:
            ui_by_coords = {}
        results = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            display_name = row.get('display_name')
            lat_text = row.get('lat')
            lon_text = row.get('lon')
            if display_name is None or lat_text is None or lon_text is None:
                continue
            try:
                lat = float(lat_text)
                lon = float(lon_text)
            except (TypeError, ValueError):
                continue
            place_id = row.get('place_id')
            ui_match = ui_by_coords.get((str(lat_text).strip(), str(lon_text).strip()), {})
            results.append({'place_id': str(place_id) if place_id is not None else None, 'display_name': str(display_name), 'name': str(ui_match.get('name') or display_name), 'lat': lat, 'lon': lon, 'latitude': lat, 'longitude': lon, 'raw_lat': str(lat_text), 'raw_lon': str(lon_text), 'latitude_text': str(ui_match.get('latitude_text') or lat_text), 'longitude_text': str(ui_match.get('longitude_text') or lon_text), 'href': ui_match.get('href'), 'url': ui_match.get('url')})
        return {'results': results}

class MapRoutes:

    def __init__(self, page):
        self.page = page

    async def get_route_by_coordinates(self, origin: dict, destination: dict, travel_mode: str) -> dict:
        import re
        from urllib.parse import urlencode, urljoin, urlsplit

        def _parse_point(name: str, value: dict):
            if not isinstance(value, dict):
                raise ValueError(f'{name} must be an object with lat and lon')
            if 'lat' not in value or 'lon' not in value:
                raise ValueError(f'{name} must include lat and lon')
            try:
                lat = float(value['lat'])
                lon = float(value['lon'])
            except (TypeError, ValueError):
                raise ValueError(f'{name}.lat and {name}.lon must be numeric')
            if not -90.0 <= lat <= 90.0:
                raise ValueError(f'{name}.lat out of range')
            if not -180.0 <= lon <= 180.0:
                raise ValueError(f'{name}.lon out of range')
            return (lat, lon)

        def _parse_duration_seconds(duration_text: str):
            if duration_text is None:
                return None
            text = duration_text.strip()
            m = re.fullmatch('(\\d+):(\\d{2})', text)
            if m:
                return int(m.group(1)) * 3600 + int(m.group(2)) * 60
            m = re.fullmatch('(\\d+)\\s*min(?:ute)?s?', text, re.IGNORECASE)
            if m:
                return int(m.group(1)) * 60
            m = re.fullmatch('(\\d+)\\s*h(?:our)?s?\\s*(\\d+)\\s*min(?:ute)?s?', text, re.IGNORECASE)
            if m:
                return int(m.group(1)) * 3600 + int(m.group(2)) * 60
            return None

        def _extract_summary_fields(text: str):
            if not text:
                return (None, None, False)
            m = re.search('Distance:\\s*([^\\.\\n]+(?:m|km))\\.\\s*Time:\\s*([0-9]+:[0-9]{2})', text)
            if m:
                return (m.group(1).strip(), m.group(2).strip(), True)
            m = re.search('Distance:\\s*(.*?)\\.?\\s*(?:Time:\\s*([^\\.\\n]+))', text, re.S)
            if m:
                distance_value = m.group(1).strip() or None
                duration_value = m.group(2).strip() or None
                return (distance_value, duration_value, True)
            return (None, None, False)
        if travel_mode not in {'car', 'walking'}:
            raise ValueError('travel_mode must be one of: car, walking')
        if not (self.page.url or '').startswith(('http://', 'https://')):
            raise RuntimeError('self.page.url must already be on the site so the deployment origin can be derived')
        parts = urlsplit(self.page.url)
        origin_url = f'{parts.scheme}://{parts.netloc}'
        origin_lat, origin_lon = _parse_point('origin', origin)
        destination_lat, destination_lon = _parse_point('destination', destination)
        if travel_mode == 'car':
            directions_url = urljoin(origin_url + '/', 'directions?' + urlencode({'from': f'{origin_lat},{origin_lon}', 'to': f'{destination_lat},{destination_lon}', 'engine': 'fossgis_osrm_car'}))
        else:
            directions_url = urljoin(origin_url + '/', 'directions?' + urlencode({'engine': 'fossgis_osrm_foot', 'route': f'{origin_lat},{origin_lon};{destination_lat},{destination_lon}'}))
        response = await self.page.goto(directions_url, wait_until='domcontentloaded')
        await self.page.wait_for_timeout(2500 if travel_mode == 'walking' else 5000)
        summary_text = await self.page.locator('body').inner_text()
        distance_text, duration_text, raw_summary_text_present = _extract_summary_fields(summary_text)
        duration_seconds = _parse_duration_seconds(duration_text)
        return {'travel_mode': travel_mode, 'transport_mode': travel_mode, 'origin': {'lat': origin_lat, 'lon': origin_lon}, 'destination': {'lat': destination_lat, 'lon': destination_lon}, 'distance_text': distance_text, 'duration_text': duration_text, 'duration_seconds': duration_seconds, 'directions_url': self.page.url, 'route_url': self.page.url, 'summary_text': summary_text, 'raw_summary_text_present': raw_summary_text_present, 'document_status': response.status if response else None}

    async def get_route_summary(self, origin: str, destination: str, travel_mode: str) -> dict:
        import re
        from urllib.parse import urljoin, urlsplit
        if not isinstance(origin, str) or not origin.strip():
            raise ValueError('origin must be a non-empty string')
        if not isinstance(destination, str) or not destination.strip():
            raise ValueError('destination must be a non-empty string')
        if travel_mode not in {'car', 'walking'}:
            raise ValueError('travel_mode must be one of: car, walking')
        if not (self.page.url or '').startswith(('http://', 'https://')):
            raise RuntimeError('self.page.url must already be on the site so the deployment origin can be derived')
        parts = urlsplit(self.page.url)
        base_origin = f'{parts.scheme}://{parts.netloc}'

        def _parse_duration_seconds(value: str):
            if not value:
                return None
            text = value.strip()
            m = re.fullmatch('(\\d+):(\\d{2})', text)
            if m:
                return int(m.group(1)) * 3600 + int(m.group(2)) * 60
            m = re.fullmatch('(\\d+)\\s*min(?:ute)?s?', text, re.IGNORECASE)
            if m:
                return int(m.group(1)) * 60
            return None

        def _extract_summary_fields(text: str):
            if not text:
                return (None, None)
            m = re.search('Distance:\\s*(.*?)\\.\\s*Time:\\s*(.*?)\\.', text, re.S)
            if m:
                return (m.group(1).strip() or None, m.group(2).strip() or None)
            m = re.search('Distance:\\s*(.*?)\\.?\\s*Time:\\s*([^\\.\\n]+)', text, re.S)
            if m:
                return (m.group(1).strip() or None, m.group(2).strip() or None)
            distance_only = re.search('Distance:\\s*([^\\n]+)', text)
            time_only = re.search('Time:\\s*([^\\n]+)', text)
            return (distance_only.group(1).strip() if distance_only else None, time_only.group(1).strip() if time_only else None)

        async def _first_visible(candidates, timeout_ms: int):
            for locator in candidates:
                try:
                    if await locator.count() == 0:
                        continue
                    await locator.first.wait_for(state='visible', timeout=timeout_ms)
                    return locator.first
                except Exception:
                    continue
            return None
        await self.page.goto(urljoin(base_origin + '/', 'directions'), wait_until='domcontentloaded')
        from_box = await _first_visible([self.page.locator('input[name="route_from"]:visible'), self.page.locator('#route_from:visible'), self.page.locator('input[placeholder="From"]:visible'), self.page.get_by_role('textbox', name='From')], 3000)
        if from_box is None:
            raise RuntimeError('Visible route origin input not found')
        to_box = await _first_visible([self.page.locator('input[name="route_to"]:visible'), self.page.locator('#route_to:visible'), self.page.locator('input[placeholder="To"]:visible'), self.page.get_by_role('textbox', name='To')], 3000)
        if to_box is None:
            raise RuntimeError('Visible route destination input not found')
        mode_select = await _first_visible([self.page.locator('select.routing_engines:visible'), self.page.locator('select[name="routing_engines"]:visible'), self.page.locator('select:visible'), self.page.get_by_role('combobox')], 3000)
        if mode_select is None:
            raise RuntimeError('Visible routing engine selector not found')
        go_button = await _first_visible([self.page.locator('input.routing_go:visible'), self.page.get_by_role('button', name='Go'), self.page.locator('button:visible').filter(has_text='Go')], 3000)
        if go_button is None:
            raise RuntimeError('Visible route submission control not found')
        await from_box.fill('')
        await from_box.fill(origin.strip())
        await to_box.fill('')
        await to_box.fill(destination.strip())
        mode_labels = {'car': 'Car (OSRM)', 'walking': 'Foot (OSRM)'}
        await mode_select.select_option(label=mode_labels[travel_mode])
        await go_button.click()
        try:
            await self.page.wait_for_load_state('networkidle')
        except Exception:
            pass
        try:
            await self.page.wait_for_function("() => {\n                    const t = document.body ? document.body.innerText : '';\n                    return t.includes('Distance:') || t.includes('Time:');\n                }", timeout=25000)
        except Exception:
            pass
        await self.page.wait_for_timeout(1000)
        sidebar_summary_text = ''
        try:
            sidebar = self.page.locator('#sidebar_content')
            if await sidebar.count() > 0:
                sidebar_summary_text = (await sidebar.first.inner_text()).strip()
        except Exception:
            sidebar_summary_text = ''
        paragraph_summary_text = ''
        try:
            paragraph = self.page.locator('p').filter(has_text='Distance:')
            if await paragraph.count() > 0:
                paragraph_summary_text = (await paragraph.first.inner_text()).strip()
        except Exception:
            paragraph_summary_text = ''
        body_text = await self.page.locator('body').inner_text()
        summary_text = sidebar_summary_text or paragraph_summary_text or body_text
        distance_text, duration_text = _extract_summary_fields(summary_text)
        try:
            resolved_origin = await from_box.input_value()
        except Exception:
            resolved_origin = origin.strip()
        try:
            resolved_destination = await to_box.input_value()
        except Exception:
            resolved_destination = destination.strip()
        try:
            selected_mode = await mode_select.input_value()
        except Exception:
            selected_mode = ''
        return {'origin_query': origin, 'destination_query': destination, 'resolved_origin': resolved_origin, 'resolved_destination': resolved_destination, 'origin_resolved_text': resolved_origin, 'destination_resolved_text': resolved_destination, 'route_mode': travel_mode, 'routing_mode': travel_mode, 'travel_mode': travel_mode, 'selected_mode': selected_mode, 'distance_text': distance_text, 'duration_text': duration_text, 'duration_seconds': _parse_duration_seconds(duration_text) if duration_text else None, 'summary_text': summary_text, 'sidebar_summary_text': sidebar_summary_text, 'final_url': self.page.url, 'result_page_contains_distance': 'Distance:' in summary_text}

class MapSite:

    def __init__(self, page):
        self.places = MapPlaces(page)
        self.routes = MapRoutes(page)
