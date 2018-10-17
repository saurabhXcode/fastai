# this test checks that the core fastai library doesn't depend on 'extras_require'
# package requirements from setup.py, which won't be installed by default

import os, sys, re
from pathlib import Path

# this is a simplified version of _load_setup_py_data.py from
# https://github.com/conda/conda-build that gives us access to
# `setup.py` data. It returns the data dict as it was parsed by
# `setup()` in `setup.py`. It incorporates data from `setup.cfg` too.
def load_setup_py_data_basic(setup_file, work_dir=None):
    _setuptools_data = {}

    import setuptools

    cd_to_work = False
    path_backup = sys.path

    def _change_cwd(target_dir):
        cd_to_work = True
        try:
            cwd = os.getcwd()
        except OSError:
            cwd = recipe_dir or work_dir
        os.chdir(target_dir)
        # this is very important - or else if versioneer or otherwise is in the start folder,
        # things will pick up the wrong versioneer/whatever!
        sys.path.insert(0, target_dir)
        return cd_to_work, cwd

    setup_cfg_data = {}
    try:
        from setuptools.config import read_configuration
    except ImportError:
        pass  # setuptools <30.3.0 cannot read metadata / options from 'setup.cfg'
    else:
        setup_cfg = os.path.join(os.path.dirname(setup_file), 'setup.cfg')
        if os.path.isfile(setup_cfg):
            # read_configuration returns a dict of dicts. Each dict (keys: 'metadata',
            # 'options'), if present, provides keyword arguments for the setup function.
            for kwargs in read_configuration(setup_cfg).values():
                # explicit arguments to setup.cfg take priority over values in setup.py
                setup_cfg_data.update(kwargs)

    def setup(**kw):
        _setuptools_data.update(kw)
        # values in setup.cfg take priority over explicit arguments to setup.py
        _setuptools_data.update(setup_cfg_data)

    # Patch setuptools, distutils
    setuptools_setup = setuptools.setup

    setuptools.setup = setup
    ns = {
        '__name__': '__main__',
        '__doc__': None,
        '__file__': setup_file,
    }
    if os.path.isfile(setup_file):
        with open(setup_file) as f:
            code = compile(f.read(), setup_file, 'exec', dont_inherit=1)
            exec(code, ns, ns)

    setuptools.setup = setuptools_setup

    if cd_to_work: os.chdir(cwd)
    # remove our workdir from sys.path
    sys.path = path_backup
    return _setuptools_data


# setup.py dir
work_dir = Path(__file__).parent.parent
print(f"setup.py is at '{work_dir}'")

# we get back a dict of the setup data
data = load_setup_py_data_basic("setup.py", work_dir)

# just test first that the parsing worked
def test_setup_parser():
    assert data['name'] == 'fastai'

    # print(data['extras_require'])
    assert 'dev' in data['extras_require']

# fastai must not depend on 'extras_require' package requirements from setup.py,
# which won't be installed by default
unwanted_deps = [(re.split(r'[>=<]+',x))[0] for x in data['extras_require']['dev']]
#print(unwanted_deps)

class CheckDependencyImporter(object):

    def find_spec(self, fullname, path, target=None):
        #print("spec: ", fullname, path, target)
        # catch if import of any unwanted dependencies gets triggered
        assert fullname not in unwanted_deps, f"detected unwanted dependency on '{fullname}'"
        return None

def test_unwanted_mod_dependencies():
    # save the original state
    mod_saved = sys.modules['fastai'] if 'fastai' in sys.modules else None
    meta_path_saved = sys.meta_path.copy

    # unload any candidates we want to test, including fastai, so we can test their import
    for mod in unwanted_deps + ['fastai']:
        if mod in sys.modules: del sys.modules[mod]

    # test
    try:
        sys.meta_path.insert(0, CheckDependencyImporter())
        import fastai
    finally:
        # restore the original state
        del sys.meta_path[0]
        if mod_saved is not None: sys.modules['fastai'] = mod_saved
