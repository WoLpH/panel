"""
Patches bokeh resources to make it easy to add external JS and CSS
resources via the panel.config object.
"""
import copy
import glob
import importlib
import json
import os

from base64 import b64encode
from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path

import param

from bokeh.embed.bundle import (
    Bundle as BkBundle, _bundle_extensions, _use_mathjax, bundle_models,
    extension_dirs,
)
from bokeh.resources import Resources as BkResources
from bokeh.settings import settings as _settings
from jinja2.environment import Environment
from jinja2.loaders import FileSystemLoader
from markupsafe import Markup

from ..util import isurl, url_path
from .state import state

with open(Path(__file__).parent.parent / 'package.json') as f:
    package_json = json.load(f)
    js_version = package_json['version'].split('+')[0]

def get_env():
    ''' Get the correct Jinja2 Environment, also for frozen scripts.
    '''
    local_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '_templates'))
    return Environment(loader=FileSystemLoader(local_path))

def conffilter(value):
    return json.dumps(OrderedDict(value)).replace('"', '\'')

_env = get_env()
_env.trim_blocks = True
_env.lstrip_blocks = True
_env.filters['json'] = lambda obj: Markup(json.dumps(obj))
_env.filters['conffilter'] = conffilter
_env.filters['sorted'] = sorted

# Handle serving of the panel extension before session is loaded
RESOURCE_MODE = 'server'
PANEL_DIR = Path(__file__).parent.parent
DIST_DIR = PANEL_DIR / 'dist'
BUNDLE_DIR = DIST_DIR / 'bundled'
ASSETS_DIR = PANEL_DIR / 'assets'
BASE_TEMPLATE = _env.get_template('base.html')
ERROR_TEMPLATE = _env.get_template('auth_error.html')
DEFAULT_TITLE = "Panel Application"
JS_RESOURCES = _env.get_template('js_resources.html')
CDN_DIST = f"https://unpkg.com/@holoviz/panel@{js_version}/dist/"
LOCAL_DIST = "static/extensions/panel/"
COMPONENT_PATH = "components/"

CSS_URLS = {
    'font-awesome': 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.1/css/all.min.css',
    'bootstrap4': 'https://cdn.jsdelivr.net/npm/bootstrap@4.6.1/dist/css/bootstrap.min.css'
}

JS_URLS = {
    'jQuery': 'https://cdn.jsdelivr.net/npm/jquery@3.5.1/dist/jquery.slim.min.js',
    'bootstrap4': 'https://cdn.jsdelivr.net/npm/bootstrap@4.6.1/dist/js/bootstrap.bundle.min.js'
}

extension_dirs['panel'] = str(DIST_DIR)

@contextmanager
def set_resource_mode(mode):
    global RESOURCE_MODE
    old_resources = _settings.resources._user_value
    old_mode = RESOURCE_MODE
    _settings.resources = RESOURCE_MODE = mode
    try:
        yield
    finally:
        RESOURCE_MODE = old_mode
        _settings.resources.set_value(old_resources)

def resolve_custom_path(obj, path):
    """
    Attempts to resolve a path relative to some component.
    """
    if not path:
        return
    path = str(path)
    if path.startswith(os.path.sep):
        return os.path.isfile(path)
    try:
        mod = importlib.import_module(obj.__module__)
        return (Path(mod.__file__).parent / path).is_file()
    except Exception:
        return None

def component_rel_path(component, path):
    """
    Computes the absolute to a component resource.
    """
    if not isinstance(component, type):
        component = type(component)
    mod = importlib.import_module(component.__module__)
    rel_dir = Path(mod.__file__).parent
    if os.path.isabs(path):
        abs_path = path
    else:
        abs_path = os.path.abspath(os.path.join(rel_dir, path))
    return os.path.relpath(abs_path, rel_dir)

def component_resource_path(component, attr, path):
    """
    Generates a canonical URL for a component resource.
    """
    if not isinstance(component, type):
        component = type(component)
    component_path = COMPONENT_PATH
    if state.rel_path:
        component_path = f"{state.rel_path}/{component_path}"
    rel_path = component_rel_path(component, path).replace(os.path.sep, '/')
    return f'{component_path}{component.__module__}/{component.__name__}/{attr}/{rel_path}'

def loading_css():
    from ..config import config
    with open(ASSETS_DIR / f'{config.loading_spinner}_spinner.svg', encoding='utf-8') as f:
        svg = f.read().replace('\n', '').format(color=config.loading_color)
    b64 = b64encode(svg.encode('utf-8')).decode('utf-8')
    return f"""
    .bk.pn-loading.{config.loading_spinner}:before {{
      background-image: url("data:image/svg+xml;base64,{b64}");
      background-size: auto calc(min(50%, {config.loading_max_height}px));
    }}
    """

def bundled_files(model, file_type='javascript'):
    bdir = os.path.join(PANEL_DIR, 'dist', 'bundled', model.__name__.lower())
    name = model.__name__.lower()

    files = []
    for url in getattr(model, f"__{file_type}_raw__", []):
        filepath = url_path(url)
        test_filepath = filepath.split('?')[0]
        if RESOURCE_MODE == 'server' and os.path.isfile(os.path.join(bdir, test_filepath)):
            files.append(f'static/extensions/panel/bundled/{name}/{filepath}')
        else:
            files.append(url)
    return files

def bundle_resources(roots, resources):
    from ..config import panel_extension as ext
    global RESOURCE_MODE
    js_resources = css_resources = resources
    RESOURCE_MODE = mode = js_resources.mode if resources is not None else "inline"

    js_files = []
    js_raw = []
    css_files = []
    css_raw = []

    use_mathjax = (_use_mathjax(roots) or 'mathjax' in ext._loaded_extensions) if roots else True

    if js_resources:
        js_resources = copy.deepcopy(js_resources)
        if not use_mathjax and "bokeh-mathjax" in js_resources.js_components:
            js_resources.js_components.remove("bokeh-mathjax")

        js_files.extend(js_resources.js_files)
        js_raw.extend(js_resources.js_raw)

    css_files.extend(css_resources.css_files)
    css_raw.extend(css_resources.css_raw)

    extensions = _bundle_extensions(None, js_resources)
    if mode == "inline":
        js_raw.extend([ Resources._inline(bundle.artifact_path) for bundle in extensions ])
    elif mode == "server":
        js_files.extend([ bundle.server_url for bundle in extensions ])
    elif mode == "cdn":
        for bundle in extensions:
            if bundle.cdn_url is not None:
                js_files.append(bundle.cdn_url)
            else:
                js_raw.append(Resources._inline(bundle.artifact_path))
    else:
        js_files.extend([ bundle.artifact_path for bundle in extensions ])

    ext = bundle_models(None)
    if ext is not None:
        js_raw.append(ext)

    hashes = js_resources.hashes if js_resources else {}

    return Bundle(
        js_files=js_files, js_raw=js_raw, css_files=css_files,
        css_raw=css_raw, hashes=hashes
    )


class Resources(BkResources):

    def __init__(self, *args, absolute=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.absolute = absolute

    @classmethod
    def from_bokeh(cls, bkr, absolute=False):
        kwargs = {}
        if bkr.mode.startswith("server"):
            kwargs['root_url'] = bkr.root_url
        return cls(
            mode=bkr.mode, version=bkr.version, minified=bkr.minified,
            legacy=bkr.legacy, log_level=bkr.log_level,
            path_versioner=bkr.path_versioner,
            components=bkr._components, base_dir=bkr.base_dir,
            root_dir=bkr.root_dir, absolute=absolute, **kwargs
        )

    def extra_resources(self, resources, resource_type):
        """
        Adds resources for ReactiveHTML components.
        """
        from ..reactive import ReactiveHTML
        for model in param.concrete_descendents(ReactiveHTML).values():
            if not (getattr(model, resource_type, None) and model._loaded()):
                continue
            for resource in getattr(model, resource_type, []):
                if not isurl(resource) and not resource.startswith('static/extensions'):
                    resource = component_resource_path(model, resource_type, resource)
                if resource not in resources:
                    resources.append(resource)

    def adjust_paths(self, resources):
        """
        Computes relative and absolute paths for resources.
        """
        new_resources = []
        for resource in resources:
            if (resource.startswith(state.base_url) or resource.startswith('static/')):
                if resource.startswith(state.base_url):
                    resource = resource[len(state.base_url):]
                if state.rel_path:
                    resource = f'{state.rel_path}/{resource}'
                elif self.absolute and self.mode == 'server':
                    resource = f'{self.root_url}{resource}'
            new_resources.append(resource)
        return new_resources

    @property
    def dist_dir(self):
        if self.mode == 'server':
            if state.rel_path:
                dist_dir = f'{state.rel_path}/{LOCAL_DIST}'
            else:
                dist_dir = LOCAL_DIST
            if self.absolute:
                dist_dir = f'{self.root_url}{dist_dir}'
        else:
            dist_dir = CDN_DIST
        return dist_dir

    @property
    def css_raw(self):
        from ..config import config
        raw = super(Resources, self).css_raw
        for cssf in config.css_files:
            if not os.path.isfile(cssf):
                continue
            with open(cssf, encoding='utf-8') as f:
                css_txt = f.read()
                if css_txt not in raw:
                    raw.append(css_txt)
        for cssf in glob.glob(str(DIST_DIR / 'css' / '*.css')):
            if self.mode != 'inline':
                break
            with open(cssf, encoding='utf-8') as f:
                css_txt = f.read()
            if css_txt not in raw:
                raw.append(css_txt)

        if config.loading_spinner:
            raw.append(loading_css())
        return raw + config.raw_css

    @property
    def js_files(self):
        from ..config import config

        files = super(Resources, self).js_files
        self.extra_resources(files, '__javascript__')

        js_files = self.adjust_paths(files)
        js_files += list(config.js_files.values())

        # Load requirejs last to avoid interfering with other libraries
        dist_dir = self.dist_dir
        require_index = [i for i, jsf in enumerate(js_files) if 'require' in jsf]
        if require_index:
            requirejs = js_files.pop(require_index[0])
            if any('ace' in jsf for jsf in js_files):
                js_files.append(dist_dir + 'pre_require.js')
            js_files.append(requirejs)
            if any('ace' in jsf for jsf in js_files):
                js_files.append(dist_dir + 'post_require.js')

        return js_files

    @property
    def js_modules(self):
        from ..config import config
        modules = list(config.js_modules.values())
        self.extra_resources(modules, '__javascript_modules__')


        return modules

    @property
    def css_files(self):
        from ..config import config

        files = super(Resources, self).css_files
        self.extra_resources(files, '__css__')
        css_files = self.adjust_paths(files)

        for cssf in config.css_files:
            if os.path.isfile(cssf) or cssf in files:
                continue
            css_files.append(cssf)

        dist_dir = self.dist_dir
        for cssf in glob.glob(str(DIST_DIR / 'css' / '*.css')):
            if self.mode == 'inline':
                break
            css_files.append(dist_dir + f'css/{os.path.basename(cssf)}')

        return css_files

    @property
    def render_js(self):
        return JS_RESOURCES.render(
            js_raw=self.js_raw, js_files=self.js_files,
            js_modules=self.js_modules, hashes=self.hashes
        )


class Bundle(BkBundle):

    def __init__(self, **kwargs):
        from ..config import config
        from ..reactive import ReactiveHTML
        js_modules = list(config.js_modules.values())
        for model in param.concrete_descendents(ReactiveHTML).values():
            if getattr(model, '__javascript_modules__', None) and model._loaded():
                for js_module in model.__javascript_modules__:
                    if js_module not in js_modules:
                        js_modules.append(js_module)
        self.js_modules = kwargs.pop("js_modules", js_modules)
        super().__init__(**kwargs)

    @classmethod
    def from_bokeh(cls, bk_bundle):
        return cls(
            js_files=bk_bundle.js_files,
            js_raw=bk_bundle.js_raw,
            css_files=bk_bundle.css_files,
            css_raw=bk_bundle.css_raw,
            hashes=bk_bundle.hashes,
        )

    def _render_js(self):
        return JS_RESOURCES.render(
            js_raw=self.js_raw, js_files=self.js_files,
            js_modules=self.js_modules, hashes=self.hashes
        )
