from binascii import hexlify
import errno
import os
import sys
from os.path import join as pjoin
from tempfile import TemporaryDirectory
from threading import Thread, Event
from unittest.mock import patch
from contextlib import contextmanager

from jupyterlab_server import LabServerApp, LabConfig

from .utilsbase import ServerTestBase
from ..server import url_path_join

import jupyter_core
from traitlets.config import Config
import tornado
from tornado.ioloop import IOLoop


here = os.path.dirname(__file__)


def expected_http_error(error, expected_code, expected_message=None):
    """Check that the error matches the expected output error."""
    e = error.value
    if isinstance(e, tornado.web.HTTPError):
        if expected_code != e.status_code:
            return False
        if expected_message is not None and expected_message != str(e):
            return False
        return True
    elif any([
        isinstance(e, tornado.httpclient.HTTPClientError),
        isinstance(e, tornado.httpclient.HTTPError)
    ]):
        if expected_code != e.code:
            return False
        if expected_message:
            message = json.loads(e.response.body.decode())['message']
            if expected_message != message:
                return False
        return True

@contextmanager
def assert_http_error(status, msg=None):
    try:
        yield
    except requests.HTTPError as e:
        real_status = e.response.status_code
        assert real_status == status, \
                    "Expected status %d, got %d" % (status, real_status)
        if msg:
            assert msg in str(e), e
    else:
        assert False, "Expected HTTP error status"

class LabTestBase(ServerTestBase):
    Application = LabServerApp
    """The application being tested. Sub-classes should change this."""

    @classmethod
    def setup_class(cls):
        cls.tmp_dir = TemporaryDirectory()

        def tmp(*parts):
            path = os.path.join(cls.tmp_dir.name, *parts)
            try:
                os.makedirs(path)
            except OSError as e:
                if e.errno != errno.EEXIST:
                    raise
            return path

        cls.home_dir = tmp('home')
        cls.data_dir = tmp('data')
        cls.config_dir = tmp('config')
        cls.runtime_dir = tmp('runtime')
        cls.lab_dir = tmp('lab')
        cls.app_settings_dir = tmp('appsettings')
        cls.lab_schemas = tmp('labschemas')
        cls.lab_settings = tmp('labsettings')
        cls.lab_workspaces = tmp('labworkspaces')
        cls.env_patch = patch.dict('os.environ', {
            'HOME': cls.home_dir,
            'PYTHONPATH': os.pathsep.join(sys.path),
            'IPYTHONDIR': pjoin(cls.home_dir, '.ipython'),
            'JUPYTER_NO_CONFIG': '1',  # needed in the future
            'JUPYTER_CONFIG_DIR': cls.config_dir,
            'JUPYTER_DATA_DIR': cls.data_dir,
            'JUPYTER_RUNTIME_DIR': cls.runtime_dir,
            'JUPYTERLAB_DIR': cls.lab_dir,
            'JUPYTERLAB_SETTINGS_DIR': cls.lab_settings
        })
        cls.env_patch.start()
        cls.lab_config = LabConfig(
            app_settings_dir=cls.app_settings_dir,
            schemas_dir=cls.lab_schemas,
            user_settings_dir=cls.lab_settings,
            workspaces_dir=cls.lab_workspaces)
        cls.notebook_dir = tmp('notebooks')
        cls.path_patch = patch.multiple(
            jupyter_core.paths,
            SYSTEM_JUPYTER_PATH=[tmp('share', 'jupyter')],
            ENV_JUPYTER_PATH=[tmp('env', 'share', 'jupyter')],
            SYSTEM_CONFIG_PATH=[tmp('etc', 'jupyter')],
            ENV_CONFIG_PATH=[tmp('env', 'etc', 'jupyter')],
        )
        cls.path_patch.start()

        cls.config = cls.config or Config()
        cls.config.NotebookNotary.db_file = ':memory:'

        cls.token = hexlify(os.urandom(4)).decode('ascii')

        started = Event()

        def start_thread():
            if 'asyncio' in sys.modules:
                import asyncio
                asyncio.set_event_loop(asyncio.new_event_loop())
            app = cls.notebook = cls.Application(
                app_dir=cls.lab_dir,
                port=cls.port,
                port_retries=0,
                open_browser=False,
                config_dir=cls.config_dir,
                data_dir=cls.data_dir,
                runtime_dir=cls.runtime_dir,
                notebook_dir=cls.notebook_dir,
                base_url=cls.url_prefix,
                config=cls.config,
                allow_root=True,
                token=cls.token,
                lab_config=cls.lab_config
            )
            # don't register signal handler during tests
            app.init_signal = lambda: None
            # clear log handlers and propagate to root for nose to capture it
            # needs to be redone after initialize, which reconfigures logging
            app.log.propagate = True
            app.log.handlers = []
            app.initialize(argv=[])
            app.log.propagate = True
            app.log.handlers = []
            loop = IOLoop.current()
            loop.add_callback(started.set)
            try:
                app.start()
            finally:
                # set the event, so failure to start doesn't cause a hang
                started.set()
                app.session_manager.close()
        cls.notebook_thread = Thread(target=start_thread)
        cls.notebook_thread.daemon = True
        cls.notebook_thread.start()
        started.wait()
        cls.wait_until_alive()


class APITester(object):
    """Wrapper for REST API requests"""
    url = '/'

    def __init__(self, request):
        self.request = request

    def _req(self, verb, path, body=None):
        response = self.request(verb,
                                url_path_join(self.url, path), data=body)

        if 400 <= response.status_code < 600:
            try:
                response.reason = response.json()['message']
            except Exception:
                pass
        response.raise_for_status()

        return response
