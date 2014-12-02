def _setup():
    import json
    import re
    from collections import OrderedDict
    from ast import literal_eval
    from os import path, environ
    from warnings import warn

    environ_var = re.compile('YOUTUBE_TO_POCKET_([A-Z_]+)')

    def relopen(name, *args, **kwargs):
        return open(path.join(path.dirname(__file__), name), *args, **kwargs)

    with relopen('default.json') as default:
        config = json.load(default, object_pairs_hook=OrderedDict)
    try:
        with relopen('config.json') as config_fp:
            config.update(json.load(config_fp, object_pairs_hook=OrderedDict))
    except IOError:
        warn('user config is missing')

    # Load options from environment and parse them as Python literals
    for key, value in environ.iteritems():
        mo = environ_var.match(key)
        if mo is not None:
            option = mo.group(1).upper()
            try:
                config[option] = literal_eval(value)
            except (ValueError, SyntaxError):
                config[option] = value

    config_keys = config.iterkeys

    def save():
        for key in config_keys():
            config[key] = globals()[key]
        with relopen('config.json', 'w') as config_fp:
            json.dump(config, config_fp, indent=4)

    globals()['save'] = save
    globals().update(config)

_setup()
del _setup
