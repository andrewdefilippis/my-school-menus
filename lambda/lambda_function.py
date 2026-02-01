# vim: ts=4 et

VERSION = '0.1'

def http(status, body='', headers=None, event=None):
    '''
    Helper to construct standard Lambda Function URL responses.
    Auto-encodes dicts/lists to JSON and logs the request in CLF.
    '''
    import json
    import sys
    if headers is None:
        headers = {}

    if isinstance(body, (dict, list)):
        if 'Content-Type' not in headers:
            headers['Content-Type'] = 'application/json'
        body = json.dumps(body)

    # Logging at end of request in Common Log Format
    if event:
        req_context = event.get('requestContext', {})
        http_req = req_context.get('http', {})
        ip = http_req.get('sourceIp', '-')
        request_time = req_context.get('time', '-')
        method = http_req.get('method', '-')
        path = event.get('rawPath', '-')
        proto = http_req.get('protocol', 'HTTP/1.1')
        size = len(body) if body else 0
        
        print(f'{ip} - - [{request_time}] "{method} {path} {proto}" {status} {size}')

    return {
        'statusCode': status,
        'headers': headers,
        'body': body
    }

def handler(event, context):
    '''
    AWS Lambda handler for Function URL parsing path parameters.
    Path structure: /{district}/{site}/{menu}
    '''
    import json
    import urllib.request
    import urllib.parse
    import os
    import time
    import hashlib

    CACHE_DIR = '/tmp/lambda_cache'
    CACHE_TTL = 7 * 24 * 60 * 60  # One week in seconds

    def get_cache(key):
        if not key:
            return None
        filename = hashlib.md5(key.encode()).hexdigest()
        path = os.path.join(CACHE_DIR, filename)
        if os.path.exists(path):
            stats = os.stat(path)
            if (time.time() - stats.st_mtime) < CACHE_TTL:
                with open(path, 'r') as f:
                    return f.read()
        return None

    def set_cache(keys, content):
        if not os.path.exists(CACHE_DIR):
            os.makedirs(CACHE_DIR, exist_ok=True)
        content_str = str(content)
        for key in keys:
            if not key:
                continue
            filename = hashlib.md5(key.encode()).hexdigest()
            path = os.path.join(CACHE_DIR, filename)
            with open(path, 'w') as f:
                f.write(content_str)

    raw_path = event.get('rawPath', '').strip('/')
    parts = raw_path.split('/')

    params = {
        'district': parts[0] if len(parts) > 0 else None,
        'site': parts[1] if len(parts) > 1 else None,
        'menu': parts[2] if len(parts) > 2 else None
    }

    # Initial Cache Check: By raw strings (case-insensitive)
    raw_cache_key = f'raw:{params["district"]}:{params["site"]}:{params["menu"]}'.lower()
    cached_response = get_cache(raw_cache_key)
    if cached_response:
        return http(200, cached_response, {'Content-Type': 'text/calendar', 'X-Cache': f'HIT {raw_cache_key}'}, event=event)

    resolved = {}
    metadata = {}

    # 1. Resolve District
    district_input = params.get('district')
    if district_input is None:
        return http(400, {'error': 'Missing district'}, event=event)

    try:
        resolved['district'] = int(district_input)
    except ValueError:
        decoded_district = urllib.parse.unquote(district_input)
        api_url = f'https://menus.healthepro.com/api/organizations/?query={urllib.parse.quote(decoded_district)}'
        try:
            with urllib.request.urlopen(api_url) as response:
                data = json.loads(response.read().decode())
            results = data.get('data', [])
            if len(results) != 1:
                return http(400, {'error': 'District resolution failed'}, event=event)
            orgs = results[0].get('organizations', [])
            if len(orgs) != 1:
                return http(400, {'error': 'Organization resolution failed'}, event=event)
            resolved['district'] = orgs[0].get('id')
        except Exception:
            return http(500, {'error': 'External API failure during district resolution'}, event=event)

    # 2. Resolve Site
    site_input = params.get('site')
    if site_input is None:
        return http(400, {'error': 'Missing site'}, event=event)

    try:
        resolved['site'] = int(site_input)
    except ValueError:
        site_list_url = f'https://menus.healthepro.com/api/organizations/{resolved["district"]}/sites/list'
        try:
            with urllib.request.urlopen(site_list_url) as response:
                site_data = json.loads(response.read().decode())
            search_term = urllib.parse.unquote(site_input).lower()
            for site in site_data.get('data', []):
                name = site.get('name', '')
                if name.lower().startswith(search_term):
                    resolved['site'] = site.get('id')
                    break
            if 'site' not in resolved:
                return http(404, {'error': 'Site not found'}, event=event)
        except Exception:
            return http(500, {'error': 'Site list failure'}, event=event)

    # 3. Resolve Menu
    menu_input = params.get('menu')
    if menu_input is None:
        return http(400, {'error': 'Missing menu'}, event=event)

    try:
        resolved['menu'] = int(menu_input)
    except ValueError:
        menu_list_url = f'https://menus.healthepro.com/api/organizations/{resolved["district"]}/sites/{resolved["site"]}/menus/'
        try:
            with urllib.request.urlopen(menu_list_url) as response:
                menu_data = json.loads(response.read().decode())
            search_term = urllib.parse.unquote(menu_input).lower()
            for menu in menu_data.get('data', []):
                name = menu.get('name', '')
                if search_term in name.lower():
                    resolved['menu'] = menu.get('id')
                    metadata['menu'] = menu
                    break
            if 'menu' not in resolved:
                return http(404, {'error': 'Menu not found'}, event=event)
        except Exception:
            return http(400, {'error': 'Menu not valid'}, event=event)

    # Unified District Metadata Retrieval
    district_id_url = f'https://menus.healthepro.com/api/organizations/{resolved["district"]}'
    try:
        with urllib.request.urlopen(district_id_url) as response:
            dist_resp = json.loads(response.read().decode())
            metadata['district'] = dist_resp.get('data')
    except Exception:
        return http(404, {'error': 'District not valid'}, event=event)

    # Unified Site Metadata Retrieval
    site_detail_url = f'https://menus.healthepro.com/api/organizations/{resolved["district"]}/sites/{resolved["site"]}'
    try:
        with urllib.request.urlopen(site_detail_url) as response:
            site_resp = json.loads(response.read().decode())
            metadata['site'] = site_resp.get('data')
    except Exception:
        return http(404, {'error': 'Site not valid'}, event=event)

    # Fetch Menu metadata if ID was provided directly
    if 'menu' not in metadata:
        menu_list_url = f'https://menus.healthepro.com/api/organizations/{resolved["district"]}/sites/{resolved["site"]}/menus/'
        try:
            with urllib.request.urlopen(menu_list_url) as response:
                menu_data = json.loads(response.read().decode())
                for menu in menu_data.get('data', []):
                    if menu.get('id') == resolved['menu']:
                        metadata['menu'] = menu
                        break
        except Exception:
            return http(404, {'error': 'Menu not valid'}, event=event)

    # Second Cache Check: By numeric IDs
    id_cache_key = f'id:{resolved["district"]}:{resolved["menu"]}'
    cached_ics = get_cache(id_cache_key)
    if cached_ics:
        set_cache([raw_cache_key], cached_ics)
        return http(200, cached_ics, {'Content-Type': 'text/calendar', 'X-Cache': f'HIT {id_cache_key}'}, event=event)

    # Call the processing logic
    ics = generate_ics(metadata, resolved)

    # Final caching
    cache_keys = [raw_cache_key, id_cache_key]
    set_cache(cache_keys, ics)

    return http(200, ics, {'Content-Type': 'text/calendar', 'X-Cache': f'MISS {id_cache_key}'}, event=event)

def generate_ics(metadata, ids):
    '''
    External library processing logic.
    Returns ical (ics) formatted string.
    '''
    from my_school_menus.msm_api import Menus
    from my_school_menus.calendar import Calendar

    menus = Menus()
    menu = menus.get(district_id=ids['district'], menu_id=ids['menu'])
    available_dates = menus.menu_months(menu)

    name = f'{metadata["site"]["name"]} - {metadata["menu"]["name"]}'
    
    desc = (
        f'School/Menu: {metadata["site"]["name"]} - {metadata["menu"]["name"]}\n'
        f'District: {metadata["district"]["name"]}\n'
        f'WWW: {metadata["district"]["url"]}\n'
        f'Address:\n'
        f'    {metadata["district"]["address"]["line_1"]}\n'
        f'    {metadata["district"]["address"]["city"]}, {metadata["district"]["address"]["state"]} {metadata["district"]["address"]["zip_code"]}\n'
        f'Phone: {metadata["district"]["phone"]}\n'
    )

    cal = Calendar(
        vendor='c13',
        product='msmcal',
        version=VERSION,
        lang=None,
        desc=desc,
        name=name,
    )

    for date in available_dates:
        datemenu = menus.get(
            district_id=ids['district'], menu_id=ids['menu'], date=date
        )
        events = cal.events(datemenu)
        cal += events
        
    return cal.ical()