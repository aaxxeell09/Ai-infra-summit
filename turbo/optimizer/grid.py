"""Lane B mass generation: bounded grids and refinement around a moving control.

Single-variable neighbourhoods keep causal attribution but reach only a few
dozen treatments. A bounded grid reaches thousands, at the price of attribution:
a grid point that changes four fields cannot tell you which field mattered. Both
are legitimate, they answer different questions, and the difference must stay
visible in the candidate itself rather than in a reader's memory, so every grid
point declares its changed fields and records ``causal_attribution=False``.

Refinement is deliberately not a black-box optimiser. It re-centres the search
on an observed region and shrinks the step, which is explainable after the fact.
An acquisition function over 39 enumerated values would be sophistication
without information.
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from turbo.optimizer import search_space as space
from turbo.optimizer.state import config_hash

#: A grid larger than this is refused rather than silently truncated. Truncating
#: turns a declared design into an arbitrary prefix of one, which is not a design.
DEFAULT_MAX_POINTS = 5000


def axes(backend, *, parameters=None, families=None):
    """Enumerable axes for this backend, as an ordered mapping name to values.

    Only controls the registry marks supported for this backend appear. A caller
    asking for an unsupported parameter gets a KeyError-free empty axis and the
    omission is reported by :func:`axis_rejections`, never silently ignored.
    """
    selected = {}
    for name in space.supported_parameters(backend):
        spec = space.PARAMETERS[name]
        if parameters is not None and name not in parameters:
            continue
        if families is not None and spec['family'] not in families:
            continue
        values = spec['allowed_values']
        if values:
            selected[name] = tuple(values)
    return selected


def axis_rejections(backend, parameters):
    """Why each requested parameter is not an axis on this backend."""
    rejected = []
    for name in parameters or ():
        if name in space.supported_parameters(backend):
            continue
        spec = space.parameter(name)
        rejected.append((name, space.lane(name, backend), spec['support_status'], spec['evidence']))
    return rejected


def grid_size(selected):
    """Point count of a full Cartesian product, computed without building it."""
    total = 1
    for values in selected.values():
        total *= len(values)
    return total if selected else 0


def bounded_grid(control_config, backend, *, parameters=None, families=None,
                 max_points=DEFAULT_MAX_POINTS, index_start=1, label='G'):
    """Materialise a Cartesian grid, refusing rather than truncating when large.

    Returns ``(candidates, rejections)``. A point identical to the control is
    skipped; a point differing in exactly one field is emitted as an ordinary
    single-variable candidate so it keeps attribution, which means a grid can
    contain both kinds and the consumer must read ``causal_attribution``.
    """
    selected = axes(backend, parameters=parameters, families=families)
    rejections = axis_rejections(backend, parameters)
    if not selected:
        return [], rejections
    size = grid_size(selected)
    if size > max_points:
        raise ValueError('Grid of ' + str(size) + ' points exceeds max_points ' + str(max_points)
                         + '; narrow the axes or raise the bound deliberately')
    names = list(selected)
    control_hash = config_hash(control_config)
    candidates, index = [], index_start
    for combination in itertools.product(*(selected[name] for name in names)):
        config = dict(control_config)
        config.update(dict(zip(names, combination)))
        changed = sorted(name for name, value in zip(names, combination)
                         if control_config.get(name) != value
                         or type(control_config.get(name)) is not type(value))
        if not changed:
            continue
        candidates.append(_candidate(config, control_config, control_hash, changed, backend,
                                     label + '-%04d' % index))
        index += 1
    return candidates, rejections


def _candidate(config, control_config, control_hash, changed, backend, candidate_id):
    single = len(changed) == 1
    family = (space.PARAMETERS[changed[0]]['family'] if single
              else '+'.join(sorted({space.PARAMETERS[n]['family'] for n in changed})))
    treatment = ', '.join(name + '=' + repr(config[name]) for name in changed)
    restart = any(space.PARAMETERS[name]['requires_restart'] for name in changed)
    record = {
        'candidate_id': candidate_id,
        'parent_control': control_hash,
        'family': family,
        'variable': changed[0] if single else None,
        'variables': list(changed),
        'treatment': treatment,
        'config': config,
        'config_hash': config_hash(config),
        'hypothesis': _hypothesis(changed, config, control_config, backend, single),
        'stage': 'S0',
        'lane': space.lane(changed[0], backend),
        'requires_restart': restart,
        'expected_hardware_seconds': None,
        'priority': None,
        'status': 'generated',
    }
    if not single:
        record['integration_test'] = True
        record['causal_attribution'] = False
    return record


def _hypothesis(changed, config, control_config, backend, single):
    if single:
        name = changed[0]
        spec = space.PARAMETERS[name]
        return ('Moving ' + name + ' from ' + repr(control_config.get(name)) + ' to '
                + repr(config[name]) + ' on ' + backend + ' changes the ' + spec['family']
                + ' behaviour; supported because ' + spec['evidence'].split(';')[0] + '.')
    return ('Bounded grid point moving ' + ', '.join(changed) + ' together on ' + backend
            + '. Attribution to any single field is not available from this point alone; it '
              'locates a region, and a single-variable follow-up explains it.')


def refine(control_config, backend, parameter, *, radius=1, index_start=1, label='R'):
    """Single-variable neighbourhood around the control's current value.

    Refinement keeps attribution, so it is what a promising grid region should
    be followed up with. Numeric and enumerated axes are both handled by
    position in the declared enumeration, never by arithmetic on the value: the
    enumerations are deliberately non-uniform and interpolating between two of
    their points would invent a value nobody declared supported.
    """
    if parameter not in space.supported_parameters(backend):
        spec = space.parameter(parameter)
        raise ValueError(parameter + ' is not refinable on ' + backend + ' (status '
                         + spec['support_status'] + ', lane ' + space.lane(parameter, backend) + ')')
    if not isinstance(radius, int) or radius < 1:
        raise ValueError('radius must be a positive integer')
    values = list(space.PARAMETERS[parameter]['allowed_values'] or ())
    current = control_config.get(parameter)
    try:
        centre = values.index(current)
        window = values[max(0, centre - radius): centre + radius + 1]
    except ValueError:
        # The control sits outside the declared enumeration, so there is no
        # neighbourhood to speak of; offering the whole axis is honest, silently
        # picking a nearest value would not be.
        window = values
    control_hash = config_hash(control_config)
    candidates, index = [], index_start
    for value in window:
        if value == current and type(value) is type(current):
            continue
        config = dict(control_config)
        config[parameter] = value
        candidates.append(_candidate(config, control_config, control_hash, [parameter], backend,
                                     label + '-%04d' % index))
        index += 1
    return candidates


def reachable_treatment_count(backend):
    """Honest ceilings, kept together so a report cannot quote the wrong one."""
    selected = axes(backend)
    return {'single_variable_treatments': space.space_size(backend),
            'full_cartesian_points': grid_size(selected),
            'axes': {name: len(values) for name, values in selected.items()}}
