import pytest, shutil, os

from jupyterlab_server import LabServerApp, LabConfig

from traitlets import Unicode

pytest_plugins = "pytest_jupyter_server"

from jupyterlab_server.tests.utils import here
from jupyterlab_server.app import LabServerApp

def mkdir(tmp_path, *parts):
    path = tmp_path.joinpath(*parts)
    if not path.exists():
        path.mkdir(parents=True)
    return path

settings_dir = pytest.fixture(lambda tmp_path: mkdir(tmp_path, "settings"))
schemas_dir = pytest.fixture(lambda tmp_path: mkdir(tmp_path, "schemas"))

@pytest.fixture
def make_lab_extension_app(root_dir, template_dir, settings_dir, schemas_dir):
    def _make_lab_extension_app(**kwargs):
        class TestLabServerApp(LabServerApp):
            base_url = '/lab'
            default_url = Unicode('/',
                                help='The default URL to redirect to from `/`')
            lab_config = LabConfig(
                app_name = 'JupyterLab Test App',
                static_dir = str(root_dir),
                templates_dir = str(template_dir),
                app_url = '/lab',
                app_settings_dir = str(settings_dir),
                schemas_dir = str(schemas_dir),
            )
        app = TestLabServerApp()
        return app

    # Create the index files.
    index = template_dir.joinpath("index.html")
    index.write_text("""
<!DOCTYPE html>
<html>
<head>
  <title>{{page_config['appName'] | e}}</title>
</head>
<body>
    {# Copy so we do not modify the page_config with updates. #}
    {% set page_config_full = page_config.copy() %}
    
    {# Set a dummy variable - we just want the side effect of the update. #}
    {% set _ = page_config_full.update(baseUrl=base_url, wsUrl=ws_url) %}
    
      <script id="jupyter-config-data" type="application/json">
        {{ page_config_full | tojson }}
      </script>
  <script src="{{page_config['fullStaticUrl'] | e}}/bundle.js" main="index"></script>

  <script type="text/javascript">
    /* Remove token from URL. */
    (function () {
      var parsedUrl = new URL(window.location.href);
      if (parsedUrl.searchParams.get('token')) {
        parsedUrl.searchParams.delete('token');
        window.history.replaceState({ }, '', parsedUrl.href);
      }
    })();
  </script>
</body>
</html>
""")

    # Copy the schema files.
    src = os.path.join(
        os.path.abspath(os.path.dirname(__file__)),
        'jupyterlab_server',
        'tests',
        'schemas',
        '@jupyterlab')
    dst = os.path.join(schemas_dir, '@jupyterlab')
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)

    # Copy the overrides file.
    src = os.path.join(
        os.path.abspath(os.path.dirname(__file__)),
        'jupyterlab_server',
        'tests',
        'app-settings',
        'overrides.json')
    dst = os.path.join(settings_dir, 'overrides.json')
    if os.path.exists(dst):
        os.remove(dst)
    shutil.copyfile(src, dst)

    return _make_lab_extension_app


@pytest.fixture
def labserverapp(serverapp, make_lab_extension_app):
    app = make_lab_extension_app()
    app.initialize(serverapp)
    return app
