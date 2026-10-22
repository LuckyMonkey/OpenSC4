"""Validation at the native boundary; all checks run before helper mutation."""
import datetime
import math

KINDS = {'Street', 'Road', 'One-Way Road', 'Dirt Road', 'Avenue', 'Maxis El Highway'}


def number(value, low, high, label, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{label}: finite number required')
    if not low <= value <= high or (integer and value != int(value)):
        raise ValueError(f'{label}: out of range or nonintegral')
    return value


def rates(values):
    if not isinstance(values, list) or len(values) != 12:
        raise ValueError('twelve tax rates required')
    for value in values:
        number(value, 0, 100, 'rate')


def city(model):
    if model.get('schema') != 'opensc4.canonical-city.v1':
        raise ValueError('unsupported canonical city schema')
    dims = model['dimensions']
    w = number(dims['width'], 1, 512, 'width', True)
    h = number(dims['height'], 1, 512, 'height', True)

    def position(pos):
        number(pos['x'], 0, w - 1, 'x')
        number(pos['y'], 0, h - 1, 'y')

    entities = model['entities']
    if not isinstance(entities, list) or len(entities) > 262144:
        raise ValueError('invalid entity count')
    ids = set()
    for entity in entities:
        ident = entity['id']
        if not isinstance(ident, str) or ident in ids:
            raise ValueError('duplicate or invalid entity id')
        ids.add(ident)
        position(entity['position'])
        attrs = entity['attributes']
        if attrs.get('class', 'other') not in {'residential', 'commercial', 'industrial', 'power', 'civic', 'other'}:
            raise ValueError('unsupported building class')
        for value in attrs.get('capacity', {}).values():
            number(value, 0, 10000000, 'capacity', True)
        number(attrs.get('upkeep', 0), 0, 100000000, 'upkeep')
        for value in attrs.get('pollution', {}).values():
            number(value, 0, 1000000, 'pollution')
        for value in attrs.get('pollution_radius', {}).values():
            number(value, 0, 512, 'pollution radius')
        foot = entity.get('footprint')
        if foot:
            position({'x': foot['min_x'], 'y': foot['min_y']})
            position({'x': foot['max_x'], 'y': foot['max_y']})
            if foot['min_x'] > foot['max_x'] or foot['min_y'] > foot['max_y']:
                raise ValueError('inverted footprint')
    roads = model['networks'].get('road', {'nodes': [], 'edges': []})
    nodes = {}
    if len(roads['nodes']) > 262144 or len(roads['edges']) > 524288:
        raise ValueError('road graph too large')
    for node in roads['nodes']:
        ident = node['id']
        if not isinstance(ident, str) or ident in nodes:
            raise ValueError('duplicate or invalid road node')
        position(node['position'])
        nodes[ident] = node['position']
    edges = set()
    for edge in roads['edges']:
        a, b = edge['from'], edge['to']
        pair = tuple(sorted((a, b)))
        if a == b or a not in nodes or b not in nodes or pair in edges:
            raise ValueError('invalid or duplicate road edge')
        edges.add(pair)
        if edge['kind'] not in KINDS:
            raise ValueError('unsupported road kind')
        p, q = nodes[a], nodes[b]
        if p == q:
            raise ValueError('zero length road')


def command(payload, city_active=False):
    kind = payload.get('type')
    if kind == 'city_init':
        city(payload['city'])
        rates(payload.get('rates', [9.0] * 12))
        number(payload.get('mult', 1), 0, 100, 'multiplier')
        number(payload.get('funds', 50000), -(2**53), 2**53, 'funds', True)
        number(payload.get('seed', 1), 0, 2**32 - 1, 'seed', True)
        datetime.date.fromisoformat(payload.get('start_date', '2000-01-01'))
    elif kind in {'city_advance', 'city_layer', 'city_traffic'}:
        if not city_active:
            raise ValueError('city not initialized')
        if kind == 'city_advance':
            number(payload.get('days', 1), 1, 366, 'days', True)
        elif kind == 'city_layer' and payload.get('name', 'AirPollution') != 'AirPollution':
            raise ValueError('unsupported layer')
    elif kind == 'add_road':
        if city_active:
            raise ValueError('legacy road mutation unavailable in city mode')
        for field, alias in [('x1','from_x'), ('y1','from_y'), ('x2','to_x'), ('y2','to_y')]:
            number(payload.get(field, payload.get(alias, 0)), -100000, 100000, field)
    elif kind == 'budget_set':
        if city_active:
            raise ValueError('legacy budget mutation unavailable in city mode')
        rates(payload['rates'])
        if len(payload['bases']) != 12:
            raise ValueError('twelve bases required')
        for value in payload['bases']:
            number(value, 0, 2**53, 'base', True)
        number(payload['funds'], -(2**53), 2**53, 'funds', True)
        number(payload.get('expenses', 0), 0, 2**53, 'expenses', True)
        number(payload.get('mult', 1), 0, 100, 'multiplier')
    elif kind == 'budget_month':
        if city_active:
            raise ValueError('legacy budget mutation unavailable in city mode')
        number(payload.get('days', 30), 1, 366, 'days', True)
    else:
        raise ValueError('unknown_command')
